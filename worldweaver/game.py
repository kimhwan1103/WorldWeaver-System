from worldweaver.config import GRAPH_OUTPUT, MAX_SCENES
from worldweaver.graph import StoryGraph
from worldweaver.persona import choose_by_persona
from worldweaver.rag import LoreMemory
from worldweaver.rule_engine import RuleEngine
from worldweaver.world_state import WorldState


class GameSession:
    """스토리 생성 게임 세션. 테마 스키마 기반 범용 엔진."""

    def __init__(self, memory: LoreMemory, chain, graph: StoryGraph, theme: dict):
        self.memory = memory
        self.chain = chain
        self.graph = graph
        self.theme = theme

        schema = theme.get("world_state_schema", {})
        self.world_state = WorldState(schema)
        self.rule_engine = RuleEngine(self.world_state, self.graph, theme)
        self._retriever = memory.as_retriever()

    def run_interactive(self, initial_prompt: str):
        """사용자가 직접 선택지를 고르는 인터랙티브 모드."""
        current_id = self.graph.add_start_node(initial_prompt)
        prompt = initial_prompt

        while True:
            print("\n========================================================")
            print("장면 생성 중 ....")

            node_data = self._generate_with_validation(prompt)
            if node_data is None:
                break

            current_id = self._process_scene(node_data, current_id, "이야기 진행")

            choices = node_data["choices"]
            if not choices:
                print("선택지가 없어 생성을 중단합니다.")
                break

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
            prompt = selected["next_node_prompt"]

            self.graph.save(GRAPH_OUTPUT)

    def run_auto(self, initial_prompt: str, persona: str = "hero", max_scenes: int = MAX_SCENES):
        """페르소나가 자동으로 선택하는 데모 모드."""
        current_id = self.graph.add_start_node(initial_prompt)
        prompt = initial_prompt

        for i in range(max_scenes):
            print("\n========================================================")
            print(f"장면 생성 중 .... [{i + 1}/{max_scenes}]")

            node_data = self._generate_with_validation(prompt)
            if node_data is None:
                break

            current_id = self._process_scene(node_data, current_id, "이야기 진행")

            choices = node_data["choices"]
            if not choices:
                print("선택지가 없어 생성을 중단합니다.")
                break

            self._print_choices(choices)

            personas = self.theme.get("personas", {})
            selected = choose_by_persona(choices, persona, personas)
            print(f"\n(시스템: 페르소나 선택 -> '{selected['text']}')")

            prompt = selected["next_node_prompt"]

            self.graph.save(GRAPH_OUTPUT)

    # ── 핵심: 생성 → 검증 → 재생성 루프 ──

    def _generate_with_validation(self, prompt: str) -> dict | None:
        """씬을 생성하고 룰엔진으로 검증. 위반 시 재생성."""
        # 사전 지시사항 생성
        directives = self.rule_engine.pre_generation_directives()
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

        # state_change 스키마 (테마에 따라 동적 생성)
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

            # 사후 검증
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

        # 그래프에 기록
        new_id = self.graph.add_scene(node_data, parent_id, choice_text)

        # RAG 메모리에 누적
        memory_text = f"[{node_data['title']}] {node_data['description']}"
        self.memory.add_memory(memory_text)
        print("\n(시스템: 새로운 기억이 저장되었음)")

        # 월드 스테이트 업데이트
        state_change = node_data.get("state_change", {})
        if state_change:
            self.world_state.apply_changes(state_change)
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
