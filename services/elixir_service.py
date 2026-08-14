"""Зелья и эликсиры (патч 16): покупка у Матушки Синель, стек в инвентаре,
расход в бою (лечебные тратят ход, боевые — бесплатное действие).

Хранение — счётчик по виду на персонажа (character_consumables), как трофеи:
"🧪 Малое исцеление ×3", не 3 отдельные записи.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import ElixirDef, load_elixirs
from game.economy import elixir_config as ec
from models import Character, CharacterConsumable
from services import wallet_service

_elixir_defs: dict[str, ElixirDef] | None = None


def _defs() -> dict[str, ElixirDef]:
    global _elixir_defs
    if _elixir_defs is None:
        _elixir_defs = load_elixirs()
    return _elixir_defs


def elixir_defs_ordered() -> list[ElixirDef]:
    """Порядок — как в content/items/elixirs.json (лечебные, затем боевые)."""
    return list(_defs().values())


def elixir_def(elixir_id: str) -> ElixirDef | None:
    return _defs().get(elixir_id)


def price(elixir_id: str) -> int:
    return ec.ELIXIR_PRICES.get(elixir_id, 0)


async def _get_row(
    db: AsyncSession, character_id: int, elixir_id: str
) -> CharacterConsumable | None:
    return await db.scalar(
        select(CharacterConsumable).where(
            CharacterConsumable.character_id == character_id,
            CharacterConsumable.elixir_id == elixir_id,
        )
    )


async def buy_bulk(db: AsyncSession, character: Character, elixir_id: str, qty: int = 1) -> int:
    """Покупка N штук разом (патч 39, ч.4) — списывает золото ОДНИМ платежом
    (wallet_service.charge кидает NotEnoughCurrency, если не хватает), +qty к
    стеку. Возвращает потраченное золото."""
    cost = price(elixir_id) * qty
    await wallet_service.charge(db, character.id, "farm", cost)
    row = await _get_row(db, character.id, elixir_id)
    if row is None:
        row = CharacterConsumable(character_id=character.id, elixir_id=elixir_id, count=0)
        db.add(row)
    row.count += qty
    await db.flush()
    return cost


async def buy(db: AsyncSession, character: Character, elixir_id: str) -> None:
    """Покупка одной штуки — см. buy_bulk."""
    await buy_bulk(db, character, elixir_id, 1)


async def grant(db: AsyncSession, character_id: int, elixir_id: str, amount: int = 1) -> None:
    """Начисляет N штук без списания золота (награды — патч 23: стрики,
    цикл входа)."""
    if amount <= 0:
        return
    row = await _get_row(db, character_id, elixir_id)
    if row is None:
        row = CharacterConsumable(character_id=character_id, elixir_id=elixir_id, count=0)
        db.add(row)
    row.count += amount
    await db.flush()


async def get_stock(db: AsyncSession, character_id: int) -> list[tuple[ElixirDef, int]]:
    """Только виды с count > 0, в порядке content/items/elixirs.json."""
    rows = (
        await db.execute(
            select(CharacterConsumable).where(CharacterConsumable.character_id == character_id)
        )
    ).scalars().all()
    counts = {r.elixir_id: r.count for r in rows if r.count > 0}
    return [(d, counts[d.id]) for d in elixir_defs_ordered() if d.id in counts]


async def consume(db: AsyncSession, character_id: int, elixir_id: str) -> bool:
    """Списывает 1 штуку. False, если стека нет/пуст — вызывающий не должен
    применять эффект в этом случае."""
    row = await _get_row(db, character_id, elixir_id)
    if row is None or row.count <= 0:
        return False
    row.count -= 1
    await db.flush()
    return True
