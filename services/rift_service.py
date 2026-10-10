"""Разломы (2026-10): состояние в базе. Правила - game/economy/rift_config.py.

Всё, что меняет «кто держит разлом», идёт под блокировкой строки
(SELECT ... FOR UPDATE): две группы жмут «Войти» одновременно, и без
очереди обе получили бы разлом.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import rift_config as rc
from game.world import grid
from game.world import world_boss as world_boss_world
from game.world import world_config as wc
from models import Character, Rift, RiftMeter

ACTIVE, CLEARED, EXPIRED = "active", "cleared", "expired"
FREE, WAITING, RUNNING = "free", "waiting", "running"


class RiftError(Exception):
    """Причина отказа - игроку."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime | None) -> datetime | None:
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def rift_type(rift: Rift) -> rc.RiftType:
    return rc.RIFT_TYPES[rift.kind]


def band(rift: Rift) -> tuple[int, int]:
    return rc.BANDS[rift.ring]


def level_fits(level: int, rift: Rift) -> bool:
    lo, hi = band(rift)
    return lo <= level <= hi


def is_expired(rift: Rift, now: datetime | None = None) -> bool:
    return _aware(rift.expires_at) <= (now or _now())


def minutes_left(rift: Rift, now: datetime | None = None) -> int:
    return max(0, int((_aware(rift.expires_at) - (now or _now())).total_seconds() // 60))


def run_level(rift: Rift, levels: list[int]) -> int:
    """Уровень противников: старший в группе, в пределах разлома."""
    lo, hi = band(rift)
    return max(lo, min(max(levels), hi))


async def active_rifts(db: AsyncSession, now: datetime | None = None) -> list[Rift]:
    """Разломы на карте: живые по времени и занятые (те не исчезают, пока
    внутри или у входа группа)."""
    now = now or _now()
    rows = (await db.scalars(select(Rift).where(Rift.status == ACTIVE).order_by(Rift.id))).all()
    return [r for r in rows if r.state != FREE or not is_expired(r, now)]


async def rift_at(db: AsyncSession, x: int, y: int, now: datetime | None = None) -> Rift | None:
    for rift in await active_rifts(db, now):
        if (rift.x, rift.y) == (x, y):
            return rift
    return None


async def lock(db: AsyncSession, rift_id: int) -> Rift | None:
    return await db.scalar(
        select(Rift).where(Rift.id == rift_id).with_for_update().execution_options(populate_existing=True)
    )


async def held_by(db: AsyncSession, character_id: int) -> Rift | None:
    """Разлом, который персонаж сейчас держит (ждёт у входа или внутри)."""
    rows = (await db.scalars(select(Rift).where(Rift.status == ACTIVE, Rift.state != FREE))).all()
    return next((r for r in rows if character_id in (r.members or [])), None)


# --- Появление ----------------------------------------------------------------


async def _players_by_ring(db: AsyncSession, now: datetime) -> dict[int, int]:
    levels = (await db.scalars(select(Character.level).where(
        Character.creation_state.is_(None), Character.last_active_at >= now - timedelta(days=1),
    ))).all()
    counts: dict[int, int] = {}
    for level in levels:
        for ring, (lo, hi) in rc.BANDS.items():
            if lo <= level <= hi:
                counts[ring] = counts.get(ring, 0) + 1
    return counts


def _pick_ring(rng: random.Random, players_by_ring: dict[int, int]) -> int:
    """Чаще там, где за сутки были игроки нужных уровней; никого - любое."""
    rings = sorted(rc.BANDS)
    weights = [players_by_ring.get(r, 0) for r in rings]
    return rng.choices(rings, weights=weights)[0] if any(weights) else rng.choice(rings)


def _pick_cell(ring: int, taken: set[tuple[int, int]], rng: random.Random) -> tuple[int, int]:
    """Свободная клетка кольца, где разрешено PvP: разлом - повод для
    стычки, и мирная клетка у ворот его бы обесценила."""
    lo, hi = wc.ring_bounds(ring)
    cells = [
        c for c in grid.all_cells()
        if lo <= grid.monolith_distance(*c) <= hi
        and world_boss_world._cell_is_free(*c)
        and not grid.pvp_forbidden(*c)
        and c not in taken
    ]
    return rng.choice(cells)


async def spawn(db: AsyncSession, rng: random.Random, now: datetime | None = None,
                ring: int | None = None, kind: str | None = None) -> Rift:
    """Новый разлом на карте. Отдельно от счётчика - для админки и тестов."""
    now = now or _now()
    ring = ring or _pick_ring(rng, await _players_by_ring(db, now))
    taken = {(r.x, r.y) for r in await active_rifts(db, now)}
    from services import world_boss_service

    boss = await world_boss_service.active_boss(db, now)
    if boss is not None:
        taken.add((boss.x, boss.y))
    x, y = _pick_cell(ring, taken, rng)
    rift = Rift(
        kind=kind or rng.choice(sorted(rc.RIFT_TYPES)), ring=ring, x=x, y=y,
        status=ACTIVE, state=FREE, members=[], spawned_at=now,
        expires_at=now + timedelta(minutes=rc.LIFETIME_MINUTES),
    )
    db.add(rift)
    await db.flush()
    return rift


async def record_exploration(db: AsyncSession, rng: random.Random, now: datetime | None = None) -> Rift | None:
    """Завершённое исследование любого игрока наполняет счётчик. Без
    объявления: разлом находят на карте."""
    now = now or _now()
    meter = await db.get(RiftMeter, 1, with_for_update=True)
    if meter is None:
        meter = RiftMeter(id=1, explorations=0)
        db.add(meter)
    meter.explorations = (meter.explorations or 0) + 1
    if meter.explorations < rc.EXPLORATIONS_PER_SPAWN or len(await active_rifts(db, now)) >= rc.MAX_ACTIVE:
        await db.flush()
        return None
    meter.explorations = 0
    return await spawn(db, rng, now)


# --- Вход ---------------------------------------------------------------------


def entry_refusal(rift: Rift, characters: list[Character], now: datetime | None = None) -> str | None:
    """Почему эта группа не может встать в очередь. None - может."""
    t = rift_type(rift)
    if rift.status != ACTIVE or (rift.state == FREE and is_expired(rift, now)):
        return "Разлом уже закрылся."
    if rift.state != FREE:
        return "Разлом занят другой группой."
    if len(characters) > t.max_size:
        return f"В этот разлом можно не больше {t.max_size} игроков, а вас {len(characters)}."
    lo, hi = band(rift)
    wrong = [c.name for c in characters if not level_fits(c.level, rift)]
    if wrong:
        return f"Разлом - для {lo}-{hi} уровня. Не по уровню: {', '.join(wrong)}."
    away = [c.name for c in characters if (c.pos_x, c.pos_y) != (rift.x, rift.y) or c.travel_target_x is not None]
    if away:
        return f"Вся группа должна стоять у разлома. Нет на месте: {', '.join(away)}."
    return None


async def begin_wait(db: AsyncSession, rift_id: int, characters: list[Character], group_id: int | None,
                     now: datetime | None = None) -> Rift:
    """Группа встаёт у входа на ENTRY_WAIT_SECONDS. Первым в members -
    лидер. RiftError - нельзя."""
    now = now or _now()
    rift = await lock(db, rift_id)
    if rift is None:
        raise RiftError("Разлом уже закрылся.")
    reason = entry_refusal(rift, characters, now)
    if reason:
        raise RiftError(reason)
    for c in characters:
        other = await held_by(db, c.id)
        if other is not None and other.id != rift.id:
            raise RiftError(f"{c.name} уже держит другой разлом.")
    rift.state = WAITING
    rift.members = [c.id for c in characters]
    rift.group_id = group_id
    rift.wait_until = now + timedelta(seconds=rc.ENTRY_WAIT_SECONDS)
    await db.flush()
    return rift


def _release(rift: Rift, now: datetime) -> None:
    rift.state = FREE
    rift.members = []
    rift.group_id = None
    rift.wait_until = None
    rift.level = None
    if is_expired(rift, now):
        rift.status = EXPIRED


async def cancel_wait(db: AsyncSession, rift_id: int, now: datetime | None = None) -> list[int]:
    """Ожидание отменено - вся группа выходит. Вернёт, кто ждал."""
    rift = await lock(db, rift_id)
    if rift is None or rift.state != WAITING:
        return []
    members = list(rift.members or [])
    _release(rift, now or _now())
    await db.flush()
    return members


async def drop_members(db: AsyncSession, rift_id: int, character_ids: list[int],
                       now: datetime | None = None) -> Rift | None:
    """Убирает из ожидания погибших и ушедших. Никого не осталось - разлом
    свободен (None)."""
    rift = await lock(db, rift_id)
    if rift is None or rift.state != WAITING:
        return None
    left = [cid for cid in rift.members or [] if cid not in character_ids]
    if not left:
        _release(rift, now or _now())
        await db.flush()
        return None
    rift.members = left
    await db.flush()
    return rift


async def due_waits(db: AsyncSession, now: datetime | None = None) -> list[int]:
    now = now or _now()
    rows = (await db.scalars(select(Rift).where(Rift.status == ACTIVE, Rift.state == WAITING))).all()
    return [r.id for r in rows if _aware(r.wait_until) is not None and _aware(r.wait_until) <= now]


async def start_run(db: AsyncSession, rift: Rift, characters: list[Character]) -> int:
    """Группа вошла. Вернёт уровень противников."""
    rift.state = RUNNING
    rift.members = [c.id for c in characters]
    rift.wait_until = None
    rift.level = run_level(rift, [c.level for c in characters])
    await db.flush()
    return rift.level


async def finish_run(db: AsyncSession, rift_id: int, cleared: bool, now: datetime | None = None) -> None:
    """Пройден - разлом закрывается. Группа погибла - он снова свободен
    (или исчезает, если время вышло)."""
    rift = await lock(db, rift_id)
    if rift is None or rift.status != ACTIVE:
        return
    if cleared:
        rift.status = CLEARED
        rift.state = FREE
        rift.members = []
    else:
        _release(rift, now or _now())
    await db.flush()


async def expire_due(db: AsyncSession, now: datetime | None = None) -> int:
    """Свободные разломы, чьё время вышло, исчезают."""
    now = now or _now()
    rows = (await db.scalars(
        select(Rift).where(Rift.status == ACTIVE, Rift.state == FREE).with_for_update()
    )).all()
    gone = 0
    for rift in rows:
        if is_expired(rift, now):
            rift.status = EXPIRED
            gone += 1
    await db.flush()
    return gone


async def recover(db: AsyncSession, now: datetime | None = None) -> list[int]:
    """При старте бота: ожидание и бой жили в памяти - разломы освобождаются.
    Вернёт персонажей, которых надо вернуть в хаб."""
    now = now or _now()
    rows = (await db.scalars(
        select(Rift).where(Rift.status == ACTIVE, Rift.state != FREE).with_for_update()
    )).all()
    affected: list[int] = []
    for rift in rows:
        affected += list(rift.members or [])
        _release(rift, now)
    for cid in affected:
        character = await db.get(Character, cid)
        if character is not None:
            character.screen = None
    await db.flush()
    return affected
