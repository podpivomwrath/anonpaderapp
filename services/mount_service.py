"""Маунты (патч 25, п.7): владение, список, путешествие с риском нападения.

Путешествие хранится в БД (mount_travels), не в памяти — переживает
перезапуск бота. Батч-сканер (scan) вызывается периодически из main.py по
образцу bot/handlers/respawn.py::scan: один общий job на всех, не задача на
игрока. Шанс нападения разыгрывается ОДИН раз при старте поездки (не при
каждом тике скана) — если выпало, момент нападения фиксируется случайно
строго между стартом и прибытием.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import MountDef, load_mounts
from game.economy import mount_config as mc
from models import Character, CharacterMount, MountTravel

_mounts: dict[str, MountDef] | None = None


def _defs() -> dict[str, MountDef]:
    global _mounts
    if _mounts is None:
        _mounts = load_mounts()
    return _mounts


def mount_def(mount_id: str) -> MountDef | None:
    return _defs().get(mount_id)


def seconds_per_cell(mount_id: str) -> float:
    d = mount_def(mount_id)
    rarity = d.rarity if d is not None else "common"
    return mc.RARITY_SECONDS_PER_CELL.get(rarity, mc.RARITY_SECONDS_PER_CELL["common"])


def ambush_chance(mount_id: str) -> float:
    d = mount_def(mount_id)
    rarity = d.rarity if d is not None else "common"
    return mc.RARITY_AMBUSH_CHANCE.get(rarity, mc.RARITY_AMBUSH_CHANCE["common"])


async def grant(db: AsyncSession, character: Character, mount_id: str) -> bool:
    """Начисляет маунт персонажу. True — реально начислен (не было раньше)."""
    existing = await db.scalar(
        select(CharacterMount).where(
            CharacterMount.character_id == character.id, CharacterMount.mount_id == mount_id,
        )
    )
    if existing is not None:
        return False
    db.add(CharacterMount(character_id=character.id, mount_id=mount_id))
    await db.flush()
    return True


@dataclass
class OwnedMount:
    mount_id: str
    name: str
    rarity: str
    emoji: str
    seconds_per_cell: float
    ambush_chance: float


async def owned_mounts(db: AsyncSession, character_id: int) -> list[OwnedMount]:
    rows = (
        await db.scalars(
            select(CharacterMount).where(CharacterMount.character_id == character_id)
        )
    ).all()
    result = []
    for row in rows:
        d = mount_def(row.mount_id)
        if d is None:
            continue
        result.append(
            OwnedMount(
                mount_id=d.id, name=d.name, rarity=d.rarity,
                emoji=mc.RARITY_EMOJI.get(d.rarity, ""),
                seconds_per_cell=seconds_per_cell(d.id), ambush_chance=ambush_chance(d.id),
            )
        )
    return result


async def has_any_mount(db: AsyncSession, character_id: int) -> bool:
    existing = await db.scalar(
        select(CharacterMount).where(CharacterMount.character_id == character_id)
    )
    return existing is not None


# --- Путешествие ---


async def active_travel(db: AsyncSession, character_id: int) -> MountTravel | None:
    return await db.scalar(
        select(MountTravel).where(
            MountTravel.character_id == character_id,
            MountTravel.status.in_(("traveling", "ambushed")),
        )
    )


async def start_travel(
    db: AsyncSession, character: Character, mount_id: str, to_x: int, to_y: int,
    rng: random.Random, now: datetime | None = None,
) -> MountTravel:
    now = now or datetime.now(timezone.utc)
    cells = max(abs(to_x - character.pos_x), abs(to_y - character.pos_y))
    seconds = cells * seconds_per_cell(mount_id)
    arrives_at = now + timedelta(seconds=seconds)

    ambush_at = None
    # Нападение — "не в начале и не в конце": окно 10%-90% пути.
    if cells > 0 and rng.random() < ambush_chance(mount_id):
        offset = rng.uniform(seconds * 0.1, seconds * 0.9)
        ambush_at = now + timedelta(seconds=offset)

    travel = MountTravel(
        character_id=character.id, mount_id=mount_id,
        from_x=character.pos_x, from_y=character.pos_y, to_x=to_x, to_y=to_y,
        started_at=now, arrives_at=arrives_at, ambush_at=ambush_at,
        ambush_done=ambush_at is None, status="traveling",
    )
    db.add(travel)
    await db.flush()
    return travel


def remaining_seconds(travel: MountTravel, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    return max((travel.arrives_at - now).total_seconds(), 0.0)


def frozen_remaining_seconds(travel: MountTravel, now: datetime | None = None) -> float:
    """Оставшееся время пути, «замороженное» в момент нападения (до
    resume_travel) — для текста предложения «Продолжить путь»."""
    if travel.ambush_at is None:
        return remaining_seconds(travel, now)
    return max((travel.arrives_at - travel.ambush_at).total_seconds(), 0.0)


async def resume_travel(db: AsyncSession, travel: MountTravel, now: datetime | None = None) -> None:
    """Победа в бою нападения (патч 25, п.7): оставшееся время пути
    сохраняется — бой не идёт в счёт дороги."""
    now = now or datetime.now(timezone.utc)
    if travel.ambush_at is not None:
        remaining = max((travel.arrives_at - travel.ambush_at).total_seconds(), 0.0)
        travel.arrives_at = now + timedelta(seconds=remaining)
    travel.status = "traveling"
    await db.flush()


async def cancel_travel(db: AsyncSession, travel: MountTravel) -> None:
    """Смерть в бою нападения отменяет поездку (патч 25, п.7)."""
    travel.status = "cancelled"
    await db.flush()


@dataclass
class ScanResult:
    ambushed: list[MountTravel]
    arrived: list[MountTravel]
    still_traveling: list[MountTravel]


async def scan(db: AsyncSession, now: datetime | None = None) -> ScanResult:
    """Батч-проход (main.py, периодический job): кто наткнулся на нападение,
    кто уже прибыл, у кого просто идёт время (для live-отсчёта). Строки со
    status="ambushed" (бой ещё не разрешён) сюда не попадают — ждут исхода боя."""
    now = now or datetime.now(timezone.utc)
    rows = (
        await db.scalars(select(MountTravel).where(MountTravel.status == "traveling"))
    ).all()
    ambushed, arrived, still = [], [], []
    for row in rows:
        if not row.ambush_done and row.ambush_at is not None and now >= row.ambush_at:
            row.ambush_done = True
            row.status = "ambushed"
            ambushed.append(row)
        elif now >= row.arrives_at:
            row.status = "completed"
            arrived.append(row)
        else:
            still.append(row)
    await db.flush()
    return ScanResult(ambushed=ambushed, arrived=arrived, still_traveling=still)
