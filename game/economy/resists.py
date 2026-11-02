"""Сопротивления (2026-11-02, решения владельца по репорту 283).

Три вида, у каждого свой ключ в buff_modifiers бойца:
  resist_crit - прибавка крит-урона по тебе меньше на эту долю (2026-11-02,
                владелец: 1.0 - крит бьёт как обычный удар);
  accuracy    - уворот твоей цели меньше на эту долю (процент от уворота);
  resist_dot  - яд и горение по тебе слабее на эту долю.

Источники:
  Выносливость - стойкость к крит-урону с убывающей отдачей, только у игроков
    (stat_model.crit_resist). Воле сопротивлений не даём: владелец - она и так
    ультимативна у мистиков и отравителей.
  Руны героя - «Закалка» и «Верный глаз» по 7% в базе; яд и горение
    режет давняя «Горькая кровь».
  Кованые вещи - одно случайное сопротивление на вещь, до 10% на 120%
    эффективности (value * эффективность / 120).
  Перстень Несгоревшего - 15% каждого, падает с моба клетки с шансом
    0.01%, без объявлений.

Мягкий потолок (2026-11-02, владелец: стопки отключали классы): сумма
источников одного вида до SOFT_CAP идёт полностью, сверху - вполовину, итог
не выше HARD_CAP. Выносливость к крит-урону считается отдельно, мимо потолка.
"""

import random

CRIT, DODGE, DOT = "crit", "dodge", "dot"
KINDS = (CRIT, DODGE, DOT)
#: Ключ в buff_modifiers.
KEYS = {CRIT: "resist_crit", DODGE: "accuracy", DOT: "resist_dot"}
TITLES = {CRIT: "стойкость к крит-урону", DODGE: "меткость", DOT: "стойкость к ядам"}
EMOJI = {CRIT: "🪨", DODGE: "🎯", DOT: "🧪"}

#: Кованая вещь: столько при 120% эффективности, ниже - пропорционально.
ITEM_VALUE = 0.10
ITEM_FULL_EFFICIENCY = 120
#: Вещь, скованная до появления эффективности, считается как на 100%.
ITEM_DEFAULT_EFFICIENCY = 100

RING_ID = "unburnt_ring"
RING_TITLE = "Перстень Несгоревшего"
RING_FLAVOR = ("Его сняли с паломника, который прошёл Пепельный круг босиком. Ступни у него были в волдырях, "
               "а под кольцом кожа осталась чистой.")
RING_VALUE = 0.15
RING_DROP_CHANCE = 0.0001

#: Мягкий потолок суммы одного вида: до SOFT_CAP полностью, выше - с
#: долей OVER_RATE, итог не больше HARD_CAP.
SOFT_CAP = 0.15
OVER_RATE = 0.5
HARD_CAP = 0.30

#: Стойкость дотов не уводит урон в ноль, как и «Горькая кровь».
DOT_FLOOR = 0.1


def roll(rng: random.Random) -> str:
    return rng.choice(KINDS)


def item_value(efficiency: int | None) -> float:
    eff = efficiency if efficiency is not None else ITEM_DEFAULT_EFFICIENCY
    return ITEM_VALUE * eff / ITEM_FULL_EFFICIENCY


def describe(kind: str, value: float) -> str:
    """«крит-урон по тебе ниже на 8.3%» - строка для вещей, кольца и сводки."""
    pct = round(value * 100, 1)
    num = f"{pct:g}"
    if kind == CRIT:
        return f"крит-урон по тебе ниже на {num}%"
    if kind == DODGE:
        return f"уворот цели ниже на {num}%"
    return f"яд и горение по тебе слабее на {num}%"


def capped(total: float) -> float:
    """Сумма источников одного вида -> что действует в бою."""
    if total <= SOFT_CAP:
        return total
    return min(SOFT_CAP + (total - SOFT_CAP) * OVER_RATE, HARD_CAP)


def add(mods: dict[str, float], kind: str, value: float) -> None:
    if value:
        key = KEYS[kind]
        mods[key] = mods.get(key, 0.0) + value
