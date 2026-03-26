"""웹 게임 세션 관리자.

동시 다중 세션을 관리하며, 각 세션은 독립된 GameSession을 가진다.
CLI의 GameSession을 웹 API에서 사용할 수 있도록 래핑한다.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from worldweaver.chain import build_ending_chain, build_npc_dialogue_chain, build_story_chain
from worldweaver.i18n import t
from worldweaver.combat import CombatEngine, EnemyRegistry
from worldweaver.item_graph import ItemGraph
from worldweaver.ending import (
    EndingEvaluator, GameOverEvaluator,
    build_ending_prompt_context, build_game_over_prompt_context,
)
from worldweaver.judgment import JudgmentEngine, build_judgment_prompt_section
from worldweaver.save_load import serialize_session, save_to_json_string, load_from_dict
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
from worldweaver.translate import ThemeTranslator
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
    item_graph: ItemGraph = field(default=None, repr=False)
    _retriever: object = field(default=None, repr=False)
    language: str = "ko"
    translator: ThemeTranslator = field(default=None, repr=False)
    current_stage: str = "default"
    current_node_id: str = ""
    last_choices: list[dict] = field(default_factory=list)
    visited_stages: set[str] = field(default_factory=set)  # 방문한 스테이지
    scene_count: int = 0
    active_enemies: list[str] = field(default_factory=list)  # 현재 씬에 감지된 적 이름 (등록된 정확한 이름)
    # 전투 상태
    active_combat: CombatEngine | None = field(default=None, repr=False)
    active_combat_template: object | None = field(default=None, repr=False)
    combat_parent_id: str = ""
    _narrative_context: dict = field(default_factory=dict)  # 서사 컨텍스트 (로드 시 복원)
    _last_auto_save: dict = field(default_factory=dict, repr=False)  # 자동저장 데이터
    _last_scene: dict | None = field(default=None, repr=False)  # 마지막 씬 데이터 (세이브용)

    def generate_scene(self, prompt: str, risky_choice: dict | None = None) -> dict:
        """씬을 생성하고 결과를 반환.

        Args:
            prompt: 씬 생성 프롬프트
            risky_choice: risky=True인 선택지를 선택한 경우 해당 선택지 dict
        """
        # 입력 필터
        injections = detect_injection(prompt)
        if injections:
            prompt = sanitize_input(prompt)

        # risky 선택지 판정: 그래프 가중치 기반
        judgment_section = ""
        judgment_result = None
        if risky_choice:
            engine = JudgmentEngine(
                self.world_state, self.graph, self.npc_manager, self.item_graph,
                lang=self.language,
            )
            scene_context = ""
            recent = self.graph.get_recent_scenes_summary(1)
            if recent:
                scene_context = f"{recent[0]['title']} {recent[0]['description']}"

            judgment_result = engine.judge(risky_choice.get("text", ""), scene_context)
            judgment_section = build_judgment_prompt_section(judgment_result, lang=self.language)

            # 실패 시 health 감소 (서사 외적 패널티)
            if not judgment_result.success and "health" in self.world_state.gauges:
                self.world_state.gauges["health"] = max(
                    0.1, self.world_state.gauges["health"] - 0.1
                )

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

        # 판정 결과를 directives에 추가
        if judgment_section:
            directives_text += "\n" + judgment_section

        # 서사 컨텍스트 주입 (로드 후 첫 씬 등에서 톤 일관성 유지)
        if self._narrative_context:
            nc = self._narrative_context
            style_text = "\n### Narrative Style (maintain this tone) ###\n"
            if nc.get("style_hints"):
                style_text += f"Style: {', '.join(nc['style_hints'])}\n"
            if nc.get("mood_history"):
                recent_moods = nc["mood_history"][-5:]
                style_text += f"Recent mood flow: {' → '.join(recent_moods)}\n"
            if nc.get("story_summary"):
                style_text += "Story so far:\n"
                for s in nc["story_summary"][-5:]:
                    style_text += f"  - {s}\n"
            directives_text += style_text
            # 한 번 주입 후 초기화 (이후는 자연스럽게 이어짐)
            self._narrative_context = {}

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
        choice_text = t(self.language, "story_progress")
        parent_id = self.current_node_id or self.graph.add_start_node(prompt, lang=self.language)
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

        # 칭호 평가 (씬마다)
        if self.item_graph:
            self.item_graph.evaluate_titles(
                self.world_state.collections.get("inventory", []),
                self.world_state,
            )

        # LLM이 만든 선택지에서 combat 타입 제거 (서버가 직접 주입)
        choices = [
            c for c in node_data.get("choices", [])
            if c.get("choice_type", "story") != "combat"
        ]

        # LLM이 생성한 dialogue 선택지의 npc_name을 원본 이름으로 매핑
        # (LLM이 번역된 이름 "에코"를 넣을 수 있으므로 원본 "Echo"로 변환)
        all_npcs = self.npc_manager.get_all_npcs()
        npc_name_map = {}  # 번역명 → 원본명
        for orig_name in all_npcs:
            translated = self.translator.tr(orig_name, f"npc.{orig_name}.name")
            npc_name_map[translated.lower()] = orig_name
            npc_name_map[orig_name.lower()] = orig_name
        for c in choices:
            if c.get("choice_type") == "dialogue" and c.get("npc_name"):
                key = c["npc_name"].lower().strip()
                if key in npc_name_map:
                    c["npc_name"] = npc_name_map[key]

        # 현재 스테이지의 적 중 처치되지 않은 적을 전투 선택지로 주입
        removed = self.world_state.get_removed_entities()
        stage_enemies = self.enemy_registry.get_enemies_at_stage(self.current_stage)
        self.active_enemies = [e.name for e in stage_enemies if e.name not in removed]

        for enemy_name in self.active_enemies:
            display_name = self.translator.tr(enemy_name, f"enemies.{enemy_name}.name")
            choices.append({
                "text": t(self.language, "combat_choice", name=display_name),
                "edge_feature": "Aggressive",
                "next_node_prompt": f"Combat encounter with {enemy_name}",
                "choice_type": "combat",
                "enemy_name": enemy_name,
            })

        # NPC 선택지 주입
        triggered = self.npc_manager.get_triggered_npcs(
            self.world_state, self.graph.get_depth()
        )
        for npc, directive in triggered:
            existing = [c for c in choices if c.get("npc_name") == npc.profile.name]
            if not existing:
                npc_display = self.translator.tr(npc.profile.name, f"npc.{npc.profile.name}.name")
                role_display = self.translator.tr(npc.profile.role, f"npc.{npc.profile.name}.role")
                choices.append({
                    "text": t(self.language, "npc_talk", name=npc_display, role=role_display),
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
                {
                    "name": self.translator.tr(n.profile.name, f"npc.{n.profile.name}.name"),
                    "role": self.translator.tr(n.profile.role, f"npc.{n.profile.name}.role"),
                    "disposition": n.disposition_label,
                }
                for n in npcs_here
            ],
            "scene_count": self.scene_count,
            "quests": self._get_quests_snapshot(),
            "ending_available": self.check_ending_available(),
            "titles": self.get_titles_snapshot(),
            "map": self.get_map_data(),
        }

        # 마지막 씬 저장 (세이브/로드 복��용)
        self._last_scene = response

        # 게임오버 체크
        game_over_info = self.check_game_over()
        if game_over_info:
            response["game_over"] = game_over_info

        # 자동저장 (매 씬마다, 게임오버가 아닐 때)
        if not game_over_info:
            try:
                self._last_auto_save = serialize_session(self)
            except Exception:
                pass

    def _resolve_npc_name(self, name: str) -> str:
        """NPC 이름을 원본 이름으로 해석. 모든 언어의 번역명/대소문자 변형도 매칭."""
        # 직접 매칭
        if self.npc_manager.get_npc(name):
            return name

        name_lower = name.lower().strip()

        # 모든 NPC에 대해 원본 이름 + 모든 언어 번역명 매칭
        translations = self.theme.get("translations", {})
        for orig_name in self.npc_manager.get_all_npcs():
            # 원본 이름 매칭
            if orig_name.lower() == name_lower:
                return orig_name

            # 현재 언어 번역 매칭
            translated = self.translator.tr(orig_name, f"npc.{orig_name}.name")
            if translated.lower() == name_lower:
                return orig_name

            # 모든 언어 번역 매칭 (en, ja 등)
            for lang_code, fields in translations.items():
                tr_name = fields.get(f"npc.{orig_name}.name", "")
                if tr_name and tr_name.lower() == name_lower:
                    return orig_name

        return name  # 매핑 실패 시 원본 반환

    def start_dialogue(self, npc_name: str, directive: str = "") -> dict:
        """NPC가 먼저 말을 거는 대화 시작. directive는 트리거 조건의 지시사항."""
        npc_name = self._resolve_npc_name(npc_name)
        npc = self.npc_manager.get_npc(npc_name)
        if not npc or not self.npc_dialogue_chain:
            return {"error": t(self.language, "npc_not_found", name=npc_name)}

        dialogue_history = npc.get_dialogue_history(self.current_stage)
        history_text = "\n".join(m["content"] for m in dialogue_history) if dialogue_history else t(self.language, "first_dialogue")

        # NPC가 먼저 말을 걸도록 player_input에 상황 설명을 넣음
        _greeting_prompt = {
            "ko": "(플레이어가 다가옵니다. NPC로서 먼저 말을 걸어 대화를 시작하세요.)",
            "en": "(The player approaches. As the NPC, initiate the conversation.)",
            "ja": "(プレイヤーが近づいてきます。NPCとして先に話しかけてください。)",
        }
        greeting_input = _greeting_prompt.get(self.language, _greeting_prompt["en"])
        if directive:
            greeting_input += f"\n상황: {directive}"

        chain_input = {
            "npc_context": npc.to_prompt_context(),
            "world_state": self.world_state.to_prompt_string(),
            "dialogue_history": history_text,
            "player_input": greeting_input,
        }

        try:
            result = self.npc_dialogue_chain.invoke(chain_input)
        except Exception as e:
            return {"error": str(e)}

        # 호감도
        delta = max(-0.2, min(0.2, result.get("disposition_delta", 0.0)))
        if delta != 0.0:
            npc.disposition += delta

        # 인사말 기억 기록
        npc.record_dialogue("(접근)", result["response"], self.current_stage, disposition_delta=delta)

        # 호감도 동기화
        self.world_state.entities[npc.profile.name] = npc.disposition_label

        tr = self.translator
        return {
            "npc_name": tr.tr(npc.profile.name, f"npc.{npc.profile.name}.name"),
            "npc_key": npc.profile.name,  # 원본 이름 (API 호출용)
            "role": tr.tr(npc.profile.role, f"npc.{npc.profile.name}.role"),
            "greeting": result["response"],
            "disposition": npc.disposition,
            "disposition_label": npc.disposition_label,
        }

    def process_dialogue(self, npc_name: str, player_input: str) -> dict:
        """NPC 대화 처리."""
        npc_name = self._resolve_npc_name(npc_name)
        npc = self.npc_manager.get_npc(npc_name)
        if not npc or not self.npc_dialogue_chain:
            return {"error": t(self.language, "npc_not_found", name=npc_name)}

        injections = detect_injection(player_input)
        if injections:
            player_input = sanitize_input(player_input)

        # 대화 내용으로 잊혀진 기억 복원 시도
        recovered = npc.recover_memory(player_input)

        dialogue_history = npc.get_dialogue_history(self.current_stage)
        history_text = "\n".join(m["content"] for m in dialogue_history) if dialogue_history else t(self.language, "first_dialogue")

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
            "quests": self._get_quests_snapshot(),
        }

    def start_combat(self, enemy_name: str) -> dict:
        """전투 시작. active_enemies에서 등록된 정확한 이름으로 참조."""
        template = self.enemy_registry.get_enemy(enemy_name)
        if not template:
            return {"error": f"Enemy '{enemy_name}' not found"}

        engine = CombatEngine.from_template(template, self.world_state, self.item_graph, lang=self.language)
        self.active_combat = engine
        self.active_combat_template = template
        self.combat_parent_id = self.current_node_id

        # 전투 진입 노드
        combat_entry = {
            "title": t(self.language, "combat_title", name=template.name),
            "description": t(self.language, "combat_desc", name=template.name, desc=template.description),
        }
        self.combat_parent_id = self.graph.add_scene(
            combat_entry, self.current_node_id, t(self.language, "combat_enter"), node_type="combat"
        )

        return {
            "enemy": {
                "name": self.translator.tr(template.name, f"enemies.{template.name}.name"),
                "description": self.translator.tr(template.description, f"enemies.{template.name}.description"),
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
            return {"error": t(self.language, "no_active_combat")}

        engine = self.active_combat
        result = engine.execute_round(action, item_name)

        # 매 라운드마다 health 게이지 동기화
        if "health" in self.world_state.gauges and engine.player.max_hp > 0:
            self.world_state.gauges["health"] = round(
                engine.player.hp / engine.player.max_hp, 2
            )

        # 그래프 기록
        self.combat_parent_id = self.graph.add_combat_round(
            result.combat_log, self.combat_parent_id, result.round_number,
            lang=self.language,
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
            "world_state": self._get_state_snapshot(),
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
            self.world_state.entities[template.name] = t(self.language, "entity_defeated")
            if template.loot:
                loot = list(template.loot)
                combat_result.loot = loot
                for item in loot:
                    self.world_state.collections.setdefault("inventory", []).append(item)
                    # ItemGraph에 아이템 등록 (출처: 적 처치)
                    if self.item_graph:
                        self.item_graph.add_item(item, "enemy_loot", template.name)
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
            combat_result.to_graph_summary(), self.combat_parent_id, outcome,
            lang=self.language,
        )
        self.memory.add_memory(sanitize_for_memory(combat_result.to_graph_summary()))
        self.npc_manager.record_scene_event(f"[전투] {combat_result.to_graph_summary()}", self.current_stage)

        self.current_node_id = result_id
        self.active_combat = None
        self.active_combat_template = None

        # 전리품 이름 번역
        enemy_name = template.name if template else ""
        translated_loot = [
            self.translator.tr(item, f"enemies.{enemy_name}.loot.{item}")
            for item in loot
        ]

        finalize_result = {
            "outcome": outcome,
            "rounds": len(combat_result.rounds),
            "damage_dealt": combat_result.total_damage_dealt,
            "damage_taken": combat_result.total_damage_taken,
            "loot": translated_loot,
            "world_state": self._get_state_snapshot(),
        }

        # 전투 후 게임오버 체크
        game_over_info = self.check_game_over()
        if game_over_info:
            finalize_result["game_over"] = game_over_info

        return finalize_result

    def _handle_npc_action(self, npc, action: str, detail: str) -> dict | None:
        """NPC 행동 처리. 결과를 dict로 반환."""
        if action == "give_item" and detail:
            self.world_state.collections.setdefault("inventory", []).append(detail)
            if self.item_graph:
                self.item_graph.add_item(detail, "npc_gift", npc.profile.name)
            return {"type": "give_item", "item": detail}
        elif action == "give_quest" and detail:
            self.world_state.collections.setdefault("unresolved_hooks", []).append(detail)
            # NPC 메모리에 퀘스트 노드 기록 → 엣지 마모/복원 추적 대상
            npc.record_memory("quest", detail, self.current_stage)
            return {"type": "give_quest", "quest": detail}
        elif action == "reveal_info" and detail:
            self.memory.add_memory(sanitize_for_memory(f"[{npc.profile.name}] {detail}"))
            return {"type": "reveal_info", "info": detail}
        elif action == "refuse":
            return {"type": "refuse"}
        elif action == "attack":
            self.world_state.entities[npc.profile.name] = t(self.language, "entity_hostile")
            return {"type": "attack"}
        return None

    @staticmethod
    def _enemy_mentioned(enemy_name: str, scene_text_lower: str) -> bool:
        """적 이름의 핵심 단어가 씬 텍스트에 언급되었는지 (유연한 매칭)."""
        import re
        words = re.findall(r"[a-zA-Z\u3040-\u9fff\uac00-\ud7a3]+", enemy_name.lower())
        # 3글자 이상 단어만, 관사 제외
        keywords = [w for w in words if len(w) > 2 and w not in ("the", "of", "and")]
        if not keywords:
            return False

        # 키워드 중 절반 이상 매칭되면 감지 (완전 매칭보다 유연)
        matched = sum(1 for kw in keywords if kw in scene_text_lower)
        return matched >= max(1, len(keywords) // 2)

    def _detect_enemies_in_scene(self, scene_text: str) -> list[str]:
        """씬 텍스트에서 등록된 적 이름을 감지. 처치된 적은 제외."""
        scene_lower = scene_text.lower()
        detected = []
        removed = self.world_state.get_removed_entities()

        for name in self.enemy_registry.get_all_enemy_names():
            # 이미 처치된 적은 제외
            if name in removed:
                continue
            # 적 이름의 핵심 단어가 씬 텍스트에 포함되어 있는지 검사
            # "Medusa's Statue" → ["medusa", "statue"] 둘 다 포함 시 매칭
            import re
            words = re.findall(r"[a-zA-Z\u3040-\u9fff\uac00-\ud7a3]+", name.lower())
            keywords = [w for w in words if len(w) > 2 and w not in ("the", "of")]
            if not keywords:
                continue

            def _kw_in_text(kw: str, text: str) -> bool:
                """키워드가 텍스트에 포함되는지 (복수형/변형 허용)."""
                if kw in text:
                    return True
                # 복수형: harpy → harpies, statue → statues
                if kw + "s" in text or kw + "es" in text:
                    return True
                if kw.endswith("y") and kw[:-1] + "ies" in text:
                    return True
                return False

            if all(_kw_in_text(kw, scene_lower) for kw in keywords):
                detected.append(name)

        return detected

    def _detect_stage(self, node_data: dict):
        """씬에서 스테이지 감지. 테마 stages의 다국어 키워드로 매칭."""
        scene_text = f"{node_data.get('title', '')} {node_data.get('description', '')}".lower()
        stages = self.theme.get("stages", {})

        best_stage = None
        best_score = 0

        for stage_name, stage_cfg in stages.items():
            keywords = stage_cfg.get("keywords", [])
            score = sum(1 for kw in keywords if kw.lower() in scene_text)
            if score > best_score:
                best_score = score
                best_stage = stage_name

        if best_stage and best_score > 0:
            if best_stage != self.current_stage:
                print(f"(Stage: {self.current_stage} → {best_stage})", flush=True)
            self.current_stage = best_stage

    # ── 게임오버 ──

    def check_game_over(self) -> dict | None:
        """그래프 기반 게임오버 조건 체크."""
        evaluator = GameOverEvaluator(
            self.theme, self.world_state, self.graph, self.npc_manager,
            lang=self.language,
        )
        result = evaluator.evaluate()
        if not result:
            return None
        return {
            "game_over_id": result.game_over_id,
            "cause": result.cause,
            "factors": result.factors,
        }

    def generate_game_over(self) -> dict:
        """게임오버 씬을 LLM으로 생성."""
        evaluator = GameOverEvaluator(
            self.theme, self.world_state, self.graph, self.npc_manager,
            lang=self.language,
        )
        game_over = evaluator.evaluate()
        if not game_over:
            return {"error": t(self.language, "gameover_not_met")}

        context = build_game_over_prompt_context(
            game_over, self.graph, self.world_state, self.npc_manager,
            lang=self.language,
        )

        ending_chain = build_ending_chain(self.language)
        try:
            result = ending_chain.invoke(context)
        except Exception as e:
            return {"error": t(self.language, "gameover_gen_fail")}

        return {
            "game_over_id": game_over.game_over_id,
            "cause": game_over.cause,
            "title": result.get("title", ""),
            "epilogue": result.get("epilogue", ""),
            "final_line": result.get("final_line", ""),
            "tone": result.get("tone", "tragic"),
            "factors": game_over.factors,
        }

    # ── 세이브/로드 ──

    def save_game(self) -> str:
        """게임 상태를 JSON 문자열로 직렬화."""
        return save_to_json_string(self)

    def load_game(self, save_data: dict) -> None:
        """JSON dict에서 게임 상태를 복원."""
        load_from_dict(save_data, self)

    # ── 월드맵/스테이지 시스템 ──

    def _check_stage_unlock(self, stage_name: str) -> bool:
        """스테이지 해금 조건을 검사."""
        stages = self.theme.get("stages", {})
        stage_cfg = stages.get(stage_name, {})
        unlock = stage_cfg.get("unlock", {})

        if not unlock:
            return True  # 조건 없음 → 항상 해금

        # 최소 깊이
        if "min_depth" in unlock:
            if self.graph.get_story_depth() < unlock["min_depth"]:
                return False

        # 필수 아이템
        if "required_item" in unlock:
            inventory = self.world_state.collections.get("inventory", [])
            if unlock["required_item"] not in inventory:
                return False

        # 게이지 조건
        for gauge_name, rule in unlock.get("gauges", {}).items():
            if gauge_name not in self.world_state.gauges:
                return False
            import operator as op
            ops = {">=": op.ge, ">": op.gt, "<=": op.le, "<": op.lt}
            op_func = ops.get(rule.get("op", ">="))
            if op_func and not op_func(self.world_state.gauges[gauge_name], rule["value"]):
                return False

        return True

    def get_map_data(self) -> dict:
        """월드맵 데이터를 생성.

        각 스테이지의 상태(해금/방문/현재), 연결, NPC/적 정보를 포함.
        """
        stages = self.theme.get("stages", {})
        tr = self.translator
        removed = self.world_state.get_removed_entities()

        stage_list = []
        for name, cfg in stages.items():
            unlocked = self._check_stage_unlock(name)
            visited = name in self.visited_stages
            is_current = name == self.current_stage

            # NPC 목록
            npcs_here = self.npc_manager.get_npcs_at_stage(name)
            npc_names = [
                tr.tr(n.profile.name, f"npc.{n.profile.name}.name")
                for n in npcs_here
            ]

            # 미처치 적 목록
            stage_enemies = self.enemy_registry.get_enemies_at_stage(name)
            alive_enemies = [
                tr.tr(e.name, f"enemies.{e.name}.name")
                for e in stage_enemies if e.name not in removed
            ]

            # 해금 조건 힌트
            unlock_hint = ""
            if not unlocked:
                unlock = cfg.get("unlock", {})
                if "min_depth" in unlock:
                    unlock_hint = f"depth >= {unlock['min_depth']}"
                elif "required_item" in unlock:
                    unlock_hint = f"item: {unlock['required_item']}"
                elif "gauges" in unlock:
                    for g, r in unlock["gauges"].items():
                        unlock_hint = f"{g} {r.get('op', '>=')} {r['value']}"
                        break

            stage_list.append({
                "name": name,
                "display_name": tr.tr(name, f"stages.{name}"),
                "description": cfg.get("description", ""),
                "layer": cfg.get("layer", 1),
                "connects_to": cfg.get("connects_to", []),
                "unlocked": unlocked,
                "visited": visited,
                "is_current": is_current,
                "npcs": npc_names,
                "enemies": alive_enemies,
                "unlock_hint": unlock_hint,
            })

        return {
            "current_stage": self.current_stage,
            "stages": stage_list,
        }

    def travel_to_stage(self, stage_name: str) -> dict:
        """스테이지 이동. 해금 확인 후 이동 씬을 생성."""
        stages = self.theme.get("stages", {})
        if stage_name not in stages:
            return {"error": t(self.language, "stage_not_found", name=stage_name)}

        if not self._check_stage_unlock(stage_name):
            return {"error": t(self.language, "stage_locked")}

        # 현재 스테이지와 연결되어 있는지 확인
        current_cfg = stages.get(self.current_stage, {})
        connects = current_cfg.get("connects_to", [])
        if stage_name not in connects and stage_name != self.current_stage:
            return {"error": t(self.language, "stage_no_path")}

        old_stage = self.current_stage
        self.current_stage = stage_name
        self.visited_stages.add(stage_name)

        # 이동 씬 생성 프롬프트
        stage_cfg = stages[stage_name]
        stage_desc = stage_cfg.get("description", "")
        travel_prompt = (
            f"The player travels from {old_stage} to {stage_name}. "
            f"{stage_desc} "
            f"Describe the journey and arrival at this new location. "
            f"Set the atmosphere for this area."
        )

        return self.generate_scene(travel_prompt)

    # ── 아이템/칭호 시스템 ──

    def investigate_item(self, item_name: str) -> dict | None:
        """아이템을 조사하여 히든 효과를 발견."""
        if not self.item_graph:
            return None
        result = self.item_graph.investigate_item(item_name)
        if result:
            # 히든 발견 후 칭호 체크
            new_titles = self.item_graph.evaluate_titles(
                self.world_state.collections.get("inventory", []),
                self.world_state,
            )
            if new_titles:
                result["new_titles"] = [
                    {"id": t["id"], "name": t["name"], "description": t.get("description", ""),
                     "bonus": t.get("bonus", {})}
                    for t in new_titles
                ]
        return result

    def get_item_info(self, item_name: str) -> dict | None:
        """아이템 상세 정보."""
        if not self.item_graph:
            return None
        return self.item_graph.get_item_info(item_name)

    def get_titles_snapshot(self) -> list[dict]:
        """현재 활성 칭호 목록."""
        if not self.item_graph:
            return []
        return [
            {"id": t["id"], "name": t["name"], "description": t.get("description", ""),
             "bonus": t.get("bonus", {})}
            for t in self.item_graph.get_active_titles()
        ]

    # ── 엔딩 시스템 ──

    def check_ending(self) -> dict | None:
        """엔딩 조건 충족 여부를 확인. 가능하면 엔딩 정보를 반환."""
        evaluator = EndingEvaluator(
            self.theme, self.world_state, self.graph, self.npc_manager
        )
        result = evaluator.evaluate()
        if not result:
            return None

        return {
            "ending_id": result.ending_id,
            "ending_type": result.ending_type,
            "prompt_hint": result.prompt_hint,
            "conditions_met": result.conditions_met,
        }

    def check_ending_available(self) -> bool:
        """엔딩 도달 가능 여부 (UI에서 엔딩 버튼 표시용)."""
        evaluator = EndingEvaluator(
            self.theme, self.world_state, self.graph, self.npc_manager
        )
        return evaluator.evaluate() is not None

    def generate_ending(self) -> dict:
        """엔딩 에필로그를 LLM으로 생성.

        1. 엔딩 조건 판정
        2. 스토리 그래프에서 플레이 요약 추출
        3. NPC 관계 + 퀘스트 상태 종합
        4. 엔딩 프롬프트로 LLM 에필로그 생성
        """
        evaluator = EndingEvaluator(
            self.theme, self.world_state, self.graph, self.npc_manager
        )
        ending = evaluator.evaluate()
        if not ending:
            return {"error": t(self.language, "ending_not_met")}

        # 엔딩 프롬프트 컨텍스트 구성
        context = build_ending_prompt_context(
            ending, self.graph, self.world_state, self.npc_manager,
            lang=self.language,
        )

        # 엔딩 체인 빌드 및 실행
        ending_chain = build_ending_chain(self.language)
        try:
            result = ending_chain.invoke(context)
        except Exception as e:
            return {"error": t(self.language, "ending_gen_fail")}

        return {
            "ending_id": ending.ending_id,
            "ending_type": ending.ending_type,
            "title": result.get("title", ""),
            "epilogue": result.get("epilogue", ""),
            "final_line": result.get("final_line", ""),
            "tone": result.get("tone", ""),
            "conditions_met": ending.conditions_met,
            "world_state": self._get_state_snapshot(),
            "quests": self._get_quests_snapshot(),
        }

    def _get_quests_snapshot(self) -> list[dict]:
        """모든 NPC의 퀘스트 상태를 집계하여 반환.

        퀘스트 상태는 NPC 메모리 그래프의 엣지 연결 상태로 결정:
          - active: 엣지 건강 → NPC가 퀘스트 맥락을 온전히 기억
          - fading: 엣지 마모 중 → NPC가 점차 잊어가는 중
          - lost: 엣지 모두 끊어짐 → NPC가 맥락을 완전히 잃음
          - completed: 수동 완료 처리됨
        """
        tr = self.translator
        quests = self.npc_manager.get_all_quests()
        return [
            {
                "id": q["id"],
                "content": q["content"],
                "npc": tr.tr(q["npc"], f"npc.{q['npc']}.name"),
                "npc_key": q["npc"],  # 원본 이름 (API 호출용)
                "status": q["status"],
                "stage": q.get("stage", ""),
                "edge_count": q.get("edge_count", 0),
            }
            for q in quests
        ]

    def _get_state_snapshot(self) -> dict:
        """현재 월드 스테이트 스냅샷 (라벨 번역 포함)."""
        tr = self.translator
        return {
            "gauges": dict(self.world_state.gauges),
            "entities": dict(self.world_state.entities),
            "properties": dict(self.world_state.properties),
            "collections": {k: list(v) for k, v in self.world_state.collections.items()},
            "gauge_labels": {
                name: tr.tr(
                    self.world_state._gauge_schema[name].get("label", name),
                    f"gauges.{name}.label",
                )
                for name in self.world_state.gauges
            },
            "property_labels": {
                name: tr.tr(
                    self.world_state._property_schema[name].get("label", name),
                    f"properties.{name}.label",
                )
                for name in self.world_state.properties
            },
            "collection_labels": {
                name: tr.tr(
                    self.world_state._collection_schema[name].get("label", name),
                    f"collections.{name}.label",
                )
                for name in self.world_state.collections
            },
        }


class SessionManager:
    """다중 세션 관리 — 세션 만료, 동시 세션 제한, FAISS 메모리 공유."""

    MAX_SESSIONS = 20          # 동시 최대 세션 수
    SESSION_TTL = 30 * 60      # 세션 만료 시간 (초) — 30분

    def __init__(self):
        self._sessions: dict[str, WebGameSession] = {}
        self._session_times: dict[str, float] = {}       # session_id → 마지막 활동 시각
        self._session_ips: dict[str, str] = {}            # session_id → 생성자 IP
        self._lore_cache: dict[str, LoreMemory] = {}     # theme_name → 공유 LoreMemory
        self._cleanup_lock = threading.Lock()

    # ── 세션 만료 정리 ──

    def _cleanup_expired(self):
        """만료된 세션을 제거."""
        import time
        now = time.time()
        expired = [
            sid for sid, ts in self._session_times.items()
            if now - ts > self.SESSION_TTL
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._session_times.pop(sid, None)
            self._session_ips.pop(sid, None)

    def _touch(self, session_id: str):
        """세션 활동 시각 갱신."""
        import time
        self._session_times[session_id] = time.time()

    # ── FAISS 메모리 공유 ──

    def _get_shared_memory(self, theme_name: str, lore_dir: Path) -> LoreMemory:
        """동일 테마의 LoreMemory를 캐시에서 반환. 없으면 새로 생성."""
        if theme_name not in self._lore_cache:
            self._lore_cache[theme_name] = LoreMemory(lore_dir)
        return self._lore_cache[theme_name]

    # ── 세션 생성 ──

    def create_session(self, theme_name: str, language: str = "ko", client_ip: str = "") -> WebGameSession:
        """새 게임 세션 생성. 동시 세션 제한 및 만료 정리 포함."""
        with self._cleanup_lock:
            self._cleanup_expired()

            if len(self._sessions) >= self.MAX_SESSIONS:
                raise RuntimeError(t(language, "err_rate_limit"))

        session_id = uuid.uuid4().hex[:12]
        theme = load_theme(theme_name)

        lore_dir = Path(theme.get("lore_dir", "lore_documents"))
        memory = self._get_shared_memory(theme_name, lore_dir)
        chain = build_story_chain(language)
        graph = StoryGraph()

        schema = theme.get("world_state_schema", {})
        world_state = WorldState(schema, lang=language)
        rule_engine = RuleEngine(world_state, graph, theme)

        npc_dialogue_chain = None
        if theme.get("npc_profiles"):
            npc_dialogue_chain = build_npc_dialogue_chain(language)

        npc_manager = NPCManager(theme, lang=language)
        enemy_registry = EnemyRegistry(theme)
        item_graph = ItemGraph(theme)
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
            item_graph=item_graph,
            _retriever=retriever,
            language=language,
            translator=ThemeTranslator(theme, language),
        )

        # 시작 스테이지 설정 (is_default: true인 스테이지)
        stages = theme.get("stages", {})
        for stage_name, stage_cfg in stages.items():
            if stage_cfg.get("is_default", False):
                session.current_stage = stage_name
                break
        # default 스테이지가 없으면 첫 번째 스테이지 사용
        if session.current_stage == "default" and stages:
            session.current_stage = next(iter(stages))

        # 시작 스테이지를 visited에 추가
        session.visited_stages.add(session.current_stage)

        # 시작 노드
        initial_prompt = theme["initial_prompt"]
        session.current_node_id = graph.add_start_node(initial_prompt, lang=language)

        self._sessions[session_id] = session
        self._session_ips[session_id] = client_ip
        self._touch(session_id)
        return session

    def get_session(self, session_id: str, client_ip: str = "") -> WebGameSession | None:
        self._cleanup_expired()
        session = self._sessions.get(session_id)
        if not session:
            return None
        # IP 바인딩 검증: 세션 생성자와 다른 IP면 거부
        if client_ip and self._session_ips.get(session_id) and client_ip != self._session_ips[session_id]:
            return None
        self._touch(session_id)
        return session

    def delete_session(self, session_id: str):
        self._sessions.pop(session_id, None)
        self._session_times.pop(session_id, None)
        self._session_ips.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        self._cleanup_expired()
        return list(self._sessions.keys())

    def active_count(self) -> int:
        """현재 활성 세션 수."""
        self._cleanup_expired()
        return len(self._sessions)
