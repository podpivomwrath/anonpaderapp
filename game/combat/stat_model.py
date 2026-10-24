"""Как характеристики превращаются в проценты боя (2026-10-24).

Одна точка для крита, уворота, снижения урона, сопротивления контролю, силы
поддержки и силы эффектов. Игра считает по CURRENT - те же формулы, что в
game/combat/formulas.py, число в число (tests/test_stat_model.py).

Зачем модель, а не только функции formulas: обсуждается ребаланс статов
(игроки качают один стат - остальные почти ничего не дают). Симулятор
(tools/sim_stat_model.py) подставляет сюда другие правила через use() и
сравнивает сборки, не трогая игру. В бою модель меняют только инструменты.
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
    base_crit: dict | None = None        # подкласс -> прибавка к криту (компенсация)
    base_dodge: dict | None = None

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
        return hyper(will, self.resist_cap, self.resist_k)

    def effect_power(self, s) -> float:
        return 1.0 + self.effect_per_int * s.intellect

    def support_power(self, s) -> float:
        if self.support_per_int:
            return self.support_per_int * s.intellect
        return formulas.support_power(s.will)


CURRENT = StatModel()
ACTIVE: StatModel = CURRENT


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
