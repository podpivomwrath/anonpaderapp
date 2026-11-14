"""Снимок мира для приложения «Монолит» (2026-11-15, владелец: «не базовые
клавиатурные кнопки, а интерактивный формат, привязанный к графике»).

Событие world канала: где герой, в каком он состоянии, что на нём сейчас
идёт и какие действия доступны. Действия - это ровно кнопки текущего экрана
бота (world._current_keyboard: бой, занятость, поездка, смерть, событие,
лавка, город, поле), разобранные по смыслу (intent). Клиент рисует их как
часть сцены - нажатие на клетку, на тварь, на здание - и отправляет обратно
ту же кнопку ({"type": "act", "label", "payload"}): сервер выполняет её той
же логикой, что в чате. Набор действий всегда совпадает с чатом, своей
логики у приложения нет.

Карта сверху - /api/miniapp/map/state (каталог клеток, разломы, босс, путь).
Текст событий и итогов по-прежнему приходит событиями message.

Снимок шлётся сам: после любого сообщения бота игроку в приложении (с
задержкой REFRESH_DELAY, пачка сообщений - один снимок) и при подключении.
"""

import asyncio
from datetime import datetime, timezone

from loguru import logger

from bot import app_channel

#: Сообщения бота идут пачкой (итог боя, опыт, кнопки) - снимок после неё.
REFRESH_DELAY = 0.25
_pending: dict[int, asyncio.Task] = {}


def _label_intents() -> dict[str, str]:
    """Подпись кнопки без payload -> намерение. Только те, что без payload:
    у остальных намерение - payload["type"]."""
    from bot.keyboards import combat_modes
    from bot.keyboards import world as kw

    pairs = {
        kw.BTN_EXPLORE: "explore", kw.BTN_REST: "rest", kw.BTN_LOOK_AROUND: "look",
        kw.BTN_ASH_HANDFUL: "ash_handful", kw.BTN_MOUNT: "mount",
        kw.BTN_ATTACK: "attack", kw.BTN_ITEM: "items", kw.BTN_FLEE: "flee", combat_modes.DEFEND_LABEL: "defend",
        kw.BTN_WALK_CANCEL: "walk_cancel", kw.BTN_CONTINUE_TRAVEL: "travel_continue",
        kw.BTN_STOP_TRAVEL: "travel_stop", kw.BTN_STAY_HERE: "travel_stay",
        kw.BTN_GATE: "city_leave", kw.BTN_SQUARE_BACK: "city_square",
        kw.BTN_TAVERN: "city_tavern", kw.BTN_TAVERN_BADGE: "city_tavern", kw.BTN_MENTOR: "city_mentor",
        kw.BTN_MENTOR_BADGE: "city_mentor", kw.BTN_APPRAISER: "city_appraiser", kw.BTN_ELIXIR_SHOP: "city_elixirs",
        kw.BTN_HOUSE: "city_house", kw.BTN_OVEN: "city_oven", kw.BTN_ALCHEMY: "city_alchemy",
        kw.BTN_ALCHEMY_OLD: "city_alchemy", kw.BTN_ARENA: "city_arena", kw.BTN_MARKET_QUARTER: "city_market",
        kw.BTN_KEEPER: "city_keeper", kw.BTN_INVENTORY: "inventory", kw.BTN_STATS: "stats",
        kw.BTN_PRESETS: "presets", kw.BTN_DAILIES: "dailies", kw.BTN_VOYAGE_RETURN: "voyage_return",
        kw.BTN_READ_SONG: "read_song", kw.BTN_CHARACTER: "character",
    }
    return pairs


_LABELS: dict[str, str] | None = None
def _directions() -> dict[tuple[int, int], str]:
    """Стрелки и подписи-названия городов несут payload move - направление по
    dx/dy из той же таблицы, что у клавиатуры: «вверх» в мире - это +y."""
    from bot.keyboards import world as kw

    names = {kw.BTN_UP: "up", kw.BTN_DOWN: "down", kw.BTN_LEFT: "left", kw.BTN_RIGHT: "right"}
    return {delta: names[arrow] for arrow, delta in kw._DIRECTION_DELTAS.items()}


def classify(button: dict) -> dict:
    """Кнопка из app_channel.parse_keyboard -> действие для клиента."""
    global _LABELS
    if _LABELS is None:
        _LABELS = _label_intents()
    payload = button.get("payload")
    out = {"label": button.get("label") or "", "payload": payload, "color": button.get("color")}
    if button.get("type") == "open_app":
        return {**out, "intent": "open_miniapp"}
    if button.get("type") == "open_link":
        return {**out, "intent": "open_link", "link": button.get("link")}
    kind = payload.get("type") if isinstance(payload, dict) else None
    if kind == "move":
        direction = _directions().get((payload.get("dx"), payload.get("dy")))
        return {**out, "intent": "move", "dir": direction, "dx": payload.get("dx"), "dy": payload.get("dy")}
    if kind:
        return {**out, "intent": str(kind)}
    return {**out, "intent": _LABELS.get(out["label"], "other")}


def actions_of(keyboard_json: str | None) -> list[dict]:
    parsed = app_channel.parse_keyboard(keyboard_json)
    if not parsed:
        return []
    return [classify(b) for row in parsed["rows"] for b in row]


async def _state_name(db, character, vk_id: int, now: datetime) -> str:
    """Тот же порядок, что у world._current_keyboard: бой важнее всего."""
    from bot import explore_rest
    from bot.battle_keyboard import active_battle_keyboard
    from bot.handlers import world as world_handlers
    from game.world import grid
    from services import mount_service, movement_service

    if active_battle_keyboard(vk_id) is not None:
        return "battle"
    if explore_rest.exploring(vk_id):
        return "exploring"
    if explore_rest.resting(vk_id):
        return "resting"
    if movement_service.is_traveling(character, now):
        return "walking"
    if await mount_service.active_travel(db, character.id) is not None:
        return "riding"
    if await world_handlers._check_still_dead(db, character, now):
        return "dead"
    if grid.city_region_at(character.pos_x, character.pos_y) is not None:
        return "screen" if character.screen else "city"
    return "screen" if character.screen else "field"


async def snapshot(vk_id: int) -> dict | None:
    from bot import now_running
    from bot.handlers import world as world_handlers
    from bot.miniapp_api import _load_character
    from game.world import grid
    from services import item_service, vitals_service
    from services.db import get_session_factory

    now = datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        # Не onboarding.get_character: тот запускает суточный сброс, и его
        # оповещение съел бы снимок, а не экран игрока.
        character = await _load_character(db, vk_id)
        if character is None:
            return None
        state = await _state_name(db, character, vk_id, now)
        keyboard = await world_handlers._current_keyboard(db, character, vk_id, now)
        gear = await item_service.compute_gear_bonus(db, character.id)
        vit = (gear or {}).get("vit", 0)
        stats = character.stats
        hp = vitals_service.current_hp(character, stats, vit) if stats is not None else None
        max_hp = vitals_service.max_hp(character, stats, vit) if stats is not None else None
        running = await now_running.collect(db, character, vk_id, now)
        await db.commit()
    return {
        "type": "world", "state": state,
        "pos": {"x": character.pos_x, "y": character.pos_y},
        "city": grid.city_region_at(character.pos_x, character.pos_y),
        "screen": character.screen or None,
        "level": character.level, "hp": hp, "max_hp": max_hp,
        "running": running,
        "actions": actions_of(keyboard),
    }


async def send(vk_id: int) -> None:
    if not app_channel.active(vk_id):
        return
    try:
        data = await snapshot(vk_id)
    except Exception:  # noqa: BLE001 - снимок не должен ронять канал
        logger.exception("Приложение: снимок мира {} не собран", vk_id)
        return
    if data is not None:
        await app_channel.publish(vk_id, data)


def refresh_soon(vk_id: int) -> None:
    """Снимок после пачки сообщений: повторный вызов в окне - один снимок."""
    vk_id = int(vk_id)
    task = _pending.get(vk_id)
    if task is not None and not task.done():
        return

    async def later() -> None:
        try:
            await asyncio.sleep(REFRESH_DELAY)
        finally:
            _pending.pop(vk_id, None)
        await send(vk_id)

    try:
        _pending[vk_id] = asyncio.get_running_loop().create_task(later())
    except RuntimeError:
        _pending.pop(vk_id, None)
