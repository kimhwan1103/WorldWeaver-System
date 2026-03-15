"""NPC 메모리 그래프 — 방향성 그래프 기반 NPC 기억 시스템.

각 NPC는 독립된 DiGraph를 가지며, 스테이지(장소/맥락)별로 격리된
기억을 유지한다. NPC는 자신이 존재했던 스테이지에서 일어난 사건만
기억하므로 게임의 몰입감이 유지된다.

그래프 구조:
  노드 = 기억 단위 (대화, 사건, 감정 변화)
  엣지 = 인과/시간 관계 (caused_by, follows, triggers)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx


# ── 기억 노드 타입 ──

MEMORY_TYPES = {"dialogue", "event", "emotion", "quest", "observation"}


@dataclass
class NPCProfile:
    """테마 JSON에서 로드되는 NPC 프로필."""

    name: str
    personality: str  # 성격 설명 (프롬프트에 주입)
    tone: str  # 말투 스타일
    role: str  # 역할 (동맹, 상인, 현자 등)
    stage: str  # 소속 스테이지 (격리 기준)
    initial_disposition: float = 0.5  # 초기 호감도 (0.0~1.0)
    trigger_conditions: list[dict] = field(default_factory=list)  # NPC 주도 이벤트 조건


class NPCMemoryGraph:
    """단일 NPC의 기억을 관리하는 방향성 그래프.

    스테이지별 격리: NPC는 자신의 stage에 해당하는 기억만 조회 가능.
    다른 스테이지의 사건은 그래프에 기록되지 않는다.
    """

    def __init__(self, profile: NPCProfile):
        self.profile = profile
        self._graph = nx.DiGraph()
        self._disposition: float = profile.initial_disposition  # 현재 호감도
        self._current_stage: str = profile.stage

    @property
    def disposition(self) -> float:
        return self._disposition

    @disposition.setter
    def disposition(self, value: float):
        self._disposition = max(0.0, min(1.0, value))

    @property
    def disposition_label(self) -> str:
        """호감도를 한글 라벨로 변환."""
        if self._disposition >= 0.8:
            return "깊은 신뢰"
        if self._disposition >= 0.6:
            return "우호적"
        if self._disposition >= 0.4:
            return "중립"
        if self._disposition >= 0.2:
            return "경계"
        return "적대적"

    # ── 기억 기록 ──

    def record_memory(
        self,
        memory_type: str,
        content: str,
        stage: str,
        *,
        caused_by: str | None = None,
        disposition_delta: float = 0.0,
    ) -> str:
        """새 기억 노드를 추가하고, 선택적으로 인과 엣지를 연결.

        Args:
            memory_type: dialogue / event / emotion / quest / observation
            content: 기억 내용 텍스트
            stage: 이 기억이 발생한 스테이지
            caused_by: 원인이 되는 기억 노드 ID (선택)
            disposition_delta: 호감도 변화량

        Returns:
            생성된 기억 노드 ID
        """
        if stage != self._current_stage:
            return ""  # 다른 스테이지 사건은 기록하지 않음

        node_id = f"{self.profile.name}_{memory_type}_{uuid.uuid4().hex[:8]}"

        self._graph.add_node(
            node_id,
            type=memory_type,
            content=content,
            stage=stage,
            disposition_at=self._disposition,
        )

        # 인과 관계 엣지
        if caused_by and caused_by in self._graph:
            self._graph.add_edge(caused_by, node_id, relation="caused_by")

        # 시간순 엣지: 같은 스테이지의 마지막 기억과 연결
        prev = self._get_latest_memory(stage)
        if prev and prev != node_id:
            self._graph.add_edge(prev, node_id, relation="follows")

        # 호감도 반영
        if disposition_delta != 0.0:
            self.disposition += disposition_delta

        return node_id

    def record_dialogue(
        self,
        player_input: str,
        npc_response: str,
        stage: str,
        *,
        disposition_delta: float = 0.0,
    ) -> str:
        """대화 기억을 기록. 플레이어 입력과 NPC 응답을 함께 저장."""
        content = f"[플레이어] {player_input}\n[{self.profile.name}] {npc_response}"
        return self.record_memory(
            "dialogue",
            content,
            stage,
            disposition_delta=disposition_delta,
        )

    # ── 기억 조회 (스테이지 격리) ──

    def get_memories(self, stage: str | None = None, limit: int = 10) -> list[dict]:
        """특정 스테이지의 최근 기억을 시간순으로 반환.

        stage가 None이면 현재 스테이지 기준.
        NPC 소속 스테이지가 아닌 기억은 반환하지 않음.
        """
        target_stage = stage or self._current_stage

        # 스테이지 격리: NPC 소속 스테이지만 조회 가능
        if target_stage != self._current_stage:
            return []

        memories = []
        for node_id in self._graph.nodes:
            node = self._graph.nodes[node_id]
            if node.get("stage") == target_stage:
                memories.append({"id": node_id, **node})

        # 시간순 정렬 (그래프 추가 순서 유지)
        return memories[-limit:]

    def get_dialogue_history(self, stage: str | None = None, limit: int = 5) -> list[dict]:
        """대화 기억만 필터링하여 반환."""
        memories = self.get_memories(stage, limit=50)
        dialogues = [m for m in memories if m.get("type") == "dialogue"]
        return dialogues[-limit:]

    def get_memory_summary(self, stage: str | None = None) -> str:
        """프롬프트에 주입할 NPC 기억 요약 문자열."""
        memories = self.get_memories(stage, limit=5)
        if not memories:
            return f"({self.profile.name}은(는) 아직 이 장소에서의 기억이 없습니다)"

        lines = []
        for m in memories:
            mem_type = m.get("type", "unknown")
            content = m.get("content", "")
            # 대화는 축약
            if len(content) > 150:
                content = content[:150] + "..."
            lines.append(f"[{mem_type}] {content}")

        return "\n".join(lines)

    def get_related_memories(self, memory_id: str, depth: int = 2) -> list[dict]:
        """특정 기억과 인과적으로 연결된 기억들을 BFS로 탐색."""
        if memory_id not in self._graph:
            return []

        visited = set()
        queue = [(memory_id, 0)]
        related = []

        while queue:
            current, d = queue.pop(0)
            if current in visited or d > depth:
                continue
            visited.add(current)

            if current != memory_id:
                node = self._graph.nodes[current]
                related.append({"id": current, **node})

            for neighbor in self._graph.successors(current):
                queue.append((neighbor, d + 1))
            for neighbor in self._graph.predecessors(current):
                queue.append((neighbor, d + 1))

        return related

    # ── 스테이지 관리 ──

    def move_to_stage(self, new_stage: str):
        """NPC를 새 스테이지로 이동. 이전 스테이지 기억은 보존되지만 접근 불가."""
        self._current_stage = new_stage

    # ── 내부 헬퍼 ──

    def _get_latest_memory(self, stage: str) -> str | None:
        """특정 스테이지의 가장 최근 기억 노드 ID."""
        latest = None
        for node_id in self._graph.nodes:
            if self._graph.nodes[node_id].get("stage") == stage:
                latest = node_id
        return latest

    # ── 직렬화 ──

    def save(self, path: Path):
        """기억 그래프를 GraphML로 저장."""
        nx.write_graphml(self._graph, str(path))

    def to_prompt_context(self) -> str:
        """NPC 프로필 + 기억을 프롬프트 주입용 문자열로 변환."""
        lines = [
            f"### NPC 정보: {self.profile.name} ###",
            f"역할: {self.profile.role}",
            f"성격: {self.profile.personality}",
            f"말투: {self.profile.tone}",
            f"현재 호감도: {self.disposition_label} ({self._disposition:.1f})",
            "",
            "### 이 장소에서의 기억 ###",
            self.get_memory_summary(),
        ]
        return "\n".join(lines)


class NPCManager:
    """게임 세션 내 모든 NPC의 메모리 그래프를 관리."""

    def __init__(self, theme: dict):
        self._npcs: dict[str, NPCMemoryGraph] = {}
        self._load_from_theme(theme)

    def _load_from_theme(self, theme: dict):
        """테마 JSON의 npc_profiles에서 NPC를 로드."""
        profiles = theme.get("npc_profiles", [])
        for p in profiles:
            profile = NPCProfile(
                name=p["name"],
                personality=p.get("personality", "중립적인 성격"),
                tone=p.get("tone", "평범한 말투"),
                role=p.get("role", "일반"),
                stage=p.get("stage", "default"),
                initial_disposition=p.get("initial_disposition", 0.5),
                trigger_conditions=p.get("trigger_conditions", []),
            )
            self._npcs[profile.name] = NPCMemoryGraph(profile)

    def get_npc(self, name: str) -> NPCMemoryGraph | None:
        """이름으로 NPC 메모리 그래프를 조회."""
        return self._npcs.get(name)

    def get_npcs_at_stage(self, stage: str) -> list[NPCMemoryGraph]:
        """특정 스테이지에 존재하는 NPC 목록."""
        return [
            npc for npc in self._npcs.values()
            if npc._current_stage == stage
        ]

    def get_all_npcs(self) -> dict[str, NPCMemoryGraph]:
        return self._npcs

    def record_scene_event(self, event_content: str, stage: str):
        """씬에서 발생한 사건을 해당 스테이지의 모든 NPC에게 기록."""
        for npc in self.get_npcs_at_stage(stage):
            npc.record_memory("event", event_content, stage)

    def record_observation(self, content: str, stage: str):
        """관찰 기억을 해당 스테이지의 모든 NPC에게 기록."""
        for npc in self.get_npcs_at_stage(stage):
            npc.record_memory("observation", content, stage)

    def get_triggered_npcs(self, world_state, story_depth: int) -> list[tuple[NPCMemoryGraph, str]]:
        """NPC 주도 이벤트 조건을 검사하여 트리거된 NPC와 이벤트 내용을 반환.

        Returns:
            [(npc, event_directive), ...] 트리거된 NPC와 지시사항 목록
        """
        triggered = []

        for npc in self._npcs.values():
            for cond in npc.profile.trigger_conditions:
                if self._check_trigger(cond, npc, world_state, story_depth):
                    triggered.append((npc, cond["directive"]))

        return triggered

    @staticmethod
    def _check_trigger(
        condition: dict,
        npc: NPCMemoryGraph,
        world_state,
        story_depth: int,
    ) -> bool:
        """단일 트리거 조건을 검사."""
        # 최소 깊이 조건
        if "min_depth" in condition and story_depth < condition["min_depth"]:
            return False

        # 호감도 조건
        if "min_disposition" in condition and npc.disposition < condition["min_disposition"]:
            return False
        if "max_disposition" in condition and npc.disposition > condition["max_disposition"]:
            return False

        # 게이지 조건
        if "gauge" in condition:
            gauge_name = condition["gauge"]
            if gauge_name in world_state.gauges:
                import operator as op
                ops = {">=": op.ge, ">": op.gt, "<=": op.le, "<": op.lt, "==": op.eq}
                op_func = ops.get(condition.get("operator", ">="))
                if op_func and not op_func(world_state.gauges[gauge_name], condition.get("threshold", 0)):
                    return False

        # 아이템 보유 조건
        if "requires_item" in condition:
            inventory = world_state.collections.get("inventory", [])
            if condition["requires_item"] not in inventory:
                return False

        return True

    def to_summary_string(self, stage: str | None = None) -> str:
        """현재 스테이지의 NPC 상태 요약."""
        npcs = self.get_npcs_at_stage(stage) if stage else list(self._npcs.values())
        if not npcs:
            return "(이 장소에 NPC가 없습니다)"

        lines = []
        for npc in npcs:
            lines.append(
                f"  {npc.profile.name}({npc.profile.role}) — "
                f"호감도: {npc.disposition_label}"
            )
        return "\n".join(lines)
