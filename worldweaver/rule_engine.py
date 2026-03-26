import operator
from dataclasses import dataclass

from worldweaver.graph import StoryGraph
from worldweaver.prompt_loader import get_rules
from worldweaver.world_state import WorldState

OPERATORS = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
}


@dataclass
class RuleResult:
    """규칙 검증 결과."""
    passed: bool
    violations: list[str]
    warnings: list[str]
    forced_directives: list[str]


class RuleEngine:
    """그래프 이력 + 월드 스테이트를 조합하여 씬을 검증하는 룰베이스 엔진.

    범용 구조: 테마 JSON의 rules + rules.json의 공통 규칙을 조합한다.
    """

    def __init__(self, world_state: WorldState, story_graph: StoryGraph, theme: dict):
        self.state = world_state
        self.graph = story_graph
        self._theme = theme
        self._theme_rules = theme.get("rules", {})
        self._common_rules = get_rules()
        self.MAX_RETRY = self._common_rules["max_retry"]

    # ── 사전 검증: 씬 생성 전에 프롬프트에 주입할 지시사항 생성 ──

    def pre_generation_directives(self) -> list[str]:
        """씬 생성 전, 현재 상태를 기반으로 강제 지시사항을 생성."""
        directives = []
        common_pre = self._common_rules["pre_generation"]
        common_thr = self._common_rules["thresholds"]

        # 범용 규칙: 제거 상태 엔티티 재등장 금지
        removed = self.state.get_removed_entities()
        if removed:
            directives.append(
                common_pre["removed_entity"].format(entities=", ".join(removed))
            )

        # 테마별 게이지 규칙 (theme JSON에서 로드)
        for rule in self._theme_rules.get("gauge_rules", []):
            gauge_name = rule["gauge"]
            if gauge_name not in self.state.gauges:
                continue
            op_func = OPERATORS.get(rule["operator"])
            if op_func and op_func(self.state.gauges[gauge_name], rule["threshold"]):
                directives.append(rule["directive"])

        # 공통 규칙: 분위기 반복 방지
        mood_count = common_thr["mood_repeat_count"]
        recent_moods = self.graph.get_recent_moods(mood_count)
        if len(recent_moods) >= mood_count and len(set(recent_moods)) == 1:
            directives.append(
                common_pre["mood_repeat"].format(count=mood_count, mood=recent_moods[0])
            )

        # 테마별 절정 규칙 (전투 노드 제외한 순수 서사 깊이 기준)
        depth = self.graph.get_story_depth()
        for rule in self._theme_rules.get("climax_rules", []):
            if depth < rule["min_depth"]:
                continue
            gauge_name = rule["gauge"]
            if gauge_name not in self.state.gauges:
                continue
            op_func = OPERATORS.get(rule["operator"])
            if op_func and op_func(self.state.gauges[gauge_name], rule["threshold"]):
                directives.append(rule["directive"])

        # 공통 규칙: 복선 회수 유도
        hooks = self.state.collections.get("unresolved_hooks", [])
        if depth >= common_thr["hook_resolve_depth"] and hooks:
            directives.append(
                common_pre["hook_resolve"].format(hook=hooks[0])
            )

        return directives

    # ── 사후 검증: 생성된 씬이 규칙을 위반하는지 체크 ──

    def validate_scene(self, scene_data: dict) -> RuleResult:
        """생성된 씬 데이터를 검증. 위반/경고/강제 지시를 반환."""
        violations = []
        warnings = []
        forced = []
        val = self._common_rules["validation"]

        title = scene_data.get("title", "")
        description = scene_data.get("description", "")
        scene_text = f"{title} {description}"

        # 범용 규칙: 제거 상태 엔티티 재등장 검사
        for name in self.state.get_removed_entities():
            if name in scene_text:
                violations.append(val["removed_entity_violation"].format(name=name))

        # 범용 규칙: 해결된 사건 재발견 검사
        resolved = self.state.collections.get("resolved_events", [])
        for event in resolved:
            if event in scene_text and "발견" in scene_text:
                warnings.append(val["resolved_event_warning"].format(event=event))

        # 공통 규칙: 분위기 연속 반복
        mood = scene_data.get("features", {}).get("mood", "")
        mood_count = self._common_rules["thresholds"]["mood_repeat_count"]
        recent_moods = self.graph.get_recent_moods(mood_count)
        if len(recent_moods) >= mood_count and len(set(recent_moods)) == 1 and mood == recent_moods[0]:
            warnings.append(val["mood_repeat_warning"].format(mood=mood))

        # 선택지 수 검사
        choices = scene_data.get("choices", [])
        if len(choices) < val["min_choices"]:
            warnings.append(val["min_choices_warning"])

        passed = len(violations) == 0
        return RuleResult(
            passed=passed,
            violations=violations,
            warnings=warnings,
            forced_directives=forced,
        )

    def build_retry_prompt(self, original_prompt: str, result: RuleResult) -> str:
        """위반 사항을 포함한 재생성 프롬프트를 구성."""
        retry = self._common_rules["retry"]
        violation_text = "\n".join(f"- {v}" for v in result.violations)
        warning_text = "\n".join(f"- {w}" for w in result.warnings)

        retry_addition = f"\n\n{retry['violation_header']}\n{violation_text}\n"
        if result.warnings:
            retry_addition += f"\n{retry['warning_header']}\n{warning_text}\n"

        return original_prompt + retry_addition
