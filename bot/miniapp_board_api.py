"""Вкладка «Доска» мини-аппа: /api/miniapp/board (2026-10-15).

Всё PvP в одном месте: розыск (клеймёные убийцы слабых и их метки),
рейтинг PTS и сезон с рангами. Последние бои не отдаём: кто с кем дрался -
личное дело игроков (решение владельца). Награды за голову нет (2026-10-16).
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiohttp import web
from sqlalchemy import func, select

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import pk_config as pkc
from game.economy import pts_config as ptc
from models import Character
from services import crown_service, leaderboard_service, pk_service, pts_service, pvp_service
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
            "marks": n,
            "next_decay_min": _next_decay_minutes(c, now),
            "city_banned": n >= pkc.CITY_BAN_FROM,
            "pos": [c.pos_x, c.pos_y] if c.pos_x is not None else None,
        })
    out.sort(key=lambda w: -w["marks"])
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
        rated_total = await db.scalar(
            select(func.count()).select_from(Character).where(
                Character.creation_state.is_(None), (Character.pvp_wins + Character.pvp_losses) > 0,
            )
        )
        revenge = None
        if pk_service.revenge_bonus(character, character.revenge_target_id or -1, now):
            target = await db.get(Character, character.revenge_target_id)
            revenge = {
                "name": target.name if target else "?",
                "until": character.revenge_until.isoformat(),
                "bonus_pct": round(pkc.REVENGE_BONUS * 100),
            }
        my_marks = pk_service.marks(character, now)
        wanted = await _wanted(db, now)
        frames = await crown_service.frames_by_id(
            db, [e.character_id for e in rating] + [w["id"] for w in wanted],
        )
        for w in wanted:
            w["crown_frame"] = frames.get(w["id"])
        data = {
            "season": _season(now),
            "me": {
                "pts": character.pts, "rank": pts_service.rank_name(character.pts), "place": my_rank, "rated_total": rated_total or 0, "fought": fought,
                "marks": my_marks,
                "next_decay_min": _next_decay_minutes(character, now) if my_marks else None,
                "consequences": pk_service.consequences(my_marks) if my_marks else None,
                "revenge": revenge,
            },
            "rules": {
                "level_gap": pkc.LEVEL_GAP, "decay_hours": pkc.DECAY_HOURS,
                "costly_from": pkc.COSTLY_DEATH_FROM, "city_penalty_from": pkc.CITY_PENALTY_FROM,
                "city_ban_from": pkc.CITY_BAN_FROM, "revenge_pct": round(pkc.REVENGE_BONUS * 100),
                "revenge_hours": pkc.REVENGE_HOURS,
            },
            "wanted": wanted,
            "rating": [
                {"rank": e.rank, "name": e.name, "value": e.value, "premium": e.premium,
                 "base_class": e.base_class, "subclass": e.subclass,
                 "title": e.title, "title_tier": e.title_tier,
                 "crown_frame": frames.get(e.character_id)}
                for e in rating
            ],
        }
    return web.json_response(data)


# --- Заказы на игроков (2026-10-16) ---


async def _contracts_state(db, character, now: datetime) -> dict:
    from game.economy import contract_config as cc
    from models import Wallet
    from services import contract_service, power_service

    contracts = await contract_service.active_contracts(db, now)
    mine_taken = await contract_service.taken_ids(db, character.id)
    counts = await contract_service.taker_counts(db, [c.id for c in contracts])
    frames = await crown_service.frames_by_id(db, list({c.target_id for c in contracts}))
    wallet = await db.get(Wallet, character.id)
    items = []
    for c in contracts:
        target = await db.get(Character, c.target_id)
        if target is None:
            continue
        expires = c.expires_at if c.expires_at.tzinfo else c.expires_at.replace(tzinfo=timezone.utc)
        taken = c.id in mine_taken
        items.append({
            "id": c.id, "target_id": target.id, "name": target.name, "level": target.level,
            "base_class": target.base_class, "subclass": target.subclass,
            "crown_frame": frames.get(target.id),
            "power": (await power_service.power_of(db, target)).total,
            "kills_left": c.kills_left, "kills_total": c.kills_total, "price": c.price,
            "minutes_left": max(int((expires - now).total_seconds() // 60), 0),
            "hunters": counts.get(c.id, 0), "taken": taken,
            "mine": c.orderer_id == character.id, "on_me": target.id == character.id,
            # Где цель - только тем, кто взял заказ.
            "where": contract_service.location_text(target) if taken else None,
        })
    return {
        "gems": wallet.donate_currency if wallet is not None else 0,
        "rules": {
            "min_kills": cc.MIN_KILLS, "max_kills": cc.MAX_KILLS, "min_price": cc.MIN_PRICE,
            "hours": cc.HOURS, "target_min_level": cc.TARGET_MIN_LEVEL,
        },
        "contracts": items,
    }


async def handle_get_contracts(request: web.Request) -> web.Response:
    now = datetime.now(timezone.utc)
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        state = await _contracts_state(db, character, now)
        await db.commit()
    return web.json_response(state)


async def handle_post_contracts(request: web.Request) -> web.Response:
    """{"action": "create", "name", "kills", "price"} | {"action": "take", "id"}."""
    from services import contract_service

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict) or body.get("action") not in ("create", "take"):
        return web.json_response({"error": "bad_request"}, status=400)
    created = None
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        await db.commit()
        try:
            if body["action"] == "create":
                created = await contract_service.create(
                    db, character, body.get("name"), body.get("kills"), body.get("price"),
                )
                done = f"📜 Заказ оформлен: {created.kills_total} убийств по 💎{created.price}. Заказчик никому не виден."
            else:
                contract = await contract_service.take(db, character, body.get("id"))
                target = await db.get(Character, contract.target_id)
                done = f"🎯 Заказ на {target.name} взят. Где цель - на карте и по команде /заказ."
            await db.commit()
        except contract_service.ContractError as exc:
            await db.rollback()
            return web.json_response({"error": str(exc)}, status=409)
        state = await _contracts_state(db, character, datetime.now(timezone.utc))
        await db.commit()
    if created is not None:
        from bot.handlers import contracts as contracts_handlers  # избегаем цикла импортов

        await contracts_handlers.notify_target(created.target_id, created.kills_total)
    state["done"] = done
    return web.json_response(state)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/board", handle_get)
    app.router.add_get("/api/miniapp/contracts", handle_get_contracts)
    app.router.add_post("/api/miniapp/contracts", handle_post_contracts)
