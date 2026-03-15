"""웹 게임 세션 관리자.

동시 다중 세션을 관리하며, 각 세션은 독립된 GameSession을 가진다.
CLI의 GameSession을 웹 API에서 사용할 수 있도록 래핑한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from worldweaver.chain import build_npc_dialogue_chain, build_story_chain
from worldweaver.combat import CombatEngine, EnemyRegistry
from worldweaver.content_filter import (
    detect_injection,
    get_npc_deflection,
    sanitize_for_memory,
    sanitize_input,
    validate_state_change,
)
from worldweaver.graph import StoryGraph
from worldweaver.npc_memory import NPCManager
from worldweaver.prompt_loader import list_themes, load_theme
from worldweaver.rag import LoreMemory
from worldweaver.rule_engine import RuleEngine
from worldweaver.world_state import WorldState


@dataclass
class WebGameSession:
    """웹 전용 게임 세션. CLI GameSession의 핵심 로직을 API 친화적으로 래핑."""

    session_id: str
    theme: dict
    memory: LoreMemory
    chain: object
    npc_dialogue_chain: object | None
    graph: StoryGraph
    world_state: WorldState
    rule_engine: RuleEngine
    npc_manager: NPCManager
    enemy_registry: EnemyRegistry
    _retriever: object = field(default=None, repr=False)
    current_stage: str = "default"
    current_node_id: str = ""
    last_choices: list[dict] = field(default_factory=list)
    scene_count: int = 0
    # 전투 상태
    active_combat: CombatEngine | None = field(default=None, repr=False)
    active_combat_template: object | None = field(default=None, repr=False)
    combat_parent_id: str = ""

    def generate_scene(self, prompt: str) -> dict:
        """씬을 생성하고 결과를 반환. CLI _generate_with_validation + _process_scene 통합."""
        # 입력 필터
        injections = detect_injection(prompt)
        if injections:
            prompt = sanitize_input(prompt)

        # 사전 지시사항
        directives = self.rule_engine.pre_generation_directives()
        npc_triggers = self.npc_manager.get_triggered_npcs(
            self.world_state, self.graph.get_depth()
        )
        for _npc, directive in npc_triggers:
            directives.append(directive)

        directives_text = ""
        if directives:
            directives_text = "\n### Mandatory Directives (MUST follow) ###\n"
            directives_text += "\n".join(f"- {d}" for d in directives)

        recent = self.graph.get_recent_scenes_summary(3)
        recent_text = "\n".join(
            f"- [{s['title']}] {s['description']}" for s in recent
        ) if recent else "(첫 번째 씬입니다)"

        state_change_schema = self.world_state.get_state_change_schema_for_prompt()

        chain_input = {
            "request": prompt,
            "retriever": self._retriever,
            "world_state": self.world_state.to_prompt_string(),
            "recent_scenes": recent_text,
            "directives": directives_text,
            "state_change_schema": state_change_schema,
        }

        for attempt in range(self.rule_engine.MAX_RETRY + 1):
            try:
                node_data = self.chain.invoke(chain_input)
            except Exception as e:
                return {"error": str(e)}

            result = self.rule_engine.validate_scene(node_data)
            if result.passed:
                break
            if attempt < self.rule_engine.MAX_RETRY:
                retry_prompt = self.rule_engine.build_retry_prompt(prompt, result)
                chain_input["request"] = retry_prompt
            else:
                break

        # 씬 처리
        self.scene_count += 1
        choice_text = "이야기 진행"
        parent_id = self.current_node_id or self.graph.add_start_node(prompt)
        self.current_node_id = self.graph.add_scene(node_data, parent_id, choice_text)

        # 스테이지 감지
        self._detect_stage(node_data)

        # NPC 기억 마모 + 사건 기록
        self.npc_manager.advance_all_scenes()
        self.npc_manager.record_scene_event(
            f"[씬: {node_data['title']}] {node_data['description'][:200]}",
            self.current_stage,
        )

        # RAG 저장
        memory_text = f"[{node_data['title']}] {node_data['description']}"
        self.memory.add_memory(sanitize_for_memory(memory_text))

        # 상태 변경
        state_change = node_data.get("state_change", {})
        if state_change:
            validated = validate_state_change(state_change, self.world_state)
            self.world_state.apply_changes(validated)

        self.graph.add_future_choices(self.current_node_id, node_data.get("choices", []))

        # NPC 선택지 주입
        choices = list(node_data.get("choices", []))
        triggered = self.npc_manager.get_triggered_npcs(
            self.world_state, self.graph.get_depth()
        )
        for npc, directive in triggered:
            existing = [c for c in choices if c.get("npc_name") == npc.profile.name]
            if not existing:
                choices.append({
                    "text": f"💬 {npc.profile.name}({npc.profile.role})과(와) 대화하기",
                    "edge_feature": "Diplomatic",
                    "next_node_prompt": directive,
                    "choice_type": "dialogue",
                    "npc_name": npc.profile.name,
                })

        self.last_choices = choices

        # NPC 목록
        npcs_here = self.npc_manager.get_npcs_at_stage(self.current_stage)

        return {
            "scene": node_data,
            "choices": choices,
            "world_state": self._get_state_snapshot(),
            "npcs": [
                {"name": n.profile.name, "role": n.profile.role, "disposition": n.disposition_label}
                for n in npcs_here
            ],
            "scene_count": self.scene_count,
        }

    def process_dialogue(self, npc_name: str, player_input: str) -> dict:
        """NPC 대화 처리."""
        npc = self.npc_manager.get_npc(npc_name)
        if not npc or not self.npc_dialogue_chain:
            return {"error": f"NPC '{npc_name}' 또는 대화 체인 없음"}

        injections = detect_injection(player_input)
        if injections:
            player_input = sanitize_input(player_input)

        # 대화 내용으로 잊혀진 기억 복원 시도
        recovered = npc.recover_memory(player_input)

        dialogue_history = npc.get_dialogue_history(self.current_stage)
        history_text = "\n".join(m["content"] for m in dialogue_history) if dialogue_history else "(첫 대화)"

        chain_input = {
            "npc_context": npc.to_prompt_context(),
            "world_state": self.world_state.to_prompt_string(),
            "dialogue_history": history_text,
            "player_input": player_input,
        }

        try:
            result = self.npc_dialogue_chain.invoke(chain_input)
        except Exception as e:
            return {"error": str(e)}

        # 호감도
        delta = max(-0.2, min(0.2, result.get("disposition_delta", 0.0)))
        old_label = npc.disposition_label
        if delta != 0.0:
            npc.disposition += delta
        new_label = npc.disposition_label

        # NPC 행동
        action = result.get("action")
        action_detail = result.get("action_detail", "")
        action_result = None
        if action:
            action_result = self._handle_npc_action(npc, action, action_detail)

        # 기억 기록
        npc.record_dialogue(player_input, result["response"], self.current_stage, disposition_delta=delta)
        if result.get("memory_note"):
            npc.record_memory("observation", result["memory_note"], self.current_stage)

        # 호감도 동기화
        self.world_state.entities[npc.profile.name] = npc.disposition_label

        # 기억 복원 결과
        recovered_info = None
        if recovered:
            recovered_info = [
                {"type": r.get("type", ""), "content": r.get("content", "")[:100]}
                for r in recovered
            ]

        return {
            "response": result["response"],
            "disposition": npc.disposition,
            "disposition_label": new_label,
            "disposition_changed": old_label != new_label,
            "action": action_result,
            "should_end": result.get("should_end", False),
            "world_state": self._get_state_snapshot(),
            "recovered_memories": recovered_info,
        }

    def start_combat(self, enemy_name: str) -> dict:
        """전투 시작."""
        template = self.enemy_registry.get_enemy(enemy_name)
        if not template:
            return {"error": f"적 '{enemy_name}' 없음"}

        engine = CombatEngine.from_template(template, self.world_state)
        self.active_combat = engine
        self.active_combat_template = template
        self.combat_parent_id = self.current_node_id

        # 전투 진입 노드
        combat_entry = {
            "title": f"전투: {template.name}",
            "description": f"{template.name}과(와)의 전투가 시작되었다. {template.description}",
        }
        self.combat_parent_id = self.graph.add_scene(
            combat_entry, self.current_node_id, "전투 돌입", node_type="combat"
        )

        return {
            "enemy": {
                "name": template.name,
                "description": template.description,
                "hp": engine.enemy.hp,
                "max_hp": engine.enemy.max_hp,
            },
            "player": {
                "hp": engine.player.hp,
                "max_hp": engine.player.max_hp,
                "attack": engine.player.attack,
                "defense": engine.player.defense,
            },
            "available_items": list(engine._player_items),
        }

    def combat_action(self, action: str, item_name: str = "") -> dict:
        """전투 행동 실행."""
        if not self.active_combat:
            return {"error": "활성 전투 없음"}

        engine = self.active_combat
        result = engine.execute_round(action, item_name)

        # 그래프 기록
        self.combat_parent_id = self.graph.add_combat_round(
            result.combat_log, self.combat_parent_id, result.round_number
        )

        fled = action == "flee" and result.player_action.success
        combat_over = engine.is_over or fled

        response = {
            "round": result.round_number,
            "player_action": {
                "type": result.player_action.action_type,
                "detail": result.player_action.detail,
                "damage": result.player_action.damage_dealt,
                "success": result.player_action.success,
            },
            "enemy_action": {
                "type": result.enemy_action.action_type,
                "detail": result.enemy_action.detail,
                "damage": result.enemy_action.damage_dealt,
            },
            "player_hp": result.player_hp,
            "player_max_hp": result.player_max_hp,
            "enemy_hp": result.enemy_hp,
            "enemy_max_hp": result.enemy_max_hp,
            "combat_over": combat_over,
        }

        if combat_over:
            combat_result = engine.get_result(fled=fled)
            finalize = self._finalize_combat(combat_result)
            response["result"] = finalize

        return response

    def _finalize_combat(self, combat_result) -> dict:
        """전투 종료 처리."""
        template = self.active_combat_template
        outcome = combat_result.outcome

        loot = []
        if outcome == "victory":
            self.world_state.entities[template.name] = "처치됨"
            if template.loot:
                loot = list(template.loot)
                combat_result.loot = loot
                for item in loot:
                    self.world_state.collections.setdefault("inventory", []).append(item)
            if "health" in self.world_state.gauges:
                self.world_state.gauges["health"] = min(1.0, self.world_state.gauges["health"] + 0.1)

        elif outcome == "defeat":
            if "corruption" in self.world_state.gauges:
                self.world_state.gauges["corruption"] = min(1.0, self.world_state.gauges["corruption"] + 0.15)
            if "health" in self.world_state.gauges:
                self.world_state.gauges["health"] = max(0.1, self.world_state.gauges["health"] - 0.3)

        elif outcome == "flee":
            if "health" in self.world_state.gauges:
                self.world_state.gauges["health"] = max(0.1, self.world_state.gauges["health"] - 0.1)

        # 그래프 + 메모리
        result_id = self.graph.add_combat_result(
            combat_result.to_graph_summary(), self.combat_parent_id, outcome
        )
        self.memory.add_memory(sanitize_for_memory(combat_result.to_graph_summary()))
        self.npc_manager.record_scene_event(f"[전투] {combat_result.to_graph_summary()}", self.current_stage)

        self.current_node_id = result_id
        self.active_combat = None
        self.active_combat_template = None

        return {
            "outcome": outcome,
            "rounds": len(combat_result.rounds),
            "damage_dealt": combat_result.total_damage_dealt,
            "damage_taken": combat_result.total_damage_taken,
            "loot": loot,
            "world_state": self._get_state_snapshot(),
        }

    def _handle_npc_action(self, npc, action: str, detail: str) -> dict | None:
        """NPC 행동 처리. 결과를 dict로 반환."""
        if action == "give_item" and detail:
            self.world_state.collections.setdefault("inventory", []).append(detail)
            return {"type": "give_item", "item": detail}
        elif action == "give_quest" and detail:
            self.world_state.collections.setdefault("unresolved_hooks", []).append(detail)
            return {"type": "give_quest", "quest": detail}
        elif action == "reveal_info" and detail:
            self.memory.add_memory(sanitize_for_memory(f"[{npc.profile.name}] {detail}"))
            return {"type": "reveal_info", "info": detail}
        elif action == "refuse":
            return {"type": "refuse"}
        elif action == "attack":
            self.world_state.entities[npc.profile.name] = "적대"
            return {"type": "attack"}
        return None

    def _detect_stage(self, node_data: dict):
        """씬에서 스테이지 감지."""
        title = node_data.get("title", "")
        desc = node_data.get("description", "")
        for npc in self.npc_manager.get_all_npcs().values():
            stage = npc.profile.stage
            if stage in title or stage in desc:
                self.current_stage = stage
                return

    def _get_state_snapshot(self) -> dict:
        """현재 월드 스테이트 스냅샷."""
        return {
            "gauges": dict(self.world_state.gauges),
            "entities": dict(self.world_state.entities),
            "properties": dict(self.world_state.properties),
            "collections": {k: list(v) for k, v in self.world_state.collections.items()},
            "gauge_labels": {
                name: self.world_state._gauge_schema[name].get("label", name)
                for name in self.world_state.gauges
            },
        }


class SessionManager:
    """다중 세션 관리."""

    def __init__(self):
        self._sessions: dict[str, WebGameSession] = {}

    def create_session(self, theme_name: str) -> WebGameSession:
        """새 게임 세션 생성."""
        session_id = uuid.uuid4().hex[:12]
        theme = load_theme(theme_name)

        lore_dir = Path(theme.get("lore_dir", "lore_documents"))
        memory = LoreMemory(lore_dir)
        chain = build_story_chain()
        graph = StoryGraph()

        schema = theme.get("world_state_schema", {})
        world_state = WorldState(schema)
        rule_engine = RuleEngine(world_state, graph, theme)

        npc_dialogue_chain = None
        if theme.get("npc_profiles"):
            npc_dialogue_chain = build_npc_dialogue_chain()

        npc_manager = NPCManager(theme)
        enemy_registry = EnemyRegistry(theme)
        retriever = memory.as_retriever()

        session = WebGameSession(
            session_id=session_id,
            theme=theme,
            memory=memory,
            chain=chain,
            npc_dialogue_chain=npc_dialogue_chain,
            graph=graph,
            world_state=world_state,
            rule_engine=rule_engine,
            npc_manager=npc_manager,
            enemy_registry=enemy_registry,
            _retriever=retriever,
        )

        # 시작 노드
        initial_prompt = theme["initial_prompt"]
        session.current_node_id = graph.add_start_node(initial_prompt)

        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> WebGameSession | None:
        return self._sessions.get(session_id)

    def delete_session(self, session_id: str):
        self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())
