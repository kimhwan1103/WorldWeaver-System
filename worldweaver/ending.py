"""엔딩 판정 + LLM 에필로그 생성 엔진.

스토리 그래프, 월드 스테이트, NPC 관계, 퀘스트 상태를 종합하여
엔딩 조건을 판정하고, 매칭된 엔딩의 prompt_hint를 LLM에 주입하여
플레이 내용을 반영한 고유한 에필로그를 생성한다.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass

from worldweaver.graph import StoryGraph
from worldweaver.npc_memory import NPCManager
from worldweaver.world_state import WorldState

OPERATORS = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
}


@dataclass
class EndingResult:
    """엔딩 판정 결과."""

    ending_id: str
    ending_type: str  # 테마가 정의한 엔딩 이름
    prompt_hint: str  # LLM에게 전달할 엔딩 방향 지시
    priority: int
    conditions_met: dict  # 충족된 조건 요약


class EndingEvaluator:
    """테마 JSON의 endings 정의를 기반으로 엔딩 조건을 판정."""

    def __init__(
        self,
        theme: dict,
        world_state: WorldState,
        story_graph: StoryGraph,
        npc_manager: NPCManager,
    ):
        self._endings = theme.get("endings", [])
        self._state = world_state
        self._graph = story_graph
        self._npc_manager = npc_manager

    def evaluate(self) -> EndingResult | None:
        """현재 상태에서 매칭되는 최우선 엔딩을 반환.

        모든 endings를 priority 순으로 평가하여
        조건을 모두 충족하는 첫 번째 엔딩을 반환한다.
        조건을 충족하는 엔딩이 없으면 None을 반환.
        """
        # priority 오름차순 정렬 (낮을수록 우선)
        sorted_endings = sorted(self._endings, key=lambda e: e.get("priority", 99))

        for ending in sorted_endings:
            result = self._check_ending(ending)
            if result:
                return result

        return None

    def check_ending_available(self) -> bool:
        """엔딩 트리거 가능 여부 (min_depth 충족하는 엔딩이 하나라도 있는지)."""
        depth = self._graph.get_story_depth()
        for ending in self._endings:
            conditions = ending.get("conditions", {})
            min_depth = conditions.get("min_depth", 999)
            if depth >= min_depth:
                return True
        return False

    def _check_ending(self, ending: dict) -> EndingResult | None:
        """단일 엔딩의 모든 조건을 검사."""
        conditions = ending.get("conditions", {})
        met = {}

        # 1. 최소 스토리 깊이
        min_depth = conditions.get("min_depth", 0)
        depth = self._graph.get_story_depth()
        if depth < min_depth:
            return None
        met["depth"] = f"{depth}/{min_depth}"

        # 2. 게이지 조건
        gauge_conds = conditions.get("gauges", {})
        for gauge_name, rule in gauge_conds.items():
            if gauge_name not in self._state.gauges:
                return None
            op_func = OPERATORS.get(rule.get("op", ">="))
            if not op_func:
                return None
            if not op_func(self._state.gauges[gauge_name], rule["value"]):
                return None
            met[f"gauge_{gauge_name}"] = f"{self._state.gauges[gauge_name]:.2f} {rule['op']} {rule['value']}"

        # 3. 퀘스트 완료 수
        min_quests = conditions.get("min_quests_completed", 0)
        if min_quests > 0:
            all_quests = self._npc_manager.get_all_quests()
            completed = sum(1 for q in all_quests if q["status"] == "completed")
            if completed < min_quests:
                return None
            met["quests_completed"] = f"{completed}/{min_quests}"

        # 4. 잃어버린 퀘스트 수 (NPC가 잊은 퀘스트)
        max_lost = conditions.get("max_quests_lost", None)
        if max_lost is not None:
            all_quests = self._npc_manager.get_all_quests()
            lost = sum(1 for q in all_quests if q["status"] == "lost")
            if lost > max_lost:
                return None
            met["quests_lost"] = f"{lost}/{max_lost}"

        min_lost = conditions.get("min_quests_lost", 0)
        if min_lost > 0:
            all_quests = self._npc_manager.get_all_quests()
            lost = sum(1 for q in all_quests if q["status"] == "lost")
            if lost < min_lost:
                return None
            met["quests_lost"] = f"{lost}>={min_lost}"

        # 5. NPC 평균 호감도
        min_disp = conditions.get("min_disposition_avg", 0)
        max_disp = conditions.get("max_disposition_avg", 1.0)
        all_npcs = self._npc_manager.get_all_npcs()
        if all_npcs:
            avg_disp = sum(n.disposition for n in all_npcs.values()) / len(all_npcs)
            if avg_disp < min_disp or avg_disp > max_disp:
                return None
            met["disposition_avg"] = f"{avg_disp:.2f}"

        # 6. 특정 엔티티 제거 수
        entities_removed_min = conditions.get("entities_removed_min", 0)
        if entities_removed_min > 0:
            removed = len(self._state.get_removed_entities())
            if removed < entities_removed_min:
                return None
            met["entities_removed"] = f"{removed}>={entities_removed_min}"

        return EndingResult(
            ending_id=ending.get("id", "unknown"),
            ending_type=ending.get("id", "unknown"),
            prompt_hint=ending.get("prompt_hint", ""),
            priority=ending.get("priority", 99),
            conditions_met=met,
        )


@dataclass
class GameOverResult:
    """게임오버 판정 결과."""

    game_over_id: str
    prompt_hint: str
    cause: str        # 게임오버 원인 요약
    factors: dict     # 충족된 조건 상세


class GameOverEvaluator:
    """그래프 상태를 종합하여 게임오버 조건을 판정.

    체크 소스:
      - 월드 스테이트 게이지 (health 0, corruption 1.0)
      - 스토리 그래프 (연속 전투 패배)
      - NPC 메모리 그래프 (핵심 퀘스트 전부 lost, 전원 Hostile)
      - 테마별 커스텀 조건 (game_over_conditions)
    """

    def __init__(
        self,
        theme: dict,
        world_state: WorldState,
        story_graph: StoryGraph,
        npc_manager: NPCManager,
    ):
        self._theme_conditions = theme.get("game_over_conditions", [])
        self._state = world_state
        self._graph = story_graph
        self._npc = npc_manager

    def evaluate(self) -> GameOverResult | None:
        """게임오버 조건을 체크. 해당하면 결과 반환, 아니면 None."""
        # 1. 즉사 조건: health 0 이하
        result = self._check_health_zero()
        if result:
            return result

        # 2. 그래프 기반 조건: 연속 패배
        result = self._check_consecutive_defeats()
        if result:
            return result

        # 3. NPC 그래프 기반: 전원 적대
        result = self._check_all_hostile()
        if result:
            return result

        # 4. NPC 퀘스트 기반: 핵심 퀘스트 전부 lost + 높은 corruption
        result = self._check_all_quests_lost()
        if result:
            return result

        # 5. 테마별 커스텀 조건
        for cond in self._theme_conditions:
            result = self._check_custom_condition(cond)
            if result:
                return result

        return None

    def _check_health_zero(self) -> GameOverResult | None:
        health = self._state.gauges.get("health", 1.0)
        if health <= 0:
            return GameOverResult(
                game_over_id="health_zero",
                prompt_hint="The guardian's life force is completely depleted. Write a dramatic death scene that reflects their journey and the state of the world they leave behind.",
                cause="체력이 완전히 소진되었다",
                factors={"health": f"{health:.2f}"},
            )
        return None

    def _check_consecutive_defeats(self) -> GameOverResult | None:
        """스토리 그래프에서 연속 전투 패배 3회를 체크."""
        path = self._graph.get_path()
        consecutive = 0
        for node_id in reversed(path):
            node = self._graph._graph.nodes.get(node_id, {})
            title = node.get("title", "")
            if "전투 결과" in title and "패배" in title:
                consecutive += 1
            elif "전투 결과" in title:
                break  # 패배 아닌 전투 결과 → 연속 끊김
            # 전투 결과가 아닌 노드는 건너뜀
        if consecutive >= 3:
            return GameOverResult(
                game_over_id="consecutive_defeats",
                prompt_hint="After suffering defeat after defeat, the guardian's body and spirit are broken. Write a scene where the accumulated wounds and exhaustion finally overwhelm them.",
                cause="연속 전투 패배로 더 이상 싸울 수 없다",
                factors={"consecutive_defeats": str(consecutive)},
            )
        return None

    def _check_all_hostile(self) -> GameOverResult | None:
        """모든 NPC가 Hostile인지 체크."""
        all_npcs = self._npc.get_all_npcs()
        if not all_npcs:
            return None

        hostile_count = sum(
            1 for npc in all_npcs.values() if npc.disposition < 0.2
        )
        if hostile_count == len(all_npcs) and len(all_npcs) >= 2:
            return GameOverResult(
                game_over_id="all_hostile",
                prompt_hint="Every ally has turned against the guardian. Alone and surrounded by former friends turned enemies, there is no one left to turn to. Write a scene of ultimate isolation and betrayal.",
                cause="모든 동맹이 적대적으로 변했다",
                factors={"hostile_npcs": f"{hostile_count}/{len(all_npcs)}"},
            )
        return None

    def _check_all_quests_lost(self) -> GameOverResult | None:
        """모든 퀘스트가 lost 상태이고 corruption이 높을 때."""
        all_quests = self._npc.get_all_quests()
        if not all_quests:
            return None

        lost = sum(1 for q in all_quests if q["status"] == "lost")
        total = len(all_quests)

        corruption = self._state.gauges.get("corruption", 0.0)

        if lost == total and total >= 2 and corruption >= 0.7:
            return GameOverResult(
                game_over_id="forgotten_collapse",
                prompt_hint="Every quest has been forgotten by the NPCs. The threads of fate are severed. Combined with rising corruption, the world's last defenses crumble. Write a scene where the consequences of neglect and corruption consume everything.",
                cause="모든 퀘스트가 잊혀지고, 타락이 세계를 삼킨다",
                factors={"quests_lost": f"{lost}/{total}", "corruption": f"{corruption:.2f}"},
            )
        return None

    def _check_custom_condition(self, cond: dict) -> GameOverResult | None:
        """테마별 커스텀 게임오버 조건 체크."""
        conditions = cond.get("condition", {})

        # 게이지 조건
        for gauge_name, rule in conditions.get("gauges", {}).items():
            if gauge_name not in self._state.gauges:
                return None
            op_func = OPERATORS.get(rule.get("op", ">="))
            if not op_func or not op_func(self._state.gauges[gauge_name], rule["value"]):
                return None

        # NPC 호감도 평균
        if "max_disposition_avg" in conditions:
            all_npcs = self._npc.get_all_npcs()
            if all_npcs:
                avg = sum(n.disposition for n in all_npcs.values()) / len(all_npcs)
                if avg > conditions["max_disposition_avg"]:
                    return None

        # 최소 깊이
        if "min_depth" in conditions:
            if self._graph.get_story_depth() < conditions["min_depth"]:
                return None

        return GameOverResult(
            game_over_id=cond.get("id", "custom"),
            prompt_hint=cond.get("prompt_hint", "The journey ends here."),
            cause=cond.get("cause", "게임오버 조건 충족"),
            factors={"condition_id": cond.get("id", "custom")},
        )


def build_game_over_prompt_context(
    game_over: GameOverResult,
    graph: StoryGraph,
    world_state: WorldState,
    npc_manager: NPCManager,
) -> dict:
    """게임오버 LLM 프롬프트 컨텍스트."""
    play_summary = graph.get_play_summary_for_prompt()

    npc_lines = []
    for name, npc in npc_manager.get_all_npcs().items():
        npc_lines.append(
            f"  {name}({npc.profile.role}): {npc.disposition_label}({npc.disposition:.1f})"
        )

    return {
        "ending_type": f"GAME OVER: {game_over.game_over_id}",
        "ending_hint": game_over.prompt_hint,
        "play_summary": play_summary,
        "world_state": world_state.to_prompt_string(),
        "npc_relationships": "\n".join(npc_lines) if npc_lines else "(없음)",
        "quest_summary": game_over.cause,
    }


def build_ending_prompt_context(
    ending: EndingResult,
    graph: StoryGraph,
    world_state: WorldState,
    npc_manager: NPCManager,
) -> dict:
    """엔딩 LLM 프롬프트에 주입할 컨텍스트를 구성.

    스토리 그래프에서 플레이 요약을 추출하고,
    NPC 관계와 퀘스트 상태를 종합한다.
    """
    # 스토리 그래프에서 플레이 요약 추출
    play_summary = graph.get_play_summary_for_prompt()

    # NPC 관계 요약
    npc_lines = []
    for name, npc in npc_manager.get_all_npcs().items():
        quests = npc.get_quest_memories()
        quest_info = ""
        if quests:
            statuses = [f"{q['content'][:30]}({q['status']})" for q in quests]
            quest_info = f" | 퀘스트: {', '.join(statuses)}"
        npc_lines.append(
            f"  {name}({npc.profile.role}): "
            f"호감도 {npc.disposition_label}({npc.disposition:.1f}){quest_info}"
        )
    npc_relationships = "\n".join(npc_lines) if npc_lines else "(NPC 없음)"

    # 퀘스트 요약
    all_quests = npc_manager.get_all_quests()
    if all_quests:
        quest_lines = []
        for q in all_quests:
            quest_lines.append(f"  [{q['status'].upper()}] {q['content']} (from {q['npc']})")
        quest_summary = "\n".join(quest_lines)
    else:
        quest_summary = "(퀘스트 없음)"

    return {
        "ending_type": ending.ending_type,
        "ending_hint": ending.prompt_hint,
        "play_summary": play_summary,
        "world_state": world_state.to_prompt_string(),
        "npc_relationships": npc_relationships,
        "quest_summary": quest_summary,
    }
