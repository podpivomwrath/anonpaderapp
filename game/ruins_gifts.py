"""Дары культа (2026-11-05): усиления на один забег руин, общие на группу.
Выбор 1 из 3 делает лидер, 60 секунд без выбора - случайный (решение
владельца). Дар «на этаж» (проклятие кладовой) снимается спуском ниже.

Здесь - только описание даров и розыгрыш. Как дар работает:
  - mods - модификаторы бойца, складываются в buff_modifiers до постройки
    (здоровье, урон, криты - всё, что движок уже умеет);
  - остальное - по id в game/combat/ruins.py (бой) и
    services/ruins_service.py (между боями).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

COMMON, RARE, CURSED = "common", "rare", "cursed"
TIER_MARK = {COMMON: "", RARE: "✨ ", CURSED: "🩸 "}


@dataclass(frozen=True)
class Gift:
    id: str
    name: str
    text: str
    tier: str = COMMON
    mods: dict = field(default_factory=dict)


GIFTS: tuple[Gift, ...] = (
    # --- урон
    Gift("rusty_nail", "Ржавый гвоздь", "в первый ход каждого боя все удары - критические"),
    Gift("candle_wax", "Свечной воск", "яды бьют на 25% сильнее", mods={"poison_damage_bonus": 0.25}),
    Gift("blood_debt", "Долг крови", "+2% урона за каждого убитого в забеге противника, до +30%", RARE),
    Gift("miner_pick", "Кирка забойщика", "+30% урона у элиты и хозяев этажа, -15% в обычных боях"),
    Gift("whetstone", "Точильный камень", "+10% урона", mods={"damage_bonus": 0.10}),
    Gift("cult_eye", "Глаз послушника", "+12% к шансу крита", RARE, mods={"crit_chance_bonus": 0.12}),
    # --- защита
    Gift("stone_skin", "Каменная кожа", "первые 2 хода боя входящий урон вдвое меньше"),
    Gift("foreign_prayer", "Чужая молитва", "раз за этаж смертельный удар оставляет бойца с 1 HP", RARE),
    Gift("thick_hide", "Толстая шкура", "+10% к здоровью", mods={"max_hp_bonus": 0.10}),
    Gift("shoulder", "Плечом к плечу", "-8% входящего урона", mods={"incoming_damage_reduction": 0.08}),
    # --- между боями
    Gift("novice_flask", "Фляга послушника", "после каждого выигранного боя +8% здоровья"),
    Gift("spare_vial", "Лишний пузырёк", "+1 зелье к лимиту этажа"),
    Gift("bandage", "Тряпьё на бинты", "после хозяина этажа вся группа лечится на 25%", RARE),
    # --- добыча
    Gift("greedy_palm", "Жадная ладонь", "+1 кубик на руну с ближайшего хозяина этажа"),
    Gift("usurer_mark", "Метка ростовщика", "+1 бросок реликвий за каждую элиту"),
    # --- проклятые: сильные, с платой
    Gift("vow_silence", "Обет молчания", "+35% урона, но зелья закрыты до конца забега", CURSED,
         mods={"damage_bonus": 0.35}),
    Gift("heavy_bag", "Тяжёлый мешок", "+2 кубика на руны с каждого хозяина, но противники на 15% крепче", CURSED),
    Gift("foreign_name", "Чужое имя", "навыки чаще обходятся без отката, но в начале боя -10% здоровья", CURSED,
         mods={"no_cooldown_chance": 0.25}),
    Gift("bad_blood", "Дурная кровь", "+20% к шансу крита, но -15% здоровья", CURSED,
         mods={"crit_chance_bonus": 0.20, "max_hp_bonus": -0.15}),
)
BY_ID: dict[str, Gift] = {g.id: g for g in GIFTS}

#: Вес редкости в обычном розыгрыше.
TIER_WEIGHT = {COMMON: 6, RARE: 2, CURSED: 1}
OFFER_SIZE = 3


def offer(rng: random.Random, owned: list[str], tiers: tuple[str, ...] = (COMMON, RARE, CURSED),
          size: int = OFFER_SIZE) -> list[str]:
    """Три разных дара, которых у группы ещё нет."""
    pool = [g for g in GIFTS if g.id not in owned and g.tier in tiers]
    picked: list[str] = []
    while pool and len(picked) < size:
        gift = rng.choices(pool, weights=[TIER_WEIGHT[g.tier] for g in pool])[0]
        picked.append(gift.id)
        pool = [g for g in pool if g.id != gift.id]
    return picked


def ids(gifts: list[dict] | None) -> list[str]:
    return [g["id"] for g in gifts or []]


def has(gifts: list[dict] | None, gift_id: str) -> bool:
    return gift_id in ids(gifts)


def mods(gifts: list[dict] | None) -> dict[str, float]:
    """Сумма модификаторов бойца от всех даров группы."""
    out: dict[str, float] = {}
    for gift_id in ids(gifts):
        for key, value in BY_ID[gift_id].mods.items() if gift_id in BY_ID else ():
            out[key] = out.get(key, 0.0) + value
    return out


def title(gift_id: str) -> str:
    gift = BY_ID[gift_id]
    return f"{TIER_MARK[gift.tier]}{gift.name}"


def line(gift_id: str) -> str:
    return f"{title(gift_id)} - {BY_ID[gift_id].text}"
