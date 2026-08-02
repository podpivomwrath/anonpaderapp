"""Трофеи (патч 9, блок 2/3): начисление с боя/событий, чтение стека, продажа.

Хранение — счётчик по градации на персонажа (character_trophies), не отдельные
записи: инвентарь/скупщик показывают "🟣 Кровяной осколок ×7".
"""

import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import TrophyDef, load_trophy_defs
from game.economy import loot
from game.world import grid
from models import Character, CharacterTrophy
from services import wallet_service

_trophy_defs: dict[str, TrophyDef] | None = None


def _defs() -> dict[str, TrophyDef]:
    global _trophy_defs
    if _trophy_defs is None:
        _trophy_defs = {t.id: t for t in load_trophy_defs()}
    return _trophy_defs


def trophy_defs_ordered() -> list[TrophyDef]:
    """От дешёвых к дорогим — порядок content/trophies.json."""
    return list(_defs().values())


async def _get_row(db: AsyncSession, character_id: int, trophy_id: str) -> CharacterTrophy | None:
    return await db.scalar(
        select(CharacterTrophy).where(
            CharacterTrophy.character_id == character_id,
            CharacterTrophy.trophy_id == trophy_id,
        )
    )


async def _add(db: AsyncSession, character_id: int, trophy_id: str, amount: int) -> None:
    row = await _get_row(db, character_id, trophy_id)
    if row is None:
        row = CharacterTrophy(character_id=character_id, trophy_id=trophy_id, count=0)
        db.add(row)
    row.count += amount


async def _grant(db: AsyncSession, character_id: int, drop: dict[str, int]) -> dict[str, int]:
    for trophy_id, amount in drop.items():
        await _add(db, character_id, trophy_id, amount)
    if drop:
        await db.flush()
    return drop


async def grant_from_kill(
    db: AsyncSession, character: Character, rng: random.Random
) -> dict[str, int]:
    """Дроп с убитого моба: число бросков растёт к центру карты (dist Чебышёва)."""
    dist = grid.chebyshev_distance(character.pos_x, character.pos_y)
    rolls = loot.rolls_for_dist(dist)
    drop = loot.roll_drop(rng, rolls)
    return await _grant(db, character.id, drop)


async def grant_from_event(
    db: AsyncSession, character: Character, rng: random.Random
) -> dict[str, int]:
    """Событие исследования — та же таблица, всегда 1 бросок."""
    drop = loot.roll_drop(rng, 1)
    return await _grant(db, character.id, drop)


async def get_stock(db: AsyncSession, character_id: int) -> list[tuple[TrophyDef, int]]:
    """Только градации с count > 0, в порядке content/trophies.json."""
    rows = (
        await db.execute(
            select(CharacterTrophy).where(CharacterTrophy.character_id == character_id)
        )
    ).scalars().all()
    counts = {r.trophy_id: r.count for r in rows if r.count > 0}
    return [(d, counts[d.id]) for d in trophy_defs_ordered() if d.id in counts]


async def sell_all(db: AsyncSession, character: Character) -> int:
    """Продаёт весь стек всех градаций разом; возвращает вырученное золото."""
    stock = await get_stock(db, character.id)
    if not stock:
        return 0
    total = sum(d.sell_price * count for d, count in stock)
    for d, _count in stock:
        row = await _get_row(db, character.id, d.id)
        row.count = 0
    await wallet_service.deposit(db, character.id, "farm", total)
    await db.flush()
    return total


async def sell_one(db: AsyncSession, character: Character, trophy_id: str) -> int:
    """Продаёт весь стек ОДНОЙ градации; возвращает вырученное золото (0, если пусто)."""
    row = await _get_row(db, character.id, trophy_id)
    if row is None or row.count <= 0:
        return 0
    trophy_def = _defs().get(trophy_id)
    if trophy_def is None:
        return 0
    total = trophy_def.sell_price * row.count
    row.count = 0
    await wallet_service.deposit(db, character.id, "farm", total)
    await db.flush()
    return total


async def transfer_all(db: AsyncSession, loser_id: int, winner_id: int) -> dict[str, int]:
    """Переносит ВЕСЬ стек трофеев проигравшего победителю (дуэль, патч 22).
    Возвращает перенесённый набор {trophy_id: count} для сообщения."""
    stock = await get_stock(db, loser_id)
    moved = {d.id: count for d, count in stock}
    for trophy_id, count in moved.items():
        row = await _get_row(db, loser_id, trophy_id)
        row.count = 0
        await _add(db, winner_id, trophy_id, count)
    if moved:
        await db.flush()
    return moved


async def split_among(
    db: AsyncSession, victim_id: int, shares: dict[int, float]
) -> dict[int, dict[str, int]]:
    """Делит весь стек трофеев жертвы между несколькими персонажами
    пропорционально shares (нанесённый урон — необязательно нормированные к 1
    доли, нормализуются здесь). Остаток от округления — тому, у кого доля
    больше (топ-дамагер). Патч 22, массовый бой.

    Пустой shares (никто из выживших не бил жертву напрямую) — трофеи
    остаются у жертвы, переноса нет. Возвращает {character_id: {trophy_id:
    count}} для сообщений — только непустые доли."""
    if not shares:
        return {}
    total_share = sum(shares.values())
    if total_share <= 0:
        return {}
    stock = await get_stock(db, victim_id)
    if not stock:
        return {}
    top_id = max(shares, key=lambda cid: shares[cid])
    result: dict[int, dict[str, int]] = {}
    for trophy_def, count in stock:
        allocated: dict[int, int] = {}
        remaining = count
        for cid, share in shares.items():
            portion = int(count * share / total_share)
            allocated[cid] = portion
            remaining -= portion
        allocated[top_id] += remaining  # остаток округления — топ-дамагеру
        row = await _get_row(db, victim_id, trophy_def.id)
        row.count = 0
        for cid, amount in allocated.items():
            if amount <= 0:
                continue
            await _add(db, cid, trophy_def.id, amount)
            result.setdefault(cid, {})[trophy_def.id] = amount
    await db.flush()
    return result


def format_drop_line(drop: dict[str, int]) -> str | None:
    """'С твари осыпается: 🟣 Кровяной осколок, ⚪ Пепельная крошка ×2.'

    Порядок — от дорогих к дешёвым (самое ценное на видном месте)."""
    if not drop:
        return None
    parts = []
    for trophy_def in reversed(trophy_defs_ordered()):
        amount = drop.get(trophy_def.id)
        if not amount:
            continue
        suffix = f" ×{amount}" if amount > 1 else ""
        parts.append(f"{trophy_def.emoji} {trophy_def.name}{suffix}")
    return "С твари осыпается: " + ", ".join(parts) + "."
