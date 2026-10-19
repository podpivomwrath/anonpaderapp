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
from services import crown_service, wallet_service

_trophy_defs: dict[str, TrophyDef] | None = None


def _defs() -> dict[str, TrophyDef]:
    global _trophy_defs
    if _trophy_defs is None:
        _trophy_defs = {t.id: t for t in load_trophy_defs()}
    return _trophy_defs


def trophy_defs_ordered() -> list[TrophyDef]:
    """От дешёвых к дорогим — порядок content/trophies.json."""
    return list(_defs().values())


def trophy_def(trophy_id: str) -> TrophyDef | None:
    return _defs().get(trophy_id)


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
    """Дроп с убитого моба: число бросков растёт к центру карты (кольцо клетки)."""
    dist = grid.monolith_distance(character.pos_x, character.pos_y)
    rolls = loot.rolls_for_dist(dist)
    drop = loot.roll_drop(rng, rolls)
    return await _grant(db, character.id, drop)


async def grant_from_event(
    db: AsyncSession, character: Character, rng: random.Random
) -> dict[str, int]:
    """Событие исследования (и горстка пепла, services/ash_service.py) —
    трофей ГАРАНТИРОВАН (патч 38): бросок без исхода «ничего», иначе
    "гарантированная" награда в ~31% случаев оказывалась пустой, что
    нарушает правило патча 10 о недопустимости пустых исходов события."""
    drop = loot.roll_guaranteed_drop(rng, 1)
    return await _grant(db, character.id, drop)


async def grant_specific(db: AsyncSession, character_id: int, trophy_id: str, amount: int) -> None:
    """Начисляет N конкретной градации напрямую, в обход обычного дропа
    (награды вроде Пепельного ларца, патч 24)."""
    if amount <= 0:
        return
    await _add(db, character_id, trophy_id, amount)
    await db.flush()


async def get_stock(db: AsyncSession, character_id: int) -> list[tuple[TrophyDef, int]]:
    """Только градации с count > 0, в порядке content/trophies.json."""
    rows = (
        await db.execute(
            select(CharacterTrophy).where(CharacterTrophy.character_id == character_id)
        )
    ).scalars().all()
    counts = {r.trophy_id: r.count for r in rows if r.count > 0}
    return [(d, counts[d.id]) for d in trophy_defs_ordered() if d.id in counts]


async def _lock_rows(
    db: AsyncSession, character_id: int, trophy_id: str | None = None
) -> list[CharacterTrophy]:
    """Непустые стаки под блокировкой строки - для продажи и переноса.

    Продажа устроена как «прочитать количество -> обнулить -> заплатить», а
    вебхук обрабатывает события ПАРАЛЛЕЛЬНО. Без блокировки два нажатия
    «Продать» читали одно и то же количество и платили оба: на настоящем
    Postgres десять трофеев за 20 золота принесли 120 (патч 94).

    FOR UPDATE держит строку до конца транзакции. Второе нажатие ждёт, а
    дождавшись, перечитывает строку уже с нулём и продаёт ничего.
    populate_existing - чтобы не взять старое число из кэша сессии.
    """
    query = select(CharacterTrophy).where(
        CharacterTrophy.character_id == character_id, CharacterTrophy.count > 0
    )
    if trophy_id is not None:
        query = query.where(CharacterTrophy.trophy_id == trophy_id)
    query = query.with_for_update().execution_options(populate_existing=True)
    return list((await db.execute(query)).scalars().all())


def display_multiplier(character: Character) -> float:
    """Венец и гильдия - те же множители, что при продаже: цены в списке у
    скупщика обязаны совпадать с тем, что реально придёт (2026-10-16)."""
    return crown_service.mob_gold_multiplier(character) * _guild_sell_multiplier(character)


def _guild_sell_multiplier(character: Character) -> float:
    from services import guild_service

    return 1 + guild_service.perk(character, "sell_pct") / 100


async def sell_all(db: AsyncSession, character: Character, price_multiplier: float = 1.0) -> int:
    """Продаёт весь стек всех градаций разом; возвращает вырученное золото.
    price_multiplier (патч 26) — наценка чужака у скупщика в чужом городе."""
    defs = _defs()
    rows = [r for r in await _lock_rows(db, character.id) if r.trophy_id in defs]
    if not rows:
        return 0
    total = round(
        sum(defs[r.trophy_id].sell_price * r.count for r in rows)
        * price_multiplier
        * crown_service.mob_gold_multiplier(character)
        * _guild_sell_multiplier(character)
    )
    for row in rows:
        row.count = 0
    await wallet_service.deposit(db, character.id, "farm", total)
    await db.flush()
    return total


async def sell_one(
    db: AsyncSession, character: Character, trophy_id: str, price_multiplier: float = 1.0
) -> int:
    """Продаёт весь стек ОДНОЙ градации; возвращает вырученное золото (0, если пусто).
    price_multiplier (патч 26) — наценка чужака у скупщика в чужом городе."""
    trophy_def = _defs().get(trophy_id)
    if trophy_def is None:
        return 0
    locked = await _lock_rows(db, character.id, trophy_id)
    if not locked:
        return 0
    row = locked[0]
    total = round(
        trophy_def.sell_price * row.count
        * price_multiplier
        * crown_service.mob_gold_multiplier(character)
        * _guild_sell_multiplier(character)
    )
    row.count = 0
    await wallet_service.deposit(db, character.id, "farm", total)
    await db.flush()
    return total


async def has_pocket(db: AsyncSession, character_id: int) -> bool:
    """Секретный карман (товар за самоцветы): половина реликвий переживает смерть."""
    return bool(await db.scalar(select(Character.secret_pocket).where(Character.id == character_id)))


def _pocketed(count: int, pocket: bool) -> int:
    """Сколько из стака уходит при смерти (остальное остаётся в кармане)."""
    from game.economy import gem_goods_config as ggc

    return count - ggc.pocket_keeps(count) if pocket else count


async def transfer_all(db: AsyncSession, loser_id: int, winner_id: int) -> dict[str, int]:
    """Переносит ВЕСЬ стек трофеев проигравшего победителю (дуэль, патч 22).
    С секретным карманом - только непрятанную часть.
    Возвращает перенесённый набор {trophy_id: count} для сообщения."""
    taken: dict[str, int] = {}
    pocket = await has_pocket(db, loser_id)
    for row in await _lock_rows(db, loser_id):
        n = _pocketed(row.count, pocket)
        if n <= 0:
            continue
        taken[row.trophy_id] = n
        row.count -= n
        await _add(db, winner_id, row.trophy_id, n)
    # Порядок каталога, как было до блокировок: из него собирается сообщение
    # о добыче, и строки не должны прыгать от боя к бою.
    moved = {d.id: taken[d.id] for d in trophy_defs_ordered() if d.id in taken}
    if moved:
        await db.flush()
    return moved


async def lose_all(db: AsyncSession, character_id: int) -> dict[str, int]:
    """Смерть в PvE (2026-10-17, решение владельца): все реликвии сгорают,
    кроме спрятанных в секретный карман.
    Возвращает потерянный набор {trophy_id: count} для сообщения."""
    lost: dict[str, int] = {}
    pocket = await has_pocket(db, character_id)
    for row in await _lock_rows(db, character_id):
        n = _pocketed(row.count, pocket)
        if n <= 0:
            continue
        lost[row.trophy_id] = n
        row.count -= n
    if lost:
        await db.flush()
    return {d.id: lost[d.id] for d in trophy_defs_ordered() if d.id in lost}


def lost_line(lost: dict[str, int]) -> str:
    if not lost:
        return ""
    parts = []
    for trophy_id, n in lost.items():
        d = trophy_def(trophy_id)
        parts.append(f"{d.emoji} {d.name} ×{n}" if d else f"{trophy_id} ×{n}")
    return "🔥 Реликвии при тебе рассыпались в пепел: " + ", ".join(parts) + "."


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
    pocket = await has_pocket(db, victim_id)
    for trophy_def, held in stock:
        count = _pocketed(held, pocket)
        if count <= 0:
            continue
        allocated: dict[int, int] = {}
        remaining = count
        for cid, share in shares.items():
            portion = int(count * share / total_share)
            allocated[cid] = portion
            remaining -= portion
        allocated[top_id] += remaining  # остаток округления — топ-дамагеру
        row = await _get_row(db, victim_id, trophy_def.id)
        row.count = held - count
        for cid, amount in allocated.items():
            if amount <= 0:
                continue
            await _add(db, cid, trophy_def.id, amount)
            result.setdefault(cid, {})[trophy_def.id] = amount
    await db.flush()
    return result


# Патч 32, ч.2: текст получения трофея обязан соответствовать РЕАЛЬНОМУ
# источнику — раньше единая фраза "С твари осыпается" использовалась и для
# находок вне боя (шкатулка, горстка пепла, алтарь, NPC), что выглядело так,
# будто игра называет предмет/событие "тварью". Ключ source — либо "mob"
# (бой, по умолчанию), либо id источника вне боя; неизвестный id → нейтральный
# фолбэк "Ты находишь". Правило на будущее: не добавлять сюда новый источник
# без своей строки — общий шаблон здесь намеренно не переиспользуется молча.
#
# Добыча с боя, рейдового этапа, мирового босса и событий - безлично:
# «Добыча: ...». «С твари осыпается» висело и над наградой за разгаданную
# загадку архива, где никакой твари нет; общая строка не врёт ни в одном
# месте, откуда бы награда ни пришла.
DROP_SOURCE_PREFIXES: dict[str, str] = {
    "mob": "Добыча",
    "ash_handful": "В пепле находится",
    "dead_box": "В шкатулке лежит",
    "monolith_shard": "Среди осколков лежит",
    "wounded_wanderer": "Он вкладывает тебе в ладонь",
    "ash_altar": "Среди подношений",
    "world_boss": "Добыча",
    "event": "Добыча",             # патч 110: события со сценами
    "ruin": "Растеряно по дороге",  # патч 110: срыв в «ещё чуть-чуть»
}


def format_drop_line(drop: dict[str, int], source: str = "mob") -> str | None:
    """'Добыча: 🟣 Кровяной осколок, ⚪ Пепельная крошка ×2.'
    (или другая формулировка по source — см. DROP_SOURCE_PREFIXES).

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
    prefix = DROP_SOURCE_PREFIXES.get(source, "Ты находишь")
    return f"{prefix}: " + ", ".join(parts) + "."
