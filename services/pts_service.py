"""Рейтинг PvP - PTS: расчёт очков за победу, сезоны, ранги. Правила и
числа - game/economy/pts_config.py.

Дуэль: победитель получает очки за побеждённого, тот теряет столько же.
Массовый бой: каждая гибель - отдельный расчёт, очки за неё делят все, кто
бил жертву, по доле урона. Осада и ничья PTS не дают.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import pts_config as pc
from models import Character, CharacterTitle, PvpBattle, PvpSeasonResult

NO_LEVEL = "level"     # жертва слабее на LEVEL_GAP+ уровней
NO_GAP = "gap"         # у победителя на CUTOFF+ PTS больше
NO_REPEAT = "repeat"   # третья+ дуэль той же пары за REPEAT_WINDOW_HOURS
NO_FIGHT = "nofight"   # проигравший ни разу не пытался ударить


def rank_name(pts: int) -> str:
    name = pc.RANKS[0][1]
    for floor, title in pc.RANKS:
        if pts >= floor:
            name = title
    return name


def _pts(c: Character) -> int:
    return c.pts if c.pts is not None else pc.START


@dataclass
class PairResult:
    points: float      # сколько получает победитель (дробно - делится в массовом)
    reason: str | None = None


def pair_points(winner: Character, victim: Character) -> PairResult:
    """Очки за победу winner над victim по рейтингам ДО боя."""
    from services import pk_service

    w, v = _pts(winner), _pts(victim)
    # Клеймёный (2026-10-15) - честная добыча при любой разнице уровней.
    # Младший, обогнавший старшего по PTS (2026-10-23, владелец), - тоже:
    # иначе рейтинг прятал бы низких от высоких. Очки за него - обычные, без
    # надбавки за победу над сильнейшим: в бою сильнее не он.
    outranks = v > w
    low = victim.level <= winner.level - pc.LEVEL_GAP
    if low and not outranks and not pk_service.marks(victim):
        return PairResult(0.0, NO_LEVEL)
    if w - v >= pc.CUTOFF:
        return PairResult(0.0, NO_GAP)
    expected = 1 / (1 + 10 ** ((v - w) / pc.SCALE))
    points = pc.K * (1 - expected)
    if v - w >= pc.UPSET_GAP and not (low and outranks):
        points *= pc.UPSET_MULT
    return PairResult(points)


def _apply(character: Character, delta: int) -> None:
    character.pts = max(pc.FLOOR, _pts(character) + delta)


def repeat_mult(prior: int) -> float:
    """Множитель очков дуэли, если у пары уже было prior дуэлей за окно."""
    return pc.REPEAT_MULTS[prior] if prior < len(pc.REPEAT_MULTS) else 0.0


async def recent_duels(db: AsyncSession, a: int, b: int, now: datetime | None = None) -> int:
    """Сколько дуэлей a и b провели за REPEAT_WINDOW_HOURS (ничьи тоже)."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=pc.REPEAT_WINDOW_HOURS)
    rows = await db.scalars(
        select(PvpBattle.participant_ids)
        .where(PvpBattle.battle_type == "duel", PvpBattle.finished_at >= since)
    )
    return sum(1 for ids in rows if a in (ids or []) and b in (ids or []))


def apply_duel(
    winner: Character, loser: Character, *, prior: int = 0, loser_tried: bool = True,
) -> tuple[int, str | None]:
    """Начисляет PTS за дуэль. Вернёт (очки, причина нуля). prior - дуэли
    этой пары за окно до боя, loser_tried - проигравший хоть раз бил или
    применял атакующий навык (промахи в счёт; только защита - нет)."""
    if not loser_tried:
        return 0, NO_FIGHT
    mult = repeat_mult(prior)
    if mult <= 0:
        return 0, NO_REPEAT
    pair = pair_points(winner, loser)
    delta = round(pair.points * mult)
    if delta:
        _apply(winner, delta)
        _apply(loser, -delta)
    return delta, pair.reason


def apply_mass(
    characters: dict[int, Character], dead_ids: list[int],
    damage_by_pair: dict[tuple[int, int], int], side_of: dict[int, int],
) -> dict[int, int]:
    """Массовый бой: за каждую гибель - очки всем, кто бил жертву, по доле
    урона. Рейтинги - снимок до боя. Вернёт {id: изменение PTS}."""
    before = {cid: _pts(c) for cid, c in characters.items()}
    snapshot = {
        cid: _Snap(c.level, before[cid], getattr(c, "pk_marks", 0) or 0, getattr(c, "pk_marks_at", None))
        for cid, c in characters.items()
    }
    deltas: dict[int, float] = {}
    for victim_id in dead_ids:
        victim = snapshot.get(victim_id)
        if victim is None:
            continue
        hitters = {
            attacker: dmg for (attacker, target), dmg in damage_by_pair.items()
            if target == victim_id and dmg > 0 and attacker in snapshot
            and side_of.get(attacker) != side_of.get(victim_id)
        }
        total = sum(hitters.values())
        if total <= 0:
            continue
        for attacker, dmg in hitters.items():
            share = pair_points(snapshot[attacker], victim).points * dmg / total
            deltas[attacker] = deltas.get(attacker, 0.0) + share
            deltas[victim_id] = deltas.get(victim_id, 0.0) - share
    result = {cid: round(d) for cid, d in deltas.items() if round(d)}
    for cid, delta in result.items():
        _apply(characters[cid], delta)
    return result


@dataclass
class _Snap:
    level: int
    pts: int
    # Клеймо: pair_points читает его через pk_service.marks (getattr) - без
    # этих полей клеймёный в массовом бою считался чистым.
    pk_marks: int = 0
    pk_marks_at: datetime | None = None


def delta_line(delta: int, character: Character, reason: str | None = None) -> str:
    """Строка итогов боя: «🏅 PTS: +24 (1 048 · Кровь)»."""
    pts = _pts(character)
    if delta:
        return f"🏅 PTS: {delta:+d} ({pts} · {rank_name(pts)})"
    if reason == NO_LEVEL:
        return "🏅 PTS не начислены: соперник слабее на 5+ уровней."
    if reason == NO_GAP:
        return "🏅 PTS не начислены: соперник намного ниже по рейтингу."
    if reason == NO_REPEAT:
        return f"🏅 PTS не начислены: третья дуэль с этим соперником за {pc.REPEAT_WINDOW_HOURS} часов."
    if reason == NO_FIGHT:
        return "🏅 PTS не начислены: соперник ни разу не пытался ударить."
    return ""


# --- Сезоны -----------------------------------------------------------------


def season_key(now: datetime | None = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(pc.SEASON_TZ))
    return f"{now.year:04d}-{now.month:02d}"


def season_bounds(key: str) -> tuple[datetime, datetime]:
    """Начало и конец сезона «ГГГГ-ММ» (по Москве)."""
    tz = ZoneInfo(pc.SEASON_TZ)
    year, month = (int(x) for x in key.split("-"))
    start = datetime(year, month, 1, tzinfo=tz)
    end = datetime(year + month // 12, month % 12 + 1, 1, tzinfo=tz)
    return start, end


async def season_fights(db: AsyncSession, key: str) -> Counter:
    """Сколько PvP-боёв за сезон провёл каждый (character_id -> боёв)."""
    start, end = season_bounds(key)
    rows = (await db.scalars(select(PvpBattle.participant_ids).where(
        PvpBattle.started_at >= start, PvpBattle.started_at < end,
    ))).all()
    return Counter(int(cid) for ids in rows for cid in ids)


async def season_close(db: AsyncSession, now: datetime | None = None) -> list[PvpSeasonResult]:
    """Итог прошлого сезона - ДО сжатия рейтинга (зовёт season_rollover).
    Пятёрка лучших по PTS среди тех, кто провёл SEASON_MIN_FIGHTS боёв:
    титул на следующий сезон и самоцветы. Сезонные титулы прошлых
    победителей снимаются. Пусто - закрывать нечего или уже закрыто."""
    from services import title_service, wallet_service

    key = season_key(now)
    prev = await db.scalar(select(Character.pts_season).where(
        Character.pts_season.is_not(None), Character.pts_season != key,
    ).limit(1))
    if prev is None:
        return []
    fights = await season_fights(db, prev)
    rows = (await db.scalars(select(Character).where(
        Character.pts_season == prev, Character.creation_state.is_(None),
    ).order_by(Character.pts.desc(), Character.id))).all()
    top = [c for c in rows if fights[c.id] >= pc.SEASON_MIN_FIGHTS][:len(pc.SEASON_PRIZES)]
    results = [
        PvpSeasonResult(
            season=prev, place=place, character_id=c.id, pts=c.pts, fights=fights[c.id],
            title_id=pc.SEASON_PRIZES[place][0], gems=pc.SEASON_PRIZES[place][1],
        )
        for place, c in enumerate(top, start=1)
    ]
    if results:
        # Сначала запись итога: второй одновременный вызов упрётся в
        # уникальность места и ничего не выдаст и не снимет.
        try:
            async with db.begin_nested():
                db.add_all(results)
                await db.flush()
        except IntegrityError:
            return []
    await db.execute(update(Character).where(Character.active_title_id.in_(pc.SEASON_TITLES))
                     .values(active_title_id=None).execution_options(synchronize_session=False))
    await db.execute(delete(CharacterTitle).where(CharacterTitle.title_id.in_(pc.SEASON_TITLES)))
    for result, character in zip(results, top):
        await db.refresh(character, ["active_title_id"])
        await title_service.unlock(db, character, result.title_id)
        # Сезонный титул надевается сразу: он на месяц, и его должны видеть.
        character.active_title_id = result.title_id
        await wallet_service.deposit(db, character.id, "donate", result.gems, taxable=False,
                                     reason="pts_service.season_close")
    await db.flush()
    return results


def previous_key(key: str) -> str:
    year, month = (int(x) for x in key.split("-"))
    return f"{year - (month == 1):04d}-{(month - 2) % 12 + 1:02d}"


async def season_recap(db: AsyncSession, character: Character, now: datetime | None = None) -> dict | None:
    """Итог прошлого сезона для катсцены - пока игрок его не посмотрел.
    None - уже видел или в прошлом сезоне его не было."""
    key = season_key(now)
    if character.pvp_season_seen == key or character.pts_prev is None or character.pts_season != key:
        return None
    prev = previous_key(key)
    rows = (await db.execute(
        select(PvpSeasonResult, Character.name)
        .join(Character, Character.id == PvpSeasonResult.character_id)
        .where(PvpSeasonResult.season == prev).order_by(PvpSeasonResult.place)
    )).all()
    mine = next((r for r, _ in rows if r.character_id == character.id), None)
    return {
        "season": prev, "next": key, "min_fights": pc.SEASON_MIN_FIGHTS,
        "top": [{"place": r.place, "name": name, "pts": r.pts, "title_id": r.title_id} for r, name in rows],
        "me": {
            "place": mine.place if mine else None,
            "title_id": mine.title_id if mine else None,
            "gems": mine.gems if mine else 0,
            "pts_was": character.pts_prev,
            "pts_now": character.pts,
        },
    }


async def season_medals(db: AsyncSession, now: datetime | None = None) -> dict[int, str]:
    """character_id -> значок за место в прошлом сезоне (весь текущий)."""
    prev = previous_key(season_key(now))
    rows = (await db.execute(select(PvpSeasonResult.character_id, PvpSeasonResult.place).where(
        PvpSeasonResult.season == prev, PvpSeasonResult.place.in_(list(pc.SEASON_MEDALS)),
    ))).all()
    return {cid: pc.SEASON_MEDALS[place] for cid, place in rows}


async def season_rollover(db: AsyncSession, now: datetime | None = None) -> int:
    """Новый сезон: рейтинг всех, кто ещё в прошлом, сжимается к START.
    Безопасно звать часто - тронет только тех, у кого сезон не текущий.
    Перед сжатием - итог и награды прошлого сезона (season_close)."""
    key = season_key(now)
    await season_close(db, now)
    result = await db.execute(
        update(Character)
        .where(or_(Character.pts_season.is_(None), Character.pts_season != key))
        .values(
            pts=pc.START + (Character.pts - pc.START) * pc.SEASON_KEEP,
            pts_season=key,
            # Новичок без сезона - без итога: показывать ему нечего.
            pts_prev=case((Character.pts_season.is_(None), None), else_=Character.pts),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0
