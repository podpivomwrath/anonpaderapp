"""Сезоны гильдий: месяц.

Очки сезона - за сутки владения землёй (снимок раз в сутки) и за славу,
набранную в месяце. Первого числа подводится итог прошлого месяца:
лучшая гильдия получает венец сезона (рамку у всех участников до конца
следующего сезона), титул участникам и самоцветы в казну.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import guild_config as gc
from models import Guild, GuildSeasonScore
from services import guild_service, guild_territory_service, title_service


def season_of(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def previous_season(day: date) -> str:
    first = day.replace(day=1)
    return season_of(first - timedelta(days=1))


async def _score_row(db: AsyncSession, season: str, guild_id: int) -> GuildSeasonScore:
    row = await db.scalar(
        select(GuildSeasonScore).where(GuildSeasonScore.season == season, GuildSeasonScore.guild_id == guild_id)
    )
    if row is None:
        row = GuildSeasonScore(season=season, guild_id=guild_id, points=0)
        db.add(row)
        await db.flush()
    return row


async def snapshot(db: AsyncSession, day: date | None = None) -> int:
    """Суточный снимок владений. Идемпотентен в пределах дня."""
    day = day or guild_service.today_msk()
    season = season_of(day)
    guilds = (await db.scalars(select(Guild))).all()
    touched = 0
    for guild in guilds:
        row = await _score_row(db, season, guild.id)
        if row.last_snapshot == day:
            continue
        counts = await guild_territory_service.territory_counts(db, guild.id)
        row.points += (
            counts["cells"] * gc.SEASON_POINTS_CELL + counts["mines"] * gc.SEASON_POINTS_MINE
            + counts["citadel"] * gc.SEASON_POINTS_CITADEL
        )
        row.last_snapshot = day
        touched += 1
    await db.flush()
    return touched


async def standings(db: AsyncSession, season: str | None = None) -> list[tuple[Guild, int]]:
    season = season or season_of(guild_service.today_msk())
    current = season == season_of(guild_service.today_msk())
    rows = (
        await db.execute(
            select(GuildSeasonScore, Guild).join(Guild, Guild.id == GuildSeasonScore.guild_id)
            .where(GuildSeasonScore.season == season)
        )
    ).all()
    scored = {g.id: (g, s.points) for s, g in rows}
    if current:
        for guild in (await db.scalars(select(Guild))).all():
            base = scored.get(guild.id, (guild, 0))[1]
            scored[guild.id] = (guild, base + guild.fame_month // gc.SEASON_FAME_PER_POINT)
    return sorted(scored.values(), key=lambda t: -t[1])


@dataclass
class SeasonResult:
    season: str
    winner: Guild | None
    points: int
    member_ids: list[int]


async def close_if_due(db: AsyncSession, now: datetime | None = None) -> SeasonResult | None:
    """Первого числа - итог прошлого месяца. Повторный вызов в тот же день
    ничего не делает: месячная слава к тому моменту уже обнулена."""
    today = guild_service.today_msk(now)
    if today.day != 1:
        return None
    season = previous_season(today)
    guilds = (await db.scalars(select(Guild))).all()
    if not any(g.fame_month for g in guilds) and not await db.scalar(
        select(GuildSeasonScore.id).where(GuildSeasonScore.season == season)
    ):
        return None
    marker = await _score_row(db, season, guilds[0].id) if guilds else None
    if marker is not None and marker.last_snapshot == today:
        return None
    totals = []
    for guild in guilds:
        row = await _score_row(db, season, guild.id)
        row.points += guild.fame_month // gc.SEASON_FAME_PER_POINT
        row.last_snapshot = today
        guild.fame_month = 0
        totals.append((row.points, guild))
    totals.sort(key=lambda t: -t[0])
    if not totals or totals[0][0] <= 0:
        await db.flush()
        return SeasonResult(season, None, 0, [])
    points, winner = totals[0]
    end_of_next = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    winner.crown_until = datetime.combine(end_of_next, datetime.min.time()).replace(
        tzinfo=guild_service.now_utc().tzinfo
    )
    winner.season_wins += 1
    await guild_service.treasury_add(db, winner.id, gems=gc.SEASON_GEMS_TO_TREASURY)
    ids = []
    for _member, character in await guild_service.members(db, winner.id):
        await title_service.unlock(db, character, gc.SEASON_TITLE_ID)
        ids.append(character.id)
    await guild_service.log(
        db, winner.id, "season",
        f"Гильдия - лучшая в сезоне {season}: {points} очков. Венец сезона и 💎 {gc.SEASON_GEMS_TO_TREASURY} в казну.",
    )
    await db.flush()
    return SeasonResult(season, winner, points, ids)


def has_crown(guild: Guild | None) -> bool:
    until = guild_service.aware(guild.crown_until) if guild else None
    return until is not None and until > guild_service.now_utc()
