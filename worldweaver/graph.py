import uuid
from pathlib import Path

import networkx as nx


class StoryGraph:
    """NetworkX DiGraph 기반 스토리 분기 그래프 관리."""

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

    def add_scene(self, node_data: dict, parent_id: str, choice_text: str) -> str:
        """씬 노드를 추가하고 부모와 엣지로 연결. 생성된 노드 ID를 반환."""
        node_id = f"{node_data['title']}_{uuid.uuid4().hex[:6]}"
        flat = self._flatten(node_data)
        self._graph.add_node(node_id, **flat)

        if parent_id != node_id:
            self._graph.add_edge(parent_id, node_id, choice_text=choice_text)

        return node_id

    def add_future_choices(self, parent_id: str, choices: list[dict]):
        """각 선택지를 미래 노드를 향한 엣지로 추가."""
        for choice in choices:
            future_id = f"future_{uuid.uuid4().hex[:8]}"
            self._graph.add_edge(parent_id, future_id, **choice)

    def save(self, path: Path):
        """그래프를 GraphML 파일로 저장."""
        nx.write_graphml(self._graph, str(path))
        print(
            f"그래프가 '{path}' 파일로 저장되었습니다. "
            f"노드 {self.node_count}개, 엣지 {self.edge_count}개"
        )

    # ── 이력 조회 메서드 (RuleEngine에서 사용) ──

    def get_path(self) -> list[str]:
        """시작 노드부터 현재까지 실제 진행된 씬 노드 ID 목록을 반환."""
        scene_nodes = [
            n for n in self._graph.nodes
            if not n.startswith("future_") and "title" in self._graph.nodes[n]
        ]
        return scene_nodes

    def get_depth(self) -> int:
        """현재 스토리 진행 깊이 (실제 씬 노드 수)."""
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

    def has_visited_location(self, location: str) -> bool:
        """특정 지역이 이전 씬 제목/설명에 등장한 적 있는지 확인."""
        for node_id in self.get_path():
            node = self._graph.nodes[node_id]
            title = node.get("title", "")
            desc = node.get("description", "")
            if location in title or location in desc:
                return True
        return False

    @staticmethod
    def _flatten(data: dict) -> dict:
        """중첩된 features/choices를 GraphML 호환 평탄 구조로 변환."""
        flat = data.copy()

        if "features" in flat and isinstance(flat["features"], dict):
            for key, value in flat["features"].items():
                flat[f"features_{key}"] = str(value)
            del flat["features"]

        if "choices" in flat:
            del flat["choices"]

        return flat
