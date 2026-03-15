"""전투 엔진 — 코드 기반 전투 판정 시스템.

전투 로직(데미지 계산, HP, 행동 판정)은 Python 코드가 처리하고,
전투 묘사/나레이션은 LLM이 담당한다.

전투 라운드는 StoryGraph에 combat 타입 노드로 기록되어
LLM이 전투 맥락을 파악하고 일관된 스토리를 생성할 수 있다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# ── 전투 행동 ──

COMBAT_ACTIONS = {
    "attack": "공격",
    "defend": "방어",
    "skill": "스킬",
    "item": "아이템 사용",
    "flee": "도주",
}


@dataclass
class EnemyTemplate:
    """테마 JSON에서 로드되는 적 정의."""

    name: str
    hp: int
    attack: int
    defense: int
    description: str = ""
    abilities: list[dict] = field(default_factory=list)  # [{"name": ..., "damage": ..., "chance": ...}]
    loot: list[str] = field(default_factory=list)  # 드랍 아이템
    stage: str = "default"  # 출현 스테이지


@dataclass
class CombatEntity:
    """전투 중 엔티티 (플레이어 또는 적)."""

    name: str
    max_hp: int
    hp: int
    attack: int
    defense: int
    is_defending: bool = False

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    @property
    def hp_bar(self) -> str:
        """HP 바 시각화."""
        ratio = self.hp / self.max_hp if self.max_hp > 0 else 0
        filled = int(ratio * 20)
        bar = "█" * filled + "░" * (20 - filled)
        return f"[{bar}] {self.hp}/{self.max_hp}"

    def take_damage(self, raw_damage: int) -> int:
        """데미지를 받고 실제 적용된 데미지를 반환."""
        effective_defense = self.defense
        if self.is_defending:
            effective_defense = int(effective_defense * 1.5)
            self.is_defending = False

        actual_damage = max(1, raw_damage - effective_defense)

        # 크리티컬/미스 변동 (±20%)
        variance = random.randint(-20, 20) / 100
        actual_damage = max(1, int(actual_damage * (1 + variance)))

        self.hp = max(0, self.hp - actual_damage)
        return actual_damage


@dataclass
class CombatAction:
    """단일 전투 행동과 결과."""

    actor: str
    action_type: str  # attack, defend, skill, item, flee
    target: str | None = None
    damage_dealt: int = 0
    detail: str = ""
    success: bool = True


@dataclass
class RoundResult:
    """한 라운드의 결과."""

    round_number: int
    player_action: CombatAction
    enemy_action: CombatAction
    player_hp: int
    player_max_hp: int
    enemy_hp: int
    enemy_max_hp: int
    combat_log: str = ""


@dataclass
class CombatResult:
    """전투 최종 결과."""

    outcome: str  # "victory", "defeat", "flee"
    rounds: list[RoundResult]
    enemy_name: str
    loot: list[str]
    total_damage_dealt: int = 0
    total_damage_taken: int = 0

    def to_graph_summary(self) -> str:
        """그래프 노드에 기록할 전투 요약."""
        outcome_text = {"victory": "승리", "defeat": "패배", "flee": "도주"}
        lines = [
            f"[전투: {self.enemy_name}] 결과: {outcome_text.get(self.outcome, self.outcome)}",
            f"총 {len(self.rounds)}라운드 | 가한 피해: {self.total_damage_dealt} | 받은 피해: {self.total_damage_taken}",
        ]
        if self.loot:
            lines.append(f"획득: {', '.join(self.loot)}")
        return " | ".join(lines)

    def to_round_summaries(self) -> list[str]:
        """각 라운드의 요약 텍스트 목록 (그래프 노드용)."""
        summaries = []
        for r in self.rounds:
            summary = (
                f"라운드 {r.round_number}: "
                f"플레이어({r.player_action.action_type}) → {r.player_action.detail} | "
                f"적({r.enemy_action.action_type}) → {r.enemy_action.detail} | "
                f"HP: {r.player_hp}/{r.player_max_hp} vs {r.enemy_hp}/{r.enemy_max_hp}"
            )
            summaries.append(summary)
        return summaries


class CombatEngine:
    """전투 판정 엔진. 순수 Python 로직으로 전투를 처리."""

    def __init__(self, player: CombatEntity, enemy: CombatEntity,
                 enemy_abilities: list[dict] | None = None,
                 player_items: list[str] | None = None):
        self.player = player
        self.enemy = enemy
        self._enemy_abilities = enemy_abilities or []
        self._player_items = player_items or []
        self._round = 0
        self._rounds: list[RoundResult] = []

    @classmethod
    def from_template(cls, enemy_template: EnemyTemplate,
                      world_state) -> CombatEngine:
        """적 템플릿과 월드 스테이트에서 전투 엔진 생성."""
        # 플레이어 스탯: 월드 스테이트 게이지에서 파생
        player_hp = int(world_state.gauges.get("health", 1.0) * 100)
        player_hp = max(10, player_hp)  # 최소 10

        player_attack = 10 + len(world_state.collections.get("inventory", [])) * 2
        player_defense = 5

        # 봉인 게이지가 높으면 공격력 보너스
        seal_bonus = int(world_state.gauges.get("seal", 0.0) * 10)
        player_attack += seal_bonus

        player = CombatEntity(
            name="수호자",
            max_hp=player_hp,
            hp=player_hp,
            attack=player_attack,
            defense=player_defense,
        )

        enemy = CombatEntity(
            name=enemy_template.name,
            max_hp=enemy_template.hp,
            hp=enemy_template.hp,
            attack=enemy_template.attack,
            defense=enemy_template.defense,
        )

        return cls(
            player=player,
            enemy=enemy,
            enemy_abilities=enemy_template.abilities,
            player_items=list(world_state.collections.get("inventory", [])),
        )

    # ── 플레이어 행동 ──

    def execute_player_attack(self) -> CombatAction:
        """기본 공격."""
        damage = self.enemy.take_damage(self.player.attack)
        return CombatAction(
            actor=self.player.name,
            action_type="attack",
            target=self.enemy.name,
            damage_dealt=damage,
            detail=f"{self.enemy.name}에게 {damage} 피해",
        )

    def execute_player_defend(self) -> CombatAction:
        """방어 태세 — 다음 적 공격의 데미지 감소."""
        self.player.is_defending = True
        return CombatAction(
            actor=self.player.name,
            action_type="defend",
            detail="방어 태세 (방어력 1.5배)",
        )

    def execute_player_skill(self) -> CombatAction:
        """강공격 — 높은 데미지, 약간의 실패 확률."""
        if random.random() < 0.15:  # 15% 실패
            return CombatAction(
                actor=self.player.name,
                action_type="skill",
                target=self.enemy.name,
                damage_dealt=0,
                detail="강공격 실패!",
                success=False,
            )

        boosted_attack = int(self.player.attack * 1.8)
        damage = self.enemy.take_damage(boosted_attack)
        return CombatAction(
            actor=self.player.name,
            action_type="skill",
            target=self.enemy.name,
            damage_dealt=damage,
            detail=f"강공격! {self.enemy.name}에게 {damage} 피해",
        )

    def execute_player_item(self, item_name: str) -> CombatAction:
        """아이템 사용 — 회복 또는 버프."""
        heal = random.randint(15, 30)
        self.player.hp = min(self.player.max_hp, self.player.hp + heal)

        if item_name in self._player_items:
            self._player_items.remove(item_name)

        return CombatAction(
            actor=self.player.name,
            action_type="item",
            detail=f"'{item_name}' 사용 → HP {heal} 회복 (현재: {self.player.hp}/{self.player.max_hp})",
        )

    def execute_player_flee(self) -> CombatAction:
        """도주 시도 — HP가 낮을수록 성공률 증가."""
        hp_ratio = self.player.hp / self.player.max_hp
        flee_chance = 0.3 + (1 - hp_ratio) * 0.4  # 30%~70%

        success = random.random() < flee_chance
        return CombatAction(
            actor=self.player.name,
            action_type="flee",
            detail="도주 성공!" if success else "도주 실패!",
            success=success,
        )

    # ── 적 AI ──

    def execute_enemy_action(self) -> CombatAction:
        """적 행동 AI — 상황에 따라 행동 결정."""
        # 특수 능력 사용 확률 체크
        for ability in self._enemy_abilities:
            if random.random() < ability.get("chance", 0.2):
                damage = self.player.take_damage(ability.get("damage", self.enemy.attack))
                return CombatAction(
                    actor=self.enemy.name,
                    action_type="skill",
                    target=self.player.name,
                    damage_dealt=damage,
                    detail=f"{ability['name']}! {self.player.name}에게 {damage} 피해",
                )

        # HP가 낮으면 강공격 확률 증가
        if self.enemy.hp < self.enemy.max_hp * 0.3 and random.random() < 0.4:
            boosted = int(self.enemy.attack * 1.5)
            damage = self.player.take_damage(boosted)
            return CombatAction(
                actor=self.enemy.name,
                action_type="skill",
                target=self.player.name,
                damage_dealt=damage,
                detail=f"필사의 공격! {self.player.name}에게 {damage} 피해",
            )

        # 기본 공격
        damage = self.player.take_damage(self.enemy.attack)
        return CombatAction(
            actor=self.enemy.name,
            action_type="attack",
            target=self.player.name,
            damage_dealt=damage,
            detail=f"{self.player.name}에게 {damage} 피해",
        )

    # ── 라운드 실행 ──

    def execute_round(self, player_action: str, item_name: str = "") -> RoundResult:
        """한 라운드 실행."""
        self._round += 1

        # 플레이어 행동
        if player_action == "attack":
            p_action = self.execute_player_attack()
        elif player_action == "defend":
            p_action = self.execute_player_defend()
        elif player_action == "skill":
            p_action = self.execute_player_skill()
        elif player_action == "item":
            p_action = self.execute_player_item(item_name)
        elif player_action == "flee":
            p_action = self.execute_player_flee()
        else:
            p_action = self.execute_player_attack()

        # 도주 성공 시 적 행동 없음
        if player_action == "flee" and p_action.success:
            e_action = CombatAction(actor=self.enemy.name, action_type="none", detail="(도주됨)")
        elif not self.enemy.is_alive:
            e_action = CombatAction(actor=self.enemy.name, action_type="none", detail="(쓰러짐)")
        else:
            e_action = self.execute_enemy_action()

        result = RoundResult(
            round_number=self._round,
            player_action=p_action,
            enemy_action=e_action,
            player_hp=self.player.hp,
            player_max_hp=self.player.max_hp,
            enemy_hp=self.enemy.hp,
            enemy_max_hp=self.enemy.max_hp,
        )

        # 전투 로그 구성
        log_lines = [f"── 라운드 {self._round} ──"]
        log_lines.append(f"  {self.player.name}: {p_action.detail}")
        if e_action.action_type != "none":
            log_lines.append(f"  {self.enemy.name}: {e_action.detail}")
        log_lines.append(f"  {self.player.name} {self.player.hp_bar}")
        log_lines.append(f"  {self.enemy.name} {self.enemy.hp_bar}")
        result.combat_log = "\n".join(log_lines)

        self._rounds.append(result)
        return result

    # ── 전투 종료 판정 ──

    @property
    def is_over(self) -> bool:
        return not self.player.is_alive or not self.enemy.is_alive

    def get_result(self, fled: bool = False) -> CombatResult:
        """전투 최종 결과를 생성."""
        if fled:
            outcome = "flee"
        elif not self.enemy.is_alive:
            outcome = "victory"
        else:
            outcome = "defeat"

        total_dealt = sum(r.player_action.damage_dealt for r in self._rounds)
        total_taken = sum(r.enemy_action.damage_dealt for r in self._rounds)

        return CombatResult(
            outcome=outcome,
            rounds=self._rounds,
            enemy_name=self.enemy.name,
            loot=[],  # 승리 시 game.py에서 설정
            total_damage_dealt=total_dealt,
            total_damage_taken=total_taken,
        )


class EnemyRegistry:
    """테마 JSON에서 적 정의를 로드하고 관리."""

    def __init__(self, theme: dict):
        self._enemies: dict[str, EnemyTemplate] = {}
        self._load_from_theme(theme)

    def _load_from_theme(self, theme: dict):
        """테마 JSON의 enemies에서 적 정의 로드."""
        enemies = theme.get("enemies", [])
        for e in enemies:
            template = EnemyTemplate(
                name=e["name"],
                hp=e.get("hp", 50),
                attack=e.get("attack", 8),
                defense=e.get("defense", 3),
                description=e.get("description", ""),
                abilities=e.get("abilities", []),
                loot=e.get("loot", []),
                stage=e.get("stage", "default"),
            )
            self._enemies[template.name] = template

    def get_enemy(self, name: str) -> EnemyTemplate | None:
        return self._enemies.get(name)

    def get_enemies_at_stage(self, stage: str) -> list[EnemyTemplate]:
        return [e for e in self._enemies.values() if e.stage == stage]

    def get_random_enemy(self, stage: str | None = None) -> EnemyTemplate | None:
        """스테이지에 맞는 랜덤 적 반환."""
        if stage:
            candidates = self.get_enemies_at_stage(stage)
        else:
            candidates = list(self._enemies.values())

        return random.choice(candidates) if candidates else None

    def get_all_enemy_names(self) -> list[str]:
        return list(self._enemies.keys())
