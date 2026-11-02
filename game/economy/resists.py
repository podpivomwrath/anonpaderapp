"""Сопротивления (2026-11-02, решения владельца по репорту 283).

Три вида, у каждого свой ключ в buff_modifiers бойца:
  resist_crit - шанс крита по тебе ниже на столько (доли, 0.07 = 7 п.п.);
  accuracy    - уворот твоей цели ниже на столько;
  resist_dot  - яд и горение по тебе слабее на эту долю.

Источники:
  Выносливость - стойкость к критам с убывающей отдачей, только у игроков
    (stat_model.crit_resist). Воле сопротивлений не даём: владелец - она и так
    ультимативна у мистиков и отравителей.
  Руны героя - «Закалка» и «Верный глаз» по 7 п.п. в базе; яд и горение
    режет давняя «Горькая кровь».
  Кованые вещи - одно случайное сопротивление на вещь, до 10% на 120%
    эффективности (value * эффективность / 120).
  Перстень Несгоревшего - 15 п.п. каждого, падает с моба клетки с шансом
    0.01%, без объявлений.
"""

import random

CRIT, DODGE, DOT = "crit", "dodge", "dot"
KINDS = (CRIT, DODGE, DOT)
#: Ключ в buff_modifiers.
KEYS = {CRIT: "resist_crit", DODGE: "accuracy", DOT: "resist_dot"}
TITLES = {CRIT: "стойкость к критам", DODGE: "меткость", DOT: "стойкость к ядам"}
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

#: Стойкость дотов не уводит урон в ноль, как и «Горькая кровь».
DOT_FLOOR = 0.1


def roll(rng: random.Random) -> str:
    return rng.choice(KINDS)


def item_value(efficiency: int | None) -> float:
    eff = efficiency if efficiency is not None else ITEM_DEFAULT_EFFICIENCY
    return ITEM_VALUE * eff / ITEM_FULL_EFFICIENCY


def describe(kind: str, value: float) -> str:
    """«шанс крита по тебе ниже на 8.3 п.п.» - строка для вещей, кольца и сводки."""
    pct = round(value * 100, 1)
    num = f"{pct:g}"
    if kind == CRIT:
        return f"шанс крита по тебе ниже на {num} п.п."
    if kind == DODGE:
        return f"уворот цели ниже на {num} п.п."
    return f"яд и горение по тебе слабее на {num}%"


def add(mods: dict[str, float], kind: str, value: float) -> None:
    if value:
        key = KEYS[kind]
        mods[key] = mods.get(key, 0.0) + value
