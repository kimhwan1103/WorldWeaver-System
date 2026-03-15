from pathlib import Path

import networkx as nx

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

    def _load_topic_filter(self, theme: dict) -> TopicFilter:
        """테마의 지식 그래프를 로드하여 TopicFilter를 생성."""
        lore_dir = Path(theme.get("lore_dir", "lore_documents"))
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
                # 대화 종료 후 이전 선택지로 복귀
                prompt = last_choices[0]["next_node_prompt"] if last_choices else prompt
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

            # 자동 모드에서는 dialogue 타입 선택지를 건너뛰고 story 타입만 선택
            story_choices = [c for c in choices if c.get("choice_type", "story") == "story"]
            if not story_choices:
                story_choices = choices  # 모든 선택지가 dialogue면 그냥 선택

            personas = self.theme.get("personas", {})
            selected = choose_by_persona(story_choices, persona, personas)
            print(f"\n(시스템: 페르소나 선택 -> '{selected['text']}')")

            prompt = selected["next_node_prompt"]

            self.graph.save(GRAPH_OUTPUT)

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
                "text": f"💬 {npc.profile.name}({npc.profile.role})과(와) 대화하기",
                "edge_feature": "Diplomatic",
                "next_node_prompt": directive,
                "choice_type": "dialogue",
                "npc_name": npc.profile.name,
            })

        return choices

    # ── 스테이지 추적 ──

    def _detect_stage(self, node_data: dict) -> str:
        """씬 데이터에서 현재 스테이지(장소)를 추론."""
        title = node_data.get("title", "")
        description = node_data.get("description", "")

        # 테마의 NPC 스테이지 목록에서 매칭
        for npc in self.npc_manager.get_all_npcs().values():
            stage = npc.profile.stage
            if stage in title or stage in description:
                return stage

        return self._current_stage

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

        # 해당 스테이지의 NPC들에게 사건 기록
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
