"""Земли гильдии: знамёна и закладка, десятина, базы и постройки, шахта,
врата, молитва, тотем и прочие бонусы на своей земле.

Захватывать можно кольца 2-4: внешнее кольцо - зона новичков, центр -
Монолит. Озёра и города не захватываются. Рудник - отдельный слот.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import guild_config as gc
from game.economy import fishing as game_fishing
from game.economy import mining as game_mining
from game.guild import tree as guild_tree
from game.world import grid
from models import Character, Guild, GuildBuilding, GuildCell, GuildSiege
from services import guild_service, mining_service, wallet_service
from services.guild_service import GuildError, aware, now_utc

STATS = ("str", "agi", "int", "vit", "wil")


# --- Чтение ---------------------------------------------------------------------


async def cell_at(db: AsyncSession, x: int, y: int) -> GuildCell | None:
    return await db.scalar(select(GuildCell).where(GuildCell.x == x, GuildCell.y == y))


async def cells_of(db: AsyncSession, guild_id: int) -> list[GuildCell]:
    return list(
        (await db.scalars(select(GuildCell).where(GuildCell.guild_id == guild_id).order_by(GuildCell.id))).all()
    )


async def buildings_of(db: AsyncSession, cell_id: int) -> list[GuildBuilding]:
    return list(
        (await db.scalars(select(GuildBuilding).where(GuildBuilding.cell_id == cell_id))).all()
    )


async def building_at(db: AsyncSession, cell_id: int, building: str) -> GuildBuilding | None:
    return await db.scalar(
        select(GuildBuilding).where(GuildBuilding.cell_id == cell_id, GuildBuilding.building == building)
    )


async def all_cells(db: AsyncSession) -> list[tuple[GuildCell, Guild]]:
    rows = (await db.execute(select(GuildCell, Guild).join(Guild, Guild.id == GuildCell.guild_id))).all()
    return [(c, g) for c, g in rows]


def claim_reason(x: int, y: int) -> str | None:
    """Почему клетку нельзя занять. None - можно."""
    if not grid.in_bounds(x, y):
        return "За краем мира знамя не поставить."
    if grid.city_region_at(x, y) is not None:
        return "Города не захватываются."
    tier = grid.ring_tier(x, y)
    if tier == 1:
        return "Внешнее кольцо - земля новичков, её не захватывают."
    if tier not in gc.CLAIMABLE_RING_TIERS:
        return "Земля у Монолита не принадлежит никому."
    if game_fishing.is_lake(x, y):
        return "Озёра не захватываются."
    return None


def _count_slots(cells: list[GuildCell]) -> tuple[int, int]:
    """(обычных, рудников) - включая идущие закладки."""
    mines = sum(1 for c in cells if c.mine_id)
    return len(cells) - mines, mines


def effects_of(guild: Guild) -> dict[str, float]:
    return guild_tree.total_effects(set(guild.tree_nodes or []))


# --- Знамя и закладка ---------------------------------------------------------


async def plant_banner(db: AsyncSession, actor: Character, x: int, y: int) -> GuildCell:
    guild, _member = await guild_service.require_treasurer(db, actor)
    if (actor.pos_x, actor.pos_y) != (x, y):
        raise GuildError("Знамя ставят на месте: встань на эту клетку.")
    reason = claim_reason(x, y)
    if reason:
        raise GuildError(reason)
    if await cell_at(db, x, y) is not None:
        raise GuildError("Эта клетка уже чья-то.")
    cells = await cells_of(db, guild.id)
    if any(c.status == "claiming" for c in cells):
        raise GuildError("Гильдия уже закладывает знамя. Доведи сначала его.")
    mine = game_mining.mine_at(x, y)
    held_cells, held_mines = _count_slots(cells)
    if mine is not None:
        if held_mines >= gc.mine_slots(guild.level):
            raise GuildError(f"Рудник можно занять с {gc.MINE_SLOT_LEVEL} уровня гильдии, и только один.")
    elif held_cells >= gc.cell_slots(guild.level):
        raise GuildError("Свободных слотов под клетки нет - нужен уровень гильдии выше.")
    effects = effects_of(guild)
    tier = grid.ring_tier(x, y)
    ore_id, ore_count = gc.CLAIM_ORE[tier]
    if mine is not None:
        ore_count *= gc.CLAIM_ORE_MINE_MULT
    cost = gc.banner_cost(mine is not None, len(cells))
    await guild_service.spend_guild_ore(db, guild.id, ore_id, ore_count)
    await guild_service.treasury_spend(db, guild.id, gold=cost)
    needed = max(1, math.ceil(gc.CLAIM_EXPLORATIONS * (1 - effects.get("claim_speed_pct", 0) / 100)))
    cell = GuildCell(
        guild_id=guild.id, x=x, y=y, mine_id=mine.id if mine else None, status="claiming",
        claim_progress=0, claim_needed=needed,
        claim_expires_at=now_utc() + timedelta(hours=gc.CLAIM_HOURS),
        base_tier=gc.BASE_OUTPOST,
    )
    db.add(cell)
    place = f"рудник «{mine.name}»" if mine else "клетку"
    await guild_service.log(
        db, guild.id, "banner",
        f"{actor.name} закладывает знамя на {place} ({x}; {y}). Нужно {needed} исследований за {gc.CLAIM_HOURS} ч.",
        actor.id,
    )
    await db.flush()
    return cell


@dataclass
class ExplorationOutcome:
    tithe_guild_id: int | None = None
    tithe_gold: int = 0
    claimed: GuildCell | None = None
    claim_progress: tuple[int, int] | None = None


async def on_exploration(db: AsyncSession, character: Character) -> ExplorationOutcome:
    """Завершённое исследование: десятина владельцу и прогресс закладки."""
    outcome = ExplorationOutcome()
    if character.pos_x is None:
        return outcome
    cell = await cell_at(db, character.pos_x, character.pos_y)
    if cell is None:
        return outcome
    now = now_utc()
    if cell.status == "held":
        guild = await db.get(Guild, cell.guild_id)
        base = gc.TITHE_BY_RING.get(grid.ring_tier(cell.x, cell.y), 0)
        gold = round(base * (1 + effects_of(guild).get("tithe_pct", 0) / 100))
        if gold > 0:
            await guild_service.treasury_add(db, guild.id, gold=gold)
            outcome.tithe_guild_id, outcome.tithe_gold = guild.id, gold
        return outcome
    if cell.status == "claiming" and character.guild_id == cell.guild_id:
        if aware(cell.claim_expires_at) < now:
            return outcome
        cell.claim_progress += 1
        outcome.claim_progress = (cell.claim_progress, cell.claim_needed)
        if cell.claim_progress >= cell.claim_needed:
            cell.status = "held"
            cell.claim_expires_at = None
            cell.shaft_checked_at = now
            outcome.claimed = cell
            await guild_service.log(
                db, cell.guild_id, "claim", f"Знамя встало: ({cell.x}; {cell.y}) теперь земля гильдии.",
                character.id,
            )
        await db.flush()
    return outcome


async def expire_claims(db: AsyncSession, now: datetime | None = None) -> list[GuildCell]:
    """Закладки, не доведённые за отпущенное время, сгорают."""
    now = now or now_utc()
    rows = (await db.scalars(select(GuildCell).where(GuildCell.status == "claiming"))).all()
    gone = []
    for cell in rows:
        if aware(cell.claim_expires_at) is not None and aware(cell.claim_expires_at) < now:
            await guild_service.log(
                db, cell.guild_id, "claim",
                f"Закладка знамени на ({cell.x}; {cell.y}) сорвалась: не успели за {gc.CLAIM_HOURS} ч.",
            )
            gone.append(cell)
            await db.delete(cell)
    await db.flush()
    return gone


async def abandon(db: AsyncSession, actor: Character, cell_id: int) -> GuildCell:
    guild, _member = await guild_service.require_treasurer(db, actor)
    cell = await db.get(GuildCell, cell_id)
    if cell is None or cell.guild_id != guild.id:
        raise GuildError("Это не земля твоей гильдии.")
    if await active_siege_on(db, cell.x, cell.y) is not None:
        raise GuildError("Под осадой землю не бросают.")
    await guild_service.log(db, guild.id, "abandon", f"{actor.name} оставляет клетку ({cell.x}; {cell.y}).", actor.id)
    await db.execute(delete(GuildBuilding).where(GuildBuilding.cell_id == cell.id))
    await db.delete(cell)
    await db.flush()
    await guild_service.refresh_perks(db, guild)
    return cell


async def active_siege_on(db: AsyncSession, x: int, y: int) -> GuildSiege | None:
    return await db.scalar(
        select(GuildSiege).where(
            GuildSiege.x == x, GuildSiege.y == y, GuildSiege.status.in_(("scheduled", "running")),
        )
    )


# --- Базы и постройки ---------------------------------------------------------


def building_max_level(cell: GuildCell, building: str) -> int:
    if building == gc.B_SHAFT:
        return gc.SHAFT_MAX_LEVEL if cell.mine_id else 0
    return gc.BASE_BUILDING_MAX[cell.base_tier]


@dataclass
class BuildQuote:
    gold: int
    ore_id: str
    ore_count: int
    hours: float


def quote(guild: Guild, building: str, level: int) -> BuildQuote:
    effects = effects_of(guild)
    gold = round(gc.build_gold(building, level) * (1 - effects.get("build_cost_pct", 0) / 100))
    ore_id, ore_count = gc.build_ore(level)
    hours = gc.build_hours(level) * (1 - effects.get("build_time_pct", 0) / 100)
    return BuildQuote(gold, ore_id, ore_count, round(hours, 2))


async def _held_cell(db: AsyncSession, guild: Guild, cell_id: int) -> GuildCell:
    cell = await db.get(GuildCell, cell_id)
    if cell is None or cell.guild_id != guild.id or cell.status != "held":
        raise GuildError("Это не база твоей гильдии.")
    return cell


async def start_build(db: AsyncSession, actor: Character, cell_id: int, building: str) -> GuildBuilding:
    guild, _member = await guild_service.require_treasurer(db, actor)
    if building not in gc.BUILDINGS:
        raise GuildError("Нет такой постройки.")
    cell = await _held_cell(db, guild, cell_id)
    existing = await buildings_of(db, cell.id)
    if any(b.upgrading_to is not None for b in existing):
        raise GuildError("На этой базе уже идёт стройка.")
    current = next((b for b in existing if b.building == building), None)
    if current is None and len(existing) >= gc.BASE_SLOTS[cell.base_tier]:
        raise GuildError("Свободных мест под постройки на этой базе нет - подними её ступень.")
    if building == gc.B_SHAFT and not cell.mine_id:
        raise GuildError("Шахту ставят только на руднике.")
    next_level = (current.level if current else 0) + 1
    if next_level > building_max_level(cell, building):
        raise GuildError("Выше на этой базе не построить.")
    q = quote(guild, building, next_level)
    await guild_service.spend_guild_ore(db, guild.id, q.ore_id, q.ore_count)
    await guild_service.treasury_spend(db, guild.id, gold=q.gold)
    if current is None:
        current = GuildBuilding(cell_id=cell.id, building=building, level=0)
        db.add(current)
    current.upgrading_to = next_level
    current.done_at = now_utc() + timedelta(hours=q.hours)
    await guild_service.log(
        db, guild.id, "build",
        f"{actor.name} начинает стройку: {gc.BUILDING_TITLES[building]} {next_level} ур. на ({cell.x}; {cell.y}).",
        actor.id,
    )
    await db.flush()
    return current


async def start_base_upgrade(db: AsyncSession, actor: Character, cell_id: int) -> GuildCell:
    guild, _member = await guild_service.require_treasurer(db, actor)
    cell = await _held_cell(db, guild, cell_id)
    if cell.upgrade_to is not None:
        raise GuildError("База уже перестраивается.")
    index = gc.BASE_ORDER.index(cell.base_tier)
    if index + 1 >= len(gc.BASE_ORDER):
        raise GuildError("Выше цитадели ничего нет.")
    target = gc.BASE_ORDER[index + 1]
    if guild.level < gc.BASE_UNLOCK_LEVEL[target]:
        raise GuildError(f"{gc.BASE_TITLES[target]} доступна с {gc.BASE_UNLOCK_LEVEL[target]} уровня гильдии.")
    if target == gc.BASE_CITADEL:
        cells = await cells_of(db, guild.id)
        if any(c.base_tier == gc.BASE_CITADEL or c.upgrade_to == gc.BASE_CITADEL for c in cells):
            raise GuildError("Цитадель у гильдии может быть только одна.")
    gold, (ore_id, ore_count), hours = gc.BASE_UPGRADE_COST[target]
    effects = effects_of(guild)
    gold = round(gold * (1 - effects.get("build_cost_pct", 0) / 100))
    hours = hours * (1 - effects.get("build_time_pct", 0) / 100)
    await guild_service.spend_guild_ore(db, guild.id, ore_id, ore_count)
    await guild_service.treasury_spend(db, guild.id, gold=gold)
    cell.upgrade_to = target
    cell.upgrade_done_at = now_utc() + timedelta(hours=hours)
    await guild_service.log(
        db, guild.id, "build",
        f"{actor.name} начинает перестройку ({cell.x}; {cell.y}) в {gc.BASE_TITLES[target].lower()}.",
        actor.id,
    )
    await db.flush()
    return cell


async def complete_due(db: AsyncSession, now: datetime | None = None) -> list[tuple[int, str]]:
    """Достроить всё, у чего вышло время. [(guild_id, текст)] - для рассылки."""
    now = now or now_utc()
    done: list[tuple[int, str]] = []
    touched: set[int] = set()
    rows = (
        await db.execute(
            select(GuildBuilding, GuildCell).join(GuildCell, GuildCell.id == GuildBuilding.cell_id)
            .where(GuildBuilding.upgrading_to.isnot(None))
        )
    ).all()
    for building, cell in rows:
        if aware(building.done_at) is None or aware(building.done_at) > now:
            continue
        building.level = building.upgrading_to
        building.upgrading_to = None
        building.done_at = None
        text = f"{gc.BUILDING_TITLES[building.building]} {building.level} ур. на ({cell.x}; {cell.y}) достроена."
        await guild_service.log(db, cell.guild_id, "build", text)
        done.append((cell.guild_id, text))
        touched.add(cell.guild_id)
    cells = (await db.scalars(select(GuildCell).where(GuildCell.upgrade_to.isnot(None)))).all()
    for cell in cells:
        if aware(cell.upgrade_done_at) is None or aware(cell.upgrade_done_at) > now:
            continue
        cell.base_tier = cell.upgrade_to
        cell.upgrade_to = None
        cell.upgrade_done_at = None
        text = f"База на ({cell.x}; {cell.y}) теперь {gc.BASE_TITLES[cell.base_tier].lower()}."
        await guild_service.log(db, cell.guild_id, "build", text)
        done.append((cell.guild_id, text))
    await db.flush()
    for guild_id in touched:
        guild = await db.get(Guild, guild_id)
        if guild is not None:
            await guild_service.refresh_perks(db, guild)
    return done


# --- Шахта ----------------------------------------------------------------------


async def shaft_tick(db: AsyncSession, rng: random.Random, now: datetime | None = None) -> int:
    """Шахты копают руду из своих рудников прямо на склад. Сколько добыто."""
    now = now or now_utc()
    mined = 0
    rows = (
        await db.execute(
            select(GuildBuilding, GuildCell).join(GuildCell, GuildCell.id == GuildBuilding.cell_id)
            .where(GuildBuilding.building == gc.B_SHAFT, GuildBuilding.level > 0, GuildCell.status == "held")
        )
    ).all()
    for shaft, cell in rows:
        mine = game_mining.mine_by_id(cell.mine_id) if cell.mine_id else None
        last = aware(cell.shaft_checked_at) or now
        cell.shaft_checked_at = now
        if mine is None:
            continue
        guild = await db.get(Guild, cell.guild_id)
        rate = gc.SHAFT_RATE.get(shaft.level, 0) * (1 + effects_of(guild).get("shaft_speed_pct", 0) / 100)
        cell.shaft_progress = min(cell.shaft_progress + (now - last).total_seconds() / gc.SHAFT_PLAYER_SECONDS * rate, 5.0)
        cap = await guild_service.capacity(db, guild)
        while cell.shaft_progress >= 1:
            if await guild_service.ore_total(db, guild.id) >= cap.ore:
                cell.shaft_progress = 1.0
                break
            if not await mining_service._take_one_ore(db, mine.id):
                cell.shaft_progress = 1.0
                break
            ore_id = game_mining.roll_ore_id(rng, mine.tier, mining_level=gc.SHAFT_MINING_LEVEL)
            grade, _name = game_mining.roll_grade(rng, mine.tier, gc.SHAFT_MINING_LEVEL)
            await guild_service.add_guild_ore(db, guild.id, ore_id, grade, 1)
            cell.shaft_progress -= 1
            mined += 1
    await db.flush()
    return mined


# --- Врата ----------------------------------------------------------------------


async def gate_targets(db: AsyncSession, guild_id: int) -> list[GuildCell]:
    rows = (
        await db.execute(
            select(GuildCell).join(GuildBuilding, GuildBuilding.cell_id == GuildCell.id)
            .where(
                GuildCell.guild_id == guild_id, GuildCell.status == "held",
                GuildBuilding.building == gc.B_GATES, GuildBuilding.level > 0,
            )
        )
    ).scalars().all()
    return list(rows)


def gates_cooldown_minutes(level: int) -> int:
    return max(1, gc.GATES_COOLDOWN_MINUTES - gc.GATES_COOLDOWN_CUT_PER_LEVEL * (level - 1))


async def travel_gates(db: AsyncSession, character: Character, target_cell_id: int) -> GuildCell:
    guild, _member = await guild_service.require_member(db, character)
    here = await cell_at(db, character.pos_x, character.pos_y)
    gates = await gate_targets(db, guild.id)
    gate_ids = {c.id for c in gates}
    if here is None or here.id not in gate_ids:
        raise GuildError("Врата открываются только на своей базе с вратами.")
    target = next((c for c in gates if c.id == target_cell_id), None)
    if target is None or target.id == here.id:
        raise GuildError("Туда врата не ведут.")
    gate = await building_at(db, here.id, gc.B_GATES)
    cooldown = gates_cooldown_minutes(gate.level if gate else 1)
    used = aware(character.gates_used_at)
    if used is not None and now_utc() - used < timedelta(minutes=cooldown):
        left = cooldown - int((now_utc() - used).total_seconds() // 60)
        raise GuildError(f"Врата ещё не остыли: {max(1, left)} мин.")
    character.pos_x, character.pos_y = target.x, target.y
    character.gates_used_at = now_utc()
    await db.flush()
    return target


# --- Часовня и молитва ----------------------------------------------------------


def prayer_cost(character: Character) -> int:
    chapel = int(guild_service.perk(character, "_chapel"))
    base = max(gc.PRAYER_MIN_COST, gc.PRAYER_BASE_COST - gc.PRAYER_CUT_PER_LEVEL * max(0, chapel - 1))
    return round(base * (1 - guild_service.perk(character, "prayer_cost_pct") / 100))


def prayer_active(character: Character, now: datetime | None = None) -> bool:
    until = aware(character.prayer_until)
    return character.prayer_stat is not None and until is not None and until > (now or now_utc())


async def pray(db: AsyncSession, character: Character, stat: str) -> int:
    await guild_service.require_member(db, character)
    if stat not in STATS:
        raise GuildError("Нет такой характеристики.")
    if guild_service.perk(character, "_chapel") < 1:
        raise GuildError("У гильдии нет часовни.")
    cost = prayer_cost(character)
    try:
        await wallet_service.charge(db, character.id, "farm", cost)
    except wallet_service.NotEnoughCurrency:
        raise GuildError(f"Молитва стоит {cost} золота.") from None
    character.prayer_stat = stat
    character.prayer_until = now_utc() + timedelta(minutes=gc.PRAYER_MINUTES)
    await db.flush()
    return cost


def chapel_respawn_cut(character) -> float:
    return guild_service.perk(character, "_chapel") * gc.CHAPEL_RESPAWN_CUT_PER_LEVEL


def respawn_multiplier(character) -> float:
    """Множитель времени возрождения: часовня и древо."""
    cut = chapel_respawn_cut(character) + guild_service.perk(character, "respawn_pct") / 100
    return max(0.3, 1.0 - cut)


async def chapel_cell(db: AsyncSession, guild_id: int) -> GuildCell | None:
    rows = (
        await db.execute(
            select(GuildCell, GuildBuilding.level).join(GuildBuilding, GuildBuilding.cell_id == GuildCell.id)
            .where(
                GuildCell.guild_id == guild_id, GuildCell.status == "held",
                GuildBuilding.building == gc.B_CHAPEL, GuildBuilding.level > 0,
            )
            .order_by(GuildBuilding.level.desc())
        )
    ).first()
    return rows[0] if rows else None


# --- Аура тотема и бонусы к характеристикам ---------------------------------------


async def _totem_level_near(db: AsyncSession, guild_id: int, x: int, y: int) -> int:
    rows = (
        await db.execute(
            select(GuildCell.x, GuildCell.y, GuildBuilding.level)
            .join(GuildBuilding, GuildBuilding.cell_id == GuildCell.id)
            .where(
                GuildCell.guild_id == guild_id, GuildCell.status == "held",
                GuildBuilding.building == gc.B_TOTEM, GuildBuilding.level > 0,
            )
        )
    ).all()
    best = 0
    for cx, cy, level in rows:
        if abs(cx - x) <= gc.TOTEM_RADIUS and abs(cy - y) <= gc.TOTEM_RADIUS:
            best = max(best, level)
    return best


async def totem_double_chance(db: AsyncSession, character: Character) -> float:
    if character.guild_id is None or character.pos_x is None:
        return 0.0
    level = await _totem_level_near(db, character.guild_id, character.pos_x, character.pos_y)
    if level <= 0:
        return 0.0
    return level * gc.TOTEM_DOUBLE_DROP_PER_LEVEL + guild_service.perk(character, "totem_drop_pct") / 100


async def stat_bonus(db: AsyncSession, character: Character, base: dict[str, int]) -> dict[str, int]:
    """Прибавка гильдии к характеристикам: древо, молитва, аура тотема.

    base - собственные статы плюс снаряжение; проценты считаются от них.
    """
    if character.guild_id is None:
        return {}
    pct = {s: guild_service.perk(character, "stat_pct") / 100 for s in STATS}
    if prayer_active(character):
        pct[character.prayer_stat] = pct.get(character.prayer_stat, 0) + gc.PRAYER_STAT_BONUS
    if character.pos_x is not None:
        level = await _totem_level_near(db, character.guild_id, character.pos_x, character.pos_y)
        if level >= gc.TOTEM_STAT_BONUS_LEVEL:
            for s in STATS:
                pct[s] += gc.TOTEM_STAT_BONUS
    return {s: round(base.get(s, 0) * p) for s, p in pct.items() if p > 0 and round(base.get(s, 0) * p)}


# --- Башня ------------------------------------------------------------------------


@dataclass
class TowerAlarm:
    guild_id: int
    x: int
    y: int
    intruder: str
    intruder_guild: str | None = None
    peers: list[int] = field(default_factory=list)


async def on_cell_enter(db: AsyncSession, character: Character) -> TowerAlarm | None:
    """Чужой зашёл на клетку с башней - офицеры владельца узнают (не чаще раза
    в TOWER_WARN_COOLDOWN_MINUTES на клетку)."""
    if character.pos_x is None:
        return None
    cell = await cell_at(db, character.pos_x, character.pos_y)
    if cell is None or cell.status != "held" or cell.guild_id == character.guild_id:
        return None
    tower = await building_at(db, cell.id, gc.B_TOWER)
    if tower is None or tower.level < 1:
        return None
    now = now_utc()
    warned = aware(cell.tower_warned_at)
    if warned is not None and now - warned < timedelta(minutes=gc.TOWER_WARN_COOLDOWN_MINUTES):
        return None
    cell.tower_warned_at = now
    other = await guild_service.guild_of(db, character)
    peers = await guild_service.peers_of(db, cell.guild_id, min_rank=gc.RANK_OFFICER)
    await db.flush()
    return TowerAlarm(cell.guild_id, cell.x, cell.y, character.name, other.tag if other else None, peers)


async def territory_counts(db: AsyncSession, guild_id: int) -> dict[str, int]:
    cells = [c for c in await cells_of(db, guild_id) if c.status == "held"]
    return {
        "cells": sum(1 for c in cells if not c.mine_id),
        "mines": sum(1 for c in cells if c.mine_id),
        "citadel": sum(1 for c in cells if c.base_tier == gc.BASE_CITADEL),
    }


async def held_count(db: AsyncSession) -> int:
    return await db.scalar(select(func.count()).select_from(GuildCell).where(GuildCell.status == "held")) or 0
