"""아이템 방향성 그래프 — 아이템의 효과, 출처, NPC 관계를 그래프로 관리.

각 아이템은 노드이며, 엣지를 통해 다음을 추적한다:
  - 효과 (effect): 기본 스탯 보너스 (attack, defense, max_hp, heal)
  - 출처 (origin): 어떤 적/NPC에서 획득했는지
  - NPC 반응 (npc_affinity): 이 아이템을 소지 시 특정 NPC의 호감 변화
  - 히든 효과 (hidden_effect): 발견되지 않은 숨겨진 효과 (엣지 마모/복원)

히든 효과는 NPC 퀘스트 메모리의 엣지 마모 패턴과 동일하게 작동:
  - 아이템 획득 시 히든 효과 엣지는 decayed=True (잠겨있음)
  - 플레이어가 아이템을 "조사"하면 엣지가 복원 → 히든 효과 발견
  - 특정 NPC와 대화하면서 아이템을 언급하면 히든 효과가 드러남
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import networkx as nx


@dataclass
class ItemEffect:
    """아이템 효과 정의."""

    attack: int = 0
    defense: int = 0
    max_hp: int = 0
    heal: int = 0  # 사용 시 회복량 (0이면 장비형)

    @property
    def is_consumable(self) -> bool:
        return self.heal > 0

    def to_dict(self) -> dict:
        return {k: v for k, v in {
            "attack": self.attack, "defense": self.defense,
            "max_hp": self.max_hp, "heal": self.heal,
        }.items() if v != 0}

    @classmethod
    def from_dict(cls, d: dict) -> ItemEffect:
        return cls(
            attack=d.get("attack", 0),
            defense=d.get("defense", 0),
            max_hp=d.get("max_hp", 0),
            heal=d.get("heal", 0),
        )


@dataclass
class ItemNode:
    """아이템 그래프의 노드 데이터."""

    name: str
    description: str = ""
    base_effect: ItemEffect = field(default_factory=ItemEffect)
    hidden_effect: ItemEffect = field(default_factory=ItemEffect)
    hidden_discovered: bool = False
    origin_type: str = ""  # "enemy_loot", "npc_gift", "quest_reward", "found"
    origin_name: str = ""  # 출처 이름 (적/NPC 이름)


class ItemGraph:
    """아이템과 그 관계를 관리하는 방향성 그래프.

    노드 타입:
      - item: 아이템 노드
      - effect: 효과 노드 (base / hidden)
      - npc_affinity: NPC 반응 노드

    엣지 관계:
      - has_effect: 아이템 → 효과 (base)
      - has_hidden: 아이템 → 히든 효과 (decayed=True면 미발견)
      - originated_from: 아이템 → 출처 (적/NPC)
      - affects_npc: 아이템 → NPC 반응 노드
      - grants_title: 아이템 조합 → 칭호
    """

    def __init__(self, theme: dict):
        self._graph = nx.DiGraph()
        self._items: dict[str, ItemNode] = {}
        self._titles: list[dict] = []  # 칭호 정의
        self._active_titles: list[str] = []  # 현재 활성 칭호
        self._load_from_theme(theme)

    def _load_from_theme(self, theme: dict):
        """테마 JSON에서 아이템 효과 정의를 로드."""
        item_defs = theme.get("item_effects", {})
        for item_name, item_data in item_defs.items():
            base = ItemEffect.from_dict(item_data.get("base_effect", {}))
            hidden = ItemEffect.from_dict(item_data.get("hidden_effect", {}))
            desc = item_data.get("description", "")
            npc_affinities = item_data.get("npc_affinity", {})

            node = ItemNode(
                name=item_name,
                description=desc,
                base_effect=base,
                hidden_effect=hidden,
            )
            self._items[item_name] = node

            # 그래프에 아이템 노드 추가
            item_id = f"item_{item_name}"
            self._graph.add_node(item_id, type="item", name=item_name, description=desc)

            # base effect 엣지
            if any(v != 0 for v in [base.attack, base.defense, base.max_hp, base.heal]):
                effect_id = f"effect_base_{item_name}"
                self._graph.add_node(effect_id, type="effect", subtype="base", **base.to_dict())
                self._graph.add_edge(item_id, effect_id, relation="has_effect")

            # hidden effect 엣지 (decayed=True → 미발견)
            if any(v != 0 for v in [hidden.attack, hidden.defense, hidden.max_hp, hidden.heal]):
                hidden_id = f"effect_hidden_{item_name}"
                self._graph.add_node(hidden_id, type="effect", subtype="hidden", **hidden.to_dict())
                self._graph.add_edge(item_id, hidden_id, relation="has_hidden", decayed=True)

            # NPC 반응 엣지
            for npc_name, affinity_data in npc_affinities.items():
                aff_id = f"affinity_{item_name}_{npc_name}_{uuid.uuid4().hex[:4]}"
                self._graph.add_node(
                    aff_id, type="npc_affinity",
                    npc_name=npc_name,
                    disposition_delta=affinity_data.get("disposition_delta", 0),
                    reaction=affinity_data.get("reaction", "neutral"),
                )
                self._graph.add_edge(item_id, aff_id, relation="affects_npc")

        # 칭호 정의 로드
        self._titles = theme.get("titles", [])

    # ── 아이템 추가 (게임 중 획득) ──

    def add_item(self, item_name: str, origin_type: str = "", origin_name: str = ""):
        """인벤토리에 아이템을 추가하고 출처 엣지를 연결."""
        item_id = f"item_{item_name}"

        if item_name in self._items:
            # 이미 정의된 아이템 → 출처 엣지만 추가
            node = self._items[item_name]
            node.origin_type = origin_type
            node.origin_name = origin_name
        else:
            # 테마에 정의되지 않은 아이템 → 기본 노드 생성
            node = ItemNode(
                name=item_name,
                origin_type=origin_type,
                origin_name=origin_name,
            )
            self._items[item_name] = node
            self._graph.add_node(item_id, type="item", name=item_name)

        # 출처 엣지
        if origin_name:
            origin_id = f"origin_{origin_name}_{uuid.uuid4().hex[:4]}"
            self._graph.add_node(
                origin_id, type="origin",
                origin_type=origin_type,
                name=origin_name,
            )
            self._graph.add_edge(item_id, origin_id, relation="originated_from")

    def remove_item(self, item_name: str):
        """인벤토리에서 아이템 제거 (소모품 사용 시)."""
        self._items.pop(item_name, None)
        # 그래프 노드는 보존 (이력 추적용)

    # ── 아이템 효과 조회 ──

    def get_item_effects(self, item_name: str) -> ItemEffect:
        """아이템의 현재 유효 효과 (base + 발견된 hidden)."""
        node = self._items.get(item_name)
        if not node:
            return ItemEffect()

        total = ItemEffect(
            attack=node.base_effect.attack,
            defense=node.base_effect.defense,
            max_hp=node.base_effect.max_hp,
            heal=node.base_effect.heal,
        )

        if node.hidden_discovered:
            total.attack += node.hidden_effect.attack
            total.defense += node.hidden_effect.defense
            total.max_hp += node.hidden_effect.max_hp
            total.heal += node.hidden_effect.heal

        return total

    def get_total_equipment_bonus(self, inventory: list[str]) -> dict:
        """인벤토리의 모든 장비형 아이템의 스탯 보너스 합산."""
        total = {"attack": 0, "defense": 0, "max_hp": 0}
        for item_name in inventory:
            effect = self.get_item_effects(item_name)
            if not effect.is_consumable:
                total["attack"] += effect.attack
                total["defense"] += effect.defense
                total["max_hp"] += effect.max_hp
        return total

    def get_consumable_heal(self, item_name: str) -> int:
        """소모품 아이템의 회복량."""
        effect = self.get_item_effects(item_name)
        return effect.heal if effect.is_consumable else 15  # 기본 회복량

    # ── 히든 효과 발견 (조사) ──

    def investigate_item(self, item_name: str) -> dict | None:
        """아이템을 조사하여 히든 효과를 발견.

        히든 효과 엣지의 decayed를 제거하여 '발견' 처리.
        NPC 메모리의 엣지 복원과 동일한 패턴.

        Returns:
            발견된 히든 효과 정보 또는 None (이미 발견/히든 없음)
        """
        node = self._items.get(item_name)
        if not node:
            return None

        if node.hidden_discovered:
            return None  # 이미 발견됨

        # 히든 효과가 있는지 확인
        item_id = f"item_{item_name}"
        hidden_edges = [
            (u, v, d) for u, v, d in self._graph.out_edges(item_id, data=True)
            if d.get("relation") == "has_hidden"
        ]

        if not hidden_edges:
            return None

        # 엣지 복원 (decayed 제거)
        for u, v, d in hidden_edges:
            self._graph.edges[u, v]["decayed"] = False

        node.hidden_discovered = True

        return {
            "item": item_name,
            "hidden_effect": node.hidden_effect.to_dict(),
            "description": f"'{item_name}'에서 숨겨진 힘이 깨어났다!",
        }

    def investigate_item_via_npc(self, item_name: str, npc_name: str) -> dict | None:
        """NPC와 대화 중 아이템을 언급하여 히든 효과를 발견.

        특정 NPC가 아이템의 출처나 반응 엣지로 연결되어 있을 때
        히든 효과가 드러난다.
        """
        node = self._items.get(item_name)
        if not node or node.hidden_discovered:
            return None

        # NPC와의 연결 확인 (affinity 또는 origin)
        item_id = f"item_{item_name}"
        has_connection = False

        for _, v, d in self._graph.out_edges(item_id, data=True):
            target = self._graph.nodes.get(v, {})
            if target.get("npc_name") == npc_name:
                has_connection = True
                break
            if target.get("name") == npc_name:
                has_connection = True
                break

        if not has_connection:
            return None

        return self.investigate_item(item_name)

    # ── NPC 반응 조회 ──

    def get_npc_affinities_for_inventory(self, inventory: list[str]) -> dict[str, float]:
        """인벤토리의 아이템들이 NPC에 미치는 호감도 영향 합산.

        Returns:
            {npc_name: total_disposition_delta}
        """
        affinities: dict[str, float] = {}

        for item_name in inventory:
            item_id = f"item_{item_name}"
            if not self._graph.has_node(item_id):
                continue

            for _, v, d in self._graph.out_edges(item_id, data=True):
                if d.get("relation") != "affects_npc":
                    continue
                target = self._graph.nodes.get(v, {})
                npc_name = target.get("npc_name", "")
                delta = target.get("disposition_delta", 0)
                if npc_name:
                    affinities[npc_name] = affinities.get(npc_name, 0) + delta

        return affinities

    def get_npc_reaction(self, item_name: str, npc_name: str) -> str:
        """특정 NPC가 특정 아이템에 대해 보이는 반응."""
        item_id = f"item_{item_name}"
        if not self._graph.has_node(item_id):
            return "neutral"

        for _, v, d in self._graph.out_edges(item_id, data=True):
            if d.get("relation") != "affects_npc":
                continue
            target = self._graph.nodes.get(v, {})
            if target.get("npc_name") == npc_name:
                return target.get("reaction", "neutral")

        return "neutral"

    # ── 칭호 시스템 ──

    def evaluate_titles(self, inventory: list[str], world_state) -> list[dict]:
        """현재 인벤토리와 월드 스테이트를 기반으로 칭호를 평가.

        칭호 조건:
          - required_items: 필수 아이템 목록
          - min_hidden_discovered: 최소 히든 효과 발견 수
          - gauge_condition: 게이지 조건
          - entities_removed_min: 처치한 적 수
        """
        earned = []
        discovered_count = sum(
            1 for n in self._items.values() if n.hidden_discovered
        )

        for title in self._titles:
            conditions = title.get("conditions", {})

            # 필수 아이템
            required = conditions.get("required_items", [])
            if required and not all(item in inventory for item in required):
                continue

            # 히든 효과 발견 수
            min_hidden = conditions.get("min_hidden_discovered", 0)
            if discovered_count < min_hidden:
                continue

            # 게이지 조건
            gauge_conds = conditions.get("gauges", {})
            gauge_ok = True
            for gauge_name, rule in gauge_conds.items():
                if gauge_name not in world_state.gauges:
                    gauge_ok = False
                    break
                import operator as op
                ops = {">=": op.ge, ">": op.gt, "<=": op.le, "<": op.lt, "==": op.eq}
                op_func = ops.get(rule.get("op", ">="))
                if op_func and not op_func(world_state.gauges[gauge_name], rule["value"]):
                    gauge_ok = False
                    break
            if not gauge_ok:
                continue

            # 처치 수
            removed_min = conditions.get("entities_removed_min", 0)
            if removed_min > 0:
                removed = len(world_state.get_removed_entities())
                if removed < removed_min:
                    continue

            earned.append(title)

        # 새로 획득한 칭호 추적
        new_titles = []
        for t in earned:
            if t["id"] not in self._active_titles:
                self._active_titles.append(t["id"])
                new_titles.append(t)

        return new_titles

    def get_active_titles(self) -> list[dict]:
        """현재 활성 칭호 목록."""
        return [t for t in self._titles if t["id"] in self._active_titles]

    def get_title_bonus(self) -> dict:
        """활성 칭호들의 스탯 보너스 합산."""
        total = {"attack": 0, "defense": 0, "max_hp": 0}
        for title in self.get_active_titles():
            bonus = title.get("bonus", {})
            total["attack"] += bonus.get("attack", 0)
            total["defense"] += bonus.get("defense", 0)
            total["max_hp"] += bonus.get("max_hp", 0)
        return total

    # ── 아이템 정보 조회 ──

    def get_item_info(self, item_name: str) -> dict | None:
        """아이템의 전체 정보 (UI 표시용)."""
        node = self._items.get(item_name)
        if not node:
            return None

        effect = self.get_item_effects(item_name)
        info = {
            "name": item_name,
            "description": node.description,
            "base_effect": node.base_effect.to_dict(),
            "total_effect": effect.to_dict(),
            "is_consumable": effect.is_consumable,
            "hidden_discovered": node.hidden_discovered,
            "has_hidden": any(
                v != 0 for v in [
                    node.hidden_effect.attack, node.hidden_effect.defense,
                    node.hidden_effect.max_hp, node.hidden_effect.heal,
                ]
            ),
            "origin_type": node.origin_type,
            "origin_name": node.origin_name,
        }

        # 히든 효과가 발견됐으면 표시
        if node.hidden_discovered:
            info["hidden_effect"] = node.hidden_effect.to_dict()

        return info

    def get_all_items_info(self, inventory: list[str]) -> list[dict]:
        """인벤토리의 모든 아이템 정보."""
        return [
            self.get_item_info(name)
            for name in inventory
            if self.get_item_info(name)
        ]
