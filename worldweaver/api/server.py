"""FastAPI 웹 서버 — WorldWeaver System API."""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from worldweaver.api.session_manager import SessionManager
from worldweaver.prompt_loader import list_themes, load_theme

app = FastAPI(title="WorldWeaver API", version="0.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

manager = SessionManager()


# ── 요청/응답 모델 ──

class StartGameRequest(BaseModel):
    theme: str = "mythology"

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


# ── 게임 세션 API ──

@app.post("/api/game/start")
def start_game(req: StartGameRequest):
    """새 게임 세션 시작."""
    try:
        session = manager.create_session(req.theme)
    except Exception as e:
        raise HTTPException(500, f"세션 생성 실패: {e}")

    return {
        "session_id": session.session_id,
        "theme": session.theme.get("display_name", ""),
        "initial_prompt": session.theme.get("initial_prompt", ""),
        "world_state": session._get_state_snapshot(),
        "enemies": session.enemy_registry.get_all_enemy_names(),
    }


@app.post("/api/game/scene")
def generate_scene(req: ChoiceRequest):
    """선택지를 선택하여 다음 씬 생성."""
    session = manager.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "세션 없음")

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
            return {"redirect": "dialogue", "npc_name": selected.get("npc_name")}
        if selected.get("choice_type") == "combat":
            return {"redirect": "combat", "enemy_name": selected.get("enemy_name")}

        prompt = selected["next_node_prompt"]

    result = session.generate_scene(prompt)
    if "error" in result:
        raise HTTPException(500, result["error"])

    return result


@app.get("/api/game/{session_id}/state")
def get_game_state(session_id: str):
    """현재 게임 상태 조회."""
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "세션 없음")

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

@app.post("/api/dialogue")
def dialogue(req: DialogueRequest):
    """NPC 대화."""
    session = manager.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "세션 없음")

    result = session.process_dialogue(req.npc_name, req.message)
    if "error" in result:
        raise HTTPException(500, result["error"])

    return result


@app.get("/api/dialogue/{session_id}/{npc_name}/info")
def get_npc_info(session_id: str, npc_name: str):
    """NPC 정보 조회."""
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "세션 없음")

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


# ── 전투 API ──

@app.post("/api/combat/start")
def start_combat(req: CombatActionRequest):
    """전투 시작."""
    session = manager.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "세션 없음")

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
def begin_combat(req: StartCombatRequest):
    """전투 시작 (명확한 인터페이스)."""
    session = manager.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "세션 없음")

    result = session.start_combat(req.enemy_name)
    if "error" in result:
        raise HTTPException(400, result["error"])

    return result


@app.post("/api/combat/action")
def combat_action(req: CombatActionRequest):
    """전투 행동."""
    session = manager.get_session(req.session_id)
    if not session:
        raise HTTPException(404, "세션 없음")

    result = session.combat_action(req.action, req.item_name)
    if "error" in result:
        raise HTTPException(400, result["error"])

    return result


# ── WebSocket (실시간 업데이트) ──

@app.websocket("/ws/game/{session_id}")
async def websocket_game(websocket: WebSocket, session_id: str):
    """게임 세션 WebSocket — 실시간 전투/대화."""
    await websocket.accept()

    session = manager.get_session(session_id)
    if not session:
        await websocket.send_json({"error": "세션 없음"})
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

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
                await websocket.send_json({"type": "scene", **result})

            elif msg_type == "dialogue":
                npc_name = data.get("npc_name", "")
                message = data.get("message", "")
                result = session.process_dialogue(npc_name, message)
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
