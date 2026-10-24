"""Как характеристики превращаются в проценты боя (2026-10-24).

Одна точка для урона основного стата, крита, уворота, снижения урона,
сопротивления контролю, силы поддержки и силы эффектов.

Игра считает по GAME (ребаланс 2026-10-24, владелец: игроки качали один стат,
остальные почти ничего не давали): проценты - с убывающей отдачей, уворот -
от Воли, урон основного стата сверх порога 30 + 2 x уровень идёт по 0.35.
CURRENT - прежние формулы game/combat/formulas.py, для сравнения в
симуляторе (tools/sim_stat_model.py подменяет модель через use()).
"""

from __future__ import annotations

from dataclasses import dataclass

from game.combat import balance_config as bc
from game.combat import formulas


def hyper(x: float, cap: float, k: float) -> float:
    """Убывающая отдача: cap * x / (x + k). Первые очки дают много, сотые мало."""
    return cap * x / (x + k) if x > 0 else 0.0


@dataclass
class StatModel:
    name: str = "current"

    def primary_value(self, value: int, level: int, is_player: bool, stat: str = "str") -> float:
        """Сколько основного стата идёт в урон. Сейчас - всё, линейно."""
        return value

    def crit_chance(self, s) -> float:
        return formulas.crit_chance(s.agility)

    def crit_multiplier_bonus(self, s) -> float:
        """Прибавка к множителю крита (база - bc.CRIT_MULTIPLIER или навыка)."""
        return 0.0

    def dodge(self, s, is_ability: bool) -> float:
        return formulas.ability_dodge_chance(s.agility) if is_ability else formulas.dodge_chance(s.agility)

    def mitigation(self, s) -> float:
        return formulas.mitigation(s.vitality)

    def control_resist(self, will: int) -> float:
        return formulas.control_resist(will)

    def support_power(self, s) -> float:
        return formulas.support_power(s.will)

    def effect_power(self, s) -> float:
        """Множитель яда, горения и вампиризма. Сейчас статы на них не влияют."""
        return 1.0


@dataclass
class HyperModel(StatModel):
    """Вариант ребаланса для симулятора. Проценты - с убывающей отдачей,
    источники процентов настраиваются, чтобы сравнивать варианты."""

    name: str = "hyper"
    crit_cap: float = 0.60
    crit_k: float = 200.0
    dodge_cap: float = 0.45
    dodge_k: float = 250.0
    dodge_stat: str = "agility"          # agility | will
    mit_cap: float = 0.50
    mit_k: float = 250.0
    resist_cap: float = 0.75
    resist_k: float = 100.0
    crit_dmg_per_str: float = 0.0        # прибавка к множителю крита за очко Силы
    effect_per_int: float = 0.0          # сила яда, горения, вампиризма за очко Интеллекта
    support_per_int: float = 0.0         # доля силы поддержки от Интеллекта вместо Воли
    resist_hyper: bool = True            # False - сопротивление контролю по-старому, линейно
    base_crit: dict | None = None        # подкласс -> прибавка к криту (компенсация)
    base_dodge: dict | None = None
    #: Убывание урона основного стата у игроков: до порога base + per_level *
    #: уровень - полностью, сверх - доля over. over=None - линейно, как сейчас.
    primary_soft_base: float = 30.0
    primary_soft_per_level: float = 2.0
    primary_over: float | None = None
    #: Множитель урона от основного стата игрока - вернуть урон, срезанный
    #: порогом, чтобы контент (разломы, рейды) не стал сложнее для всех.
    primary_k_mult: float = 1.0
    #: Порог по стату: Ловкость даёт 1.5 урона за очко против 2 у Силы и
    #: Интеллекта, поэтому её порог выше в 2/1.5 раза - одинаковый по урону
    #: (2026-10-24, разбойники после ребаланса потеряли больше всех).
    primary_soft_stat_mult: dict | None = None

    def primary_value(self, value: int, level: int, is_player: bool, stat: str = "str") -> float:
        if self.primary_over is None or not is_player:
            return value
        threshold = (self.primary_soft_base + self.primary_soft_per_level * level) *             (self.primary_soft_stat_mult or {}).get(stat, 1.0)
        eff = value if value <= threshold else threshold + (value - threshold) * self.primary_over
        return eff * self.primary_k_mult

    def crit_chance(self, s) -> float:
        return hyper(s.agility, self.crit_cap, self.crit_k)

    def crit_multiplier_bonus(self, s) -> float:
        return self.crit_dmg_per_str * s.strength

    def dodge(self, s, is_ability: bool) -> float:
        value = hyper(getattr(s, self.dodge_stat), self.dodge_cap, self.dodge_k)
        return value * bc.ABILITY_DODGE_RATIO if is_ability else value

    def mitigation(self, s) -> float:
        return hyper(s.vitality, self.mit_cap, self.mit_k)

    def control_resist(self, will: int) -> float:
        if not self.resist_hyper:
            return formulas.control_resist(will)
        return hyper(will, self.resist_cap, self.resist_k)

    def effect_power(self, s) -> float:
        return 1.0 + self.effect_per_int * s.intellect

    def support_power(self, s) -> float:
        if self.support_per_int:
            return self.support_per_int * s.intellect
        return formulas.support_power(s.will)


CURRENT = StatModel()
#: Правила игры с 2026-10-24 (вариант D2 симулятора). Сопротивление контролю
#: оставлено прежним: правка про PvE и моностат, PvP-контроль не трогаем.
#: Разбойники теряли сразу крит и уворот с Ловкости - подкласс возвращает
#: часть (tools/balance_check.py: все подклассы в коридорах).
GAME = HyperModel(
    name="game", dodge_stat="will", primary_over=0.35, resist_hyper=False,
    primary_soft_stat_mult={"agi": 4 / 3},
    # Клинок теней живёт критами - ему больше (2026-10-24, владелец: «урон плох»).
    base_crit={"shadow_blade": 0.15, "poisoner": 0.10},
    base_dodge={"shadow_blade": 0.05, "poisoner": 0.05},
)
ACTIVE: StatModel = GAME


def use(model: StatModel) -> None:
    """Только для инструментов: подменить правила на время прогона."""
    global ACTIVE
    ACTIVE = model


def subclass_crit_bonus(subclass_id: str | None) -> float:
    model = ACTIVE
    return (getattr(model, "base_crit", None) or {}).get(subclass_id or "", 0.0)


def subclass_dodge_bonus(subclass_id: str | None) -> float:
    model = ACTIVE
    return (getattr(model, "base_dodge", None) or {}).get(subclass_id or "", 0.0)
