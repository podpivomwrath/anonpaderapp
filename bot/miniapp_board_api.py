"""Вкладка «Доска» мини-аппа: /api/miniapp/board (2026-10-15).

Всё PvP в одном месте: розыск (клеймёные убийцы слабых и награда за их
голову), рейтинг PTS и сезон с рангами. Последние бои
не отдаём: кто с кем дрался - личное дело игроков (решение владельца). Позже сюда же -
награда за голову, назначенная игроками.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiohttp import web
from sqlalchemy import select

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import pk_config as pkc
from game.economy import pts_config as ptc
from models import Character
from services import leaderboard_service, pk_service, pts_service, pvp_service
from services import onboarding_service as onboarding_svc

MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
          "сентябрь", "октябрь", "ноябрь", "декабрь"]


def _season(now: datetime) -> dict:
    local = now.astimezone(ZoneInfo(ptc.SEASON_TZ))
    nxt = (local.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {
        "name": f"{MONTHS[local.month - 1].capitalize()} {local.year}",
        "ends_at": nxt.astimezone(timezone.utc).isoformat(),
        "days_left": max((nxt - local).days, 0),
        "keep_pct": round(ptc.SEASON_KEEP * 100),
        "start": ptc.START,
        "ranks": [{"from": floor, "name": name} for floor, name in ptc.RANKS],
    }


def _next_decay_minutes(c: Character, now: datetime) -> int | None:
    started = pk_service._aware(c.pk_marks_at)
    if started is None:
        return None
    period = timedelta(hours=pkc.DECAY_HOURS)
    gone = int((now - started) / period)
    return max(0, int((started + (gone + 1) * period - now).total_seconds() // 60))


async def _wanted(db, now: datetime) -> list[dict]:
    rows = (await db.scalars(select(Character).where(Character.pk_marks > 0))).all()
    out = []
    for c in rows:
        n = pk_service.marks(c, now)
        if n <= 0:
            continue
        out.append({
            "id": c.id, "name": c.name, "level": c.level,
            "base_class": c.base_class, "subclass": c.subclass,
            "marks": n, "bounty": c.pk_bounty or 0,
            "next_decay_min": _next_decay_minutes(c, now),
            "city_banned": n >= pkc.CITY_BAN_FROM,
            "pos": [c.pos_x, c.pos_y] if c.pos_x is not None else None,
        })
    out.sort(key=lambda w: (-w["marks"], -w["bounty"]))
    return out


async def handle_get(request: web.Request) -> web.Response:
    now = datetime.now(timezone.utc)
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        await db.commit()
        await pts_service.season_rollover(db)
        await db.commit()
        rating = await leaderboard_service.board(db, leaderboard_service.BOARD_PVP, limit=20)
        await db.refresh(character, ["pts", "pts_season"])  # после сжатия сезона
        # Кто не дрался, в таблице не стоит - и места у него нет.
        fought = (character.pvp_wins or 0) + (character.pvp_losses or 0) > 0
        my_rank = await pvp_service.rank_of(db, character) if fought else None
        revenge = None
        if pk_service.revenge_bonus(character, character.revenge_target_id or -1, now):
            target = await db.get(Character, character.revenge_target_id)
            revenge = {
                "name": target.name if target else "?",
                "until": character.revenge_until.isoformat(),
                "bonus_pct": round(pkc.REVENGE_BONUS * 100),
            }
        my_marks = pk_service.marks(character, now)
        data = {
            "season": _season(now),
            "me": {
                "pts": character.pts, "rank": pts_service.rank_name(character.pts), "place": my_rank,
                "marks": my_marks, "bounty": character.pk_bounty or 0,
                "next_decay_min": _next_decay_minutes(character, now) if my_marks else None,
                "consequences": pk_service.consequences(my_marks) if my_marks else None,
                "revenge": revenge,
            },
            "rules": {
                "level_gap": pkc.LEVEL_GAP, "decay_hours": pkc.DECAY_HOURS,
                "bounty_from": pkc.BOUNTY_FROM, "bounty_pct_per_mark": round(pkc.BOUNTY_SHARE_PER_MARK * 100),
                "costly_from": pkc.COSTLY_DEATH_FROM, "city_penalty_from": pkc.CITY_PENALTY_FROM,
                "city_ban_from": pkc.CITY_BAN_FROM, "revenge_pct": round(pkc.REVENGE_BONUS * 100),
                "revenge_hours": pkc.REVENGE_HOURS,
            },
            "wanted": await _wanted(db, now),
            "rating": [
                {"rank": e.rank, "name": e.name, "value": e.value, "premium": e.premium,
                 "base_class": e.base_class, "subclass": e.subclass}
                for e in rating
            ],
        }
    return web.json_response(data)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/board", handle_get)
