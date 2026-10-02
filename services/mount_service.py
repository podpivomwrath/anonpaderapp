"""Маунты (патч 25, п.7): владение, список, путешествие с риском нападения.

Путешествие хранится в БД (mount_travels), не в памяти — переживает
перезапуск бота. Батч-сканер (scan) вызывается периодически из main.py по
образцу bot/handlers/respawn.py::scan: один общий job на всех, не задача на
игрока. Поездка идёт по клеткам: персонаж реально переходит с клетки на
клетку, нападение разыгрывается на каждой (см. «Путешествие» ниже).
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import MountDef, load_mounts
from game.economy import mount_config as mc
from game.world import grid
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
#
# Поездка идёт по клеткам (grid.line_path): каждые step_seconds персонаж
# реально переходит на следующую клетку - его координаты в базе меняются,
# его видно в «Осмотреться» на этой клетке, моб нападает по ЭТОЙ клетке.
# Нападение разыгрывается на каждой новой клетке; шанс за всю поездку на
# ~REF_CELLS клеток в среднем равен ambush_chance маунта, а по кольцу он
# растёт к центру (RING_AMBUSH_MULT). На мирных клетках не нападают.


async def active_travel(db: AsyncSession, character_id: int) -> MountTravel | None:
    return await db.scalar(
        select(MountTravel).where(
            MountTravel.character_id == character_id,
            MountTravel.status.in_(("traveling", "ambushed")),
        )
    )


def total_travel_seconds(mount_id: str, cells: int) -> float:
    """Патч 34, ч.3: «Пепельный вестник» (ADMIN_MOUNT_ID) — фиксированное
    время НА ВЕСЬ путь (ADMIN_MOUNT_TRAVEL_SECONDS), а не за клетку, вне
    зависимости от расстояния. Остальные маунты — как раньше."""
    if mount_id == mc.ADMIN_MOUNT_ID:
        return mc.ADMIN_MOUNT_TRAVEL_SECONDS
    return cells * seconds_per_cell(mount_id)


def path_of(travel: MountTravel) -> list[tuple[int, int]]:
    return grid.line_path(travel.from_x, travel.from_y, travel.to_x, travel.to_y)


def _is_safe_cell(x: int, y: int) -> bool:
    from services import fishing_service, mining_service  # избегаем цикла импортов

    return (
        grid.city_region_at(x, y) is not None
        or fishing_service.is_safe_lake(x, y)
        or mining_service.is_safe_mine(x, y)
    )


def cell_ambush_chance(mount_id: str, x: int, y: int, trip: float | None = None) -> float:
    """Шанс нападения при входе на клетку (x;y) верхом. trip - шанс за
    поездку, если он не от маунта (у повозки - от охраны)."""
    trip = ambush_chance(mount_id) if trip is None else trip
    if trip <= 0 or _is_safe_cell(x, y):
        return 0.0
    per_cell = 1 - (1 - trip) ** (1 / mc.AMBUSH_REF_CELLS)
    return min(per_cell * mc.RING_AMBUSH_MULT[grid.ring_tier(x, y)], 0.5)


def trip_ambush_chance(
    mount_id: str, from_x: int, from_y: int, to_x: int, to_y: int, trip: float | None = None,
) -> float:
    """Шанс хотя бы одного нападения на этом маршруте - для подсказки игроку."""
    safe = 1.0
    for x, y in grid.line_path(from_x, from_y, to_x, to_y)[:-1]:
        safe *= 1 - cell_ambush_chance(mount_id, x, y, trip)
    return 1 - safe


async def start_travel(
    db: AsyncSession, character: Character, mount_id: str, to_x: int, to_y: int,
    rng: random.Random | None = None, now: datetime | None = None, step_seconds: float | None = None,
) -> MountTravel:
    """step_seconds - шаг, если он не от маунта (у повозки - от лошадей)."""
    now = now or datetime.now(timezone.utc)
    cells = grid.cells_between(character.pos_x, character.pos_y, to_x, to_y)
    if step_seconds is not None:
        seconds = cells * step_seconds
    else:
        seconds = total_travel_seconds(mount_id, cells)
    step = seconds / cells if cells else 0.0
    travel = MountTravel(
        character_id=character.id, mount_id=mount_id,
        from_x=character.pos_x, from_y=character.pos_y, to_x=to_x, to_y=to_y,
        started_at=now, arrives_at=now + timedelta(seconds=seconds),
        ambush_at=None, ambush_done=True, status="traveling",
        step_seconds=step, cell_index=0, next_cell_at=now + timedelta(seconds=step),
    )
    db.add(travel)
    await db.flush()
    return travel


def cells_left(travel: MountTravel) -> int:
    return max(grid.cells_between(travel.from_x, travel.from_y, travel.to_x, travel.to_y) - travel.cell_index, 0)


def remaining_seconds(travel: MountTravel, now: datetime | None = None) -> float:
    """До прибытия: остаток текущего шага плюс целые шаги после него."""
    now = now or datetime.now(timezone.utc)
    left = cells_left(travel)
    if left == 0 or travel.next_cell_at is None:
        return max((travel.arrives_at - now).total_seconds(), 0.0)
    current = max((travel.next_cell_at - now).total_seconds(), 0.0)
    return current + (left - 1) * travel.step_seconds


def frozen_remaining_seconds(travel: MountTravel, now: datetime | None = None) -> float:
    """Оставшийся путь, пока поездка стоит (нападение): все клетки целиком."""
    if travel.status == "ambushed":
        return cells_left(travel) * travel.step_seconds
    return remaining_seconds(travel, now)


async def resume_travel(db: AsyncSession, travel: MountTravel, now: datetime | None = None) -> None:
    """Победа в бою нападения: путь продолжается с той клетки, где напали."""
    now = now or datetime.now(timezone.utc)
    travel.status = "traveling"
    travel.next_cell_at = now + timedelta(seconds=travel.step_seconds)
    travel.arrives_at = now + timedelta(seconds=cells_left(travel) * travel.step_seconds)
    await db.flush()


async def cancel_travel(db: AsyncSession, travel: MountTravel) -> None:
    """Смерть в бою нападения отменяет поездку (патч 25, п.7)."""
    travel.status = "cancelled"
    await db.flush()


@dataclass
class StepResult:
    moved: bool = False      # перешёл хотя бы на одну клетку
    ambushed: bool = False   # на новой клетке напали - поездка встала
    arrived: bool = False    # дошёл до цели


def advance(
    travel: MountTravel, character: Character, rng: random.Random,
    now: datetime | None = None, paused: bool = False, trip_chance: float | None = None,
) -> StepResult:
    """Шаги, которые уже пора сделать. paused - персонаж занят (бой,
    исследование): поездка ждёт его, шаг откладывается, а не теряется.
    После простоя бота догоняет все пропущенные клетки, на каждой разыгрывая
    нападение, - пропущенное время не даёт проскочить опасный участок."""
    now = now or datetime.now(timezone.utc)
    result = StepResult()
    if travel.status != "traveling":
        return result
    if travel.next_cell_at is None:
        # Поездка, начатая до движения по клеткам: доезжает по старому таймеру.
        if now >= travel.arrives_at and not paused:
            character.pos_x, character.pos_y = travel.to_x, travel.to_y
            travel.status = "completed"
            result.moved = result.arrived = True
        return result
    if paused:
        if now >= travel.next_cell_at:
            travel.next_cell_at = now + timedelta(seconds=travel.step_seconds)
            travel.arrives_at = travel.next_cell_at + timedelta(
                seconds=(cells_left(travel) - 1) * travel.step_seconds
            )
        return result
    path = path_of(travel)
    while travel.status == "traveling" and now >= travel.next_cell_at:
        travel.cell_index += 1
        x, y = path[travel.cell_index - 1]
        character.pos_x, character.pos_y = x, y
        result.moved = True
        if travel.cell_index >= len(path):
            travel.status = "completed"
            result.arrived = True
            break
        travel.next_cell_at += timedelta(seconds=travel.step_seconds)
        if rng.random() < cell_ambush_chance(travel.mount_id, x, y, trip_chance):
            travel.status = "ambushed"
            travel.ambush_at = now
            result.ambushed = True
    return result
