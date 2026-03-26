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

# 스테이지 격리 대상: 이 타입만 스테이지가 달라도 기록/조회 차단
_STAGE_ISOLATED_TYPES = {"event", "observation"}

# pruning 보호 대상: 이 타입의 *노드*는 자동 마모되지 않음 (엣지만 마모)
_PRUNING_PROTECTED_TYPES = {"quest"}

# 기억 타입별 기본 수명 (씬 수 기준). 이 씬 수가 지나면 마모 대상이 됨
_MEMORY_LIFESPAN = {
    "dialogue": 15,     # 대화는 비교적 오래 기억
    "event": 8,         # 사건은 중간
    "observation": 5,   # 관찰은 빨리 잊음
    "emotion": 20,      # 감정은 오래 남음
    "quest": -1,        # 퀘스트 노드 자체는 영구 (-1). 엣지만 마모됨
}

# 퀘스트 엣지 마모 설정
QUEST_EDGE_LIFESPAN = 12       # 이 씬 수 이후부터 엣지 마모 시작
QUEST_EDGE_FULL_DECAY = 20     # 이 씬 수가 지나면 모든 엣지 끊어짐

# 마모된 기억의 상태
MEMORY_STATE_ACTIVE = "active"      # 정상
MEMORY_STATE_FADED = "faded"        # 흐릿함 (조회 시 축약)
MEMORY_STATE_FORGOTTEN = "forgotten"  # 잊혀짐 (조회 안 됨, 복원 가능)


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
        self._scene_counter: int = 0  # 씬 카운터 (기억 마모 기준)

    @property
    def disposition(self) -> float:
        return self._disposition

    @disposition.setter
    def disposition(self, value: float):
        self._disposition = max(0.0, min(1.0, value))

    @property
    def disposition_label(self) -> str:
        """Disposition as an English label."""
        if self._disposition >= 0.8:
            return "Deep Trust"
        if self._disposition >= 0.6:
            return "Friendly"
        if self._disposition >= 0.4:
            return "Neutral"
        if self._disposition >= 0.2:
            return "Wary"
        return "Hostile"

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
        # 스테이지 격리: event/observation만 소속 스테이지에서만 기록
        # dialogue/quest/emotion은 NPC 고유 기억이므로 항상 기록
        if memory_type in _STAGE_ISOLATED_TYPES and stage != self._current_stage:
            return ""

        node_id = f"{self.profile.name}_{memory_type}_{uuid.uuid4().hex[:8]}"

        self._graph.add_node(
            node_id,
            type=memory_type,
            content=content,
            stage=stage,
            disposition_at=self._disposition,
            created_at_scene=self._scene_counter,
            memory_state=MEMORY_STATE_ACTIVE,
            protected=memory_type in _PRUNING_PROTECTED_TYPES,
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
        """최근 기억을 시간순으로 반환.

        - forgotten 상태 기억은 제외
        - faded 상태 기억은 포함하되 content가 축약됨
        - dialogue/quest/emotion: 스테이지 무관 (NPC 고유 기억)
        - event/observation: 해당 스테이지만 (격리)
        """
        target_stage = stage or self._current_stage

        memories = []
        for node_id in self._graph.nodes:
            node = self._graph.nodes[node_id]
            state = node.get("memory_state", MEMORY_STATE_ACTIVE)

            # forgotten은 제외
            if state == MEMORY_STATE_FORGOTTEN:
                continue

            mem_type = node.get("type", "")

            if mem_type in _STAGE_ISOLATED_TYPES:
                if node.get("stage") != target_stage:
                    continue

            entry = {"id": node_id, **node}

            # faded 기억은 내용 축약
            if state == MEMORY_STATE_FADED:
                content = entry.get("content", "")
                entry["content"] = content[:60] + "... (흐릿한 기억)" if len(content) > 60 else content

            memories.append(entry)

        return memories[-limit:]

    def get_dialogue_history(self, stage: str | None = None, limit: int = 5) -> list[dict]:
        """대화 기억을 반환. forgotten 제외, faded는 축약 포함."""
        dialogues = []
        for node_id in self._graph.nodes:
            node = self._graph.nodes[node_id]
            if node.get("type") != "dialogue":
                continue

            state = node.get("memory_state", MEMORY_STATE_ACTIVE)
            if state == MEMORY_STATE_FORGOTTEN:
                continue

            entry = {"id": node_id, **node}
            if state == MEMORY_STATE_FADED:
                content = entry.get("content", "")
                entry["content"] = content[:60] + "... (흐릿한 기억)" if len(content) > 60 else content

            dialogues.append(entry)

        return dialogues[-limit:]

    def get_memory_summary(self, stage: str | None = None) -> str:
        """프롬프트에 주입할 NPC 기억 요약 문자열."""
        memories = self.get_memories(stage, limit=5)
        if not memories:
            return f"({self.profile.name}은(는) 아직 기억이 없습니다)"

        lines = []
        for m in memories:
            mem_type = m.get("type", "unknown")
            content = m.get("content", "")
            state = m.get("memory_state", MEMORY_STATE_ACTIVE)
            if len(content) > 150:
                content = content[:150] + "..."
            prefix = "🔅 " if state == MEMORY_STATE_FADED else ""
            lines.append(f"{prefix}[{mem_type}] {content}")

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

    # ── 기억 마모 (Memory Decay & Pruning) ──

    def advance_scene(self):
        """씬 카운터를 1 증가시키고 기억 마모를 실행."""
        self._scene_counter += 1
        self._decay_memories()
        self._decay_quest_edges()

    def _decay_memories(self):
        """씬 경과에 따라 기억을 마모시킨다.

        - protected(quest) 노드는 마모되지 않음 (엣지만 마모됨, _decay_quest_edges 참조)
        - 수명 초과 시: active → faded → forgotten 단계적 전환
        - faded 기억은 수명의 1.5배가 지나면 forgotten으로 전환
        """
        for node_id in list(self._graph.nodes):
            node = self._graph.nodes[node_id]

            # 보호된 기억은 건너뜀
            if node.get("protected", False):
                continue

            state = node.get("memory_state", MEMORY_STATE_ACTIVE)
            if state == MEMORY_STATE_FORGOTTEN:
                continue  # 이미 잊혀진 기억

            mem_type = node.get("type", "event")
            lifespan = _MEMORY_LIFESPAN.get(mem_type, 8)
            if lifespan < 0:
                continue  # -1 = 영구 기억

            created = node.get("created_at_scene", 0)
            age = self._scene_counter - created

            if state == MEMORY_STATE_ACTIVE and age >= lifespan:
                # active → faded
                self._graph.nodes[node_id]["memory_state"] = MEMORY_STATE_FADED

            elif state == MEMORY_STATE_FADED and age >= int(lifespan * 1.5):
                # faded → forgotten
                self._graph.nodes[node_id]["memory_state"] = MEMORY_STATE_FORGOTTEN

    def _decay_quest_edges(self):
        """퀘스트 노드의 엣지를 시간 경과에 따라 마모시킨다.

        퀘스트 노드 자체는 보존되지만, 연결된 엣지(인과/시간 관계)가
        점진적으로 끊어진다. 엣지가 모두 끊어지면 NPC는 퀘스트의
        맥락(어떤 사건에서 비롯됐는지 등)을 잃어버린다.

        엣지 마모 단계:
          1. 생성 후 QUEST_EDGE_LIFESPAN 씬 → 엣지에 decayed=True 마킹
          2. QUEST_EDGE_FULL_DECAY 씬 → 엣지 제거 (끊어짐)
        """
        quest_nodes = [
            nid for nid in self._graph.nodes
            if self._graph.nodes[nid].get("type") == "quest"
        ]

        for quest_id in quest_nodes:
            quest_created = self._graph.nodes[quest_id].get("created_at_scene", 0)
            age = self._scene_counter - quest_created

            if age < QUEST_EDGE_LIFESPAN:
                continue

            # 퀘스트에 연결된 모든 엣지 (incoming + outgoing)
            edges_to_process = (
                list(self._graph.in_edges(quest_id, data=True))
                + list(self._graph.out_edges(quest_id, data=True))
            )

            for u, v, data in edges_to_process:
                if age >= QUEST_EDGE_FULL_DECAY:
                    # 엣지 완전 제거 — 퀘스트 맥락 완전 상실
                    if self._graph.has_edge(u, v):
                        self._graph.remove_edge(u, v)
                elif not data.get("decayed", False):
                    # 엣지 마모 마킹 — 흐릿한 연결
                    self._graph.edges[u, v]["decayed"] = True

    def recover_memory(self, keyword: str) -> list[dict]:
        """대화를 통해 잊혀진 기억을 복원.

        keyword가 forgotten 기억의 content에 포함되면 해당 기억을 faded로 복원.
        퀘스트 기억이면 노드를 active로 복원하고 끊어진 엣지도 재연결한다.

        Returns:
            복원된 기억 목록
        """
        recovered = []
        for node_id in list(self._graph.nodes):
            node = self._graph.nodes[node_id]
            if node.get("memory_state") != MEMORY_STATE_FORGOTTEN:
                continue

            content = node.get("content", "")
            if keyword in content:
                # forgotten → faded로 복원 (완전 복원이 아닌 흐릿한 기억)
                self._graph.nodes[node_id]["memory_state"] = MEMORY_STATE_FADED
                # 씬 카운터 갱신 → 다시 마모 시작 시점 리셋
                self._graph.nodes[node_id]["created_at_scene"] = self._scene_counter

                # 퀘스트 기억이 복원되면 active로 복원 + 엣지 재연결
                if node.get("type") == "quest":
                    self._graph.nodes[node_id]["memory_state"] = MEMORY_STATE_ACTIVE
                    self._recover_quest_edges(node_id)

                recovered.append({"id": node_id, **self._graph.nodes[node_id]})

        # 퀘스트 노드의 엣지 복원도 시도 (키워드가 퀘스트 내용에 매칭)
        recovered_quests = self._recover_quest_edges_by_keyword(keyword)
        for q in recovered_quests:
            if q not in [r["id"] for r in recovered]:
                recovered.append({"id": q, **self._graph.nodes[q]})

        return recovered

    def _recover_quest_edges(self, quest_id: str):
        """퀘스트 노드의 끊어진 엣지를 재연결.

        같은 스테이지의 최근 기억들과 시간순(follows) 엣지를 다시 연결하고,
        씬 카운터를 리셋하여 마모 타이머를 재시작한다.
        """
        quest_node = self._graph.nodes[quest_id]
        quest_stage = quest_node.get("stage", self._current_stage)

        # 씬 카운터 리셋 → 엣지 마모 타이머 재시작
        self._graph.nodes[quest_id]["created_at_scene"] = self._scene_counter

        # 현재 연결된 엣지의 decayed 마킹 제거
        for u, v, data in list(self._graph.in_edges(quest_id, data=True)):
            if data.get("decayed"):
                self._graph.edges[u, v]["decayed"] = False
        for u, v, data in list(self._graph.out_edges(quest_id, data=True)):
            if data.get("decayed"):
                self._graph.edges[u, v]["decayed"] = False

        # 엣지가 완전히 끊어져 고립된 경우 → 최근 기억과 재연결
        has_connections = (
            self._graph.in_degree(quest_id) > 0
            or self._graph.out_degree(quest_id) > 0
        )
        if not has_connections:
            # 같은 스테이지의 가장 최근 active/faded 기억을 찾아 연결
            latest = self._get_latest_active_memory(quest_stage)
            if latest and latest != quest_id:
                self._graph.add_edge(latest, quest_id, relation="recalled_by")

    def _recover_quest_edges_by_keyword(self, keyword: str) -> list[str]:
        """키워드로 퀘스트 노드의 끊어진 엣지를 복원.

        forgotten 상태가 아닌 퀘스트 노드라도, 엣지가 끊어져 고립되었거나
        decayed 상태라면 키워드 매칭으로 엣지를 복원한다.
        """
        recovered_ids = []
        quest_nodes = [
            nid for nid in self._graph.nodes
            if self._graph.nodes[nid].get("type") == "quest"
        ]

        for quest_id in quest_nodes:
            node = self._graph.nodes[quest_id]
            content = node.get("content", "")
            if keyword not in content:
                continue

            state = node.get("memory_state", MEMORY_STATE_ACTIVE)
            if state == MEMORY_STATE_FORGOTTEN:
                continue  # forgotten은 recover_memory에서 처리

            # decayed 엣지가 있거나 고립된 경우 복원
            has_decayed = any(
                d.get("decayed") for _, _, d in self._graph.in_edges(quest_id, data=True)
            ) or any(
                d.get("decayed") for _, _, d in self._graph.out_edges(quest_id, data=True)
            )
            is_isolated = (
                self._graph.in_degree(quest_id) == 0
                and self._graph.out_degree(quest_id) == 0
            )

            if has_decayed or is_isolated:
                self._recover_quest_edges(quest_id)
                recovered_ids.append(quest_id)

        return recovered_ids

    def _get_latest_active_memory(self, stage: str) -> str | None:
        """특정 스테이지에서 가장 최근의 active/faded 기억 노드 ID."""
        latest = None
        for node_id in self._graph.nodes:
            node = self._graph.nodes[node_id]
            state = node.get("memory_state", MEMORY_STATE_ACTIVE)
            if state == MEMORY_STATE_FORGOTTEN:
                continue
            if node.get("stage") == stage:
                latest = node_id
        return latest

    # ── 퀘스트 상태 조회 ──

    def get_quest_memories(self) -> list[dict]:
        """모든 퀘스트 기억과 엣지 기반 상태를 반환.

        퀘스트 상태는 엣지 연결 상태로 판정:
          - "active": 엣지가 모두 건강 (decayed 없음, 연결 있음)
          - "fading": 일부 엣지가 decayed 마킹됨 (NPC가 맥락을 잊어가는 중)
          - "lost": 엣지가 모두 끊어짐 (NPC가 퀘스트 맥락을 완전히 잃음)
          - "completed": 퀘스트가 완료된 상태 (수동으로 마킹)
        """
        quests = []
        for node_id in self._graph.nodes:
            node = self._graph.nodes[node_id]
            if node.get("type") != "quest":
                continue

            # 완료 마킹 체크
            if node.get("quest_completed", False):
                status = "completed"
            else:
                status = self._evaluate_quest_status(node_id)

            quests.append({
                "id": node_id,
                "content": node.get("content", ""),
                "stage": node.get("stage", ""),
                "npc": self.profile.name,
                "status": status,
                "created_at_scene": node.get("created_at_scene", 0),
                "edge_count": (
                    self._graph.in_degree(node_id)
                    + self._graph.out_degree(node_id)
                ),
            })

        return quests

    def _evaluate_quest_status(self, quest_id: str) -> str:
        """퀘스트 노드의 엣지 상태를 기반으로 퀘스트 상태를 판정."""
        in_edges = list(self._graph.in_edges(quest_id, data=True))
        out_edges = list(self._graph.out_edges(quest_id, data=True))
        all_edges = in_edges + out_edges

        # 엣지가 없는 경우: 아직 마모 전(신생 퀘스트)이면 active, 아니면 lost
        if not all_edges:
            quest_node = self._graph.nodes[quest_id]
            created = quest_node.get("created_at_scene", 0)
            age = self._scene_counter - created
            if age < QUEST_EDGE_FULL_DECAY:
                return "active"  # 엣지 없지만 아직 마모 기간 전
            return "lost"

        decayed_count = sum(1 for _, _, d in all_edges if d.get("decayed", False))

        # 모든 엣지가 decayed → 거의 잊혀진 상태
        if decayed_count == len(all_edges):
            return "fading"

        # 일부 엣지가 decayed
        if decayed_count > 0:
            return "fading"

        return "active"

    def complete_quest(self, quest_id: str) -> bool:
        """퀘스트를 완료 처리."""
        if quest_id not in self._graph:
            return False
        node = self._graph.nodes[quest_id]
        if node.get("type") != "quest":
            return False
        self._graph.nodes[quest_id]["quest_completed"] = True
        return True

    def complete_quest_by_keyword(self, keyword: str) -> list[str]:
        """키워드로 매칭되는 퀘스트를 완료 처리."""
        completed = []
        for node_id in self._graph.nodes:
            node = self._graph.nodes[node_id]
            if node.get("type") != "quest":
                continue
            if node.get("quest_completed", False):
                continue
            if keyword in node.get("content", ""):
                self._graph.nodes[node_id]["quest_completed"] = True
                completed.append(node_id)
        return completed

    def refresh_memory(self, node_id: str):
        """특정 기억을 '다시 떠올림' 처리.

        대화에서 언급되거나 관련 사건이 발생하면 호출하여
        기억의 씬 카운터를 갱신하고 active 상태로 복원.
        """
        if node_id not in self._graph:
            return
        self._graph.nodes[node_id]["created_at_scene"] = self._scene_counter
        self._graph.nodes[node_id]["memory_state"] = MEMORY_STATE_ACTIVE

    def get_forgotten_memories(self) -> list[dict]:
        """잊혀진 기억 목록 (복원 가능한 기억)."""
        forgotten = []
        for node_id in self._graph.nodes:
            node = self._graph.nodes[node_id]
            if node.get("memory_state") == MEMORY_STATE_FORGOTTEN:
                forgotten.append({"id": node_id, **node})
        return forgotten

    def get_memory_stats(self) -> dict:
        """기억 상태 통계."""
        stats = {MEMORY_STATE_ACTIVE: 0, MEMORY_STATE_FADED: 0, MEMORY_STATE_FORGOTTEN: 0}
        protected = 0
        for node_id in self._graph.nodes:
            node = self._graph.nodes[node_id]
            state = node.get("memory_state", MEMORY_STATE_ACTIVE)
            stats[state] = stats.get(state, 0) + 1
            if node.get("protected", False):
                protected += 1
        stats["protected"] = protected
        stats["total"] = len(self._graph.nodes)
        return stats

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
        """이름으로 NPC 메모리 그래프를 조회. 대소문자 무시."""
        # 정확한 매칭
        if name in self._npcs:
            return self._npcs[name]
        # 대소문자 무시 매칭
        name_lower = name.lower().strip()
        for key, npc in self._npcs.items():
            if key.lower() == name_lower:
                return npc
        return None

    def get_npcs_at_stage(self, stage: str) -> list[NPCMemoryGraph]:
        """특정 스테이지에 존재하는 NPC 목록."""
        return [
            npc for npc in self._npcs.values()
            if npc._current_stage == stage
        ]

    def get_all_npcs(self) -> dict[str, NPCMemoryGraph]:
        return self._npcs

    def advance_all_scenes(self):
        """모든 NPC의 씬 카운터를 진행시키고 기억 마모 실행."""
        for npc in self._npcs.values():
            npc.advance_scene()

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

    def get_all_quests(self) -> list[dict]:
        """모든 NPC의 퀘스트 기억을 집계하여 반환.

        각 퀘스트에 NPC 이름, 엣지 기반 상태(active/fading/lost/completed)를 포함.
        """
        all_quests = []
        for npc in self._npcs.values():
            quests = npc.get_quest_memories()
            all_quests.extend(quests)
        return all_quests

    def complete_quest(self, npc_name: str, quest_id: str) -> bool:
        """특정 NPC의 퀘스트를 완료 처리."""
        npc = self.get_npc(npc_name)
        if not npc:
            return False
        return npc.complete_quest(quest_id)

    def complete_quests_by_keyword(self, keyword: str) -> list[dict]:
        """키워드로 매칭되는 모든 NPC의 퀘스트를 완료 처리."""
        results = []
        for npc in self._npcs.values():
            completed_ids = npc.complete_quest_by_keyword(keyword)
            for qid in completed_ids:
                results.append({"npc": npc.profile.name, "quest_id": qid})
        return results

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
