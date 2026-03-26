import json
import uuid
from collections import deque
from pathlib import Path

import networkx as nx


class StoryGraph:
    """NetworkX DiGraph 기반 스토리 분기 그래프 관리."""

    START_NODE_ID = "시작"

    def __init__(self):
        self._graph = nx.DiGraph()

    @property
    def node_count(self) -> int:
        return len(self._graph.nodes)

    @property
    def edge_count(self) -> int:
        return len(self._graph.edges)

    def add_start_node(self, prompt: str) -> str:
        """시작 노드를 추가하고 ID를 반환."""
        node_id = "시작"
        self._graph.add_node(node_id, title="시작", prompt=prompt)
        return node_id

    def add_scene(self, node_data: dict, parent_id: str, choice_text: str,
                  node_type: str = "story") -> str:
        """씬 노드를 추가하고 부모와 엣지로 연결. 생성된 노드 ID를 반환.

        node_type: "story" (일반 씬), "combat" (전투), "dialogue" (NPC 대화)
        """
        node_id = f"{node_data['title']}_{uuid.uuid4().hex[:6]}"
        flat = self._flatten(node_data)
        flat["node_type"] = node_type
        self._graph.add_node(node_id, **flat)

        if parent_id != node_id:
            self._graph.add_edge(parent_id, node_id, choice_text=choice_text)

        return node_id

    def add_combat_round(self, combat_summary: str, parent_id: str,
                         round_number: int) -> str:
        """전투 라운드를 그래프 노드로 기록."""
        node_id = f"combat_r{round_number}_{uuid.uuid4().hex[:6]}"
        self._graph.add_node(
            node_id,
            title=f"전투 라운드 {round_number}",
            description=combat_summary,
            node_type="combat",
        )
        self._graph.add_edge(parent_id, node_id, choice_text=f"라운드 {round_number}")
        return node_id

    def add_combat_result(self, result_summary: str, parent_id: str,
                          outcome: str) -> str:
        """전투 결과를 그래프 노드로 기록."""
        outcome_text = {"victory": "승리", "defeat": "패배", "flee": "도주"}
        title = f"전투 결과: {outcome_text.get(outcome, outcome)}"
        node_id = f"{title}_{uuid.uuid4().hex[:6]}"
        self._graph.add_node(
            node_id,
            title=title,
            description=result_summary,
            node_type="combat",
        )
        self._graph.add_edge(parent_id, node_id, choice_text="전투 종료")
        return node_id

    def add_future_choices(self, parent_id: str, choices: list[dict]):
        """선택지를 부모 노드의 속성으로 저장 (유령 노드 생성 안 함)."""
        if self._graph.has_node(parent_id):
            self._graph.nodes[parent_id]["choices_json"] = json.dumps(
                choices, ensure_ascii=False
            )

    def save(self, path: Path):
        """그래프를 GraphML 파일로 저장."""
        nx.write_graphml(self._graph, str(path))
        print(
            f"그래프가 '{path}' 파일로 저장되었습니다. "
            f"노드 {self.node_count}개, 엣지 {self.edge_count}개"
        )

    # ── 이력 조회 메서드 (RuleEngine에서 사용) ──

    def get_path(self) -> list[str]:
        """BFS로 시작 노드부터 실제 진행된 노드만 추적하여 반환.

        future_ 노드(미선택 선택지)는 제외하고, 실제 플레이된
        서사 경로만 레벨 순서(깊이 순)로 반환한다.
        """
        if not self._graph.has_node(self.START_NODE_ID):
            return []

        visited = set()
        queue = deque([self.START_NODE_ID])
        path = []

        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)

            # future_ 노드는 큐에 넣지 않으므로 여기 도달하지 않지만 방어적 체크
            if node_id.startswith("future_"):
                continue

            path.append(node_id)

            # 자식 노드 중 future_가 아닌 실제 진행 노드만 큐에 추가
            for child in self._graph.successors(node_id):
                if not child.startswith("future_") and child not in visited:
                    queue.append(child)

        return path

    def get_story_depth(self) -> int:
        """서사 진행 깊이 (전투 노드 제외, 순수 스토리 씬 수)."""
        return len([
            n for n in self.get_path()
            if self._graph.nodes[n].get("node_type", "story") == "story"
        ])

    def get_depth(self) -> int:
        """현재 전체 진행 깊이 (모든 실제 노드 수)."""
        return len(self.get_path())

    def get_recent_moods(self, count: int = 3) -> list[str]:
        """최근 N개 씬의 분위기(mood) 목록."""
        path = self.get_path()
        moods = []
        for node_id in path[-count:]:
            mood = self._graph.nodes[node_id].get("features_mood", "")
            if mood:
                moods.append(mood)
        return moods

    def get_recent_scenes_summary(self, count: int = 3) -> list[dict]:
        """최근 N개 씬의 제목과 설명 요약."""
        path = self.get_path()
        summaries = []
        for node_id in path[-count:]:
            node = self._graph.nodes[node_id]
            summaries.append({
                "title": node.get("title", node_id),
                "description": node.get("description", "")[:200],
            })
        return summaries

    def get_recent_combat_summary(self, count: int = 3) -> list[dict]:
        """최근 N개 전투 결과 노드의 요약 (BFS 경로 기반)."""
        combat_nodes = [
            n for n in self.get_path()
            if self._graph.nodes[n].get("node_type") == "combat"
            and "전투 결과" in self._graph.nodes[n].get("title", "")
        ]
        summaries = []
        for node_id in combat_nodes[-count:]:
            node = self._graph.nodes[node_id]
            summaries.append({
                "title": node.get("title", ""),
                "description": node.get("description", "")[:200],
            })
        return summaries

    def has_visited_location(self, location: str) -> bool:
        """특정 지역이 이전 씬 제목/설명에 등장한 적 있는지 확인."""
        for node_id in self.get_path():
            node = self._graph.nodes[node_id]
            title = node.get("title", "")
            desc = node.get("description", "")
            if location in title or location in desc:
                return True
        return False

    # ── 엔딩용: 플레이 전체 요약 추출 ──

    def extract_play_summary(self) -> dict:
        """스토리 그래프를 순회하여 플레이 전체 요약을 추출.

        엔딩 프롬프트에 주입하여 LLM이 플레이 내용을 반영한
        에필로그를 생성할 수 있도록 한다.

        Returns:
            {
                "story_arc": [...],      # 핵심 스토리 씬 요약 (제목+설명 축약)
                "key_choices": [...],     # 플레이어가 선택한 분기점 엣지 라벨
                "combat_history": [...],  # 전투 결과 요약
                "mood_progression": [...], # 분위기 변화 흐름
                "total_scenes": int,
                "story_depth": int,
            }
        """
        path = self.get_path()

        story_arc = []
        key_choices = []
        combat_history = []
        mood_progression = []

        for i, node_id in enumerate(path):
            node = self._graph.nodes[node_id]
            node_type = node.get("node_type", "story")
            title = node.get("title", node_id)
            desc = node.get("description", "")

            # 분위기 추적
            mood = node.get("features_mood", "")
            if mood:
                mood_progression.append(mood)

            # 전투 결과
            if node_type == "combat" and "전투 결과" in title:
                combat_history.append(f"{title}: {desc[:100]}")
                continue

            # 전투 라운드는 건너뜀 (결과만 기록)
            if node_type == "combat":
                continue

            # 스토리 씬 요약
            if node_type == "story" and title != "시작":
                story_arc.append(f"[{title}] {desc[:120]}")

            # 이 노드로 진입한 선택지 (엣지 라벨)
            if i > 0:
                prev_id = path[i - 1]
                edge_data = self._graph.get_edge_data(prev_id, node_id)
                if edge_data:
                    choice_text = edge_data.get("choice_text", "")
                    if choice_text and choice_text not in ("이야기 진행", "전투 종료"):
                        key_choices.append(choice_text)

        return {
            "story_arc": story_arc,
            "key_choices": key_choices,
            "combat_history": combat_history,
            "mood_progression": mood_progression,
            "total_scenes": len(path),
            "story_depth": self.get_story_depth(),
        }

    def get_play_summary_for_prompt(self) -> str:
        """엔딩 프롬프트에 주입할 수 있는 플레이 요약 문자열."""
        summary = self.extract_play_summary()

        lines = [f"### 플레이 기록 (총 {summary['total_scenes']}씬, 서사 깊이 {summary['story_depth']}) ###"]

        if summary["story_arc"]:
            lines.append("\n## 스토리 흐름 ##")
            # 전체가 너무 길면 처음 3개 + 마지막 3개
            arc = summary["story_arc"]
            if len(arc) > 8:
                shown = arc[:3] + ["  ... (중략) ..."] + arc[-3:]
            else:
                shown = arc
            for s in shown:
                lines.append(f"  - {s}")

        if summary["key_choices"]:
            lines.append("\n## 플레이어의 주요 선택 ##")
            for c in summary["key_choices"][-6:]:
                lines.append(f"  - {c}")

        if summary["combat_history"]:
            lines.append("\n## 전투 기록 ##")
            for c in summary["combat_history"]:
                lines.append(f"  - {c}")

        if summary["mood_progression"]:
            lines.append(f"\n## 분위기 흐름 ##")
            lines.append(f"  {' → '.join(summary['mood_progression'][-8:])}")

        return "\n".join(lines)

    @staticmethod
    def _flatten(data: dict) -> dict:
        """중첩된 features/choices를 GraphML 호환 평탄 구조로 변환.

        GraphML은 str/int/float만 지원하므로, dict/list 값은
        JSON 문자열로 직렬화한다.
        """
        flat = data.copy()

        if "features" in flat and isinstance(flat["features"], dict):
            for key, value in flat["features"].items():
                flat[f"features_{key}"] = str(value)
            del flat["features"]

        if "choices" in flat:
            del flat["choices"]

        # state_change 등 남은 dict/list 값을 JSON 문자열로 변환
        for key, value in flat.items():
            if isinstance(value, (dict, list)):
                flat[key] = json.dumps(value, ensure_ascii=False)

        return flat
