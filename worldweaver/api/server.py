"""FastAPI 웹 서버 — WorldWeaver System API."""

import logging
import os
import shutil
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from worldweaver.api.session_manager import SessionManager
from worldweaver.prompt_loader import get_game_config, list_themes, load_theme

# ── 데모 모드 설정 ──
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

app = FastAPI(title="WorldWeaver API", version="0.5.0")

# ── CORS: 환경변수로 허용 오리진 설정 ──
_allowed_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = SessionManager()

# ── 접속 로그 설정 ──
_log_dir = Path("logs")
_log_dir.mkdir(exist_ok=True)
_access_logger = logging.getLogger("worldweaver.access")
_access_logger.setLevel(logging.INFO)
_file_handler = logging.FileHandler(_log_dir / "access.log", encoding="utf-8")
_file_handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s"))
_access_logger.addHandler(_file_handler)

# ── Rate Limiting (IP당) ──
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60        # 윈도우 (초)
RATE_LIMIT_MAX_REQUESTS = 30  # 윈도우당 최대 요청 수

# ── LLM 호출 횟수 제한 (전체 일일) ──
_daily_llm_calls = 0
_daily_llm_reset_date = ""
DAILY_LLM_LIMIT = int(os.getenv("DAILY_LLM_LIMIT", "500"))


def _check_rate_limit(client_ip: str) -> bool:
    """IP당 rate limit 체크. True면 허용, False면 거부."""
    now = time.time()
    timestamps = _rate_limit_store[client_ip]
    # 윈도우 밖의 오래된 기록 제거
    _rate_limit_store[client_ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return False
    _rate_limit_store[client_ip].append(now)
    return True


def _check_daily_llm_limit() -> bool:
    """일일 LLM 호출 한도 체크."""
    global _daily_llm_calls, _daily_llm_reset_date
    today = time.strftime("%Y-%m-%d")
    if today != _daily_llm_reset_date:
        _daily_llm_calls = 0
        _daily_llm_reset_date = today
    return _daily_llm_calls < DAILY_LLM_LIMIT


def _increment_llm_calls():
    """LLM 호출 카운트 증가."""
    global _daily_llm_calls
    _daily_llm_calls += 1


def _get_client_ip(request: Request) -> str:
    """클라이언트 IP 추출 (프록시 지원)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── 미들웨어: Rate Limiting + 접속 로그 + 에러 필터링 ──

@app.middleware("http")
async def rate_limit_and_logging_middleware(request: Request, call_next):
    client_ip = _get_client_ip(request)
    path = request.url.path

    # 헬스체크 및 정적 리소스는 rate limit 제외
    if path in ("/health", "/api/health", "/docs", "/openapi.json"):
        return await call_next(request)

    # Rate limit 체크
    if not _check_rate_limit(client_ip):
        _access_logger.warning(f"RATE_LIMITED | {client_ip} | {request.method} {path}")
        return JSONResponse(
            status_code=429,
            content={"detail": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."},
        )

    # 접속 로그
    start = time.time()
    try:
        response = await call_next(request)
    except Exception:
        _access_logger.error(f"ERROR | {client_ip} | {request.method} {path}")
        return JSONResponse(
            status_code=500,
            content={"detail": "서버 내부 오류가 발생했습니다."},
        )
    elapsed = round((time.time() - start) * 1000)
    _access_logger.info(f"{response.status_code} | {client_ip} | {request.method} {path} | {elapsed}ms")

    # 보안 헤더
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ── 전역 에러 핸들러 (내부 정보 노출 방지) ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    _access_logger.error(f"UNHANDLED | {_get_client_ip(request)} | {request.method} {request.url.path} | {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "서버 내부 오류가 발생했습니다."},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # HTTPException은 의도된 에러이므로 detail을 그대로 반환하되, 500은 필터링
    if exc.status_code >= 500:
        _access_logger.error(f"HTTP_{exc.status_code} | {_get_client_ip(request)} | {request.method} {request.url.path} | {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": "서버 내부 오류가 발생했습니다."},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# ── 헬스체크 ──

@app.get("/health")
@app.get("/api/health")
def health_check():
    """서버 상태 확인."""
    return {
        "status": "ok",
        "active_sessions": manager.active_count(),
        "max_sessions": SessionManager.MAX_SESSIONS,
        "daily_llm_calls": _daily_llm_calls,
        "daily_llm_limit": DAILY_LLM_LIMIT,
        "demo_mode": DEMO_MODE,
    }


# ── 요청/응답 모델 ──

class StartGameRequest(BaseModel):
    theme: str = "mythology"
    language: str = "ko"

class ChoiceRequest(BaseModel):
    session_id: str
    choice_index: int

class DialogueRequest(BaseModel):
    session_id: str
    npc_name: str
    message: str

class CombatActionRequest(BaseModel):
    session_id: str
    action: str  # attack, defend, skill, item, flee
    item_name: str = ""


# ── 테마 API ──

@app.get("/api/languages")
def get_languages():
    """지원 언어 목록."""
    cfg = get_game_config()
    supported = cfg.get("supported_languages", {})
    labels = {"ko": "한국어", "en": "English", "ja": "日本語"}
    return {
        "languages": [
            {"code": code, "label": labels.get(code, code)}
            for code in supported
        ],
        "default": cfg.get("default_language", "ko"),
    }


@app.get("/api/themes")
def get_themes():
    """사용 가능한 테마 목록."""
    themes = []
    for name in list_themes():
        theme = load_theme(name)
        enemies = theme.get("enemies", [])
        themes.append({
            "name": name,
            "display_name": theme.get("display_name", name),
            "description": theme.get("description", ""),
            "npc_count": len(theme.get("npc_profiles", [])),
            "enemy_count": len(enemies),
        })
    return {"themes": themes}


@app.get("/api/themes/{theme_name}")
def get_theme_detail(theme_name: str):
    """테마 상세 정보."""
    try:
        theme = load_theme(theme_name)
    except Exception:
        raise HTTPException(404, f"테마 '{theme_name}' 없음")

    return {
        "name": theme["name"],
        "display_name": theme.get("display_name", ""),
        "description": theme.get("description", ""),
        "initial_prompt": theme.get("initial_prompt", ""),
        "npcs": [
            {"name": n["name"], "role": n.get("role", ""), "stage": n.get("stage", "")}
            for n in theme.get("npc_profiles", [])
        ],
        "enemies": [
            {"name": e["name"], "hp": e.get("hp", 0), "description": e.get("description", "")}
            for e in theme.get("enemies", [])
        ],
        "gauges": list(theme.get("world_state_schema", {}).get("gauges", {}).keys()),
    }


# ── 세션 조회 헬퍼 (IP 바인딩 검증 포함) ──

def _resolve_session(session_id: str, request: Request) -> "WebGameSession":
    """세션 조회 + IP 소유권 검증. 실패 시 HTTPException 발생."""
    client_ip = _get_client_ip(request)
    session = manager.get_session(session_id, client_ip=client_ip)
    if not session:
        raise HTTPException(404, "세션 없음")
    return session


# ── 게임 세션 API ──

@app.post("/api/game/start")
def start_game(req: StartGameRequest, request: Request):
    """새 게임 세션 시작."""
    client_ip = _get_client_ip(request)
    try:
        session = manager.create_session(req.theme, req.language, client_ip=client_ip)
    except RuntimeError as e:
        # 세션 풀 초과
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"세션 생성 실패: {e}")

    t = session.translator
    return {
        "session_id": session.session_id,
        "theme": t.tr(session.theme.get("display_name", ""), "display_name"),
        "description": t.tr(session.theme.get("description", ""), "description"),
        "initial_prompt": t.tr(session.theme.get("initial_prompt", ""), "initial_prompt"),
        "world_state": session._get_state_snapshot(),
        "enemies": [
            t.tr(name, f"enemies.{name}.name")
            for name in session.enemy_registry.get_all_enemy_names()
        ],
    }


@app.post("/api/game/scene")
def generate_scene(req: ChoiceRequest, request: Request):
    """선택지를 선택하여 다음 씬 생성."""
    if not _check_daily_llm_limit():
        raise HTTPException(429, "오늘의 AI 사용량을 초과했습니다. 내일 다시 시도해주세요.")

    session = _resolve_session(req.session_id, request)

    # 첫 씬 또는 선택 처리
    if not session.last_choices:
        prompt = session.theme.get("initial_prompt", "")
    else:
        try:
            selected = session.last_choices[req.choice_index]
        except IndexError:
            raise HTTPException(400, "잘못된 선택지 인덱스")

        # 대화/전투 선택지 체크
        if selected.get("choice_type") == "dialogue":
            npc_name = selected.get("npc_name")
            directive = selected.get("next_node_prompt", "")
            greeting = session.start_dialogue(npc_name, directive)
            if "error" in greeting:
                raise HTTPException(500, greeting["error"])
            return {"redirect": "dialogue", "npc_name": npc_name, "greeting": greeting}
        if selected.get("choice_type") == "combat":
            return {"redirect": "combat", "enemy_name": selected.get("enemy_name")}

        prompt = selected["next_node_prompt"]

    # risky 선택지 판정
    risky_choice = None
    if session.last_choices and 0 <= req.choice_index < len(session.last_choices):
        sel = session.last_choices[req.choice_index]
        if sel.get("risky", False):
            risky_choice = sel

    result = session.generate_scene(prompt, risky_choice=risky_choice)
    if "error" in result:
        raise HTTPException(500, result["error"])

    _increment_llm_calls()
    return result


@app.get("/api/game/{session_id}/state")
def get_game_state(session_id: str, request: Request):
    """현재 게임 상태 조회."""
    session = _resolve_session(session_id, request)

    return {
        "session_id": session_id,
        "scene_count": session.scene_count,
        "world_state": session._get_state_snapshot(),
        "last_choices": session.last_choices,
        "current_stage": session.current_stage,
    }


@app.delete("/api/game/{session_id}")
def end_game(session_id: str):
    """게임 세션 종료."""
    manager.delete_session(session_id)
    return {"status": "ended"}


# ── NPC 대화 API ──

@app.post("/api/dialogue/start")
def start_dialogue(req: DialogueRequest, request: Request):
    """NPC 대화 시작 — NPC가 먼저 인사."""
    if not _check_daily_llm_limit():
        raise HTTPException(429, "오늘의 AI 사용량을 초과했습니다. 내일 다시 시도해주세요.")

    session = _resolve_session(req.session_id, request)

    result = session.start_dialogue(req.npc_name, req.message or "")
    if "error" in result:
        raise HTTPException(500, result["error"])

    _increment_llm_calls()
    return result


@app.post("/api/dialogue")
def dialogue(req: DialogueRequest, request: Request):
    """NPC 대화 (플레이어 메시지에 대한 NPC 응답)."""
    if not _check_daily_llm_limit():
        raise HTTPException(429, "오늘의 AI 사용량을 초과했습니다. 내일 다시 시도해주세요.")

    session = _resolve_session(req.session_id, request)

    result = session.process_dialogue(req.npc_name, req.message)
    if "error" in result:
        raise HTTPException(500, result["error"])

    _increment_llm_calls()
    return result


@app.get("/api/dialogue/{session_id}/{npc_name}/info")
def get_npc_info(session_id: str, npc_name: str, request: Request):
    """NPC 정보 조회."""
    session = _resolve_session(session_id, request)

    npc = session.npc_manager.get_npc(npc_name)
    if not npc:
        raise HTTPException(404, f"NPC '{npc_name}' 없음")

    return {
        "name": npc.profile.name,
        "role": npc.profile.role,
        "personality": npc.profile.personality,
        "disposition": npc.disposition,
        "disposition_label": npc.disposition_label,
        "stage": npc.profile.stage,
    }


# ── 게임오버 API ──

@app.get("/api/game/{session_id}/gameover/check")
def check_game_over(session_id: str, request: Request):
    """게임오버 조건 체크."""
    session = _resolve_session(session_id, request)

    result = session.check_game_over()
    return {"game_over": result is not None, "info": result}


@app.post("/api/game/{session_id}/gameover")
def generate_game_over(session_id: str, request: Request):
    """게임오버 씬 생성. 그래프 상태를 반영한 LLM 사망/실패 씬."""
    if not _check_daily_llm_limit():
        raise HTTPException(429, "오늘의 AI 사용량을 초과했습니다. 내일 다시 시도해주세요.")

    session = _resolve_session(session_id, request)

    result = session.generate_game_over()
    if "error" in result:
        raise HTTPException(400, result["error"])

    _increment_llm_calls()
    return result


# ── 세이브/로드 API ──

@app.get("/api/game/{session_id}/save")
def save_game(session_id: str, request: Request):
    """현재 게임 상태를 JSON으로 반환 (다운로드용)."""
    session = _resolve_session(session_id, request)

    # 자동저장 데이터가 있으면 사용, 없으면 새로 생성
    if session._last_auto_save:
        return session._last_auto_save
    else:
        import json
        return json.loads(session.save_game())


class LoadGameRequest(BaseModel):
    save_data: dict


@app.post("/api/game/load")
def load_game(req: LoadGameRequest):
    """세이브 데이터에서 게임을 복원. 새 세션을 생성하고 상태를 복원."""
    save_data = req.save_data
    meta = save_data.get("meta", {})
    theme_name = meta.get("theme_name", "mythology")
    language = meta.get("language", "ko")

    try:
        session = manager.create_session(theme_name, language)
    except Exception as e:
        raise HTTPException(500, f"세션 생성 실패: {e}")

    try:
        session.load_game(save_data)
    except Exception as e:
        raise HTTPException(500, f"로드 실패: {e}")

    # 로드 후 현재 상태 반환
    npcs_here = session.npc_manager.get_npcs_at_stage(session.current_stage)
    t = session.translator

    return {
        "session_id": session.session_id,
        "meta": meta,
        "scene_count": session.scene_count,
        "world_state": session._get_state_snapshot(),
        "choices": session.last_choices,
        "npcs": [
            {
                "name": t.tr(n.profile.name, f"npc.{n.profile.name}.name"),
                "role": t.tr(n.profile.role, f"npc.{n.profile.name}.role"),
                "disposition": n.disposition_label,
            }
            for n in npcs_here
        ],
        "quests": session._get_quests_snapshot(),
        "titles": session.get_titles_snapshot(),
        "map": session.get_map_data(),
        "ending_available": session.check_ending_available(),
        "last_scene": session._last_scene,
    }


# ── 월드맵 API ──

@app.get("/api/game/{session_id}/map")
def get_map(session_id: str, request: Request):
    """월드맵 데이터 조회."""
    session = _resolve_session(session_id, request)
    return session.get_map_data()


class TravelRequest(BaseModel):
    session_id: str
    stage_name: str


@app.post("/api/game/travel")
def travel(req: TravelRequest, request: Request):
    """스테이지 이동. 해금 조건 확인 후 이동 씬 생성."""
    if not _check_daily_llm_limit():
        raise HTTPException(429, "오늘의 AI 사용량을 초과했습니다. 내일 다시 시도해주세요.")

    session = _resolve_session(req.session_id, request)

    result = session.travel_to_stage(req.stage_name)
    if "error" in result:
        raise HTTPException(400, result["error"])
    _increment_llm_calls()
    return result


# ── 엔딩 API ──

@app.get("/api/game/{session_id}/ending/check")
def check_ending(session_id: str, request: Request):
    """엔딩 조건 충족 여부 확인."""
    session = _resolve_session(session_id, request)

    ending_info = session.check_ending()
    return {
        "available": ending_info is not None,
        "ending": ending_info,
    }


@app.post("/api/game/{session_id}/ending")
def generate_ending(session_id: str, request: Request):
    """엔딩 에필로그 생성. 스토리 그래프 + 월드 스테이트 + NPC 관계를 종합하여 LLM이 에필로그를 작성."""
    if not _check_daily_llm_limit():
        raise HTTPException(429, "오늘의 AI 사용량을 초과했습니다. 내일 다시 시도해주세요.")

    session = _resolve_session(session_id, request)

    result = session.generate_ending()
    if "error" in result:
        raise HTTPException(400, result["error"])

    _increment_llm_calls()
    return result


# ── 아이템/칭호 API ──

class InvestigateItemRequest(BaseModel):
    session_id: str
    item_name: str


@app.post("/api/game/item/investigate")
def investigate_item(req: InvestigateItemRequest, request: Request):
    """아이템을 조사하여 히든 효과를 발견."""
    session = _resolve_session(req.session_id, request)

    result = session.investigate_item(req.item_name)
    if not result:
        return {"discovered": False, "message": "발견할 히든 효과가 없습니다"}

    return {"discovered": True, **result}


@app.get("/api/game/{session_id}/item/{item_name}")
def get_item_info(session_id: str, item_name: str, request: Request):
    """아이템 상세 정보 조회."""
    session = _resolve_session(session_id, request)

    info = session.get_item_info(item_name)
    if not info:
        return {"name": item_name, "description": "", "base_effect": {}, "total_effect": {}}

    return info


@app.get("/api/game/{session_id}/titles")
def get_titles(session_id: str, request: Request):
    """현재 활성 칭호 목록."""
    session = _resolve_session(session_id, request)

    return {"titles": session.get_titles_snapshot()}


# ── 퀘스트 API ──

@app.get("/api/game/{session_id}/quests")
def get_quests(session_id: str, request: Request):
    """현재 세션의 모든 퀘스트 상태 조회.

    퀘스트 상태는 NPC 메모리 그래프의 엣지 연결 상태로 결정:
      - active: NPC가 퀘스트 맥락을 온전히 기억
      - fading: NPC가 점차 잊어가는 중 (엣지 마모)
      - lost: NPC가 맥락을 완전히 잃음 (엣지 끊어짐)
      - completed: 퀘스트 완료
    """
    session = _resolve_session(session_id, request)

    return {"quests": session._get_quests_snapshot()}


class QuestCompleteRequest(BaseModel):
    session_id: str
    npc_name: str
    quest_id: str


@app.post("/api/game/quest/complete")
def complete_quest(req: QuestCompleteRequest, request: Request):
    """퀘스트 완료 처리."""
    session = _resolve_session(req.session_id, request)

    success = session.npc_manager.complete_quest(req.npc_name, req.quest_id)
    if not success:
        raise HTTPException(400, "퀘스트 완료 실패")

    return {"status": "completed", "quests": session._get_quests_snapshot()}


# ── 전투 API ──

@app.post("/api/combat/start")
def start_combat(req: CombatActionRequest, request: Request):
    """전투 시작."""
    session = _resolve_session(req.session_id, request)

    # item_name 필드를 enemy_name으로 재활용 (StartCombatRequest 별도 정의 대신)
    enemy_name = req.item_name or req.action
    result = session.start_combat(enemy_name)
    if "error" in result:
        raise HTTPException(400, result["error"])

    return result


class StartCombatRequest(BaseModel):
    session_id: str
    enemy_name: str


@app.post("/api/combat/begin")
def begin_combat(req: StartCombatRequest, request: Request):
    """전투 시작 (명확한 인터페이스)."""
    session = _resolve_session(req.session_id, request)

    result = session.start_combat(req.enemy_name)
    if "error" in result:
        raise HTTPException(400, result["error"])

    return result


@app.post("/api/combat/action")
def combat_action(req: CombatActionRequest, request: Request):
    """전투 행동."""
    session = _resolve_session(req.session_id, request)

    result = session.combat_action(req.action, req.item_name)
    if "error" in result:
        raise HTTPException(400, result["error"])

    return result


# ── WebSocket (실시간 업데이트) ──

@app.websocket("/ws/game/{session_id}")
async def websocket_game(websocket: WebSocket, session_id: str):
    """게임 세션 WebSocket — 실시간 전투/대화. 메시지 rate limit 포함."""
    await websocket.accept()

    # WebSocket에서는 IP 검증 불가 (프록시 환경) → 세션 존재만 확인
    session = manager.get_session(session_id)
    if not session:
        await websocket.send_json({"error": "세션 없음"})
        await websocket.close()
        return

    # WebSocket 메시지 rate limiting (초당 2회, 버스트 5회)
    ws_message_times: list[float] = []
    WS_RATE_WINDOW = 10   # 10초 윈도우
    WS_RATE_MAX = 20      # 윈도우당 최대 메시지 수

    try:
        while True:
            data = await websocket.receive_json()

            # 메시지 rate limit 체크
            now = time.time()
            ws_message_times[:] = [t for t in ws_message_times if now - t < WS_RATE_WINDOW]
            if len(ws_message_times) >= WS_RATE_MAX:
                await websocket.send_json({"error": "요청이 너무 빠릅니다. 잠시 후 다시 시도해주세요."})
                continue
            ws_message_times.append(now)

            # LLM 일일 호출 제한 체크 (scene, dialogue 등 LLM 호출 시)
            msg_type = data.get("type", "")
            llm_types = {"scene", "dialogue", "combat_start"}
            if msg_type in llm_types and not _check_daily_llm_limit():
                await websocket.send_json({"error": "오늘의 AI 사용량을 초과했습니다."})
                continue

            if msg_type == "scene":
                choice_index = data.get("choice_index", 0)
                if not session.last_choices:
                    prompt = session.theme.get("initial_prompt", "")
                else:
                    try:
                        selected = session.last_choices[choice_index]
                    except IndexError:
                        await websocket.send_json({"error": "잘못된 선택지"})
                        continue

                    if selected.get("choice_type") == "dialogue":
                        await websocket.send_json({
                            "type": "redirect_dialogue",
                            "npc_name": selected.get("npc_name"),
                        })
                        continue
                    if selected.get("choice_type") == "combat":
                        await websocket.send_json({
                            "type": "redirect_combat",
                            "enemy_name": selected.get("enemy_name"),
                        })
                        continue

                    prompt = selected["next_node_prompt"]

                result = session.generate_scene(prompt)
                _increment_llm_calls()
                await websocket.send_json({"type": "scene", **result})

            elif msg_type == "dialogue":
                npc_name = data.get("npc_name", "")
                message = data.get("message", "")
                result = session.process_dialogue(npc_name, message)
                _increment_llm_calls()
                await websocket.send_json({"type": "dialogue", **result})

            elif msg_type == "combat_start":
                enemy_name = data.get("enemy_name", "")
                result = session.start_combat(enemy_name)
                await websocket.send_json({"type": "combat_start", **result})

            elif msg_type == "combat_action":
                action = data.get("action", "attack")
                item_name = data.get("item_name", "")
                result = session.combat_action(action, item_name)
                await websocket.send_json({"type": "combat_action", **result})

            elif msg_type == "state":
                await websocket.send_json({
                    "type": "state",
                    "world_state": session._get_state_snapshot(),
                    "scene_count": session.scene_count,
                })

    except WebSocketDisconnect:
        pass


# ── 테마 빌더 API ──

# 빌드 작업 상태 추적
_build_jobs: dict[str, dict] = {}


class ThemeBuildRequest(BaseModel):
    theme_name: str | None = None


# ── 빌더 비밀번호 ──
import os
_BUILDER_PASSWORD = os.getenv("BUILDER_PASSWORD", "worldweaver")


class BuilderAuthRequest(BaseModel):
    password: str


@app.post("/api/builder/auth")
def builder_auth(req: BuilderAuthRequest):
    """빌더 비밀번호 검증."""
    if DEMO_MODE:
        raise HTTPException(403, "데모 모드에서는 테마 빌더를 사용할 수 없습니다.")
    if req.password != _BUILDER_PASSWORD:
        raise HTTPException(403, "비밀번호가 올바르지 않습니다")
    return {"authorized": True}


@app.post("/api/builder/upload")
async def upload_lore_files(files: list[UploadFile]):
    """세계관 문서 파일 업로드. 임시 폴더에 저장하고 build_id를 반환."""
    if DEMO_MODE:
        raise HTTPException(403, "데모 모드에서는 테마 빌더를 사용할 수 없습니다.")
    build_id = uuid.uuid4().hex[:12]
    upload_dir = Path("uploads") / build_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for file in files:
        if not file.filename:
            continue
        # .txt 파일만 허용
        if not file.filename.endswith(".txt"):
            continue
        # Path traversal 방지: 파일명에서 디렉토리 경로 제거
        safe_name = Path(file.filename).name
        if safe_name != file.filename or ".." in safe_name:
            continue
        dest = (upload_dir / safe_name).resolve()
        if not str(dest).startswith(str(upload_dir.resolve())):
            continue  # 경로 탈출 시도 차단
        content = await file.read()
        dest.write_bytes(content)
        saved.append(safe_name)

    if not saved:
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(400, "유효한 .txt 파일이 없습니다")

    _build_jobs[build_id] = {
        "status": "uploaded",
        "progress": 0,
        "message": f"{len(saved)}개 파일 업로드 완료",
        "files": saved,
        "lore_dir": str(upload_dir),
        "theme_name": None,
        "error": None,
    }

    return {"build_id": build_id, "files": saved}


@app.post("/api/builder/start/{build_id}")
def start_build(build_id: str, req: ThemeBuildRequest):
    """업로드된 문서로 테마 빌드 시작 (백그라운드)."""
    if DEMO_MODE:
        raise HTTPException(403, "데모 모드에서는 테마 빌더를 사용할 수 없습니다.")
    job = _build_jobs.get(build_id)
    if not job:
        raise HTTPException(404, "빌드 작업 없음")

    if job["status"] not in ("uploaded", "error"):
        raise HTTPException(400, f"현재 상태: {job['status']}")

    job["status"] = "building"
    job["progress"] = 0
    job["message"] = "테마 빌드 시작..."
    job["theme_name"] = req.theme_name
    job["error"] = None

    # 백그라운드 스레드에서 빌드 실행
    thread = threading.Thread(
        target=_run_build,
        args=(build_id,),
        daemon=True,
    )
    thread.start()

    return {"build_id": build_id, "status": "building"}


def _run_build(build_id: str):
    """백그라운드 테마 빌드 실행."""
    from dotenv import load_dotenv
    load_dotenv()

    job = _build_jobs[build_id]
    lore_dir = Path(job["lore_dir"])
    theme_name = job["theme_name"]

    try:
        from worldweaver.theme_builder import build_theme_from_lore, save_theme

        def _on_progress(progress: int, message: str):
            job["progress"] = progress
            job["message"] = message

        theme_data = build_theme_from_lore(
            lore_dir,
            theme_name=theme_name,
            on_progress=_on_progress,
        )

        job["progress"] = 96
        job["message"] = "테마 저장 중..."

        # 임시 업로드 폴더를 테마 전용 영구 경로로 이동
        final_name = theme_data.get("name", build_id)
        permanent_lore_dir = Path("lore_documents") / final_name
        permanent_lore_dir.parent.mkdir(parents=True, exist_ok=True)
        if permanent_lore_dir.exists():
            shutil.rmtree(permanent_lore_dir)
        shutil.copytree(str(lore_dir), str(permanent_lore_dir))

        # 테마 JSON의 lore_dir를 영구 경로로 갱신
        # knowledge_graph.graphml은 lore_dir 내부에 저장되므로 copytree로 함께 복사됨
        theme_data["lore_dir"] = str(permanent_lore_dir)

        output_path = save_theme(theme_data)

        job["progress"] = 100
        job["status"] = "completed"
        job["message"] = f"테마 '{theme_data['display_name']}' 생성 완료!"
        job["result"] = {
            "theme_name": theme_data["name"],
            "display_name": theme_data.get("display_name", ""),
            "description": theme_data.get("description", ""),
            "npc_count": len(theme_data.get("npc_profiles", [])),
            "enemy_count": len(theme_data.get("enemies", [])),
        }

    except Exception as e:
        _access_logger.error(f"BUILD_FAILED | {build_id} | {type(e).__name__}: {e}")
        job["status"] = "error"
        job["message"] = "테마 빌드 중 오류가 발생했습니다."
        job["error"] = "빌드 처리 중 문제가 발생했습니다. 다시 시도해주세요."

    finally:
        # 임시 업로드 폴더 정리 (영구 경로로 복사 완료 후)
        if lore_dir.exists():
            shutil.rmtree(lore_dir, ignore_errors=True)


@app.get("/api/builder/status/{build_id}")
def get_build_status(build_id: str):
    """빌드 진행 상태 조회."""
    job = _build_jobs.get(build_id)
    if not job:
        raise HTTPException(404, "빌드 작업 없음")

    response = {
        "build_id": build_id,
        "status": job["status"],
        "progress": job["progress"],
        "message": job["message"],
    }

    if job["status"] == "completed" and "result" in job:
        response["result"] = job["result"]

    if job["error"]:
        response["error"] = job["error"]

    return response


# ── 프론트엔드 정적 파일 서빙 (프로덕션) ──
_frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    # 정적 에셋 (JS, CSS, 이미지 등)
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="static")

    # SPA fallback: API 경로가 아닌 모든 요청에 index.html 반환
    @app.get("/{path:path}")
    async def serve_spa(path: str):
        file_path = _frontend_dist / path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_frontend_dist / "index.html"))
