from pathlib import Path

import networkx as nx

from worldweaver.combat import CombatEngine, EnemyRegistry
from worldweaver.config import GRAPH_OUTPUT, MAX_SCENES
from worldweaver.content_filter import (
    TopicFilter,
    detect_injection,
    get_npc_deflection,
    sanitize_for_memory,
    sanitize_input,
    validate_state_change,
)
from worldweaver.graph import StoryGraph
from worldweaver.npc_memory import NPCManager
from worldweaver.persona import choose_by_persona
from worldweaver.rag import LoreMemory
from worldweaver.rule_engine import RuleEngine
from worldweaver.world_state import WorldState


class GameSession:
    """스토리 생성 게임 세션. 테마 스키마 기반 범용 엔진."""

    def __init__(self, memory: LoreMemory, chain, graph: StoryGraph, theme: dict,
                 npc_dialogue_chain=None):
        self.memory = memory
        self.chain = chain
        self.npc_dialogue_chain = npc_dialogue_chain
        self.graph = graph
        self.theme = theme

        schema = theme.get("world_state_schema", {})
        self.world_state = WorldState(schema)
        self.rule_engine = RuleEngine(self.world_state, self.graph, theme)
        self._retriever = memory.as_retriever()

        # 지식 그래프 기반 주제 필터 초기화
        self._topic_filter = self._load_topic_filter(theme)

        # NPC 매니저 초기화
        self.npc_manager = NPCManager(theme)
        self._current_stage = "default"  # 현재 스테이지 추적

        # 전투 시스템 초기화
        self.enemy_registry = EnemyRegistry(theme)

    def _load_topic_filter(self, theme: dict) -> TopicFilter:
        """테마의 지식 그래프를 로드하여 TopicFilter를 생성."""
        lore_dir = Path(theme.get("lore_dir", "lore_documents"))
        # 테마별 lore_dir 내부 → 이전 호환(parent) 순으로 탐색
        kg_path = lore_dir / "knowledge_graph.graphml"
        if not kg_path.exists():
            kg_path = lore_dir.parent / "knowledge_graph.graphml"

        if kg_path.exists():
            try:
                kg = nx.read_graphml(str(kg_path))
                print(f"(시스템: 지식 그래프 로드 — 노드 {kg.number_of_nodes()}개)")
                return TopicFilter(kg)
            except Exception:
                pass

        print("(시스템: 지식 그래프 없음 — 주제 필터 비활성)")
        return TopicFilter(None)

    def run_interactive(self, initial_prompt: str):
        """사용자가 직접 선택지를 고르는 인터랙티브 모드."""
        current_id = self.graph.add_start_node(initial_prompt)
        prompt = initial_prompt
        last_choices = None  # 세계관 이탈 시 이전 선택지 재사용

        while True:
            print("\n========================================================")
            print("장면 생성 중 ....")

            node_data = self._generate_with_validation(prompt)
            if node_data is None:
                break

            choices = node_data["choices"]

            # NPC 주도 이벤트 선택지 주입
            choices = self._inject_npc_choices(choices)

            # 세계관 이탈 NPC 반응 (choices가 빈 리스트) → 대사만 출력하고 이전 선택지 재사용
            if not choices and last_choices:
                print(f"\n{node_data['description']}")
                choices = last_choices
                self._print_choices(choices)
            elif not choices:
                print("선택지가 없어 생성을 중단합니다.")
                break
            else:
                current_id = self._process_scene(node_data, current_id, "이야기 진행")
                last_choices = choices
                self._print_choices(choices)

            user_input = input("\n당신의 선택은? (숫자 입력, 종료: exit): ").strip()
            if user_input.lower() == "exit":
                print("게임을 종료합니다.")
                break

            try:
                choice_index = int(user_input) - 1
                selected = choices[choice_index]
            except (ValueError, IndexError):
                print("잘못된 입력입니다. 다시 선택해주세요.")
                continue

            print(f"\n(선택: '{selected['text']}')")

            # NPC 대화 선택지인 경우 대화 모드 진입
            if selected.get("choice_type") == "dialogue" and selected.get("npc_name"):
                self._run_npc_dialogue(selected["npc_name"])
                prompt = last_choices[0]["next_node_prompt"] if last_choices else prompt
            # 전투 선택지인 경우 전투 모드 진입
            elif selected.get("choice_type") == "combat" and selected.get("enemy_name"):
                combat_result = self._run_combat(selected["enemy_name"], current_id)
                if combat_result:
                    current_id = combat_result
                prompt = selected["next_node_prompt"]
            else:
                prompt = selected["next_node_prompt"]

            self.graph.save(GRAPH_OUTPUT)

    def run_auto(self, initial_prompt: str, persona: str = "hero", max_scenes: int = MAX_SCENES):
        """페르소나가 자동으로 선택하는 데모 모드."""
        current_id = self.graph.add_start_node(initial_prompt)
        prompt = initial_prompt
        last_choices = None

        for i in range(max_scenes):
            print("\n========================================================")
            print(f"장면 생성 중 .... [{i + 1}/{max_scenes}]")

            node_data = self._generate_with_validation(prompt)
            if node_data is None:
                break

            choices = node_data["choices"]

            # NPC 주도 이벤트 선택지 주입
            choices = self._inject_npc_choices(choices)

            if not choices and last_choices:
                print(f"\n{node_data['description']}")
                choices = last_choices
            elif not choices:
                print("선택지가 없어 생성을 중단합니다.")
                break
            else:
                current_id = self._process_scene(node_data, current_id, "이야기 진행")
                last_choices = choices

            self._print_choices(choices)

            # 자동 모드에서는 dialogue 타입 선택지를 건너뛰고 story/combat 타입만 선택
            action_choices = [c for c in choices if c.get("choice_type", "story") in ("story", "combat")]
            if not action_choices:
                action_choices = choices
            story_choices = action_choices

            personas = self.theme.get("personas", {})
            selected = choose_by_persona(story_choices, persona, personas)
            print(f"\n(시스템: 페르소나 선택 -> '{selected['text']}')")

            # 자동 모드 전투 처리
            if selected.get("choice_type") == "combat" and selected.get("enemy_name"):
                combat_result = self._run_combat_auto(selected["enemy_name"], current_id)
                if combat_result:
                    current_id = combat_result

            prompt = selected["next_node_prompt"]

            self.graph.save(GRAPH_OUTPUT)

    # ── 전투 모드 ──

    def _run_combat(self, enemy_name: str, parent_id: str) -> str | None:
        """인터랙티브 전투 모드. 전투 라운드를 그래프에 기록."""
        template = self.enemy_registry.get_enemy(enemy_name)
        if not template:
            print(f"(시스템: '{enemy_name}' 적을 찾을 수 없습니다)")
            return None

        engine = CombatEngine.from_template(template, self.world_state)

        print(f"\n{'='*50}")
        print(f"  ⚔ 전투 시작: {template.name}")
        if template.description:
            print(f"  {template.description}")
        print(f"\n  {engine.player.name} {engine.player.hp_bar}")
        print(f"  {engine.enemy.name}  {engine.enemy.hp_bar}")
        print(f"{'='*50}")

        # 전투 진입 노드
        combat_entry = {
            "title": f"전투: {template.name}",
            "description": f"{template.name}과(와)의 전투가 시작되었다. {template.description}",
        }
        current_combat_id = self.graph.add_scene(
            combat_entry, parent_id, "전투 돌입", node_type="combat"
        )

        fled = False
        while not engine.is_over:
            print(f"\n--- 행동 선택 ---")
            print(f"  1. ⚔ 공격")
            print(f"  2. 🛡 방어")
            print(f"  3. 💥 강공격 (높은 데미지, 실패 확률)")
            if engine._player_items:
                print(f"  4. 🧪 아이템 사용 ({', '.join(engine._player_items[:3])})")
            print(f"  5. 🏃 도주")

            user_input = input("\n행동 선택 (숫자): ").strip()

            action_map = {"1": "attack", "2": "defend", "3": "skill", "4": "item", "5": "flee"}
            action = action_map.get(user_input, "attack")

            item_name = ""
            if action == "item":
                if engine._player_items:
                    item_name = engine._player_items[0]
                else:
                    print("사용할 아이템이 없습니다.")
                    continue

            result = engine.execute_round(action, item_name)
            print(f"\n{result.combat_log}")

            # 라운드를 그래프에 기록
            current_combat_id = self.graph.add_combat_round(
                result.combat_log, current_combat_id, result.round_number
            )

            # 도주 성공 체크
            if action == "flee" and result.player_action.success:
                fled = True
                break

        combat_result = engine.get_result(fled=fled)
        return self._finalize_combat(combat_result, template, current_combat_id)

    def _run_combat_auto(self, enemy_name: str, parent_id: str) -> str | None:
        """자동 모드 전투. AI가 행동을 선택."""
        template = self.enemy_registry.get_enemy(enemy_name)
        if not template:
            return None

        engine = CombatEngine.from_template(template, self.world_state)

        print(f"\n⚔ 자동 전투: {template.name}")
        print(f"  {engine.player.name} {engine.player.hp_bar}")
        print(f"  {engine.enemy.name}  {engine.enemy.hp_bar}")

        combat_entry = {
            "title": f"전투: {template.name}",
            "description": f"{template.name}과(와)의 전투가 시작되었다.",
        }
        current_combat_id = self.graph.add_scene(
            combat_entry, parent_id, "전투 돌입", node_type="combat"
        )

        import random
        fled = False
        while not engine.is_over:
            # 자동 행동 결정
            hp_ratio = engine.player.hp / engine.player.max_hp
            if hp_ratio < 0.2:
                action = random.choice(["flee", "item", "defend"])
            elif hp_ratio < 0.5:
                action = random.choice(["attack", "defend", "skill"])
            else:
                action = random.choice(["attack", "attack", "skill"])

            item_name = engine._player_items[0] if action == "item" and engine._player_items else ""
            if action == "item" and not item_name:
                action = "defend"

            result = engine.execute_round(action, item_name)
            print(f"  라운드 {result.round_number}: "
                  f"{result.player_action.detail} | {result.enemy_action.detail}")

            current_combat_id = self.graph.add_combat_round(
                result.combat_log, current_combat_id, result.round_number
            )

            if action == "flee" and result.player_action.success:
                fled = True
                break

        combat_result = engine.get_result(fled=fled)
        return self._finalize_combat(combat_result, template, current_combat_id)

    def _finalize_combat(self, combat_result, template, current_combat_id: str) -> str:
        """전투 종료 처리: 결과 출력, 보상/페널티, 그래프/메모리 기록."""
        outcome_text = {"victory": "승리!", "defeat": "패배...", "flee": "도주!"}
        print(f"\n{'='*50}")
        print(f"  ⚔ 전투 종료: {outcome_text.get(combat_result.outcome, '')}")
        print(f"  총 {len(combat_result.rounds)}라운드")
        print(f"  가한 피해: {combat_result.total_damage_dealt} | 받은 피해: {combat_result.total_damage_taken}")

        if combat_result.outcome == "victory":
            # 적 처치 → 엔티티 상태 반영
            self.world_state.entities[template.name] = "처치됨"

            # 전리품
            if template.loot:
                combat_result.loot = template.loot
                for item in template.loot:
                    self.world_state.collections.setdefault("inventory", []).append(item)
                print(f"  획득: {', '.join(template.loot)}")

            # HP 반영 (전투 후 잔여 HP 비율을 게이지에 반영)
            if "health" in self.world_state.gauges:
                # 승리 시 체력 일부 회복
                self.world_state.gauges["health"] = min(1.0, self.world_state.gauges["health"] + 0.1)

        elif combat_result.outcome == "defeat":
            # 패배 시 타락 게이지 상승
            if "corruption" in self.world_state.gauges:
                self.world_state.gauges["corruption"] = min(
                    1.0, self.world_state.gauges["corruption"] + 0.15
                )
            if "health" in self.world_state.gauges:
                self.world_state.gauges["health"] = max(0.1, self.world_state.gauges["health"] - 0.3)
            print("  타락의 기운이 강해집니다...")

        elif combat_result.outcome == "flee":
            # 도주 시 소량 페널티
            if "health" in self.world_state.gauges:
                self.world_state.gauges["health"] = max(0.1, self.world_state.gauges["health"] - 0.1)

        print(f"{'='*50}")
        print(self.world_state.to_summary_string())

        # 그래프에 전투 결과 노드 기록
        result_id = self.graph.add_combat_result(
            combat_result.to_graph_summary(),
            current_combat_id,
            combat_result.outcome,
        )

        # RAG 메모리에 전투 기록 저장
        memory_text = combat_result.to_graph_summary()
        clean = sanitize_for_memory(memory_text)
        self.memory.add_memory(clean)

        # 해당 스테이지 NPC들에게 전투 사건 기록
        self.npc_manager.record_scene_event(
            f"[전투] {memory_text}",
            self._current_stage,
        )

        return result_id

    # ── NPC 대화 모드 ──

    def _run_npc_dialogue(self, npc_name: str):
        """NPC와의 1:1 대화 모드를 실행."""
        npc = self.npc_manager.get_npc(npc_name)
        if not npc:
            print(f"(시스템: '{npc_name}' NPC를 찾을 수 없습니다)")
            return

        if not self.npc_dialogue_chain:
            print(f"(시스템: NPC 대화 체인이 초기화되지 않았습니다)")
            return

        print(f"\n{'='*50}")
        print(f"  💬 {npc.profile.name}({npc.profile.role})과(와) 대화를 시작합니다")
        print(f"  호감도: {npc.disposition_label} ({npc.disposition:.1f})")
        print(f"  (대화를 끝내려면 '떠나기'를 입력하세요)")
        print(f"{'='*50}")

        # NPC가 먼저 인사
        greeting = self._get_npc_greeting(npc)
        if greeting:
            print(f"\n[{npc.profile.name}] {greeting}")

        while True:
            player_input = input(f"\n[당신] > ").strip()
            if not player_input or player_input == "떠나기":
                print(f"\n{npc.profile.name}과(와)의 대화를 마칩니다.")
                break

            # 인젝션 필터
            injections = detect_injection(player_input)
            if injections:
                player_input = sanitize_input(player_input)

            # 대화 기록 조회
            dialogue_history = npc.get_dialogue_history(self._current_stage)
            history_text = ""
            if dialogue_history:
                history_text = "\n".join(m["content"] for m in dialogue_history)
            else:
                history_text = "(첫 대화입니다)"

            # NPC 대화 체인 호출
            chain_input = {
                "npc_context": npc.to_prompt_context(),
                "world_state": self.world_state.to_prompt_string(),
                "dialogue_history": history_text,
                "player_input": player_input,
            }

            try:
                result = self.npc_dialogue_chain.invoke(chain_input)
            except Exception as e:
                print(f"(시스템: NPC 대화 생성 오류 — {e})")
                continue

            # NPC 응답 출력
            print(f"\n[{npc.profile.name}] {result['response']}")

            # 호감도 변화
            delta = result.get("disposition_delta", 0.0)
            delta = max(-0.2, min(0.2, delta))  # 클램핑
            if delta != 0.0:
                old_label = npc.disposition_label
                npc.disposition += delta
                new_label = npc.disposition_label
                if old_label != new_label:
                    print(f"  (호감도 변화: {old_label} → {new_label})")

            # NPC 행동 처리
            action = result.get("action")
            action_detail = result.get("action_detail", "")
            if action:
                self._handle_npc_action(npc, action, action_detail)

            # 기억 기록
            memory_note = result.get("memory_note", "")
            npc.record_dialogue(
                player_input,
                result["response"],
                self._current_stage,
                disposition_delta=delta,
            )
            if memory_note:
                npc.record_memory(
                    "observation",
                    memory_note,
                    self._current_stage,
                )

            # 대화 종료 판단
            if result.get("should_end", False):
                print(f"\n(대화가 자연스럽게 마무리됩니다)")
                break

        # 대화 종료 후 호감도를 월드 스테이트에 반영
        self._sync_npc_disposition(npc)

    def _get_npc_greeting(self, npc) -> str | None:
        """NPC가 먼저 건네는 인사말을 LLM으로 생성."""
        if not self.npc_dialogue_chain:
            return None

        dialogue_history = npc.get_dialogue_history(self._current_stage)
        history_text = "\n".join(m["content"] for m in dialogue_history) if dialogue_history else "(첫 대화)"

        chain_input = {
            "npc_context": npc.to_prompt_context(),
            "world_state": self.world_state.to_prompt_string(),
            "dialogue_history": history_text,
            "player_input": "(플레이어가 다가옵니다. NPC로서 먼저 말을 걸어 대화를 시작하세요.)",
        }

        try:
            result = self.npc_dialogue_chain.invoke(chain_input)
            greeting = result.get("response", "")
            if greeting:
                npc.record_dialogue("(접근)", greeting, self._current_stage)
            return greeting
        except Exception:
            return None

    def _handle_npc_action(self, npc, action: str, detail: str):
        """NPC 행동을 월드 스테이트에 반영."""
        if action == "give_item" and detail:
            inventory = self.world_state.collections.get("inventory", [])
            if detail not in inventory:
                self.world_state.collections.setdefault("inventory", []).append(detail)
                print(f"  ✦ {npc.profile.name}이(가) '{detail}'을(를) 건네줍니다!")

        elif action == "give_quest" and detail:
            hooks = self.world_state.collections.get("unresolved_hooks", [])
            if detail not in hooks:
                self.world_state.collections.setdefault("unresolved_hooks", []).append(detail)
                print(f"  ✦ 새로운 퀘스트: {detail}")

        elif action == "reveal_info" and detail:
            print(f"  ✦ {npc.profile.name}이(가) 비밀을 알려줍니다: {detail}")
            # RAG 메모리에 저장하여 향후 스토리에 반영
            clean = sanitize_for_memory(f"[{npc.profile.name}의 정보] {detail}")
            self.memory.add_memory(clean)

        elif action == "refuse":
            print(f"  ✦ {npc.profile.name}이(가) 요청을 거절합니다.")

        elif action == "attack":
            print(f"  ✦ {npc.profile.name}이(가) 적대적으로 변합니다!")
            self.world_state.entities[npc.profile.name] = "적대"

    def _sync_npc_disposition(self, npc):
        """NPC 호감도를 월드 스테이트 엔티티에 동기화."""
        self.world_state.entities[npc.profile.name] = npc.disposition_label

    # ── NPC 주도 이벤트 선택지 주입 ──

    def _inject_npc_choices(self, choices: list[dict]) -> list[dict]:
        """NPC 주도 이벤트 조건을 검사하여 대화 선택지를 주입."""
        triggered = self.npc_manager.get_triggered_npcs(
            self.world_state,
            self.graph.get_depth(),
        )

        for npc, directive in triggered:
            # 이미 같은 NPC 대화 선택지가 있으면 건너뜀
            existing = [c for c in choices if c.get("npc_name") == npc.profile.name]
            if existing:
                continue

            choices.append({
                "text": f"💬 Talk to {npc.profile.name} ({npc.profile.role})",
                "edge_feature": "Diplomatic",
                "next_node_prompt": directive,
                "choice_type": "dialogue",
                "npc_name": npc.profile.name,
            })

        return choices

    # ── 스테이지 추적 ──

    def _detect_stage(self, node_data: dict) -> str:
        """씬 데이터에서 현재 스테이지를 추론. 테마 stages의 다국어 키워드로 매칭."""
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

        return best_stage if best_stage and best_score > 0 else self._current_stage

    # ── 핵심: 생성 → 검증 → 재생성 루프 ──

    def _generate_with_validation(self, prompt: str) -> dict | None:
        """씬을 생성하고 필터 + 룰엔진으로 검증. 위반 시 재생성."""

        # ── 입력 필터: 인젝션 패턴 탐지 + 제거 ──
        injections = detect_injection(prompt)
        if injections:
            print(f"(보안: 인젝션 패턴 {len(injections)}건 탐지 → 제거)")
            prompt = sanitize_input(prompt)

        # ── 입력 필터: 세계관 이탈 검사 → NPC 반응 반환 ──
        if self._topic_filter.is_available:
            input_check = self._topic_filter.check_input_relevance(prompt)
            if not input_check["relevant"]:
                print(f"(시스템: 세계관 이탈 입력 감지 — 관련도 {input_check['score']:.1%})")
                return get_npc_deflection()

        # 사전 지시사항 생성
        directives = self.rule_engine.pre_generation_directives()

        # NPC 주도 이벤트 지시사항 추가
        npc_triggers = self.npc_manager.get_triggered_npcs(
            self.world_state, self.graph.get_depth()
        )
        for npc, directive in npc_triggers:
            directives.append(directive)

        directives_text = ""
        if directives:
            directives_text = "\n### Mandatory Directives (MUST follow) ###\n"
            directives_text += "\n".join(f"- {d}" for d in directives)
            print(f"\n(시스템: 룰엔진 지시사항 {len(directives)}건 주입)")

        # 최근 씬 요약
        recent = self.graph.get_recent_scenes_summary(3)
        if recent:
            recent_text = "\n".join(
                f"- [{s['title']}] {s['description']}" for s in recent
            )
        else:
            recent_text = "(첫 번째 씬입니다)"

        # state_change 스키마
        state_change_schema = self.world_state.get_state_change_schema_for_prompt()

        # 체인 입력 구성
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
                print(f"스토리 생성 오류: {e}")
                return None

            # ── 출력 필터: 지식 그래프 주제 검증 ──
            if self._topic_filter.is_available:
                relevance = self._topic_filter.check_scene_relevance(node_data)
                if not relevance["relevant"]:
                    print(
                        f"(보안: 세계관 이탈 감지 — 관련도 {relevance['score']:.1%}, "
                        f"미확인 용어: {', '.join(relevance['unknown_terms'][:5])})"
                    )
                    if attempt < self.rule_engine.MAX_RETRY:
                        chain_input["request"] = prompt + "\n\n[주의: 반드시 제공된 세계관 내에서만 스토리를 작성하세요.]"
                        continue

            # 룰엔진 사후 검증
            result = self.rule_engine.validate_scene(node_data)

            if result.warnings:
                for w in result.warnings:
                    print(f"(시스템 경고: {w})")

            if result.passed:
                return node_data

            # 위반 발생 → 재생성
            print(f"\n(시스템: 규칙 위반 감지 — 재생성 {attempt + 1}/{self.rule_engine.MAX_RETRY})")
            for v in result.violations:
                print(f"  위반: {v}")

            if attempt < self.rule_engine.MAX_RETRY:
                retry_prompt = self.rule_engine.build_retry_prompt(prompt, result)
                chain_input["request"] = retry_prompt
            else:
                print("(시스템: 최대 재시도 초과. 경고와 함께 현재 씬을 사용합니다.)")
                return node_data

        return None

    def _process_scene(self, node_data: dict, parent_id: str, choice_text: str) -> str:
        """씬을 출력하고 그래프/메모리/월드스테이트에 반영. 새 노드 ID를 반환."""
        print(f"\n[ {node_data['title']} ]")
        print(node_data["description"])

        # 스테이지 감지 및 업데이트
        detected_stage = self._detect_stage(node_data)
        if detected_stage != self._current_stage:
            self._current_stage = detected_stage
            print(f"(시스템: 스테이지 변경 → {self._current_stage})")

        # NPC 기억 마모 + 사건 기록
        self.npc_manager.advance_all_scenes()
        self.npc_manager.record_scene_event(
            f"[씬: {node_data['title']}] {node_data['description'][:200]}",
            self._current_stage,
        )

        # NPC 상태 표시
        npcs_here = self.npc_manager.get_npcs_at_stage(self._current_stage)
        if npcs_here:
            print(f"\n(이 장소의 NPC:)")
            print(self.npc_manager.to_summary_string(self._current_stage))

        # 그래프에 기록
        new_id = self.graph.add_scene(node_data, parent_id, choice_text)

        # ── RAG 메모리 저장 전 sanitize ──
        memory_text = f"[{node_data['title']}] {node_data['description']}"
        clean_memory = sanitize_for_memory(memory_text)
        self.memory.add_memory(clean_memory)
        print("\n(시스템: 새로운 기억이 저장되었음)")

        # ── state_change 검증 후 적용 ──
        state_change = node_data.get("state_change", {})
        if state_change:
            validated_change = validate_state_change(state_change, self.world_state)
            self.world_state.apply_changes(validated_change)
            print("(시스템: 월드 스테이트 업데이트됨)")
            print(self.world_state.to_summary_string())

        # 미래 선택지 엣지 추가
        self.graph.add_future_choices(new_id, node_data["choices"])

        return new_id

    @staticmethod
    def _print_choices(choices: list[dict]):
        """선택지를 번호와 함께 출력."""
        print("\n--- 선택지 ---")
        for i, choice in enumerate(choices):
            print(f"{i + 1}. {choice['text']}")
