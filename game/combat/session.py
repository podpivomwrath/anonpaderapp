"""Runtime-состояние боя (в памяти движка; БД хранит только персистентный снимок).

CombatantState/CombatSessionState — рабочие объекты tick_engine и duel_engine.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, Field

from game.combat import balance_config as bc
from game.combat import formulas


class CombatMode(StrEnum):
    PVE = "pve"              # соло/группа против мобов: без таймера, ждём всех живых игроков
    PVP_GROUP = "pvp_group"  # групповой PvP: таймер 1 мин + досрочный резолв
    DUEL = "duel"            # 1×1, последовательные ходы (duel_engine)


class ActionType(StrEnum):
    ATTACK = "attack"
    SKILL = "skill"
    SKIP = "skip"


class EffectKind(StrEnum):
    DOT = "dot"                    # периодический урон (value = урон за ход)
    VULNERABILITY = "vulnerability"  # входящий урон * (1 + value)
    WEAKEN = "weaken"              # исходящий урон * (1 - value)
    FREEZE = "freeze"              # пропуск действия в ход (оглушение/заморозка)
    PROVOKE_PVP = "provoke_pvp"    # PvP-провокация: урон по целям != source * (1 - value)
    MARK = "mark"                  # стаки «Метки добычи» Клинка теней
    DAMAGE_BUFF = "damage_buff"    # исходящий урон * (1 + value) — Боевой клич
    DODGE = "dodge"                # шанс полного уклонения от входящего удара — Дымовая завеса


class DeclaredAction(BaseModel):
    """Действие, объявленное в окно тика / ход дуэли."""

    type: ActionType = ActionType.SKIP
    target_id: int | None = None
    skill_id: str | None = None
    payload: dict = Field(default_factory=dict)


@dataclass
class Stats:
    strength: int = bc.STARTING_STAT
    agility: int = bc.STARTING_STAT
    intellect: int = bc.STARTING_STAT
    vitality: int = bc.STARTING_STAT
    will: int = bc.STARTING_STAT

    def by_key(self, key: str) -> int:
        return {
            "str": self.strength,
            "agi": self.agility,
            "int": self.intellect,
            "vit": self.vitality,
            "wil": self.will,
        }[key]


@dataclass
class Effect:
    kind: EffectKind
    value: float
    remaining_ticks: int
    source_id: int
    stacks: int = 1


@dataclass
class CombatantState:
    id: int
    side: int              # 0/1; в PvE игроки — 0, мобы — 1
    kind: str              # "character" | "mob"
    name: str
    level: int
    stats: Stats
    primary_stat: str      # "str" | "agi" | "int"
    tier: str
    max_hp: int
    current_hp: int
    subclass_id: str | None = None

    # Однотиковые защитные состояния (сбрасываются после резолва тика /
    # в дуэли — в начале собственного хода)
    shield: int = 0                 # пул поглощения
    block_reduction: float = 0.0    # доля срезаемого входящего урона
    mitigation_penalty: float = 0.0  # штраф к митигации (групповой щит стража)
    taunted_by: int | None = None   # PvE-форс цели для моба

    effects: list[Effect] = field(default_factory=list)
    # Кулдауны навыков в ходах боя {skill_id: осталось}; сбрасываются между
    # боями естественно (новый CombatantState на каждую встречу).
    cooldowns: dict[str, int] = field(default_factory=dict)

    # --- Защита от чейн-контроля (diminishing returns, progression-patch-4/8) ---
    # Стрик считает ходы, ПРОПУЩЕННЫЕ из-за контроля подряд (не число наложений):
    # долгая заморозка тоже накручивает стрик каждым пропущенным ходом.
    control_streak: int = 0            # подряд пропущенных из-за контроля ходов
    control_immune_turns: int = 0      # осталось ходов иммунитета к контролю
    skipped_by_control_this_turn: bool = False  # transient: пропустил ход из-за контроля

    @property
    def alive(self) -> bool:
        return self.current_hp > 0

    @property
    def tier_mult(self) -> float:
        return formulas.tier_multiplier(self.tier)

    def effect_total(self, kind: EffectKind) -> float:
        return sum(e.value * e.stacks for e in self.effects if e.kind == kind)

    def has_effect(self, kind: EffectKind) -> bool:
        return any(e.kind == kind for e in self.effects)

    def effects_of(self, kind: EffectKind) -> list[Effect]:
        return [e for e in self.effects if e.kind == kind]

    def apply_effect(
        self, kind: EffectKind, value: float, duration: int, source_id: int
    ) -> None:
        """Наложить временный эффект. Non-stacking: повторное применение того же
        вида от того же источника ОБНОВЛЯЕТ значение и длительность, не суммирует."""
        for effect in self.effects:
            if effect.kind == kind and effect.source_id == source_id:
                effect.value = value
                effect.remaining_ticks = max(effect.remaining_ticks, duration)
                return
        self.effects.append(Effect(kind=kind, value=value, remaining_ticks=duration, source_id=source_id))

    def is_on_cooldown(self, skill_id: str) -> bool:
        return self.cooldowns.get(skill_id, 0) > 0

    def tick_cooldowns(self) -> None:
        for skill_id in list(self.cooldowns):
            self.cooldowns[skill_id] -= 1
            if self.cooldowns[skill_id] <= 0:
                del self.cooldowns[skill_id]

    def reset_transient(self) -> None:
        self.shield = 0
        self.block_reduction = 0.0
        self.mitigation_penalty = 0.0
        self.taunted_by = None


def build_combatant(
    id: int,
    side: int,
    kind: str,
    name: str,
    level: int,
    stats: Stats,
    primary_stat: str,
    subclass_id: str | None = None,
    tier: str | None = None,
) -> CombatantState:
    """Собирает участника, считая HP/тир по формулам v2."""
    tier = tier or formulas.tier_for_level(level)
    max_hp = round(formulas.hp(level, stats.vitality, formulas.tier_multiplier(tier)))
    return CombatantState(
        id=id,
        side=side,
        kind=kind,
        name=name,
        level=level,
        stats=stats,
        primary_stat=primary_stat,
        tier=tier,
        max_hp=max_hp,
        current_hp=max_hp,
        subclass_id=subclass_id,
    )


@dataclass
class CombatSessionState:
    session_id: int
    mode: CombatMode
    combatants: dict[int, CombatantState] = field(default_factory=dict)
    tick_number: int = 0
    is_raid: bool = False  # влияет на точность % в логе (п.11)

    def add(self, combatant: CombatantState) -> None:
        self.combatants[combatant.id] = combatant

    def alive_on_side(self, side: int) -> list[CombatantState]:
        return [c for c in self.combatants.values() if c.side == side and c.alive]

    def alive_enemies_of(self, combatant: CombatantState) -> list[CombatantState]:
        return [
            c for c in self.combatants.values() if c.side != combatant.side and c.alive
        ]

    def alive_allies_of(self, combatant: CombatantState) -> list[CombatantState]:
        return [
            c
            for c in self.combatants.values()
            if c.side == combatant.side and c.alive and c.id != combatant.id
        ]

    def expected_declarers(self) -> set[int]:
        """Кто должен объявить действие в тик: живые игроки (мобы — AI)."""
        return {
            c.id
            for c in self.combatants.values()
            if c.alive and c.kind == "character"
        }

    def sides_alive(self) -> set[int]:
        return {c.side for c in self.combatants.values() if c.alive}
