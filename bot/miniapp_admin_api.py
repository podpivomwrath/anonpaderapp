"""Админ-эндпоинты мини-аппа (патч 27, ч.1-2): /api/miniapp/admin/*.

Каждый хендлер НЕЗАВИСИМО проверяет доступ: админ (settings.admin_vk_id) или модератор (services/staff.py)
(положенное miniapp_auth_middleware после проверки подписи — см. bot/miniapp_auth.py)
и возвращает 403 без каких-либо данных при несовпадении. Не полагаться на то,
что вкладка скрыта на фронтенде — см. safe-rollout секцию патча."""

import random
from datetime import datetime, timezone

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY, SETTINGS_KEY
from bot.handlers import combat as combat_handlers
from bot.handlers import group_combat as group_combat_handlers
from bot.handlers import pvp as pvp_handlers
from bot.handlers import raid_combat as raid_combat_handlers
from bot.handlers import world as world_handlers
from bot.miniapp_auth import VK_USER_ID_KEY
from config import Settings
from game.world import grid
from models import Character
from services import (
    admin_grant_service,
    admin_journal_text,
    admin_service,
    admin_systems_service,
    character_reset_service,
    maintenance_service,
    mining_service,
    naming,
    promo_service,
    staff,
)
from services import onboarding_service as onboarding_svc

_rng = random.Random()


def _is_admin(request: web.Request) -> bool:
    settings: Settings = request.app[SETTINGS_KEY]
    vk_user_id = request.get(VK_USER_ID_KEY)
    # Админ или модератор (services/staff.py): доступ к панели одинаковый.
    return staff.has_panel_access(settings, vk_user_id)


def _forbidden() -> web.Response:
    return web.json_response({"error": "forbidden"}, status=403)


async def handle_get_overview(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        stats = await admin_service.overview_stats(db)
        systems = await admin_systems_service.systems_stats(db)
    return web.json_response(
        {
            "players": stats.players,
            "progression": _humanize_progression(stats.progression),
            "retention": stats.retention,
            "economy": _humanize_economy(stats.economy),
            "combat": stats.combat,
            "systems": systems,
        }
    )


def _titled(counts: dict, title) -> dict:
    """{технический id: n} -> {название: n}; неизвестный id остаётся как есть."""
    out: dict[str, int] = {}
    for key, n in counts.items():
        name = title(key) or key
        out[name] = out.get(name, 0) + n
    return out


def _humanize_progression(progression: dict) -> dict:
    """Классы, подклассы и регионы в обзоре - по-русски, а не warrior/ridge
    (2026-10-13: в обзоре висели технические id)."""
    from bot.onboarding_texts import REGION_TITLES
    from game.classes.base import REGISTRY
    from services.naming import BASE_CLASS_TITLES

    def subclass_title(sid):
        sub = REGISTRY.get(sid)
        return sub.title if sub is not None else None

    return {
        **progression,
        "by_class": _titled(progression.get("by_class", {}), BASE_CLASS_TITLES.get),
        "by_subclass": _titled(progression.get("by_subclass", {}), subclass_title),
        "by_region": _titled(progression.get("by_region", {}), REGION_TITLES.get),
    }


def _humanize_economy(economy: dict) -> dict:
    from services import trophy_service

    def trophy_title(tid):
        trophy = trophy_service.trophy_def(tid)
        return f"{trophy.emoji} {trophy.name}" if trophy is not None else None

    return {**economy, "trophies_in_circulation": _titled(economy.get("trophies_in_circulation", {}), trophy_title)}


async def handle_get_search(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    query = request.query.get("q", "")
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        characters = await admin_service.search_characters(db, query)
        results = []
        for c in characters:
            from models import User

            user = await db.get(User, c.user_id)
            vk_id = user.vk_id if user is not None else None
            results.append(
                {
                    "id": c.id, "vk_id": vk_id, "name": c.name, "level": c.level,
                    "vk_name": " ".join(p for p in (user.vk_first_name, user.vk_last_name) if p) if user else None,
                    "class_title": admin_service.class_title(c), "region": c.region,
                    "region_title": naming.region_title(c.region),
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

    # Патч 31, п.5: живые in-memory флаги (бой/PvP/занятость), которых нет в
    # БД — считаются здесь, а не в services/admin_service.py, тем же способом,
    # что и bot/miniapp_map_api.py::_blocked_reason (сервисный слой намеренно
    # не импортирует bot/handlers/*, см. докстринг admin_service.py).
    vk_id = card.get("vk_id")
    card["in_combat"] = vk_id is not None and combat_handlers.has_active_encounter(vk_id)
    card["in_pvp"] = vk_id is not None and pvp_handlers.has_active_battle(vk_id)
    card["busy"] = vk_id is not None and world_handlers.is_busy(vk_id)
    card["in_city"] = grid.city_region_at(card["pos_x"], card["pos_y"]) is not None
    return web.json_response(card)


CONFIRM_REQUIRED = {"ban", "set_level", "reset_stats", "reset_character"}


def _in_any_battle(peer_id: int) -> bool:
    """Любой бой в памяти бота (PvE, PvP, рейд, группа): удалять игрока из
    живого боя нельзя - движок боя держит на него ссылку."""
    return (
        combat_handlers.has_active_encounter(peer_id)
        or pvp_handlers.has_active_battle(peer_id)
        or raid_combat_handlers.has_active_battle(peer_id)
        or group_combat_handlers.has_active_group_battle(peer_id)
    )


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
    # В журнал - тот, кто нажал: админ или модератор.
    admin_vk_id = request[VK_USER_ID_KEY]

    if action in CONFIRM_REQUIRED and not body.get("confirm"):
        return web.json_response({"error": "confirmation_required"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        character = await db.get(Character, character_id)
        if character is None:
            return web.json_response({"error": "not_found"}, status=404)

        granted = None
        reset_info = None
        reset_peer_id = None
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
                # Патч 39: admin_override=True — снимает ВСЕ состояния (в т.ч.
                # PvP) без ранних выходов и телепортирует в родной город, а
                # не просто прерывает первое найденное "событие" (см.
                # докстринг force_unstick и reset_activity_db).
                peer_id = await onboarding_svc.vk_id_for_character(db, character.id)
                if peer_id is not None:
                    await world_handlers.force_unstick(db, character, peer_id, admin_override=True)
                await admin_service.reset_activity_db(db, character)
                await admin_service.log_reset_activity(db, admin_vk_id, character)
            elif action == "reset_stats":
                await admin_service.reset_stats(db, admin_vk_id, character)
            elif action == "reset_character":
                # Полное обнуление: игрок начнёт заново с онбординга. Защита от
                # промаха по кнопке: ник в теле обязан совпасть с ником персонажа.
                confirm_name = body.get("confirm_name")
                if (
                    not isinstance(confirm_name, str)
                    or confirm_name.strip().casefold() != character.name.strip().casefold()
                ):
                    return web.json_response({"error": "name_mismatch"}, status=400)
                reset_peer_id = await onboarding_svc.vk_id_for_character(db, character.id)
                if reset_peer_id is not None:
                    # Снимаем путь/отдых/исследование/бой (force_unstick сам коммитит
                    # перед вложенными сессиями), рейд и групповой бой он не
                    # прерывает - их проверяем ниже и отказываем.
                    await world_handlers.force_unstick(db, character, reset_peer_id, admin_override=True)
                    if _in_any_battle(reset_peer_id):
                        return web.json_response({"error": "in_battle"}, status=409)
                await admin_service.reset_activity_db(db, character)
                reset_info = await character_reset_service.reset_character(db, admin_vk_id, character.id)
            elif action == "ban":
                reason = body.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    return web.json_response({"error": "bad_request"}, status=400)
                await admin_service.ban(db, admin_vk_id, character, reason.strip())
            elif action == "unban":
                await admin_service.unban(db, admin_vk_id, character)
            elif action == "grant_admin_mount":
                await admin_service.grant_admin_mount(db, admin_vk_id, character)
            elif action == "grant_admin_weapon":
                await admin_service.grant_admin_weapon(db, admin_vk_id, character)
            elif action == "grant_any":
                # Патч 107: выдача любой позиции каталога (admin_grant_service).
                key, amount, ilvl = body.get("key"), body.get("amount"), body.get("ilvl")
                if (
                    not isinstance(key, str) or not isinstance(amount, int)
                    or (ilvl is not None and not isinstance(ilvl, int))
                ):
                    return web.json_response({"error": "bad_request"}, status=400)
                granted = await admin_grant_service.grant(db, admin_vk_id, character, key, amount, ilvl, _rng)
            else:
                return web.json_response({"error": "unknown_action"}, status=400)
        except character_reset_service.ResetBlocked as e:
            await db.rollback()
            return web.json_response({"error": e.code, "message": e.message}, status=409)
        except admin_grant_service.GrantError as e:
            return web.json_response({"error": str(e)}, status=400)
        except ValueError:
            return web.json_response({"error": "out_of_bounds"}, status=400)
        except admin_service.NotSelfTarget:
            # Патч 34, ч.3: тестовые предметы — только себе.
            return web.json_response({"error": "self_only"}, status=400)

        await db.commit()
        if reset_info is not None:
            # Персонажа больше нет - карточки не будет. Игроку сообщаем, что делать
            # дальше: его следующее сообщение запустит онбординг.
            if reset_peer_id is not None:
                await world_handlers.send_plain_notice(
                    reset_peer_id,
                    "🔄 Твой персонаж обнулён администратором. Напиши любое сообщение - начнёшь заново.",
                )
            return web.json_response({"reset": True, **reset_info})
        card = await admin_service.player_card(db, character_id)
        if granted is not None:
            card["granted"] = granted
            peer_id = await onboarding_svc.vk_id_for_character(db, character_id)
            if peer_id is not None:
                await world_handlers.send_plain_notice(peer_id, admin_grant_service.player_notice(granted))
        return web.json_response(card)


async def handle_get_catalog(request: web.Request) -> web.Response:
    """Патч 107: всё, что можно выдать, по группам - для кнопки «Выдать
    предмет» в карточке игрока."""
    if not _is_admin(request):
        return _forbidden()
    return web.json_response({"groups": admin_grant_service.catalog()})


#: Действия, которые игрок делает сам (покупки в магазине), - в журнале
#: подписываются им, а не админом.
SELF_ACTIONS = {"shop_rename", "shop_firm_rename"}


async def handle_get_journal(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    limit = min(int(request.query.get("limit", 50)), 200)
    offset = int(request.query.get("offset", 0))
    session_factory = request.app[SESSION_FACTORY_KEY]
    settings: Settings = request.app[SETTINGS_KEY]
    async with session_factory() as db:
        actions = await admin_service.action_journal(db, limit, offset)
        targets = await _character_names(db, [a.target_character_id for a in actions if a.target_character_id])
        actors = await _actor_labels(db, settings, {a.admin_vk_id for a in actions})
        actor_ids = await _actor_character_ids(db, {a.admin_vk_id for a in actions})
        return web.json_response(
            {
                "actions": [
                    {
                        "id": a.id, "admin_vk_id": a.admin_vk_id, "action_type": a.action_type,
                        "target_character_id": a.target_character_id,
                        "old_value": a.old_value, "new_value": a.new_value, "note": a.note,
                        "created_at": a.created_at.isoformat(),
                        # Обычным языком (2026-10-13): кто и что сделал. Донат
                        # делает сам игрок - подписываем его, а не «модератора».
                        "who": (
                            f"💰 {(a.new_value or {}).get('donor')}" if a.action_type == "donation"
                            else f"🛒 {targets.get(a.target_character_id, 'игрок')}" if a.action_type in SELF_ACTIONS
                            else actors.get(a.admin_vk_id, f"vk {a.admin_vk_id}")
                        ),
                        "who_character_id": (
                            None if a.action_type == "donation" or a.action_type in SELF_ACTIONS
                            else actor_ids.get(a.admin_vk_id)
                        ),
                        "target_name": targets.get(a.target_character_id),
                        "text": admin_journal_text.describe(a, targets.get(a.target_character_id)),
                    }
                    for a in actions
                ]
            }
        )


async def _character_names(db, character_ids: list[int]) -> dict[int, str]:
    from sqlalchemy import select

    from models import Character

    if not character_ids:
        return {}
    rows = await db.execute(select(Character.id, Character.name).where(Character.id.in_(set(character_ids))))
    return {cid: name for cid, name in rows.all()}


async def _actor_character_ids(db, vk_ids: set[int]) -> dict[int, int]:
    from sqlalchemy import select

    from models import Character, User

    if not vk_ids:
        return {}
    rows = await db.execute(
        select(User.vk_id, Character.id).join(Character, Character.user_id == User.id).where(User.vk_id.in_(vk_ids))
    )
    return {vk: cid for vk, cid in rows.all()}


async def _actor_labels(db, settings: Settings, vk_ids: set[int]) -> dict[int, str]:
    """«Админ» или «Модератор <ник персонажа>»."""
    from sqlalchemy import select

    from models import Character, User

    labels: dict[int, str] = {}
    others = [v for v in vk_ids if v != settings.admin_vk_id]
    names: dict[int, str] = {}
    if others:
        rows = await db.execute(
            select(User.vk_id, Character.name).join(Character, Character.user_id == User.id)
            .where(User.vk_id.in_(others))
        )
        names = {vk: name for vk, name in rows.all()}
    for vk in vk_ids:
        if vk == settings.admin_vk_id:
            labels[vk] = "Админ"
        else:
            role = "Модератор" if staff.is_moderator(vk) else "Бывший модератор"
            labels[vk] = f"{role} {names.get(vk, f'vk {vk}')}"
    return labels


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


# --- Обслуживание (патч 58) ---

#: Что видят игроки при массовом сбросе. Текст здесь, а не на фронтенде:
#: формулировки принадлежат серверу (то же правило, что и в bot/*_texts.py).
SERVICE_RESET_NOTICE = "Рестарт сервера, все состояния сброшены"


async def handle_post_reset_activities(request: web.Request) -> web.Response:
    """Вытащить всех разом из зависания после рестарта сервера.

    Сам сброс — services/maintenance_service.py, тот же код, что у
    scripts/reset_activities.py. Рассылка обязательна, а не опциональна:
    у игрока, сброшенного из пути или боя, внизу висит клавиатура ожидания,
    и без нового сообщения с актуальной клавиатурой он остаётся «в зависании»
    даже после того, как БД уже чистая.
    """
    if not _is_admin(request):
        return _forbidden()
    settings: Settings = request.app[SETTINGS_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        report = await maintenance_service.reset_stuck_activities(db)
    report.redis_cleared = await maintenance_service.clear_redis_combat_keys(
        settings.redis_url
    )
    notified = await world_handlers.broadcast_service_notice(SERVICE_RESET_NOTICE)
    return web.json_response({
        "travel_reset": report.travel_reset,
        "mount_reset": report.mount_reset,
        "fishing_reset": report.fishing_reset,
        "mining_reset": report.mining_reset,
        "redis_cleared": report.redis_cleared,
        "notified": notified,
    })


async def handle_get_mining_stats(request: web.Request) -> web.Response:
    """Как горное дело ведёт себя на проде: сбор, спавн, длительность добычи.

    Считается по журналу событий (models/mining.py::MiningEvent), а не по
    остатку в жилах: остаток не показывает ни оборота, ни скорости.
    """
    if not _is_admin(request):
        return _forbidden()
    try:
        hours = max(1, min(int(request.query.get("hours", 24)), 24 * 30))
    except ValueError:
        hours = 24
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        return web.json_response(await mining_service.stats(db, hours))


async def handle_post_mining_refill(request: web.Request) -> web.Response:
    """Наполнить все жилы до кромки — тестовый инструмент.

    В журнал эти события НЕ пишутся: это не игровой спавн, и он не должен
    искажать статистику, по которой мы судим о настоящем.
    """
    if not _is_admin(request):
        return _forbidden()
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        added = await mining_service.refill_all_veins(db)
        stats = await mining_service.stats(db)
    return web.json_response({"added": added, "in_veins": stats["in_veins"]})


# --- Промокоды (патч 50) ---


def _promo_code_json(overview) -> dict:
    return {
        "id": overview.id,
        "code": overview.code,
        "rewards": overview.rewards,
        "max_activations": overview.max_activations,
        "one_per_player": overview.one_per_player,
        "expires_at": overview.expires_at.isoformat() if overview.expires_at else None,
        "created_at": overview.created_at.isoformat() if overview.created_at else None,
        "activation_count": overview.activation_count,
    }


async def handle_get_promo_codes(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        codes = await promo_service.list_codes(db)
        return web.json_response({"codes": [_promo_code_json(c) for c in codes]})


async def handle_post_promo_codes(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)

    code = body.get("code")
    rewards = body.get("rewards")
    max_activations = body.get("max_activations")
    one_per_player = body.get("one_per_player", True)
    expires_at_raw = body.get("expires_at")
    if not isinstance(code, str) or not isinstance(rewards, list):
        return web.json_response({"error": "bad_request"}, status=400)
    if max_activations is not None and not isinstance(max_activations, int):
        return web.json_response({"error": "bad_request"}, status=400)
    expires_at = None
    if expires_at_raw:
        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except ValueError:
            return web.json_response({"error": "bad_request"}, status=400)

    settings: Settings = request.app[SETTINGS_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        try:
            promo = await promo_service.create_code(
                db, request[VK_USER_ID_KEY], code, rewards, max_activations, bool(one_per_player), expires_at,
            )
        except promo_service.PromoValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        await db.commit()
        codes = await promo_service.list_codes(db)
        created = next((c for c in codes if c.id == promo.id), None)
        return web.json_response(_promo_code_json(created) if created else {"id": promo.id})


async def handle_delete_promo_code(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    try:
        promo_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "bad_request"}, status=400)
    settings: Settings = request.app[SETTINGS_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        deleted = await promo_service.delete_code(db, request[VK_USER_ID_KEY], promo_id)
        if not deleted:
            return web.json_response({"error": "not_found"}, status=404)
        await db.commit()
        return web.json_response({"deleted": True})


async def handle_get_promo_code_activations(request: web.Request) -> web.Response:
    if not _is_admin(request):
        return _forbidden()
    try:
        promo_id = int(request.match_info["id"])
    except ValueError:
        return web.json_response({"error": "bad_request"}, status=400)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as db:
        entries = await promo_service.code_activations(db, promo_id)
        return web.json_response(
            {
                "activations": [
                    {
                        "character_id": e.character_id, "character_name": e.character_name,
                        "activated_at": e.activated_at.isoformat(),
                    }
                    for e in entries
                ]
            }
        )


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/admin/overview", handle_get_overview)
    app.router.add_get("/api/miniapp/admin/search", handle_get_search)
    app.router.add_get("/api/miniapp/admin/player/{id}", handle_get_player)
    app.router.add_post("/api/miniapp/admin/player/{id}/action", handle_post_action)
    app.router.add_get("/api/miniapp/admin/catalog", handle_get_catalog)
    app.router.add_get("/api/miniapp/admin/journal", handle_get_journal)
    app.router.add_get("/api/miniapp/admin/bug_reports", handle_get_bug_reports)
    app.router.add_post("/api/miniapp/admin/bug_reports/{id}/status", handle_post_bug_report_status)
    app.router.add_post("/api/miniapp/admin/reset_activities", handle_post_reset_activities)
    app.router.add_get("/api/miniapp/admin/mining_stats", handle_get_mining_stats)
    app.router.add_post("/api/miniapp/admin/mining_refill", handle_post_mining_refill)
    app.router.add_get("/api/miniapp/admin/promo_codes", handle_get_promo_codes)
    app.router.add_get("/api/miniapp/admin/donations", handle_get_donations)
    app.router.add_post("/api/miniapp/admin/donations", handle_post_donations)
    app.router.add_post("/api/miniapp/admin/promo_codes", handle_post_promo_codes)
    app.router.add_delete("/api/miniapp/admin/promo_codes/{id}", handle_delete_promo_code)
    app.router.add_get("/api/miniapp/admin/promo_codes/{id}/activations", handle_get_promo_code_activations)


# --- Донаты (2026-10-16): учёт для выдачи после вайпа. Только владелец. ---


def _is_owner(request: web.Request) -> bool:
    settings: Settings = request.app[SETTINGS_KEY]
    return request.get(VK_USER_ID_KEY) == settings.admin_vk_id


def _donations_json(rows, totals) -> dict:
    return {
        "total_rub": sum(r.amount_rub for r in rows),
        "donors": [
            {"donor": t.donor, "vk_id": t.vk_id, "character_name": t.character_name,
             "total_rub": t.total_rub, "count": t.count}
            for t in totals
        ],
        "entries": [
            {"id": r.id, "donor": r.donor, "vk_id": r.vk_id, "character_name": r.character_name,
             "amount_rub": r.amount_rub, "gems": r.gems, "source": r.source, "note": r.note,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ],
    }


async def handle_get_donations(request: web.Request) -> web.Response:
    if not _is_owner(request):
        return _forbidden()
    from services import donation_service

    async with request.app[SESSION_FACTORY_KEY]() as db:
        rows, totals = await donation_service.ledger(db)
        return web.json_response(_donations_json(rows, totals))


async def handle_post_donations(request: web.Request) -> web.Response:
    """{"action": "add", "donor", "amount", "vk_id"?, "note"?} | {"action": "delete", "id"}."""
    if not _is_owner(request):
        return _forbidden()
    from services import donation_service

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)
    admin_vk_id = request[VK_USER_ID_KEY]
    async with request.app[SESSION_FACTORY_KEY]() as db:
        try:
            if body.get("action") == "add":
                await donation_service.add_manual(
                    db, admin_vk_id, body.get("donor"), body.get("amount"), body.get("vk_id"), body.get("note"),
                )
            elif body.get("action") == "delete":
                await donation_service.delete_manual(db, admin_vk_id, body.get("id"))
            else:
                return web.json_response({"error": "bad_request"}, status=400)
            await db.commit()
        except donation_service.DonationError as exc:
            await db.rollback()
            return web.json_response({"error": str(exc)}, status=409)
        rows, totals = await donation_service.ledger(db)
        return web.json_response(_donations_json(rows, totals))
