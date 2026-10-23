"""Рынок (2026-10-23, решения владельца): числа и каталог товаров.

Товары с заявками («офферами»): руда, травы, еда, расходники ремёсел, ларцы.
Витрина: некованые уникальные вещи - лот с ценой, без заявок на покупку.
Зелий и прочего нет вовсе (зелья - позже, только свои). Валюта - золото.
"""

from dataclasses import dataclass
from functools import lru_cache

#: Комиссия за выставление заявки (обе стороны) - не возвращается.
LISTING_FEE = 0.01
#: Комиссия с выручки продавца.
SALE_FEE = 0.05
#: Заявка или лот дешевле этого (цена * количество) не принимаются.
MIN_ORDER_GOLD = 100
#: Срок заявки, часы: потом товар или золото возвращаются.
ORDER_HOURS = 48
#: Открытых заявок и лотов на игрока; с Меткой Хранителя - больше.
MAX_ORDERS = 10
MAX_ORDERS_PREMIUM = 20
#: Больше этого в одной заявке не выставить - защита от опечаток.
MAX_QTY = 10_000
MAX_PRICE = 100_000_000
#: Сколько уровней стакана показывать.
BOOK_DEPTH = 5

#: Расходники ремёсел, что продаются штуками. Пряности - нет: у набора тир,
#: и купленный набор другого тира заменил бы свой вместе с зарядами.
CRAFT_GOODS = ("flasks", "bait")

CATEGORIES = (
    ("ore", "⛏ Руда"),
    ("herb", "🌿 Травы"),
    ("food", "🍲 Еда"),
    ("craft", "🧰 Расходники ремёсел"),
    ("chest", "🗃 Ларцы"),
)


@dataclass(frozen=True)
class Good:
    key: str
    category: str
    name: str
    emoji: str
    icon: str | None


@lru_cache(maxsize=1)
def goods() -> dict[str, Good]:
    """Весь каталог: ключ -> товар, в порядке показа."""
    from game.economy import cooking, craft_gear_config, fishing, herbalism, mining
    from game.economy import cooking_config as cc
    from game.economy import mining_config as mc
    from services import lootbox_service

    out: dict[str, Good] = {}
    for ore in mining.ore_defs_ordered():
        for _t, grade, grade_name in mc.GRADES:
            mark = mc.GRADE_EMOJI.get(grade, "")
            out[f"ore:{ore.id}:{grade}"] = Good(
                f"ore:{ore.id}:{grade}", "ore", f"{ore.name} ({grade_name})",
                mark or ore.emoji, f"ore:{ore.id}",
            )
    for herb in herbalism.herb_defs_ordered():
        out[f"herb:{herb.id}"] = Good(f"herb:{herb.id}", "herb", herb.name, herb.emoji, f"herb:{herb.id}")
    for dish in cc.DISHES:
        d = cooking.dish_def(dish.dish_id)
        for grade in cc.GRADE_ORDER:
            key = f"food:{dish.dish_id}:{grade}"
            out[key] = Good(key, "food", f"{d.name} (рыба {fishing.grade_name(grade)})", d.emoji, f"dish:{dish.dish_id}")
    for tool_id in CRAFT_GOODS:
        tool = craft_gear_config.TOOLS[tool_id]
        out[f"craft:{tool_id}"] = Good(f"craft:{tool_id}", "craft", tool.title, tool.emoji, f"gear:{tool_id}")
    # Шансы пепельного - от серии того, кто открывает: все ларцы одинаковые.
    for kind in (lootbox_service.ASHEN, lootbox_service.ORE, lootbox_service.SUPPLY):
        info = lootbox_service.CHEST_KINDS[kind]
        out[f"chest:{kind}"] = Good(f"chest:{kind}", "chest", info.name, "🗃️", info.icon)
    return out


def good(key: str) -> Good | None:
    if key.startswith("item:"):
        return None
    return goods().get(key)
