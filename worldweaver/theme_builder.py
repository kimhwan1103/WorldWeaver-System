import json
from pathlib import Path

import networkx as nx
from langchain_community.document_loaders import DirectoryLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from worldweaver.config import CHUNK_OVERLAP, CHUNK_SIZE
from worldweaver.llm_factory import create_llm
from worldweaver.prompt_loader import get_theme_builder_prompt

# 테마 JSON 출력 스키마 설명
SCHEMA_INSTRUCTIONS = """{
  "name": "string (영문 소문자, 공백 없음)",
  "display_name": "string (한글 테마 이름)",
  "description": "string (한글 1-2문장 설명)",
  "initial_prompt": "string (한글 도입 시나리오 3-5문장)",
  "lore_dir": "string (세계관 문서 폴더 경로)",
  "world_state_schema": {
    "entities": {
      "label": "string", "description": "string",
      "removed_statuses": ["string"]
    },
    "gauges": {
      "gauge_name": {
        "label": "string", "description": "string",
        "min": 0.0, "max": 1.0, "default": 0.0
      }
    },
    "properties": {
      "property_name": {
        "label": "string", "description": "string", "default": "string"
      }
    },
    "collections": {
      "collection_name": {
        "label": "string", "description": "string"
      }
    }
  },
  "rules": {
    "gauge_rules": [
      {"gauge": "string", "operator": ">=", "threshold": 0.0, "directive": "string"}
    ],
    "climax_rules": [
      {"min_depth": 8, "gauge": "string", "operator": ">=", "threshold": 0.0, "directive": "string"}
    ]
  },
  "personas": {
    "persona_name": ["string"]
  },
  "npc_profiles": [
    {
      "name": "string (NPC 이름, 한글)",
      "personality": "string (성격 묘사 2-3문장, 한글)",
      "tone": "string (말투 스타일 묘사, 한글. 예: 고풍스러운 존댓말, 반말 섞인 친근한 말투)",
      "role": "string (역할: 현자, 상인, 전사, 정보원, 동맹, 적 등)",
      "stage": "string (소속 장소/스테이지 이름 — NPC는 이 장소에서만 등장하고, 다른 장소의 사건을 모름)",
      "initial_disposition": 0.5,
      "trigger_conditions": [
        {
          "min_depth": 0,
          "min_disposition": 0.0,
          "max_disposition": 1.0,
          "gauge": "string (optional)",
          "operator": "string (optional, >=, >, <=, <, ==)",
          "threshold": 0.0,
          "requires_item": "string (optional)",
          "directive": "string (한글, NPC가 등장할 때 스토리에 반영할 지시사항)"
        }
      ]
    }
  ],
  "stages": {
    "stage_name": {
      "keywords": ["keyword1", "keyword2"],
      "is_default": false,
      "layer": 1,
      "description": "string (장소 설명 1-2문장)",
      "connects_to": ["other_stage_name"],
      "unlock": {}
    }
  },
  "item_effects": {
    "item_name (must match enemy loot names)": {
      "description": "string (아이템 설명 1문장)",
      "base_effect": {"attack": 0, "defense": 0, "max_hp": 0, "heal": 0},
      "hidden_effect": {"attack": 0, "defense": 0, "max_hp": 0, "heal": 0},
      "npc_affinity": {
        "npc_name": {"disposition_delta": 0.0, "reaction": "neutral/curious/hostile/respectful"}
      }
    }
  },
  "titles": [
    {
      "id": "string",
      "name": "string (칭호 이름)",
      "description": "string (획득 조건 설명)",
      "conditions": {"entities_removed_min": 0, "min_hidden_discovered": 0},
      "bonus": {"attack": 0, "defense": 0, "max_hp": 0}
    }
  ],
  "enemies": [
    {
      "name": "string (적 이름, 한글)",
      "hp": 50,
      "attack": 10,
      "defense": 3,
      "description": "string (적 묘사 1-2문장, 한글)",
      "abilities": [
        {"name": "string (스킬 이름)", "damage": 15, "chance": 0.2}
      ],
      "loot": ["string (드랍 아이템 이름)"],
      "stage": "string (출현 스테이지/장소)"
    }
  ],
  "endings": [
    {
      "id": "string",
      "priority": 1,
      "conditions": {"min_depth": 10, "gauges": {"gauge_name": {"op": ">=", "value": 0.5}}},
      "prompt_hint": "string (엔딩 방향 지시, 영문)"
    }
  ],
  "game_over_conditions": [
    {
      "id": "string",
      "condition": {"gauges": {"gauge_name": {"op": ">=", "value": 1.0}}},
      "cause": "string (게임오버 원인, 한글)",
      "prompt_hint": "string (게임오버 씬 지시, 영문)"
    }
  ]
}"""


def build_theme_from_lore(
    lore_dir: Path,
    theme_name: str | None = None,
    on_progress: "callable | None" = None,
) -> dict:
    """세계관 문서 폴더를 분석하여 테마 JSON을 자동 생성.

    파이프라인: 문서 로드 → 청킹 → 청크별 그래프 추출 → 그래프 병합 → 테마 JSON 생성

    Args:
        on_progress: 콜백 함수 (progress: int, message: str) → None.
                     progress는 0-100 범위.
    """
    def _report(progress: int, message: str):
        print(f"  [{progress}%] {message}", flush=True)
        if on_progress:
            on_progress(progress, message)

    prompts = get_theme_builder_prompt()
    llm = create_llm()

    # ── 1단계: 문서 로드 + 청킹 (0-5%) ──
    _report(2, f"세계관 문서 로드 중: {lore_dir}")
    loader = DirectoryLoader(str(lore_dir), glob="**/*.txt")
    docs = loader.load()
    if not docs:
        raise FileNotFoundError(f"'{lore_dir}' 폴더에서 .txt 파일을 찾을 수 없습니다.")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(docs)
    _report(5, f"문서 {len(docs)}개 → 청크 {len(chunks)}개로 분할 완료")

    # ── 2단계: 각 청크에서 지식 그래프 추출 (5-55%) ──
    _report(6, f"지식 그래프 추출 시작 (청크 {len(chunks)}개)")
    extract_template = prompts["extract_graph"]["template"]
    partial_graphs = []

    # 청크 진행률: 5% ~ 55% 구간을 청크 수로 분배
    chunk_progress_start = 6
    chunk_progress_end = 55
    chunk_progress_range = chunk_progress_end - chunk_progress_start

    for i, chunk in enumerate(chunks):
        chunk_pct = chunk_progress_start + int(
            chunk_progress_range * i / len(chunks)
        )
        _report(chunk_pct, f"청크 분석 중 ({i + 1}/{len(chunks)})")
        prompt_text = extract_template.replace("{chunk_text}", chunk.page_content)

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = llm.invoke(prompt_text)
                raw = response.content
                # Gemini 등에서 content가 list[dict] 형태로 올 수 있음
                if isinstance(raw, list):
                    parts = []
                    for part in raw:
                        if isinstance(part, dict) and "text" in part:
                            parts.append(part["text"])
                        else:
                            parts.append(str(part))
                    raw = "\n".join(parts)
                elif not isinstance(raw, str):
                    raw = str(raw) if raw else ""
                print(f"      [응답 수신] 길이: {len(raw)}", flush=True)
                if not raw or not raw.strip():
                    if attempt < max_retries:
                        print(f"      → 빈 응답, 재시도 {attempt + 2}/{max_retries + 1}...", flush=True)
                        continue
                    raise ValueError("빈 응답 (모든 재시도 실패)")
                graph_data = _parse_json_response(raw)
                partial_graphs.append(graph_data)
                node_count = len(graph_data.get("nodes", []))
                edge_count = len(graph_data.get("edges", []))
                print(f"      → 노드 {node_count}개, 엣지 {edge_count}개 추출", flush=True)
                break
            except Exception as e:
                if attempt < max_retries:
                    print(f"      → 시도 {attempt + 1} 실패, 재시도...", flush=True)
                    continue
                print(f"      → 청크 {i + 1} 분석 실패: {type(e).__name__}: {e}", flush=True)
                break

    if not partial_graphs:
        raise RuntimeError("모든 청크에서 그래프 추출에 실패했습니다.")

    # ── 3단계: 그래프 병합 (55-60%) ──
    _report(56, "지식 그래프 병합 중...")
    merged_graph = _merge_graphs(partial_graphs)
    node_total = merged_graph.number_of_nodes()
    edge_total = merged_graph.number_of_edges()

    # 병합된 그래프를 GraphML로 저장 (테마별 lore_dir 내부에 저장)
    graph_output = lore_dir / "knowledge_graph.graphml"
    nx.write_graphml(merged_graph, str(graph_output))
    _report(60, f"그래프 병합 완료: 노드 {node_total}개, 엣지 {edge_total}개")

    # ── 4단계: 병합된 그래프 → 테마 JSON 생성 (60-80%) ──
    _report(62, "테마 JSON 생성 중... (AI가 게임 시스템을 설계하고 있습니다)")
    nodes_by_type = _format_nodes_by_type(merged_graph)
    edges_summary = _format_edges_summary(merged_graph)
    document_summaries = _build_document_summaries(chunks)

    # 토큰 제한 대응: 입력이 너무 크면 축약
    max_chars = 3000  # 노드+엣지+문서 합산 상한
    total = len(nodes_by_type) + len(edges_summary) + len(document_summaries)
    if total > max_chars:
        ratio = max_chars / total
        nodes_by_type = nodes_by_type[:int(len(nodes_by_type) * ratio)]
        edges_summary = edges_summary[:int(len(edges_summary) * ratio)]
        document_summaries = document_summaries[:int(len(document_summaries) * ratio)]
        print(f"      (입력 축약: {total}자 → {max_chars}자)")

    generate_prompt = prompts["generate_theme"]
    replacements = {
        "{node_count}": str(merged_graph.number_of_nodes()),
        "{edge_count}": str(merged_graph.number_of_edges()),
        "{nodes_by_type}": nodes_by_type,
        "{edges_summary}": edges_summary,
        "{schema_instructions}": SCHEMA_INSTRUCTIONS,
        "{lore_dir}": str(lore_dir),
        "{document_summaries}": document_summaries,
    }
    prompt_text = _assemble_sections(generate_prompt, replacements)

    theme_data = None
    for attempt in range(3):
        try:
            _report(65 + attempt * 5, f"테마 생성 중... (시도 {attempt + 1}/3)")
            response = llm.invoke(prompt_text)
            raw = response.content
            if isinstance(raw, list):
                parts = []
                for part in raw:
                    if isinstance(part, dict) and "text" in part:
                        parts.append(part["text"])
                    else:
                        parts.append(str(part))
                raw = "\n".join(parts)
            elif not isinstance(raw, str):
                raw = str(raw) if raw else ""
            print(f"      [테마 응답 수신] 길이: {len(raw)}", flush=True)
            if not raw or not raw.strip():
                print(f"      → 빈 응답, 재시도 {attempt + 2}/3...", flush=True)
                continue
            theme_data = _parse_json_response(raw)
            break
        except Exception as e:
            if attempt < 2:
                print(f"      → 테마 생성 시도 {attempt + 1} 실패: {e}, 재시도...", flush=True)
                continue
            raise

    if theme_data is None:
        raise RuntimeError("테마 JSON 생성에 실패했습니다 (모든 재시도 실패).")

    if theme_name:
        theme_data["name"] = theme_name

    _report(78, "테마 검증 중...")
    _validate_theme(theme_data)
    _report(80, "테마 검증 완료")

    # ── 5단계: 다국어 번역 (80-95%) ──
    _report(82, "다국어 번역 시작...")
    theme_data = _translate_theme(theme_data, source_lang="ko", on_progress=on_progress)
    translated_langs = list(theme_data.get("translations", {}).keys())
    _report(95, f"번역 완료: {', '.join(translated_langs) if translated_langs else '없음'}")

    _report(98, f"테마 '{theme_data['display_name']}' 생성 완료!")
    return theme_data


def save_theme(theme_data: dict, output_dir: Path | None = None) -> Path:
    """생성된 테마 JSON을 파일로 저장."""
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent.parent / "prompts" / "themes"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{theme_data['name']}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(theme_data, f, ensure_ascii=False, indent=2)

    print(f"테마 저장 완료: {output_path}")
    return output_path


# ── 번역 함수 ──


def _extract_translatable_fields(theme_data: dict) -> dict[str, str]:
    """테마 JSON에서 사용자 표시 텍스트를 {경로: 원문} 딕셔너리로 추출."""
    fields: dict[str, str] = {}

    # 최상위 텍스트
    for key in ("display_name", "description", "initial_prompt"):
        if key in theme_data and theme_data[key]:
            fields[key] = theme_data[key]

    # world_state_schema
    schema = theme_data.get("world_state_schema", {})

    entities = schema.get("entities", {})
    for attr in ("label", "description"):
        if attr in entities:
            fields[f"entities.{attr}"] = entities[attr]

    for section in ("gauges", "properties", "collections"):
        for name, cfg in schema.get(section, {}).items():
            for attr in ("label", "description"):
                if attr in cfg:
                    fields[f"{section}.{name}.{attr}"] = cfg[attr]

    # NPC
    for npc in theme_data.get("npc_profiles", []):
        prefix = f"npc.{npc['name']}"
        for attr in ("name", "personality", "tone", "role"):
            if attr in npc and npc[attr]:
                fields[f"{prefix}.{attr}"] = npc[attr]
        for i, tc in enumerate(npc.get("trigger_conditions", [])):
            if "directive" in tc:
                fields[f"{prefix}.trigger.{i}.directive"] = tc["directive"]

    # 적
    for enemy in theme_data.get("enemies", []):
        prefix = f"enemies.{enemy['name']}"
        for attr in ("name", "description"):
            if attr in enemy and enemy[attr]:
                fields[f"{prefix}.{attr}"] = enemy[attr]
        for ab in enemy.get("abilities", []):
            if "name" in ab:
                fields[f"{prefix}.abilities.{ab['name']}"] = ab["name"]
        for loot_item in enemy.get("loot", []):
            fields[f"{prefix}.loot.{loot_item}"] = loot_item

    # 스테이지
    for stage_name in theme_data.get("stages", {}):
        fields[f"stages.{stage_name}"] = stage_name

    # 룰 디렉티브
    rules = theme_data.get("rules", {})
    for section in ("gauge_rules", "climax_rules"):
        for i, rule in enumerate(rules.get(section, [])):
            if "directive" in rule:
                fields[f"rules.{section}.{i}.directive"] = rule["directive"]

    return fields


_BATCH_MAX_CHARS = 1500  # 배치당 소스 JSON 최대 문자 수


def _split_into_batches(fields: dict[str, str], max_chars: int = _BATCH_MAX_CHARS) -> list[dict[str, str]]:
    """번역 대상 필드를 토큰 제한에 맞게 배치로 분할."""
    batches: list[dict[str, str]] = []
    current: dict[str, str] = {}
    current_len = 0

    for key, value in fields.items():
        entry_len = len(key) + len(value) + 10  # JSON 오버헤드
        if current and current_len + entry_len > max_chars:
            batches.append(current)
            current = {}
            current_len = 0
        current[key] = value
        current_len += entry_len

    if current:
        batches.append(current)

    return batches


def _translate_theme(
    theme_data: dict,
    source_lang: str = "ko",
    on_progress: "callable | None" = None,
) -> dict:
    """테마의 사용자 표시 텍스트를 지원 언어로 번역 (배치 분할)."""
    from worldweaver.prompt_loader import get_game_config

    config = get_game_config()
    supported = config.get("supported_languages", {})
    target_langs = [lang for lang in supported if lang != source_lang]

    if not target_langs:
        return theme_data

    prompts = get_theme_builder_prompt()
    translate_template = prompts["translate_theme"]["template"]
    llm = create_llm()
    source_fields = _extract_translatable_fields(theme_data)

    if not source_fields:
        return theme_data

    batches = _split_into_batches(source_fields)
    lang_names = {"ko": "Korean(한국어)", "en": "English", "ja": "Japanese(日本語)"}
    translations: dict[str, dict] = {}

    # 번역 진행률: 82% ~ 94% 구간을 언어×배치로 분배
    translate_start = 82
    translate_end = 94
    total_work = len(target_langs) * max(len(batches), 1)
    work_done = 0

    for lang in target_langs:
        lang_label = lang_names.get(lang, lang)
        print(f"      {lang_label} 번역 중... ({len(batches)}개 배치)")
        lang_result: dict[str, str] = {}

        for i, batch in enumerate(batches):
            work_done += 1
            pct = translate_start + int(
                (translate_end - translate_start) * work_done / total_work
            )
            if on_progress:
                on_progress(pct, f"{lang_label} 번역 중 ({i + 1}/{len(batches)})")

            batch_json = json.dumps(batch, ensure_ascii=False, indent=2)
            prompt_text = translate_template.replace(
                "{target_language}", lang_label
            ).replace("{source_fields_json}", batch_json)

            try:
                response = llm.invoke(prompt_text)
                tr_raw = response.content
                if isinstance(tr_raw, list):
                    parts = []
                    for part in tr_raw:
                        if isinstance(part, dict) and "text" in part:
                            parts.append(part["text"])
                        else:
                            parts.append(str(part))
                    tr_raw = "\n".join(parts)
                elif not isinstance(tr_raw, str):
                    tr_raw = str(tr_raw) if tr_raw else ""
                translated = _parse_json_response(tr_raw)
                lang_result.update(translated)
                print(f"        배치 {i + 1}/{len(batches)}: {len(translated)}개 완료")
            except Exception as e:
                print(f"        배치 {i + 1}/{len(batches)} 실패: {e}")
                continue

        if lang_result:
            translations[lang] = lang_result
            print(f"      → {lang}: 총 {len(lang_result)}/{len(source_fields)}개 번역 완료")

    theme_data["translations"] = translations
    return theme_data


def translate_existing_theme(theme_name: str, source_lang: str = "en") -> Path:
    """기존 테마 JSON을 로드하여 번역을 추가하고 저장."""
    from worldweaver.prompt_loader import load_theme, _cache

    theme_data = load_theme(theme_name)
    theme_data = _translate_theme(theme_data, source_lang=source_lang)

    # 캐시 무효화
    _cache.pop(f"theme:{theme_name}", None)

    return save_theme(theme_data)


# ── 내부 함수 ──


def _assemble_sections(prompt_config: dict, replacements: dict) -> str:
    """generate_theme의 sections 배열을 ### 헤더로 구분된 프롬프트 텍스트로 조립."""
    parts = [prompt_config["system_role"]]

    for section in prompt_config["sections"]:
        header = section["header"]
        parts.append(f"\n### {header} ###")

        # description이 있으면 헤더 바로 아래에 추가
        if "description" in section:
            parts.append(section["description"])

        body = section["body"]
        if isinstance(body, list):
            # 배열이면 불릿 리스트로 조립
            parts.append("\n".join(f"- {item}" for item in body))
        else:
            # 문자열이면 그대로 사용
            parts.append(body)

    text = "\n".join(parts)

    for key, value in replacements.items():
        text = text.replace(key, value)

    return text


def _parse_json_response(raw_text: str) -> dict:
    """LLM 응답에서 JSON을 파싱. <think> 블록 + 마크다운 코드블록 자동 제거.

    Qwen3 등 thinking 모델이 <think> 태그를 닫지 않는 경우도 처리.
    """
    import re
    import sys
    text = raw_text.strip()

    # 1) <think>...</think> 닫힌 블록 제거
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)

    # 2) 닫히지 않은 <think> 처리: <think> 이후 첫 번째 { 또는 [ 전까지 제거
    if "<think>" in text:
        before, after = text.split("<think>", 1)
        # after에서 첫 JSON 시작점 찾기
        json_start = re.search(r"[{\[]", after)
        if json_start:
            text = before + after[json_start.start():]
        else:
            text = before
        text = text.strip()

    # 3) 마크다운 코드블록 추출
    md_match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if md_match:
        text = md_match.group(1).strip()

    # 4) 중괄호 매칭으로 JSON 추출 (가장 견고한 방법)
    text = _extract_json_by_braces(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"      [JSON 파싱 실패] {e} — 자동 복구 시도 중...", flush=True)
        # 잘린 JSON 자동 복구 시도
        repaired = _repair_truncated_json(text)
        if repaired:
            try:
                result = json.loads(repaired)
                print(f"      [JSON 복구 성공]", flush=True)
                return result
            except json.JSONDecodeError:
                pass
        print(f"      [정제된 텍스트 앞 300자] {text[:300]!r}", flush=True)
        raise


def _repair_truncated_json(text: str) -> str | None:
    """잘린 JSON을 복구. 미완성 문자열/배열/객체를 닫아줌.

    Groq 등에서 max_tokens 초과로 JSON이 중간에 끊기는 경우를 처리.
    """
    if not text or not text.strip():
        return None

    text = text.strip()

    # 문자열 내부에서 잘렸으면 닫기
    # 마지막 완성된 항목까지 자르기: 마지막 }, ] 또는 완전한 key-value 쌍 찾기
    # 전략: 마지막으로 올바르게 끝난 줄까지 잘라내고 괄호 닫기
    lines = text.split("\n")

    # 뒤에서부터 유효한 JSON 라인 찾기
    for i in range(len(lines) - 1, -1, -1):
        candidate = "\n".join(lines[: i + 1]).rstrip().rstrip(",")

        # 열린 괄호 카운트
        open_braces = candidate.count("{") - candidate.count("}")
        open_brackets = candidate.count("[") - candidate.count("]")

        # 미완성 문자열 체크 (홀수 개의 이스케이프되지 않은 따옴표)
        in_str = False
        esc = False
        for c in candidate:
            if esc:
                esc = False
                continue
            if c == "\\" and in_str:
                esc = True
                continue
            if c == '"':
                in_str = not in_str

        # 문자열이 열려있으면 닫기
        if in_str:
            candidate += '"'

        # 괄호 닫기
        candidate += "]" * max(0, open_brackets)
        candidate += "}" * max(0, open_braces)

        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            continue

    return None


def _extract_json_by_braces(text: str) -> str:
    """텍스트에서 균형 잡힌 {} 또는 [] JSON 블록을 추출."""
    start = -1
    for i, c in enumerate(text):
        if c in ("{", "["):
            start = i
            break

    if start < 0:
        return text  # { 또는 [ 가 없으면 원본 반환

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if esc:
            esc = False
            continue
        if c == "\\" and in_str:
            esc = True
            continue
        if c == '"' and not esc:
            in_str = not in_str
            continue
        if in_str:
            continue
        if c in ("{", "["):
            depth += 1
        elif c in ("}", "]"):
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    # 균형이 안 맞으면 시작점부터 전체 반환
    return text[start:]


def _merge_graphs(partial_graphs: list[dict]) -> nx.DiGraph:
    """여러 부분 그래프를 하나의 NetworkX DiGraph로 병합.

    같은 이름의 노드는 하나로 합쳐지고, 설명은 더 긴 쪽을 유지한다.
    """
    merged = nx.DiGraph()

    for graph_data in partial_graphs:
        # 노드 병합
        for node in graph_data.get("nodes", []):
            name = node["name"]
            if merged.has_node(name):
                # 기존 노드가 있으면 설명이 더 긴 쪽을 유지
                existing_desc = merged.nodes[name].get("description", "")
                new_desc = node.get("description", "")
                if len(new_desc) > len(existing_desc):
                    merged.nodes[name]["description"] = new_desc
            else:
                merged.add_node(
                    name,
                    type=node.get("type", "concept"),
                    description=node.get("description", ""),
                )

        # 엣지 병합
        for edge in graph_data.get("edges", []):
            source = edge.get("source", "")
            target = edge.get("target", "")
            if not source or not target:
                continue

            # 소스/타겟 노드가 없으면 자동 추가
            if not merged.has_node(source):
                merged.add_node(source, type="concept", description="")
            if not merged.has_node(target):
                merged.add_node(target, type="concept", description="")

            # 같은 소스-타겟 엣지가 있어도 관계 유형이 다르면 추가
            if not merged.has_edge(source, target):
                merged.add_edge(
                    source,
                    target,
                    relation=edge.get("relation", "related_to"),
                    description=edge.get("description", ""),
                )

    return merged


def _format_nodes_by_type(graph: nx.DiGraph) -> str:
    """그래프 노드를 타입별로 정리한 문자열."""
    by_type: dict[str, list[str]] = {}
    for node, data in graph.nodes(data=True):
        node_type = data.get("type", "concept")
        desc = data.get("description", "")
        entry = f"{node}: {desc}" if desc else node
        by_type.setdefault(node_type, []).append(entry)

    lines = []
    type_labels = {
        "character": "캐릭터/존재",
        "location": "장소/지역",
        "item": "아이템/유물",
        "system": "시스템/메카닉",
        "concept": "개념/현상",
        "faction": "세력/집단",
    }
    for node_type, entries in sorted(by_type.items()):
        label = type_labels.get(node_type, node_type)
        lines.append(f"\n[{label}] ({len(entries)}개)")
        for entry in entries:
            lines.append(f"  - {entry}")

    return "\n".join(lines)


def _format_edges_summary(graph: nx.DiGraph) -> str:
    """그래프 엣지를 관계 유형별로 정리한 문자열."""
    by_relation: dict[str, list[str]] = {}
    for source, target, data in graph.edges(data=True):
        relation = data.get("relation", "related_to")
        desc = data.get("description", "")
        entry = f"{source} → {target}"
        if desc:
            entry += f" ({desc})"
        by_relation.setdefault(relation, []).append(entry)

    lines = []
    for relation, entries in sorted(by_relation.items()):
        lines.append(f"\n[{relation}] ({len(entries)}개)")
        for entry in entries:
            lines.append(f"  - {entry}")

    return "\n".join(lines)


def _build_document_summaries(chunks) -> str:
    """청크 원본 텍스트의 앞 200자씩을 요약으로 제공."""
    lines = []
    for i, chunk in enumerate(chunks):
        source = Path(chunk.metadata.get("source", "unknown")).name
        preview = chunk.page_content[:200].replace("\n", " ")
        lines.append(f"[{source} - 청크 {i + 1}] {preview}...")
    return "\n".join(lines)


def _validate_theme(data: dict):
    """테마 JSON의 필수 필드 존재 여부를 검증하고, 누락 필드를 자동 보완."""
    required_top = ["name", "display_name", "initial_prompt", "world_state_schema"]
    for field in required_top:
        if field not in data:
            raise ValueError(f"테마 JSON에 필수 필드 '{field}'가 없습니다.")

    # lore_dir이 없으면 기본값 설정
    if "lore_dir" not in data:
        print("(경고: 'lore_dir' 누락 → 기본값 'lore_documents' 설정)")
        data["lore_dir"] = "lore_documents"

    schema = data["world_state_schema"]
    required_schema = ["entities", "gauges", "collections"]
    for field in required_schema:
        if field not in schema:
            raise ValueError(f"world_state_schema에 필수 필드 '{field}'가 없습니다.")

    if "gauges" in schema and not schema["gauges"]:
        raise ValueError("최소 1개 이상의 게이지가 필요합니다.")

    # properties가 없으면 빈 dict로 초기화
    if "properties" not in schema:
        print("(경고: 'properties' 누락 → 빈 구조로 자동 추가)")
        schema["properties"] = {}

    # rules가 없으면 빈 구조로 초기화
    if "rules" not in data:
        print("(경고: 'rules' 누락 → 빈 구조로 자동 추가)")
        data["rules"] = {"gauge_rules": [], "climax_rules": []}

    # personas가 없으면 기본값 설정
    if "personas" not in data:
        print("(경고: 'personas' 누락 → 기본 hero/villain 설정)")
        data["personas"] = {
            "hero": ["Good", "Diplomatic", "Cautious"],
            "villain": ["Evil", "Aggressive"],
        }

    # 필수 컬렉션 자동 보완
    collections = schema.get("collections", {})
    required_collections = {
        "inventory": {"label": "보유 아이템", "description": "보유한 아이템 목록"},
        "resolved_events": {"label": "해결된 사건", "description": "해결된 사건 목록"},
        "unresolved_hooks": {"label": "미회수 복선", "description": "미회수 복선 목록"},
    }
    for col_name, default_val in required_collections.items():
        if col_name not in collections:
            print(f"(경고: 권장 컬렉션 '{col_name}' 누락 → 자동 추가)")
            collections[col_name] = default_val

    # health 게이지 자동 추가 (전투 시스템용)
    gauges = schema.get("gauges", {})
    if "health" not in gauges:
        print("(경고: 'health' 게이지 누락 → 전투 시스템용 자동 추가)")
        gauges["health"] = {
            "label": "생명력",
            "description": "전투에서 데미지를 받으면 감소",
            "min": 0.0,
            "max": 1.0,
            "default": 1.0,
        }

    # stages 자동 보완
    if "stages" not in data or not data["stages"]:
        print("(경고: 'stages' 누락 → 기본 스테이지 자동 생성)")
        data["stages"] = {
            "default": {
                "keywords": [],
                "is_default": True,
                "layer": 1,
                "description": "",
                "connects_to": [],
                "unlock": {},
            }
        }
    else:
        # 각 스테이지에 필수 필드 보완
        for stage_name, cfg in data["stages"].items():
            cfg.setdefault("keywords", [])
            cfg.setdefault("layer", 1)
            cfg.setdefault("description", "")
            cfg.setdefault("connects_to", [])
            cfg.setdefault("unlock", {})
        # is_default가 없으면 첫 번째에 설정
        has_default = any(c.get("is_default") for c in data["stages"].values())
        if not has_default:
            first_stage = next(iter(data["stages"].values()))
            first_stage["is_default"] = True

    # item_effects 자동 보완 (없으면 빈 dict)
    if "item_effects" not in data:
        data["item_effects"] = {}

    # titles 자동 보완 (없으면 빈 list)
    if "titles" not in data:
        data["titles"] = []

    # endings 자동 보완 (없으면 기본 엔딩)
    if "endings" not in data or not data["endings"]:
        print("(경고: 'endings' 누락 → 기본 엔딩 자동 추가)")
        data["endings"] = [
            {
                "id": "default",
                "priority": 99,
                "conditions": {"min_depth": 12},
                "prompt_hint": "The journey reaches its natural conclusion. Write an ending that reflects the overall tone of the adventure.",
            }
        ]

    # game_over_conditions 자동 보완 (없으면 빈 list)
    if "game_over_conditions" not in data:
        data["game_over_conditions"] = []

    # NPC 프로필 검증 및 자동 보완
    _validate_npc_profiles(data)

    # 적 정의 검증 및 자동 보완
    _validate_enemies(data)


def _validate_npc_profiles(data: dict):
    """NPC 프로필 목록을 검증하고 누락 필드를 자동 보완."""
    profiles = data.get("npc_profiles", [])

    if not profiles:
        print("(경고: 'npc_profiles' 누락 → 빈 목록으로 설정)")
        data["npc_profiles"] = []
        return

    if not isinstance(profiles, list):
        print("(경고: 'npc_profiles' 형식 오류 → 빈 목록으로 초기화)")
        data["npc_profiles"] = []
        return

    valid_profiles = []
    for i, npc in enumerate(profiles):
        if not isinstance(npc, dict):
            print(f"(경고: NPC #{i + 1} 형식 오류 → 건너뜀)")
            continue

        # 필수 필드: name
        if "name" not in npc or not npc["name"]:
            print(f"(경고: NPC #{i + 1} 이름 없음 → 건너뜀)")
            continue

        name = npc["name"]

        # 누락 필드 자동 보완
        if "personality" not in npc or not npc["personality"]:
            npc["personality"] = "중립적인 성격의 인물."
            print(f"(경고: NPC '{name}' personality 누락 → 기본값 설정)")

        if "tone" not in npc or not npc["tone"]:
            npc["tone"] = "평범한 말투"
            print(f"(경고: NPC '{name}' tone 누락 → 기본값 설정)")

        if "role" not in npc or not npc["role"]:
            npc["role"] = "일반"
            print(f"(경고: NPC '{name}' role 누락 → 기본값 설정)")

        if "stage" not in npc or not npc["stage"]:
            npc["stage"] = "default"
            print(f"(경고: NPC '{name}' stage 누락 → 'default' 설정)")

        # 호감도 범위 보정
        disposition = npc.get("initial_disposition", 0.5)
        try:
            disposition = float(disposition)
        except (ValueError, TypeError):
            disposition = 0.5
        npc["initial_disposition"] = max(0.0, min(1.0, disposition))

        # trigger_conditions 검증
        triggers = npc.get("trigger_conditions", [])
        if not isinstance(triggers, list):
            npc["trigger_conditions"] = []
        else:
            valid_triggers = []
            for t in triggers:
                if isinstance(t, dict) and "directive" in t:
                    valid_triggers.append(t)
            npc["trigger_conditions"] = valid_triggers

        valid_profiles.append(npc)

    data["npc_profiles"] = valid_profiles
    print(f"NPC 프로필 검증 완료: {len(valid_profiles)}명")


def _validate_enemies(data: dict):
    """적 정의 목록을 검증하고 누락 필드를 자동 보완."""
    enemies = data.get("enemies", [])

    if not enemies:
        print("(경고: 'enemies' 누락 → 빈 목록으로 설정)")
        data["enemies"] = []
        return

    if not isinstance(enemies, list):
        print("(경고: 'enemies' 형식 오류 → 빈 목록으로 초기화)")
        data["enemies"] = []
        return

    valid_enemies = []
    for i, enemy in enumerate(enemies):
        if not isinstance(enemy, dict):
            continue

        if "name" not in enemy or not enemy["name"]:
            print(f"(경고: 적 #{i + 1} 이름 없음 → 건너뜀)")
            continue

        name = enemy["name"]

        # 스탯 기본값 및 범위 보정
        enemy["hp"] = max(10, min(200, int(enemy.get("hp", 50))))
        enemy["attack"] = max(1, min(30, int(enemy.get("attack", 8))))
        enemy["defense"] = max(0, min(15, int(enemy.get("defense", 3))))

        if "description" not in enemy:
            enemy["description"] = ""

        if "stage" not in enemy or not enemy["stage"]:
            enemy["stage"] = "default"

        # abilities 검증
        abilities = enemy.get("abilities", [])
        if not isinstance(abilities, list):
            enemy["abilities"] = []
        else:
            valid_abilities = []
            for a in abilities:
                if isinstance(a, dict) and "name" in a:
                    a["damage"] = max(1, int(a.get("damage", enemy["attack"])))
                    a["chance"] = max(0.05, min(0.5, float(a.get("chance", 0.2))))
                    valid_abilities.append(a)
            enemy["abilities"] = valid_abilities

        # loot 검증
        loot = enemy.get("loot", [])
        if not isinstance(loot, list):
            enemy["loot"] = []

        valid_enemies.append(enemy)

    data["enemies"] = valid_enemies
    print(f"적 정의 검증 완료: {len(valid_enemies)}종")
