"""테마 번역 헬퍼 — 테마 JSON의 translations 딕셔너리를 기반으로 번역 조회."""

from __future__ import annotations


def tr(text: str, language: str, translations: dict | None,
       path: str | None = None) -> str:
    """translations 딕셔너리에서 번역된 문자열을 조회.

    Args:
        text: 원문 (번역이 없을 때 폴백).
        language: 대상 언어 코드 (ko, en, ja).
        translations: 테마의 "translations" 딕셔너리 (언어코드 → {경로: 번역}).
        path: 점(.) 구분 경로 키 (예: "gauges.health.label").

    Returns:
        번역된 문자열. 없으면 원문 반환.
    """
    if not translations or language not in translations:
        return text

    lang_dict = translations[language]

    if path and path in lang_dict:
        return lang_dict[path]

    return text


class ThemeTranslator:
    """테마와 언어를 바인딩한 번역 편의 래퍼."""

    def __init__(self, theme: dict, language: str):
        self._translations = theme.get("translations", {})
        self._language = language

    @property
    def language(self) -> str:
        return self._language

    def tr(self, text: str, path: str | None = None) -> str:
        return tr(text, self._language, self._translations, path)

    def tr_enemy(self, enemy_name: str, field: str) -> str:
        """적 관련 필드 번역. field: name, description"""
        return self.tr(
            _get_nested(field, enemy_name),
            path=f"enemies.{enemy_name}.{field}",
        )

    def tr_ability(self, enemy_name: str, ability_name: str) -> str:
        """적 스킬 이름 번역."""
        return self.tr(
            ability_name,
            path=f"enemies.{enemy_name}.abilities.{ability_name}",
        )

    def tr_loot(self, enemy_name: str, loot_item: str) -> str:
        """전리품 이름 번역."""
        return self.tr(
            loot_item,
            path=f"enemies.{enemy_name}.loot.{loot_item}",
        )

    def tr_npc(self, npc_name: str, field: str) -> str:
        """NPC 관련 필드 번역. field: name, role, personality, tone"""
        return self.tr(
            _get_nested(field, npc_name),
            path=f"npc.{npc_name}.{field}",
        )

    def tr_gauge(self, gauge_name: str, field: str = "label") -> str:
        """게이지 라벨/설명 번역."""
        return self.tr(gauge_name, path=f"gauges.{gauge_name}.{field}")

    def tr_stage(self, stage_name: str) -> str:
        """스테이지 이름 번역."""
        return self.tr(stage_name, path=f"stages.{stage_name}")


def _get_nested(field: str, name: str) -> str:
    """필드 값이 없을 때 name을 폴백으로 반환."""
    # tr()에서 path 기반 조회가 실패하면 text(=이 반환값)가 폴백
    return name if field == "name" else ""
