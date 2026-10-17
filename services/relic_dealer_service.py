"""Пепельный меняла: сделка и её последствия (правила - game/world/relic_dealer.py).

Цена - как у скупщика в городе со всеми множителями игрока (клеймо,
процветание РОДНОГО города - меняла стоит в поле, венец, гильдия, налог) и
+25% сверху. Сделка одна: всё разом или одна градация, как у Иргала.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from game.world import relic_dealer as rd
from models import Character
from services import daily_service, faction_service, trophy_service

ALL = "all"


async def price_mult(db: AsyncSession, character: Character) -> float:
    """Множитель к цене скупщика, кроме венца и гильдии (их добавляет сама
    продажа в trophy_service)."""
    from services import pk_service

    tier = await faction_service.tier_of(db, character.region)
    city = tier.relic_mult if tier else 1.0
    return (1 + rd.PRICE_BONUS) * pk_service.relic_mult(character) * city


async def offer(db: AsyncSession, character: Character) -> list[tuple[str, str, int]]:
    """[(выбор, подпись, золото)]: «всё» и каждая градация, что есть в сумке."""
    stock = await trophy_service.get_stock(db, character.id)
    if not stock:
        return []
    mult = await price_mult(db, character) * trophy_service.display_multiplier(character)
    rows = [(d.id, f"{d.emoji} {d.name} ×{count}", round(d.sell_price * count * mult)) for d, count in stock]
    total = sum(gold for _id, _label, gold in rows)
    return [(ALL, "Всё разом", total), *rows]


async def lot(db: AsyncSession, character: Character, choice: str) -> dict[str, int]:
    """Что выставлено на сделку: {trophy_id: штук}."""
    stock = await trophy_service.get_stock(db, character.id)
    if choice == ALL:
        return {d.id: count for d, count in stock if count > 0}
    return {d.id: count for d, count in stock if d.id == choice and count > 0}


async def sell(db: AsyncSession, character: Character, choice: str):
    """(золото, прогресс ежедневок/гильдии «Торг» - для строки игроку)."""
    mult = await price_mult(db, character)
    if choice == ALL:
        gold = await trophy_service.sell_all(db, character, mult)
    else:
        gold = await trophy_service.sell_one(db, character, choice, mult)
    progress = await daily_service.record_sell_gold(db, character, gold) if gold > 0 else None
    return gold, progress


async def take_stolen(db: AsyncSession, character_id: int, stolen: dict[str, int]) -> dict[str, int]:
    """Меняла уносит украденное (продавец пал). Возвращает, что реально снято."""
    taken: dict[str, int] = {}
    for row in await trophy_service._lock_rows(db, character_id):
        want = stolen.get(row.trophy_id, 0)
        if want <= 0:
            continue
        n = min(want, row.count)
        row.count -= n
        if n:
            taken[row.trophy_id] = n
    await db.flush()
    return taken


async def grant_win_loot(db: AsyncSession, character: Character, mob_level: int, rng) -> list[str]:
    """Победа над менялой: rd.WIN_MOBS бросков добычи, как с убитых мобов -
    трофеи, вещь и лечебное зелье, каждый бросок независимо. Строки для игрока."""
    from services import elixir_service, item_service

    trophies: dict[str, int] = {}
    items = []
    elixirs: list[str] = []
    for _ in range(rd.WIN_MOBS):
        for trophy_id, n in (await trophy_service.grant_from_kill(db, character, rng)).items():
            trophies[trophy_id] = trophies.get(trophy_id, 0) + n
        item = await item_service.grant_from_kill(db, character, mob_level, rng)
        if item is not None:
            items.append(item)
        line = await elixir_service.grant_heal_from_kill(db, character, rng)
        if line:
            elixirs.append(line)
    lines = []
    drop = trophy_service.format_drop_line(trophies)
    if drop:
        lines.append(drop)
    lines += [f"{item_service.format_drop_announcement(item)}. В сумке." for item in items]
    lines += elixirs
    return lines


def stolen_line(taken: dict[str, int]) -> str:
    if not taken:
        return ""
    parts = []
    for trophy_id, n in taken.items():
        d = trophy_service.trophy_def(trophy_id)
        parts.append(f"{d.emoji} {d.name} ×{n}" if d else f"{trophy_id} ×{n}")
    return f"💰 {rd.DEALER_NAME} уносит украденное: " + ", ".join(parts) + "."
