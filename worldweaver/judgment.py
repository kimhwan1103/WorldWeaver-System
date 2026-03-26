"""서사 판정 엔진 — 세 그래프의 엣지 가중치를 종합하여 상황별 판정.

스토리 그래프, NPC 메모리 그래프, 아이템 그래프의 엣지 상태를 분석하여
플레이어가 특정 선택지에서 얼마나 유리/불리한지를 계산한다.

판정 결과는 수치가 아닌 **자연어 근거 목록**으로 변환되어
LLM 프롬프트에 주입된다. 플레이어는 수치를 보지 못하고,
서사를 통해서만 판정의 영향을 체감한다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from worldweaver.graph import StoryGraph
from worldweaver.item_graph import ItemGraph
from worldweaver.npc_memory import NPCManager, MEMORY_STATE_ACTIVE, MEMORY_STATE_FADED
from worldweaver.world_state import WorldState


@dataclass
class JudgmentFactor:
    """판정에 영향을 미치는 단일 요소."""

    source: str       # "item", "npc", "combat", "quest", "title", "gauge"
    description: str   # 자연어 근거 (프롬프트에 주입)
    weight: float      # 가중치 (-1.0 ~ +1.0)


@dataclass
class JudgmentResult:
    """판정 결과."""

    total_weight: float           # 합산 가중치
    factors: list[JudgmentFactor] # 근거 목록
    outcome: str                  # "favorable", "neutral", "unfavorable"
    success: bool                 # 최종 성공/실패
    narrative_hint: str           # LLM에게 전달할 서사 지시

    @property
    def factor_count(self) -> int:
        return len(self.factors)


class JudgmentEngine:
    """세 그래프의 엣지 가중치를 종합하여 상황 판정을 수행.

    판정 흐름:
      1. 선택지의 키워드/맥락을 추출
      2. 아이템 그래프에서 관련 아이템 효과 + 히든 발견 여부
      3. NPC 메모리에서 관련 퀘스트/관계 상태
      4. 스토리 그래프에서 관련 경험 (전투 이력, 방문 지역)
      5. 월드 스테이트 게이지 상태
      6. 칭호 보너스
      7. 가중치 합산 + 확률적 판정 → 결과
    """

    def __init__(
        self,
        world_state: WorldState,
        story_graph: StoryGraph,
        npc_manager: NPCManager,
        item_graph: ItemGraph | None = None,
    ):
        self._state = world_state
        self._graph = story_graph
        self._npc = npc_manager
        self._items = item_graph

    def judge(self, choice_text: str, scene_context: str = "") -> JudgmentResult:
        """선택지에 대한 종합 판정을 수행.

        Args:
            choice_text: 선택지 텍스트
            scene_context: 현재 씬의 제목+설명 (맥락 매칭용)

        Returns:
            판정 결과 (가중치, 근거, 성공/실패, 서사 지시)
        """
        context = f"{choice_text} {scene_context}".lower()
        factors: list[JudgmentFactor] = []

        # 1. 아이템 그래프 분석
        factors.extend(self._evaluate_items(context))

        # 2. NPC 관계/퀘스트 분석
        factors.extend(self._evaluate_npc(context))

        # 3. 전투 경험 분석
        factors.extend(self._evaluate_combat_history(context))

        # 4. 게이지 상태 분석
        factors.extend(self._evaluate_gauges())

        # 5. 칭호 보너스
        factors.extend(self._evaluate_titles())

        # 합산
        total = sum(f.weight for f in factors)

        # 결과 판정: 가중치가 높을수록 성공 확률 상승
        # base 50% + 가중치 * 25% (최소 10%, 최대 95%)
        success_rate = max(0.10, min(0.95, 0.50 + total * 0.25))
        success = random.random() < success_rate

        # 결과 분류
        if total >= 0.8:
            outcome = "favorable"
        elif total <= -0.5:
            outcome = "unfavorable"
        else:
            outcome = "neutral"

        # 서사 지시 생성
        narrative_hint = self._build_narrative_hint(factors, outcome, success)

        return JudgmentResult(
            total_weight=round(total, 2),
            factors=factors,
            outcome=outcome,
            success=success,
            narrative_hint=narrative_hint,
        )

    # ── 아이템 그래프 분석 ──

    def _evaluate_items(self, context: str) -> list[JudgmentFactor]:
        """인벤토리 아이템의 관련성을 평가."""
        factors = []
        if not self._items:
            return factors

        inventory = self._state.collections.get("inventory", [])
        for item_name in inventory:
            info = self._items.get_item_info(item_name)
            if not info:
                continue

            # 아이템 이름, 출처, 설명, NPC 연결을 맥락에 포함
            item_lower = item_name.lower()
            origin = (info.get("origin_name", "") or "").lower()
            desc = (info.get("description", "") or "").lower()

            # NPC affinity 이름도 추가 (아이템과 연결된 NPC)
            npc_names = ""
            if self._items:
                for npc_name in self._npc.get_all_npcs():
                    reaction = self._items.get_npc_reaction(item_name, npc_name)
                    if reaction != "neutral":
                        npc_names += f" {npc_name.lower()}"

            target_text = f"{item_lower} {origin} {desc} {npc_names}"
            relevance = self._keyword_overlap(context, target_text)
            if relevance == 0:
                continue

            # 기본 효과
            base = info.get("base_effect", {})
            base_weight = sum(base.values()) * 0.02 * relevance
            if base_weight > 0:
                factors.append(JudgmentFactor(
                    source="item",
                    description=f"소지 중인 '{item_name}'의 힘이 작용한다",
                    weight=min(0.4, base_weight),
                ))

            # 히든 효과 발견 보너스
            if info.get("hidden_discovered"):
                factors.append(JudgmentFactor(
                    source="item",
                    description=f"'{item_name}'의 숨겨진 힘을 알고 있다",
                    weight=0.3 * relevance,
                ))

        return factors

    # ── NPC 관계/퀘스트 분석 ──

    def _evaluate_npc(self, context: str) -> list[JudgmentFactor]:
        """NPC 관계와 퀘스트 상태를 평가."""
        factors = []

        for name, npc in self._npc.get_all_npcs().items():
            name_lower = name.lower()
            role_lower = npc.profile.role.lower()

            # NPC 이름/역할 직접 매칭
            npc_relevance = self._keyword_overlap(context, f"{name_lower} {role_lower}")

            # NPC 퀘스트 내용으로도 간접 매칭 (퀘스트가 맥락과 관련 있으면 NPC도 관련)
            quests = npc.get_quest_memories()
            quest_relevance = 0.0
            for quest in quests:
                quest_content = quest.get("content", "").lower()
                qr = self._keyword_overlap(context, quest_content)
                quest_relevance = max(quest_relevance, qr)

            # NPC 직접 매칭 또는 퀘스트 간접 매칭 중 높은 것
            relevance = max(npc_relevance, quest_relevance * 0.8)
            if relevance == 0:
                continue

            # 호감도 기반 가중치
            if npc.disposition >= 0.7:
                factors.append(JudgmentFactor(
                    source="npc",
                    description=f"{name}과(와)의 깊은 신뢰가 도움이 된다",
                    weight=0.4 * relevance,
                ))
            elif npc.disposition >= 0.5:
                factors.append(JudgmentFactor(
                    source="npc",
                    description=f"{name}의 조언이 떠오른다",
                    weight=0.2 * relevance,
                ))
            elif npc.disposition < 0.3:
                factors.append(JudgmentFactor(
                    source="npc",
                    description=f"{name}과(와)의 불화가 마음에 걸린다",
                    weight=-0.2 * relevance,
                ))

            # 퀘스트 상태 (독립적으로 매칭)
            for quest in quests:
                quest_content = quest.get("content", "").lower()
                q_relevance = self._keyword_overlap(context, quest_content)
                if q_relevance == 0:
                    continue

                status = quest.get("status", "active")
                if status == "active":
                    factors.append(JudgmentFactor(
                        source="quest",
                        description=f"{name}에게 받은 임무의 맥락이 도움이 된다",
                        weight=0.3 * q_relevance,
                    ))
                elif status == "lost":
                    factors.append(JudgmentFactor(
                        source="quest",
                        description=f"잊혀진 임무의 빈자리가 불안감을 준다",
                        weight=-0.3 * q_relevance,
                    ))

        return factors

    # ── 전투 경험 분석 ──

    def _evaluate_combat_history(self, context: str) -> list[JudgmentFactor]:
        """이전 전투 경험의 관련성을 평가."""
        factors = []
        combat_summaries = self._graph.get_recent_combat_summary(10)

        for summary in combat_summaries:
            combat_text = f"{summary.get('title', '')} {summary.get('description', '')}".lower()
            relevance = self._keyword_overlap(context, combat_text)
            if relevance > 0:
                is_victory = "승리" in summary.get("title", "")
                if is_victory:
                    factors.append(JudgmentFactor(
                        source="combat",
                        description="유사한 적과 싸워 승리한 경험이 있다",
                        weight=0.3 * relevance,
                    ))
                else:
                    factors.append(JudgmentFactor(
                        source="combat",
                        description="이전 패배의 교훈이 떠오른다",
                        weight=0.1 * relevance,
                    ))

        return factors

    # ── 게이지 상태 분석 ──

    def _evaluate_gauges(self) -> list[JudgmentFactor]:
        """월드 스테이트 게이지를 평가."""
        factors = []

        health = self._state.gauges.get("health", 1.0)
        if health < 0.3:
            factors.append(JudgmentFactor(
                source="gauge",
                description="체력이 위태롭다",
                weight=-0.3,
            ))
        elif health > 0.8:
            factors.append(JudgmentFactor(
                source="gauge",
                description="충분한 체력으로 자신감이 있다",
                weight=0.1,
            ))

        corruption = self._state.gauges.get("corruption", 0.0)
        if corruption > 0.7:
            factors.append(JudgmentFactor(
                source="gauge",
                description="타락의 기운이 판단력을 흐린다",
                weight=-0.3,
            ))

        seal = self._state.gauges.get("seal", 0.0)
        if seal > 0.5:
            factors.append(JudgmentFactor(
                source="gauge",
                description="축적된 봉인력이 보호한다",
                weight=0.2,
            ))

        return factors

    # ── 칭호 보너스 ──

    def _evaluate_titles(self) -> list[JudgmentFactor]:
        """활성 칭호의 영향을 평가."""
        factors = []
        if not self._items:
            return factors

        for title in self._items.get_active_titles():
            factors.append(JudgmentFactor(
                source="title",
                description=f"'{title['name']}' 칭호의 명성이 뒷받침한다",
                weight=0.15,
            ))

        return factors

    # ── 서사 지시 생성 ──

    def _build_narrative_hint(
        self,
        factors: list[JudgmentFactor],
        outcome: str,
        success: bool,
    ) -> str:
        """LLM 프롬프트에 주입할 서사 판정 지시를 생성.

        플레이어에게는 보이지 않고, LLM만 읽는다.
        """
        lines = []

        # 판정 결과 지시
        if success:
            if outcome == "favorable":
                lines.append("이 선택은 확실히 성공합니다. 플레이어의 축적된 경험과 준비가 빛을 발합니다.")
            elif outcome == "neutral":
                lines.append("이 선택은 성공하지만 쉽지 않았습니다. 약간의 고생 끝에 목표를 달성합니다.")
            else:
                lines.append("운 좋게 성공합니다. 하지만 위태로운 순간이 있었음을 서사에 반영하세요.")
        else:
            if outcome == "unfavorable":
                lines.append("이 선택은 실패합니다. 준비 부족이 원인입니다. 하지만 완전한 재앙은 아닙니다 — 대안이 열립니다.")
            elif outcome == "neutral":
                lines.append("이 선택은 실패합니다. 예상치 못한 변수가 생깁니다. 체력이나 자원에 소량의 손실이 있습니다.")
            else:
                lines.append("아쉽게 실패합니다. 하지만 시도 자체에서 무언가를 배웁니다.")

        # 근거를 서사 힌트로 변환 (상위 3개)
        sorted_factors = sorted(factors, key=lambda f: abs(f.weight), reverse=True)
        positive = [f for f in sorted_factors if f.weight > 0][:2]
        negative = [f for f in sorted_factors if f.weight < 0][:1]

        if positive:
            lines.append("서사에 자연스럽게 녹여야 할 유리한 요소:")
            for f in positive:
                lines.append(f"  - {f.description}")

        if negative:
            lines.append("서사에 암시해야 할 불리한 요소:")
            for f in negative:
                lines.append(f"  - {f.description}")

        if not positive and not negative:
            lines.append("특별한 유/불리 요소 없이 순수한 상황 판단으로 진행됩니다.")

        return "\n".join(lines)

    # ── 유틸리티 ──

    @staticmethod
    def _keyword_overlap(context: str, target: str) -> float:
        """두 텍스트의 키워드 겹침 정도 (0.0 ~ 1.0)."""
        import re
        # 3글자 이상 단어 추출 (관사/전치사 제외)
        stop_words = {"the", "of", "and", "in", "to", "for", "is", "a", "an", "this", "that"}
        ctx_words = set(re.findall(r"[\w\u3040-\u9fff\uac00-\ud7a3]{3,}", context)) - stop_words
        tgt_words = set(re.findall(r"[\w\u3040-\u9fff\uac00-\ud7a3]{3,}", target)) - stop_words

        if not ctx_words or not tgt_words:
            return 0.0

        overlap = len(ctx_words & tgt_words)
        if overlap == 0:
            return 0.0

        # 겹침 비율 (0~1, 최대 1.0)
        return min(1.0, overlap / max(2, min(len(ctx_words), len(tgt_words))))


def build_judgment_prompt_section(result: JudgmentResult) -> str:
    """판정 결과를 프롬프트 섹션 문자열로 변환.

    story_template의 directives에 주입하기 위한 형식.
    """
    if not result.factors:
        return ""

    return (
        "\n### Narrative Judgment (DO NOT reveal numbers to the player) ###\n"
        f"{result.narrative_hint}"
    )
