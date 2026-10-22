"""Мини-апп, пресеты экипировки: список, сохранение, переключение, покупка
слота. В бою пресет не меняется.

Вынесено из bot/miniapp_api.py без изменений (2026-10-22, нарезка); маршруты
регистрирует miniapp_api.register_routes.
"""

from aiohttp import web
from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from services import subclass_service
from game.content_loader import load_content
from game.economy import buff_descriptions
from services import preset_service, trial_service
from services.preset_service import PresetValidationError
from services.wallet_service import NotEnoughCurrency
from bot import miniapp_api


def _in_battle(vk_user_id: int) -> bool:
    """Пресет в бою не меняется (2026-10-18): ни в соло, ни в группе, PvP и рейде."""
    from bot.battle_keyboard import in_any_battle

    return in_any_battle(vk_user_id)


async def handle_get_presets(request: web.Request) -> web.Response:
    """Патч 14, ч.3: секция «Пресеты» — слоты, состав, каталог баффов подкласса
    (открытые + неоткрытые с подсказкой категории). Заглушка до выбора подкласса."""
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        pool = subclass_service.buff_pool(character)
        if pool is None:
            return web.json_response(
                {"subclass": None, "preset_slots": character.preset_slots, "next_slot_cost": None,
                 "presets": [], "buffs": [], "rule_hint": ""}
            )

        presets = await preset_service.presets_of(session, character)
        catalog = load_content().buffs
        unlocked = await trial_service.unlocked_buff_ids(session, character.id)
        subclass_buffs = [b for b in catalog.values() if b.subclass == pool]
        try:
            next_cost = preset_service.next_slot_cost(character.preset_slots)
        except PresetValidationError:
            next_cost = None

        return web.json_response(
            {
                "subclass": pool,
                "preset_slots": character.preset_slots,
                "next_slot_cost": next_cost,
                "presets": [
                    {"id": p.id, "name": p.name, "buff_ids": p.buff_ids, "is_active": p.is_active}
                    for p in presets
                ],
                # Правило состава приходит с сервера: клиент его пересказывал
                # своими словами и врал про групповую поддержку.
                "rule_hint": preset_service.preset_rule_hint(buff_descriptions.CATEGORY_LABELS),
                "buffs": [
                    {
                        "id": b.id,
                        "name": b.name,
                        "category": b.category,
                        "category_label": buff_descriptions.category_label(b.category),
                        # без описания игрок собирает пресет вслепую, по одним названиям
                        "description": buff_descriptions.describe(b),
                        "unlocked": b.id in unlocked,
                    }
                    for b in subclass_buffs
                ],
            }
        )


async def handle_post_presets(request: web.Request) -> web.Response:
    """Создание/изменение состава пресета — платно (services.preset_service)."""
    vk_user_id = request[VK_USER_ID_KEY]
    if _in_battle(vk_user_id):
        return web.json_response({"error": "Не сейчас: идёт бой. Пресет меняется вне боя."}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)

    name = body.get("name")
    buff_ids = body.get("buff_ids")
    preset_id = body.get("preset_id")
    if not isinstance(name, str) or not name.strip() or not isinstance(buff_ids, list):
        return web.json_response({"error": "bad_request"}, status=400)
    if preset_id is not None and not isinstance(preset_id, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        if subclass_service.buff_pool(character) is None:
            return web.json_response({"error": "no_subclass"}, status=400)

        catalog = load_content().buffs
        try:
            preset = await preset_service.save_preset(session, character, name, buff_ids, catalog, preset_id)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except NotEnoughCurrency:
            return web.json_response({"error": "not_enough_gold"}, status=400)
        await session.commit()
        return web.json_response({"id": preset.id, "name": preset.name, "buff_ids": preset.buff_ids})


async def handle_post_preset_switch(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    if _in_battle(vk_user_id):
        return web.json_response({"error": "Не сейчас: идёт бой. Пресет меняется вне боя."}, status=400)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    preset_id = body.get("preset_id") if isinstance(body, dict) else None
    if not isinstance(preset_id, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        try:
            await preset_service.switch_active_preset(session, character, preset_id)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        await session.commit()
        return web.json_response({"ok": True})


async def handle_post_preset_buy_slot(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        try:
            await preset_service.buy_preset_slot(session, character)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except NotEnoughCurrency:
            return web.json_response({"error": "not_enough_gold"}, status=400)
        await session.commit()
        return web.json_response({"preset_slots": character.preset_slots})
