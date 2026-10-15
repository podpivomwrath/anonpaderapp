"""Процветание фракций - городов (2026-10-15, решения владельца).

  - у каждого из 4 городов шкала 0..MAX_POINTS, на запуске - START_POINTS;
  - растёт от торговли: каждый проданный фирмой ящик даёт очки РОДНОМУ
    городу торговца, куда бы он ни возил;
  - один торговец даёт городу не больше дневного потолка; потолок растёт
    на 10 за каждые 10 уровней торговли;
  - падает плавно на DECAY_PER_DAY от текущего значения в сутки: без
    торговли город теряет половину примерно за 17 дней;
  - ступень даёт скидку на зелья в лавке и надбавку за реликвии у скупщика
    этого города - всем, кто там торгует; на цены ящиков не влияет.
"""

from dataclasses import dataclass

CITIES = ("ridge", "docks", "scorched", "woods")

START_POINTS = 2_000
MAX_POINTS = 10_000
DECAY_PER_DAY = 0.04

#: Очков за проданный ящик по градации товара.
POINTS_PER_CRATE = {1: 1, 2: 1, 3: 2, 4: 2}

DAILY_CAP_BASE = 100
DAILY_CAP_PER_10_LEVELS = 10


def daily_cap(trade_level: int) -> int:
    return DAILY_CAP_BASE + DAILY_CAP_PER_10_LEVELS * (max(trade_level, 0) // 10)


@dataclass(frozen=True)
class Tier:
    id: str
    name: str
    emoji: str
    min_points: int
    elixir_mult: float     # цена зелий в лавке
    relic_mult: float      # выручка за реликвии у скупщика


TIERS: list[Tier] = [
    Tier("decline", "Упадок", "🥀", 0, 1.05, 0.95),
    Tier("stagnation", "Застой", "⚖", 1_000, 1.0, 1.0),
    Tier("plenty", "Достаток", "🌾", 3_000, 0.96, 1.04),
    Tier("bloom", "Расцвет", "🌸", 5_500, 0.93, 1.07),
    Tier("golden", "Золотой век", "👑", 8_000, 0.90, 1.10),
]


def tier_for(points: float) -> Tier:
    current = TIERS[0]
    for tier in TIERS:
        if points >= tier.min_points:
            current = tier
    return current


def next_tier(points: float) -> Tier | None:
    for tier in TIERS:
        if points < tier.min_points:
            return tier
    return None
