"""Скупка руды у Иргала (2026-10-21): только железо и кварц, дёшево."""

import json

from bot.keyboards import appraiser as akb
from services import mining_service, wallet_service


async def _seed(db, cid):
    for ore_id, grade, count in [
        ("brown_iron", "common", 10),      # 10 * 5 = 50
        ("brown_iron", "epic", 2),         # 2 * 5 * 2.5 = 25
        ("salt_quartz", "common", 4),      # 4 * 12 = 48
        ("salt_quartz", "legendary", 1),   # 12 * 5 = 60
        ("taint_pyrite", "common", 7),     # не берёт
    ]:
        await mining_service.add_ore(db, cid, ore_id, grade, count)


def _left(stock):
    return {(d.id, g): c for d, g, c in stock}


async def test_sell_one_kind_takes_only_common(db_session, character_at) -> None:
    c = await character_at(0, 30, farm=0)
    await _seed(db_session, c.id)
    gold, pieces = await mining_service.sell_ore(db_session, c.id, "brown_iron", best=False)
    assert (gold, pieces) == (50, 10)
    assert (await wallet_service.get_wallet(db_session, c.id)).farm_currency == 50
    left = _left(await mining_service.get_ore(db_session, c.id))
    assert ("brown_iron", "common") not in left and left[("brown_iron", "epic")] == 2


async def test_best_grades_sold_separately_and_pyrite_kept(db_session, character_at) -> None:
    c = await character_at(0, 30, farm=0)
    await _seed(db_session, c.id)
    gold, pieces = await mining_service.sell_ore(db_session, c.id, None, best=True, price_multiplier=0.5)
    assert (gold, pieces) == (round((25 + 60) * 0.5), 3)
    left = _left(await mining_service.get_ore(db_session, c.id))
    assert left == {("brown_iron", "common"): 10, ("salt_quartz", "common"): 4, ("taint_pyrite", "common"): 7}
    # Колчедан Иргал не берёт вовсе.
    assert await mining_service.sell_ore(db_session, c.id, "taint_pyrite", best=False) == (0, 0)


def test_ore_keyboard_and_root_button() -> None:
    raw = akb.appraiser_ore_keyboard([("brown_iron", "⚪", 10, 50), ("salt_quartz", "🔵", 4, 48)], (3, 85))
    rows = json.loads(raw)["buttons"]
    payloads = [b["action"].get("payload") for row in rows for b in row]
    payloads = [json.loads(p) if isinstance(p, str) else p for p in payloads if p]
    assert {"type": "sell_ore", "best": 1} in payloads
    assert payloads[-1] == {"type": "appraiser_root"}
    assert len(rows) <= 10 and all(len(r) <= 5 for r in rows)
