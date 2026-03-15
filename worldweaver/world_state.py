class WorldState:
    """테마 스키마 기반 동적 월드 스테이트.

    고정 필드 없이, 테마 JSON의 world_state_schema가 정의하는
    gauges / entities / properties / collections를 동적으로 관리한다.
    """

    def __init__(self, schema: dict):
        self._schema = schema

        # 엔티티 (캐릭터, NPC 등): {"메두사": "처치됨", "아테나": "동맹"}
        self.entities: dict[str, str] = {}
        self._removed_statuses: list[str] = (
            schema.get("entities", {}).get("removed_statuses", ["처치됨", "소멸"])
        )

        # 게이지 (corruption, seal, health 등): {"corruption": 0.0, "seal": 0.0}
        self.gauges: dict[str, float] = {}
        self._gauge_schema: dict[str, dict] = schema.get("gauges", {})
        for name, cfg in self._gauge_schema.items():
            self.gauges[name] = cfg.get("default", 0.0)

        # 단일 속성 (active_rift, current_era 등): {"active_rift": "없음"}
        self.properties: dict[str, str] = {}
        self._property_schema: dict[str, dict] = schema.get("properties", {})
        for name, cfg in self._property_schema.items():
            self.properties[name] = cfg.get("default", "")

        # 컬렉션 (inventory, visited_locations 등): {"inventory": [...]}
        self.collections: dict[str, list[str]] = {}
        self._collection_schema: dict[str, dict] = schema.get("collections", {})
        for name in self._collection_schema:
            self.collections[name] = []

    def get_removed_entities(self) -> list[str]:
        """제거 상태(처치됨, 소멸 등)인 엔티티 이름 목록."""
        return [
            name for name, status in self.entities.items()
            if status in self._removed_statuses
        ]

    def apply_changes(self, changes: dict):
        """LLM이 출력한 state_change dict를 현재 상태에 반영."""
        # 엔티티 상태 업데이트
        for name, status in changes.get("entities_changed", {}).items():
            self.entities[name] = status

        # 게이지 변동
        for gauge_name, delta in changes.get("gauge_deltas", {}).items():
            if gauge_name in self.gauges:
                cfg = self._gauge_schema[gauge_name]
                new_val = self.gauges[gauge_name] + delta
                self.gauges[gauge_name] = max(cfg.get("min", 0.0), min(cfg.get("max", 1.0), new_val))

        # 단일 속성 변경
        for prop_name, value in changes.get("properties_changed", {}).items():
            if prop_name in self.properties:
                self.properties[prop_name] = value

        # 컬렉션 아이템 추가/제거
        for col_name, items in changes.get("items_added", {}).items():
            if col_name in self.collections:
                for item in items:
                    if item not in self.collections[col_name]:
                        self.collections[col_name].append(item)

        for col_name, items in changes.get("items_removed", {}).items():
            if col_name in self.collections:
                for item in items:
                    if item in self.collections[col_name]:
                        self.collections[col_name].remove(item)

    def to_prompt_string(self) -> str:
        """프롬프트에 주입할 수 있는 문자열로 변환. 라벨은 스키마에서 가져옴."""
        lines = []

        # 속성
        for name, value in self.properties.items():
            label = self._property_schema[name].get("label", name)
            lines.append(f"{label}: {value}")

        # 게이지
        gauge_parts = []
        for name, value in self.gauges.items():
            label = self._gauge_schema[name].get("label", name)
            gauge_parts.append(f"{label}: {value:.1f}")
        if gauge_parts:
            lines.append(" | ".join(gauge_parts))

        # 엔티티
        if self.entities:
            entity_label = self._schema.get("entities", {}).get("label", "엔티티 상태")
            chars = ", ".join(f"{k}({v})" for k, v in self.entities.items())
            lines.append(f"{entity_label}: {chars}")

        # 컬렉션
        for name, items in self.collections.items():
            if items:
                label = self._collection_schema[name].get("label", name)
                lines.append(f"{label}: {', '.join(items)}")

        return "\n".join(lines) if lines else "(초기 상태)"

    def to_summary_string(self) -> str:
        """콘솔 출력용 간결한 요약 문자열."""
        parts = []

        # 속성
        for name, value in self.properties.items():
            label = self._property_schema[name].get("label", name)
            parts.append(f"{label}: {value}")

        # 게이지
        for name, value in self.gauges.items():
            label = self._gauge_schema[name].get("label", name)
            parts.append(f"{label}: {value:.1f}")

        line1 = " | ".join(parts)

        lines = [f"  {line1}"]

        if self.entities:
            chars = ", ".join(f"{k}({v})" for k, v in self.entities.items())
            entity_label = self._schema.get("entities", {}).get("label", "엔티티")
            lines.append(f"  {entity_label}: {chars}")

        for name, items in self.collections.items():
            if items and name == "inventory":
                label = self._collection_schema[name].get("label", name)
                lines.append(f"  {label}: {', '.join(items)}")

        return "\n".join(lines)

    def get_state_change_schema_for_prompt(self) -> str:
        """LLM에게 state_change 필드의 구조를 알려주는 스키마 설명을 생성."""
        lines = [
            '"state_change": {',
            '  "entities_changed": {"엔티티이름": "새로운상태"},',
            '  "gauge_deltas": {',
        ]
        for name in self._gauge_schema:
            lines.append(f'    "{name}": 0.0,  // 변동량 (-0.3 ~ +0.3)')
        lines.append('  },')
        lines.append('  "properties_changed": {')
        for name in self._property_schema:
            lines.append(f'    "{name}": ""  // 변경 시에만 값 입력')
        lines.append('  },')
        lines.append('  "items_added": {')
        for name in self._collection_schema:
            lines.append(f'    "{name}": []  // 이 씬에서 추가된 항목')
        lines.append('  },')
        lines.append('  "items_removed": {')
        for name in self._collection_schema:
            lines.append(f'    "{name}": []  // 이 씬에서 제거된 항목')
        lines.append('  }')
        lines.append('}')
        return "\n".join(lines)
