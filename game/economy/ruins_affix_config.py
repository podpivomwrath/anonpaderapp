"""Навыки обычных мобов руин (2026-11-13, идея Есты, решения владельца).

Вместо надбавки уровня мобам руин с глубиной достаются навыки: отражение,
регенерация, вампиризм и так далее. Механики - готовые, из
game/combat/mob_abilities.py (те же, что у мобов карты); здесь только
каталог и числа.

Как раздаются:
- этажи 1-5 - без навыков; с 6-го один навык, с 16-го два, с 31-го три
  (AFFIX_COUNTS). Разыгрываются на каждый бой (2026-11-14, владелец: на
  весь этаж выходил один и тот же), внутри боя у мобов общие;
- элита и хозяин этажа - на один навык больше (свой, не из общих);
- уникальные боссы и мимик - без навыков, у них свои механики;
- сила растёт ступенью раз в TIER_FLOORS этажей («Отражение II») до потолка
  навыка. Ступени не кончаются: каталог рассчитан и на этажи после
  расширения капов.

Немота (2026-11-13, владелец): глушит то, что моб делает своим ходом
(вампиризм, яд, ярость). Тело (уворот, каменная кожа, отражение,
регенерация, последний вздох) работает и под ней - флаг
CombatantState.silence_keeps_body.

Новый навык - строка в AFFIXES; новая механика - kind в mob_abilities.KINDS.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

#: (с какого этажа, сколько навыков у мобов этажа). Дописывается вниз.
AFFIX_COUNTS: tuple[tuple[int, int], ...] = ((6, 1), (16, 2), (31, 3))
#: Сколько этажей на ступень силы. Этажи 6-10 - ступень I, 11-15 - II...
TIER_FLOORS = 5
#: Элите и хозяину этажа - столько навыков сверх этажных.
ELITE_EXTRA = 1

ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


@dataclass(frozen=True)
class Affix:
    id: str
    title: str
    #: подсказка перед боем, {p} - сила в процентах
    hint: str
    kind: str
    #: сила на ступени I, прибавка за ступень, потолок
    base: float
    step: float = 0.0
    cap: float = 0.0
    #: с какого этажа навык может выпасть
    min_floor: int = 1
    #: прочие поля MobTraitDef (threshold, duration, effect...)
    extra: dict = field(default_factory=dict)

    def value(self, tier: int) -> float:
        v = self.base + self.step * (max(tier, 1) - 1)
        return min(v, self.cap) if self.cap else v


AFFIXES: tuple[Affix, ...] = (
    # 2026-11-13, владелец: отражение с 20% до 50% (было предложено 5-20%).
    Affix("reflect", "Отражение", "отражают {p}% урона ударившему", "reflect", 0.20, 0.05, 0.50),
    Affix("regen", "Регенерация", "восстанавливают {p}% здоровья за ход", "regen", 0.015, 0.005, 0.04),
    Affix("lifesteal", "Кровопийца", "лечатся на {p}% нанесённого урона", "lifesteal", 0.15, 0.10, 0.60),
    Affix("stone_skin", "Каменная кожа", "получают на {p}% меньше урона", "armor_start", 0.10, 0.05, 0.35,
          extra={"duration": 999}),
    Affix("dodge", "Увёртливость", "уклоняются от {p}% ударов", "dodge", 0.08, 0.04, 0.25),
    Affix("rage", "Ярость", "ниже 30% здоровья бьют на {p}% сильнее", "rage_below", 0.20, 0.10, 0.60,
          extra={"threshold": 0.30}),
    Affix("poison", "Яд", "удар отравляет: {p}% от удара каждый ход, 3 хода", "on_hit", 0.10, 0.05, 0.30,
          extra={"effect": "dot", "duration": 3}),
    Affix("last_breath", "Последний вздох", "раз за бой остаются на 1 HP вместо смерти", "last_breath", 1.0,
          min_floor=16),
)
BY_ID = {a.id: a for a in AFFIXES}


def count(floor: int) -> int:
    n = 0
    for start, value in AFFIX_COUNTS:
        if floor >= start:
            n = value
    return n


def tier(floor: int) -> int:
    """Ступень силы: этажи 6-10 - I, 11-15 - II и так далее."""
    return max(1, (max(floor, 1) - 1) // TIER_FLOORS)


def tier_name(t: int) -> str:
    return ROMAN[t - 1] if 1 <= t <= len(ROMAN) else str(t)


def for_fight(floor: int, rng: random.Random) -> tuple[list[str], list[str]]:
    """(навыки мобов этого боя, добавка элите и хозяину этажа).

    Розыгрыш на каждый бой (2026-11-14, владелец): навык на весь этаж
    выходил одним и тем же бой за боем. Внутри боя навыки у мобов общие -
    подсказку перед боем читать одну."""
    n = count(floor)
    if n <= 0:
        return [], []
    pool = [a.id for a in AFFIXES if a.min_floor <= floor]
    rng.shuffle(pool)
    return pool[:n], pool[n:n + ELITE_EXTRA]


def percent(affix: Affix, t: int) -> int:
    return round(affix.value(t) * 100)


def label(affix_id: str, t: int) -> str:
    """«Отражение II - отражают 25% урона ударившему»."""
    a = BY_ID[affix_id]
    name = a.title if a.kind == "last_breath" else f"{a.title} {tier_name(t)}"
    return f"{name} - {a.hint.format(p=percent(a, t))}"


def short(affix_id: str, t: int) -> str:
    a = BY_ID[affix_id]
    return a.title if a.kind == "last_breath" else f"{a.title} {tier_name(t)}"


def traits(affix_ids: list[str], t: int) -> list[dict]:
    """Механики для MobAbilityDef: kind, сила и прочие поля навыка."""
    out = []
    for affix_id in affix_ids:
        a = BY_ID[affix_id]
        trait = {"kind": a.kind, "label": a.title, **a.extra}
        if a.kind == "rage_below":
            trait["mult"] = 1.0 + a.value(t)
        elif a.kind != "last_breath":
            trait["value"] = a.value(t)
        out.append(trait)
    return out
