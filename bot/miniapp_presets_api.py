"""Мини-апп, пресеты экипировки: список, сохранение, переключение, покупка
слота. В бою пресет не меняется.

Вынесено из bot/miniapp_api.py без изменений (2026-10-22, нарезка); маршруты
регистрирует miniapp_api.register_routes.
"""

from aiohttp import web
from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from services import preset_service
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
        presets = await preset_service.presets_of(session, character)
        try:
            next_cost = preset_service.next_slot_cost(character.preset_slots)
        except PresetValidationError:
            next_cost = None

        # Руны-навыки (2026-11-10): пресет - имя и запомненная раскладка рун,
        # баффов больше нет. Пассивка подкласса - на вкладке «Герой».
        return web.json_response(
            {
                "preset_slots": character.preset_slots,
                "next_slot_cost": next_cost,
                "presets": [
                    {"id": p.id, "name": p.name, "is_active": p.is_active,
                     # None - пресет руны не трогает, иначе сколько рун запомнено
                     "runes": None if p.runes is None else len(p.runes)}
                    for p in presets
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
    preset_id = body.get("preset_id")
    if not isinstance(name, str) or not name.strip():
        return web.json_response({"error": "bad_request"}, status=400)
    if preset_id is not None and not isinstance(preset_id, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        try:
            preset = await preset_service.save_preset(session, character, name.strip()[:40], [], {}, preset_id)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except NotEnoughCurrency:
            return web.json_response({"error": "not_enough_gold"}, status=400)
        await session.commit()
        return web.json_response({"id": preset.id, "name": preset.name})


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
            _preset, note = await preset_service.switch_with_runes(session, character, preset_id)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        await session.commit()
        return web.json_response({"ok": True, "note": note})


async def handle_post_preset_runes(request: web.Request) -> web.Response:
    """Запомнить в пресете вставленные сейчас руны или забыть (репорт 340)."""
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    preset_id = body.get("preset_id") if isinstance(body, dict) else None
    keep = body.get("keep", True) if isinstance(body, dict) else True
    if not isinstance(preset_id, int) or not isinstance(keep, bool):
        return web.json_response({"error": "bad_request"}, status=400)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        try:
            preset = await preset_service.remember_runes(session, character, preset_id, keep)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        await session.commit()
        return web.json_response({"runes": None if preset.runes is None else len(preset.runes)})


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
