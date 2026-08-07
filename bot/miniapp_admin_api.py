"""Админ-эндпоинты мини-аппа (патч 27, ч.1-2): /api/miniapp/admin/*.

Каждый хендлер НЕЗАВИСИМО проверяет request[VK_USER_ID_KEY] == settings.admin_vk_id
(положенное miniapp_auth_middleware после проверки подписи — см. bot/miniapp_auth.py)
и возвращает 403 без каких-либо данных при несовпадении. Не полагаться на то,
что вкладка скрыта на фронтенде — см. safe-rollout секцию патча."""

import random

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY, SETTINGS_KEY
from bot.handlers import world as world_handlers
from bot.miniapp_auth import VK_USER_ID_KEY
from config import Settings
from models import Character
from services import admin_service
from services import onboarding_service as onboarding_svc

_rng = random.Random()


def _is_admin(request: web.Request) -> bool:
    settings: Settings = request.app[SETTINGS_KEY]
    vk_user_id = request.get(VK_USER_ID_KEY)
    return bool(settings.admin_vk_id) and vk_user_id == settings.admin_vk_id


def _forbidden() -> web.Response:
    return web.json_response({"error": "forbidden"}, status=403)


async def handle_get_overview(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        stats = await admin_service.overview_stats(db)
        return web.json_response(
            {
                "players": stats.players,
                "progression": stats.progression,
                "retention": stats.retention,
                "economy": stats.economy,
                "combat": stats.combat,
            }
        )


async def handle_get_search(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    query = request.query.get("q", "")
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        characters = await admin_service.search_characters(db, query)
        results = []
        for c in characters:
            vk_id = await onboarding_svc.vk_id_for_character(db, c.id)
            results.append(
                {
                    "id": c.id, "vk_id": vk_id, "name": c.name, "level": c.level,
                    "class_title": admin_service.class_title(c), "region": c.region,
                    "is_banned": c.is_banned,
                }
            )
        return web.json_response({"results": results})


async def handle_get_player(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    try:
        character_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "bad_request"}, status=400)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        card = await admin_service.player_card(db, character_id)
        if card is None:
            return web.json_response({"error": "not_found"}, status=404)
        return web.json_response(card)


CONFIRM_REQUIRED = {"ban", "set_level", "reset_stats"}


async def handle_post_action(request: web.Request) -> web.Response:
    """Единая точка для всех действий 2.3 — тело: {"action": "...", ...,
    "confirm": true — для опасных}. Каждое действие логируется admin_service."""
    if not _is_admin(request):
        return _forbidden()
    try:
        character_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "bad_request"}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)

    action = body.get("action")
    settings: Settings = request.app[SETTINGS_KEY]
    admin_vk_id = settings.admin_vk_id

    if action in CONFIRM_REQUIRED and not body.get("confirm"):
        return web.json_response({"error": "confirmation_required"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        character = await db.get(Character, character_id)
        if character is None:
            return web.json_response({"error": "not_found"}, status=404)

        try:
            if action == "grant_currency":
                currency = body.get("currency")
                amount = body.get("amount")
                if currency not in ("farm", "donate") or not isinstance(amount, int):
                    return web.json_response({"error": "bad_request"}, status=400)
                await admin_service.grant_currency(db, admin_vk_id, character, currency, amount)
            elif action == "grant_xp":
                amount = body.get("amount")
                if not isinstance(amount, int) or amount <= 0:
                    return web.json_response({"error": "bad_request"}, status=400)
                await admin_service.grant_xp(db, admin_vk_id, character, amount)
            elif action == "grant_trophy":
                trophy_id = body.get("trophy_id")
                amount = body.get("amount")
                if not isinstance(trophy_id, str) or not isinstance(amount, int) or amount <= 0:
                    return web.json_response({"error": "bad_request"}, status=400)
                await admin_service.grant_trophy(db, admin_vk_id, character, trophy_id, amount)
            elif action == "grant_item":
                ilvl = body.get("ilvl")
                if not isinstance(ilvl, int) or ilvl <= 0:
                    return web.json_response({"error": "bad_request"}, status=400)
                await admin_service.grant_item(db, admin_vk_id, character, ilvl, _rng)
            elif action == "set_level":
                level = body.get("level")
                if not isinstance(level, int):
                    return web.json_response({"error": "bad_request"}, status=400)
                await admin_service.set_level(db, admin_vk_id, character, level)
            elif action == "teleport":
                x, y = body.get("x"), body.get("y")
                if not isinstance(x, int) or not isinstance(y, int):
                    return web.json_response({"error": "bad_request"}, status=400)
                await admin_service.teleport(db, admin_vk_id, character, x, y)
            elif action == "restore_hp":
                await admin_service.restore_hp(db, admin_vk_id, character)
            elif action == "reset_activity":
                peer_id = await onboarding_svc.vk_id_for_character(db, character.id)
                if peer_id is not None:
                    await world_handlers.force_unstick(db, character, peer_id)
                await admin_service.reset_activity_db(db, character)
                await admin_service.log_reset_activity(db, admin_vk_id, character)
            elif action == "reset_stats":
                await admin_service.reset_stats(db, admin_vk_id, character)
            elif action == "ban":
                reason = body.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    return web.json_response({"error": "bad_request"}, status=400)
                await admin_service.ban(db, admin_vk_id, character, reason.strip())
            elif action == "unban":
                await admin_service.unban(db, admin_vk_id, character)
            else:
                return web.json_response({"error": "unknown_action"}, status=400)
        except ValueError:
            return web.json_response({"error": "out_of_bounds"}, status=400)

        await db.commit()
        card = await admin_service.player_card(db, character_id)
        return web.json_response(card)


async def handle_get_journal(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    limit = min(int(request.query.get("limit", 50)), 200)
    offset = int(request.query.get("offset", 0))
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        actions = await admin_service.action_journal(db, limit, offset)
        return web.json_response(
            {
                "actions": [
                    {
                        "id": a.id, "admin_vk_id": a.admin_vk_id, "action_type": a.action_type,
                        "target_character_id": a.target_character_id,
                        "old_value": a.old_value, "new_value": a.new_value, "note": a.note,
                        "created_at": a.created_at.isoformat(),
                    }
                    for a in actions
                ]
            }
        )


async def handle_get_bug_reports(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    status = request.query.get("status")
    limit = min(int(request.query.get("limit", 50)), 200)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        reports = await admin_service.list_bug_reports(db, status, limit)
        return web.json_response(
            {
                "reports": [
                    {
                        "id": r.id, "character_id": r.character_id, "text": r.text,
                        "snapshot": r.snapshot, "status": r.status,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in reports
                ]
            }
        )


async def handle_post_bug_report_status(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    try:
        report_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "bad_request"}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    status = body.get("status") if isinstance(body, dict) else None
    if status not in ("new", "in_progress", "closed"):
        return web.json_response({"error": "bad_request"}, status=400)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        report = await admin_service.set_bug_report_status(db, report_id, status)
        if report is None:
            return web.json_response({"error": "not_found"}, status=404)
        await db.commit()
        return web.json_response({"id": report.id, "status": report.status})


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/admin/overview", handle_get_overview)
    app.router.add_get("/api/miniapp/admin/search", handle_get_search)
    app.router.add_get("/api/miniapp/admin/player/{id}", handle_get_player)
    app.router.add_post("/api/miniapp/admin/player/{id}/action", handle_post_action)
    app.router.add_get("/api/miniapp/admin/journal", handle_get_journal)
    app.router.add_get("/api/miniapp/admin/bug_reports", handle_get_bug_reports)
    app.router.add_post("/api/miniapp/admin/bug_reports/{id}/status", handle_post_bug_report_status)
