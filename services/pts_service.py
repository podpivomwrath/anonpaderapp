"""Рейтинг PvP - PTS: расчёт очков за победу, сезоны, ранги. Правила и
числа - game/economy/pts_config.py.

Дуэль: победитель получает очки за побеждённого, тот теряет столько же.
Массовый бой: каждая гибель - отдельный расчёт, очки за неё делят все, кто
бил жертву, по доле урона. Осада и ничья PTS не дают.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import pts_config as pc
from models import Character

NO_LEVEL = "level"     # жертва слабее на LEVEL_GAP+ уровней
NO_GAP = "gap"         # у победителя на CUTOFF+ PTS больше


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
    if victim.level <= winner.level - pc.LEVEL_GAP:
        return PairResult(0.0, NO_LEVEL)
    w, v = _pts(winner), _pts(victim)
    if w - v >= pc.CUTOFF:
        return PairResult(0.0, NO_GAP)
    expected = 1 / (1 + 10 ** ((v - w) / pc.SCALE))
    points = pc.K * (1 - expected)
    if v - w >= pc.UPSET_GAP:
        points *= pc.UPSET_MULT
    return PairResult(points)


def _apply(character: Character, delta: int) -> None:
    character.pts = max(pc.FLOOR, _pts(character) + delta)


def apply_duel(winner: Character, loser: Character) -> tuple[int, str | None]:
    """Начисляет PTS за дуэль. Вернёт (очки, причина нуля)."""
    pair = pair_points(winner, loser)
    delta = round(pair.points)
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
    snapshot = {cid: _Snap(c.level, before[cid]) for cid, c in characters.items()}
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


def delta_line(delta: int, character: Character, reason: str | None = None) -> str:
    """Строка итогов боя: «🏅 PTS: +24 (1 048 · Кровь)»."""
    pts = _pts(character)
    if delta:
        return f"🏅 PTS: {delta:+d} ({pts} · {rank_name(pts)})"
    if reason == NO_LEVEL:
        return "🏅 PTS не начислены: соперник слабее на 5+ уровней."
    if reason == NO_GAP:
        return "🏅 PTS не начислены: соперник намного ниже по рейтингу."
    return ""


# --- Сезоны -----------------------------------------------------------------


def season_key(now: datetime | None = None) -> str:
    now = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(pc.SEASON_TZ))
    return f"{now.year:04d}-{now.month:02d}"


async def season_rollover(db: AsyncSession, now: datetime | None = None) -> int:
    """Новый сезон: рейтинг всех, кто ещё в прошлом, сжимается к START.
    Безопасно звать часто - тронет только тех, у кого сезон не текущий."""
    key = season_key(now)
    result = await db.execute(
        update(Character)
        .where(or_(Character.pts_season.is_(None), Character.pts_season != key))
        .values(
            pts=pc.START + (Character.pts - pc.START) * pc.SEASON_KEEP,
            pts_season=key,
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0
