"""Осады: объявление, окно защитников, час сбора, исход.

Порядок жизни осады:
  1. Глава или казначей объявляет осаду чужой базы - платит казна.
  2. Начало - в ближайшее окно защитников (их час, МСК), но не раньше чем
     через SIEGE_MIN_NOTICE_HOURS: обе стороны успевают собраться.
  3. За SIEGE_GATHER_MINUTES до начала на клетке нельзя драться - ни PvP,
     ни исследовать (исследование может затянуть в бой с мобом, и к началу
     осады игрок оказался бы занят).
  4. В назначенный момент бот собирает всех, кто стоит на клетке, и
     начинает массовый бой: осаждающие против защитников и гарнизона.
  5. Захват - клетка переходит к нападавшим, постройки теряют уровень,
     часть казны уходит победителю. Отражение - клетка под щитом.

Сам бой ведёт bot/handlers/guild_siege.py поверх массового PvP.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.combat.session import CombatantState, Stats, build_combatant
from game.economy import guild_config as gc
from models import Character, Guild, GuildBuilding, GuildCell, GuildSiege
from services import guild_service, guild_territory_service
from services.guild_service import GuildError, aware, now_utc

_TZ = ZoneInfo("Europe/Moscow")


def next_window(siege_hour: int, now: datetime | None = None) -> datetime:
    """Ближайшее начало окна защитников не раньше минимального срока."""
    now = now or now_utc()
    earliest = now + timedelta(hours=gc.SIEGE_MIN_NOTICE_HOURS)
    local = earliest.astimezone(_TZ)
    candidate = local.replace(hour=siege_hour, minute=0, second=0, microsecond=0)
    if candidate < local:
        candidate += timedelta(days=1)
    return candidate.astimezone(now.tzinfo)


async def active_of(db: AsyncSession, guild_id: int) -> list[GuildSiege]:
    """Осады с участием гильдии, ещё не закончившиеся."""
    return list(
        (
            await db.scalars(
                select(GuildSiege).where(
                    GuildSiege.status.in_(("scheduled", "running")),
                    (GuildSiege.attacker_guild_id == guild_id) | (GuildSiege.defender_guild_id == guild_id),
                ).order_by(GuildSiege.starts_at)
            )
        ).all()
    )


async def recent_of(db: AsyncSession, guild_id: int, limit: int = 10) -> list[GuildSiege]:
    return list(
        (
            await db.scalars(
                select(GuildSiege).where(
                    (GuildSiege.attacker_guild_id == guild_id) | (GuildSiege.defender_guild_id == guild_id),
                ).order_by(GuildSiege.declared_at.desc()).limit(limit)
            )
        ).all()
    )


def siege_cost(guild: Guild, base_tier: str) -> int:
    effects = guild_territory_service.effects_of(guild)
    return round(gc.SIEGE_COST[base_tier] * (1 - effects.get("siege_cost_pct", 0) / 100))


async def declare(db: AsyncSession, actor: Character, cell_id: int) -> GuildSiege:
    guild, _member = await guild_service.require_treasurer(db, actor)
    cell = await db.get(GuildCell, cell_id)
    if cell is None or cell.status != "held":
        raise GuildError("Осаждать можно только чужую базу.")
    if cell.guild_id == guild.id:
        raise GuildError("Это твоя земля.")
    now = now_utc()
    if aware(cell.shield_until) is not None and aware(cell.shield_until) > now:
        raise GuildError("Клетка под щитом - осаду пока не объявить.")
    if await guild_territory_service.active_siege_on(db, cell.x, cell.y) is not None:
        raise GuildError("Эту клетку уже осаждают.")
    if any(s.attacker_guild_id == guild.id for s in await active_of(db, guild.id)):
        raise GuildError("У гильдии уже есть объявленная осада.")
    own = await guild_territory_service.cells_of(db, guild.id)
    cells, mines = guild_territory_service._count_slots(own)
    if cell.mine_id and mines >= gc.mine_slots(guild.level):
        raise GuildError("Взятый рудник некуда будет поставить: нет слота под рудник.")
    if not cell.mine_id and cells >= gc.cell_slots(guild.level):
        raise GuildError("Взятую клетку некуда будет поставить: нет свободного слота.")
    defender = await db.get(Guild, cell.guild_id)
    await guild_service.treasury_spend(db, guild.id, gold=siege_cost(guild, cell.base_tier))
    siege = GuildSiege(
        attacker_guild_id=guild.id, defender_guild_id=defender.id, cell_id=cell.id,
        x=cell.x, y=cell.y, declared_at=now, starts_at=next_window(defender.siege_hour, now),
        status="scheduled",
    )
    db.add(siege)
    when = siege.starts_at.astimezone(_TZ).strftime("%d.%m %H:%M")
    await guild_service.log(
        db, guild.id, "siege", f"{actor.name} объявляет осаду [{defender.tag}] на ({cell.x}; {cell.y}): {when} МСК.",
        actor.id,
    )
    await guild_service.log(
        db, defender.id, "siege", f"[{guild.tag}] объявляет осаду ({cell.x}; {cell.y}): {when} МСК.",
    )
    await db.flush()
    return siege


async def set_siege_hour(db: AsyncSession, actor: Character, hour: int) -> None:
    guild, _member = await guild_service.require_treasurer(db, actor)
    if hour not in gc.SIEGE_HOURS_ALLOWED:
        raise GuildError("Окно осад - с 12 до 23 часов по Москве.")
    guild.siege_hour = hour
    await guild_service.log(db, guild.id, "siege", f"{actor.name} назначает окно осад: {hour}:00 МСК.", actor.id)


async def lock_at(db: AsyncSession, x: int, y: int, now: datetime | None = None) -> GuildSiege | None:
    """Осада, из-за которой на клетке сейчас нельзя драться (сбор или бой)."""
    now = now or now_utc()
    siege = await guild_territory_service.active_siege_on(db, x, y)
    if siege is None:
        return None
    if siege.status == "running":
        return siege
    if aware(siege.starts_at) - timedelta(minutes=gc.SIEGE_GATHER_MINUTES) <= now:
        return siege
    return None


async def due(db: AsyncSession, now: datetime | None = None) -> tuple[list[GuildSiege], list[GuildSiege]]:
    """(осады, у которых начался час сбора; осады, которым пора начинаться)."""
    now = now or now_utc()
    rows = (await db.scalars(select(GuildSiege).where(GuildSiege.status == "scheduled"))).all()
    gather, start = [], []
    for siege in rows:
        starts = aware(siege.starts_at)
        if starts <= now:
            start.append(siege)
        elif not siege.gather_notified and starts - timedelta(minutes=gc.SIEGE_GATHER_MINUTES) <= now:
            siege.gather_notified = True
            gather.append(siege)
    await db.flush()
    return gather, start


# --- Гарнизон -------------------------------------------------------------------


async def garrison(db: AsyncSession, siege: GuildSiege, first_id: int) -> list[CombatantState]:
    """Стражи защищающейся базы: казармы дают число и силу, башня и древо -
    прибавку к силе. id - отрицательные, с first_id вниз (не пересекаются с
    персонажами)."""
    cell = await db.get(GuildCell, siege.cell_id) if siege.cell_id else None
    if cell is None:
        return []
    defender = await db.get(Guild, siege.defender_guild_id)
    barracks = await guild_territory_service.building_at(db, cell.id, gc.B_BARRACKS)
    tower = await guild_territory_service.building_at(db, cell.id, gc.B_TOWER)
    b_level = barracks.level if barracks else 0
    effects = guild_territory_service.effects_of(defender)
    size = gc.garrison_size(b_level)
    if size > 0:
        size += int(effects.get("garrison_size", 0))
    power = (
        1 + gc.GARRISON_POWER_PER_LEVEL * b_level
        + gc.TOWER_GARRISON_PER_LEVEL * (tower.level if tower else 0)
        + effects.get("garrison_power_pct", 0) / 100
    )
    stat = round(gc.GARRISON_BASE_STAT * power)
    result = []
    for i in range(size):
        result.append(build_combatant(
            id=first_id - i, side=1, kind="mob", name=f"Страж [{defender.tag}] {i + 1}",
            level=gc.GARRISON_LEVEL,
            stats=Stats(strength=stat, agility=round(stat * 0.6), intellect=stat, vitality=round(stat * 1.3), will=stat),
            primary_stat="str",
        ))
    return result


def siege_modifiers(stats: Stats, character, attacker: bool) -> Stats:
    """Древо: урон и защита в осадах - через основные статы бойца."""
    dmg = guild_service.perk(character, "siege_damage_pct") / 100
    defense = guild_service.perk(character, "siege_defense_pct") / 100
    return Stats(
        strength=round(stats.strength * (1 + dmg)),
        agility=stats.agility,
        intellect=round(stats.intellect * (1 + dmg)),
        vitality=round(stats.vitality * (1 + defense * 2)),
        will=stats.will,
    )


# --- Исход ------------------------------------------------------------------------


@dataclass
class SiegeOutcome:
    siege: GuildSiege
    captured: bool
    text: str
    loot: int = 0


async def finish(db: AsyncSession, siege_id: int, attackers_won: bool, attackers_present: bool = True) -> SiegeOutcome:
    siege = await db.get(GuildSiege, siege_id)
    attacker = await db.get(Guild, siege.attacker_guild_id)
    defender = await db.get(Guild, siege.defender_guild_id)
    cell = await db.get(GuildCell, siege.cell_id) if siege.cell_id else None
    now = now_utc()
    siege.finished_at = now
    a_tag = attacker.tag if attacker else "?"
    d_tag = defender.tag if defender else "?"
    if not attackers_present:
        siege.status = "failed"
        siege.result = f"[{a_tag}] не явились под стены ({siege.x}; {siege.y})."
        if cell is not None:
            cell.shield_until = now + timedelta(hours=gc.DEFENSE_SHIELD_HOURS)
        await _log_both(db, siege, siege.result)
        await db.flush()
        return SiegeOutcome(siege, False, siege.result)
    if not attackers_won or cell is None or attacker is None:
        siege.status = "repelled"
        siege.result = f"[{d_tag}] отбивают осаду [{a_tag}] на ({siege.x}; {siege.y})."
        if cell is not None:
            cell.shield_until = now + timedelta(hours=gc.DEFENSE_SHIELD_HOURS)
        await _log_both(db, siege, siege.result)
        await db.flush()
        return SiegeOutcome(siege, False, siege.result)

    siege.status = "captured"
    # Склад срезает добычу: чем он больше, тем надёжнее спрятана казна.
    levels = await guild_service.building_levels(db, defender.id)
    share = max(0.0, gc.SIEGE_LOOT_SHARE - gc.SIEGE_LOOT_CUT_PER_WAREHOUSE_LEVEL * levels.get(gc.B_WAREHOUSE, 0))
    loot = int(defender.treasury_gold * share)
    if loot > 0:
        await guild_service.treasury_spend(db, defender.id, gold=loot)
        await guild_service.treasury_add(db, attacker.id, gold=loot)
    # База переходит, постройки теряют уровень.
    if cell.base_tier == gc.BASE_CITADEL:
        own = await guild_territory_service.cells_of(db, attacker.id)
        if any(c.base_tier == gc.BASE_CITADEL for c in own):
            cell.base_tier = gc.BASE_FORT
    cell.guild_id = attacker.id
    cell.upgrade_to = None
    cell.upgrade_done_at = None
    cell.shaft_progress = 0.0
    cell.shaft_checked_at = now
    effects = guild_territory_service.effects_of(attacker)
    cell.shield_until = now + timedelta(hours=gc.CAPTURE_SHIELD_HOURS + effects.get("shield_hours", 0))
    for building in (await db.scalars(select(GuildBuilding).where(GuildBuilding.cell_id == cell.id))).all():
        building.upgrading_to = None
        building.done_at = None
        building.level -= 1
        if building.level <= 0:
            await db.delete(building)
    siege.result = f"[{a_tag}] берут ({siege.x}; {siege.y}) у [{d_tag}]" + (
        f" и уносят {loot} золота из казны." if loot else "."
    )
    await _log_both(db, siege, siege.result)
    await db.flush()
    await guild_service.refresh_perks(db, attacker)
    await guild_service.refresh_perks(db, defender)
    return SiegeOutcome(siege, True, siege.result, loot)


async def _log_both(db: AsyncSession, siege: GuildSiege, text: str) -> None:
    await guild_service.log(db, siege.attacker_guild_id, "siege", text)
    await guild_service.log(db, siege.defender_guild_id, "siege", text)


def max_turns() -> int:
    return bc.PVP_MAX_TURNS
