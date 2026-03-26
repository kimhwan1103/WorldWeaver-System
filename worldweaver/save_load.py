"""세이브/로드 엔진 — 전체 게임 상태를 JSON으로 직렬화/역직렬화.

저장 대상:
  - 메타 정보 (세션ID, 테마, 언어, 시각)
  - 월드 스테이트 (게이지, 엔티티, 속성, 컬렉션)
  - 스토리 그래프 (NetworkX → node_link_data)
  - NPC 메모리 그래프 (각 NPC별 그래프 + 호감도 + 씬 카운터)
  - 아이템 그래프 (아이템 상태 + 히든 발견 + 칭호)
  - 서사 컨텍스트 (문체, 분위기 흐름, 이야기 요약, 최근 씬 전문)
  - 스테이지 정보 (현재 위치, 방문 이력)
  - 마지막 선택지
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx


def serialize_session(session) -> dict:
    """WebGameSession을 JSON 직렬화 가능한 dict로 변환."""
    data = {
        "version": "1.0",
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "meta": _serialize_meta(session),
        "world_state": _serialize_world_state(session.world_state),
        "story_graph": _serialize_nx_graph(session.graph._graph),
        "npc_memories": _serialize_npc_memories(session.npc_manager),
        "item_graph": _serialize_item_graph(session.item_graph),
        "narrative_context": _build_narrative_context(session),
        "stage": {
            "current": session.current_stage,
            "visited": list(session.visited_stages),
        },
        "last_choices": session.last_choices,
        "last_scene": session._last_scene or _build_last_scene_from_graph(session),
        "scene_count": session.scene_count,
    }
    return data


def save_to_file(session, path: Path) -> Path:
    """세션을 JSON 파일로 저장."""
    data = serialize_session(session)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def save_to_json_string(session) -> str:
    """세션을 JSON 문자열로 반환 (다운로드용)."""
    data = serialize_session(session)
    return json.dumps(data, ensure_ascii=False, indent=2)


def load_from_dict(save_data: dict, session) -> None:
    """JSON dict에서 세션 상태를 복원."""
    # 월드 스테이트 복원
    ws = save_data.get("world_state", {})
    session.world_state.gauges = ws.get("gauges", {})
    session.world_state.entities = ws.get("entities", {})
    session.world_state.properties = ws.get("properties", {})
    session.world_state.collections = ws.get("collections", {})

    # 스토리 그래프 복원
    graph_data = save_data.get("story_graph")
    if graph_data:
        session.graph._graph = nx.node_link_graph(graph_data)

    # NPC 메모리 복원
    _restore_npc_memories(save_data.get("npc_memories", {}), session.npc_manager)

    # 아이템 그래프 복원
    if session.item_graph:
        _restore_item_graph(save_data.get("item_graph", {}), session.item_graph)

    # 스테이지 복원
    stage_data = save_data.get("stage", {})
    session.current_stage = stage_data.get("current", session.current_stage)
    session.visited_stages = set(stage_data.get("visited", []))

    # 기타 복원
    session.last_choices = save_data.get("last_choices", [])
    session._last_scene = save_data.get("last_scene")
    session.scene_count = save_data.get("scene_count", 0)

    # 현재 노드 ID 복원 (그래프의 마지막 노드)
    path = session.graph.get_path()
    if path:
        session.current_node_id = path[-1]

    # RAG 메모리 재구축 (스토리 그래프에서)
    _rebuild_rag_memory(session)

    # 서사 컨텍스트를 세션에 저장 (다음 씬 생성 시 주입)
    session._narrative_context = save_data.get("narrative_context", {})


def load_from_file(path: Path, session) -> dict:
    """JSON 파일에서 세션을 복원."""
    with open(path, "r", encoding="utf-8") as f:
        save_data = json.load(f)
    load_from_dict(save_data, session)
    return save_data.get("meta", {})


# ── 직렬화 헬퍼 ──

def _build_last_scene_from_graph(session) -> dict | None:
    """스토리 그래프에서 마지막 씬 데이터를 복원."""
    path = session.graph.get_path()
    if not path:
        return None

    last_id = path[-1]
    node = session.graph._graph.nodes.get(last_id, {})
    title = node.get("title", "")
    desc = node.get("description", "")

    if not title or title == "시작":
        return None

    # choices_json이 있으면 파싱
    import json as _json
    choices = []
    choices_raw = node.get("choices_json", "")
    if choices_raw:
        try:
            choices = _json.loads(choices_raw)
        except Exception:
            pass

    return {
        "scene": {
            "title": title,
            "description": desc,
            "features": {
                "mood": node.get("features_mood", ""),
                "morality_impact": node.get("features_morality_impact", ""),
            },
            "choices": choices,
            "state_change": {},
        },
        "choices": session.last_choices or choices,
    }


def _serialize_meta(session) -> dict:
    return {
        "session_id": session.session_id,
        "theme_name": session.theme.get("name", ""),
        "theme_display": session.theme.get("display_name", ""),
        "language": session.language,
        "scene_count": session.scene_count,
    }


def _serialize_world_state(ws) -> dict:
    return {
        "gauges": dict(ws.gauges),
        "entities": dict(ws.entities),
        "properties": dict(ws.properties),
        "collections": {k: list(v) for k, v in ws.collections.items()},
    }


def _serialize_nx_graph(graph: nx.DiGraph) -> dict:
    """NetworkX 그래프를 node_link_data로 변환."""
    return nx.node_link_data(graph)


def _serialize_npc_memories(npc_manager) -> dict:
    """모든 NPC의 메모리 그래프를 직렬화."""
    memories = {}
    for name, npc in npc_manager.get_all_npcs().items():
        memories[name] = {
            "disposition": npc.disposition,
            "scene_counter": npc._scene_counter,
            "current_stage": npc._current_stage,
            "graph": nx.node_link_data(npc._graph),
        }
    return memories


def _serialize_item_graph(item_graph) -> dict:
    """아이템 그래프를 직렬화."""
    if not item_graph:
        return {}

    items = {}
    for name, node in item_graph._items.items():
        items[name] = {
            "description": node.description,
            "base_effect": node.base_effect.to_dict(),
            "hidden_effect": node.hidden_effect.to_dict(),
            "hidden_discovered": node.hidden_discovered,
            "origin_type": node.origin_type,
            "origin_name": node.origin_name,
        }

    return {
        "items": items,
        "active_titles": list(item_graph._active_titles),
        "graph": nx.node_link_data(item_graph._graph),
    }


def _build_narrative_context(session) -> dict:
    """서사 컨텍스트를 구축 — LLM 톤 일관성 유지용."""
    # 분위기 흐름
    mood_progression = session.graph.get_recent_moods(10)

    # 최근 5개 씬의 전체 description
    recent_full = []
    path = session.graph.get_path()
    for node_id in path[-5:]:
        node = session.graph._graph.nodes.get(node_id, {})
        title = node.get("title", "")
        desc = node.get("description", "")
        if title and desc:
            recent_full.append({"title": title, "description": desc})

    # 전체 이야기 요약 (핵심 씬만)
    all_scenes = []
    for node_id in path:
        node = session.graph._graph.nodes.get(node_id, {})
        node_type = node.get("node_type", "story")
        if node_type == "story":
            title = node.get("title", "")
            desc = node.get("description", "")
            if title and title != "시작":
                all_scenes.append(f"[{title}] {desc[:80]}")

    # 요약이 너무 길면 앞뒤만
    if len(all_scenes) > 10:
        story_summary = all_scenes[:3] + ["..."] + all_scenes[-3:]
    else:
        story_summary = all_scenes

    # 문체 추론 (최근 씬 기반)
    style_hints = []
    if mood_progression:
        dominant_mood = max(set(mood_progression), key=mood_progression.count)
        style_hints.append(f"dominant mood: {dominant_mood}")
    if recent_full:
        # 최근 씬에서 문체 특징 추출 (간략)
        last_desc = recent_full[-1].get("description", "")
        if len(last_desc) > 200:
            style_hints.append("detailed, paragraph-style narration")
        else:
            style_hints.append("concise narration")

    return {
        "mood_history": mood_progression,
        "style_hints": style_hints,
        "story_summary": story_summary,
        "recent_scenes_full": recent_full,
    }


# ── 역직렬화 헬퍼 ──

def _restore_npc_memories(memories_data: dict, npc_manager) -> None:
    """NPC 메모리를 복원."""
    for name, data in memories_data.items():
        npc = npc_manager.get_npc(name)
        if not npc:
            continue

        npc._disposition = data.get("disposition", npc._disposition)
        npc._scene_counter = data.get("scene_counter", 0)
        npc._current_stage = data.get("current_stage", npc._current_stage)

        graph_data = data.get("graph")
        if graph_data:
            npc._graph = nx.node_link_graph(graph_data)


def _restore_item_graph(item_data: dict, item_graph) -> None:
    """아이템 그래프를 복원."""
    from worldweaver.item_graph import ItemEffect, ItemNode

    # 아이템 상태 복원
    items = item_data.get("items", {})
    for name, idata in items.items():
        if name in item_graph._items:
            node = item_graph._items[name]
        else:
            node = ItemNode(name=name)
            item_graph._items[name] = node

        node.description = idata.get("description", "")
        node.base_effect = ItemEffect.from_dict(idata.get("base_effect", {}))
        node.hidden_effect = ItemEffect.from_dict(idata.get("hidden_effect", {}))
        node.hidden_discovered = idata.get("hidden_discovered", False)
        node.origin_type = idata.get("origin_type", "")
        node.origin_name = idata.get("origin_name", "")

    # 칭호 복원
    item_graph._active_titles = item_data.get("active_titles", [])

    # 그래프 복원
    graph_data = item_data.get("graph")
    if graph_data:
        item_graph._graph = nx.node_link_graph(graph_data)


def _rebuild_rag_memory(session) -> None:
    """스토리 그래프에서 RAG 메모리를 재구축."""
    path = session.graph.get_path()
    for node_id in path:
        node = session.graph._graph.nodes.get(node_id, {})
        title = node.get("title", "")
        desc = node.get("description", "")
        if title and desc and title != "시작":
            text = f"[{title}] {desc}"
            try:
                session.memory.add_memory(text[:500])
            except Exception:
                pass  # RAG 저장 실패는 무시 (치명적이지 않음)
