"""Маунты (патч 25, п.7): выбор маунта, ввод координат назначения, поездка с
риском нападения.

Путешествие хранится в БД (services/mount_service.py) — переживает рестарт
бота. Батч-сканер scan() вызывается периодически из main.py по образцу
bot/handlers/respawn.py::scan: один общий job на всех игроков в пути, не
задача-на-игрока. Он же — источник live-отсчёта оставшегося времени (edit
сообщения "в пути", как respawn.py делает со смертью).

Ввод координат X:Y — FSM на vkbottle-диспенсере (тот же механизм, что и
никнейм при онбординге, см. bot/handlers/onboarding.py): пока игрок в
состоянии COORD_INPUT, любой текст перехватывается этим хендлером.
"""

from bot.activity import activity_action
from bot.battle_keyboard import in_any_battle

import random
import re

from vkbottle.dispatch.rules.base import FuncRule
from datetime import datetime, timezone

from loguru import logger
from vkbottle import BaseMiddleware, BaseStateGroup
from vkbottle.bot import BotLabeler, Message

from bot import group_texts
from bot.dispatch_rules import TEXT_ONLY
from bot.handlers import combat as combat_handlers
from bot.handlers import pvp as pvp_handlers
from bot.handlers import world as world_handlers
from bot.keyboards import world as kb
from bot.onboarding_texts import REGION_TITLES
from bot.world_texts import foreign_city_entry_text, hub_attachment
from bot.world_summary import location_attachment, location_summary
from game.world import encounters, grid
from game.economy import mount_config as mc
from game.world import world_config as wc
from game.world.location_types import region_for
from models import Character, CharacterStats, User
from services import (
    item_service,
    mount_service,
    preset_service,
    scene_event_service,
    screen_service,
    story_service,
    wallet_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»


_bot_api = None
_dispenser = None
_live_countdown = True
_rng = random.Random()

# peer_id -> message_id последнего сообщения "в пути" (live-отсчёт)
_travel_message: dict[int, int] = {}
# peer_id -> id поездки, ожидающей подтверждения "Продолжить путь"
_pending_continue: dict[int, int] = {}

_COORD_RE = re.compile(r"^\s*(-?\d+)\s*(?:[:;,]\s*|\s+)(-?\d+)\s*$")
#: «12-20» - только когда оба числа без минуса: «-27-14» неоднозначно.
_COORD_DASH_RE = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
#: Похоже на координаты - цифры и разделители, без букв. Только такие
#: сообщения перехватывает ожидание координат: раньше оно глотало всё подряд,
#: и кнопки «Статы»/«Руда», промокоды и команды отвечали «Не понял
#: координаты» (2026-10-13, переписка игроков).
_COORD_LIKE_RE = re.compile(r"^[\s\d:;,\-]+$")


def parse_coords(text: str) -> tuple[int, int] | None:
    match = _COORD_RE.match(text or "") or _COORD_DASH_RE.match(text or "")
    return (int(match.group(1)), int(match.group(2))) if match else None


_looks_like_coords = FuncRule(lambda message: bool(_COORD_LIKE_RE.match(message.text or "")))


class MountCoordState(BaseStateGroup):
    COORD_INPUT = "mount_coord_input"


class CoordCancelMiddleware(BaseMiddleware[Message]):
    """Любое сообщение, не похожее на координаты (кнопка, команда, промокод),
    отменяет ожидание координат маунта - и само обрабатывается как обычно.
    Раньше ожидание висело дальше, и следующее число бот принимал за
    координаты (2026-10-13)."""

    async def pre(self) -> None:
        if _dispenser is None:
            return
        state = await _dispenser.get(self.event.peer_id)
        # Строкой: str != StateRepresentation у vkbottle даёт True всегда.
        if state is None or str(state.state) != str(MountCoordState.COORD_INPUT):
            return
        if "mount_route_toggle" in str(self.event.payload or "") or "mount_go" in str(self.event.payload or ""):
            return  # переключатель пути - часть того же выбора
        if self.event.payload or not _COORD_LIKE_RE.match(self.event.text or ""):
            await _dispenser.delete(self.event.peer_id)


def setup(bot, bot_api, live_countdown: bool = True) -> None:
    global _bot_api, _dispenser, _live_countdown
    _bot_api = bot_api
    _dispenser = bot.state_dispenser
    _live_countdown = live_countdown
    bot.labeler.message_view.register_middleware(CoordCancelMiddleware)


async def _stats(db, character_id: int) -> CharacterStats:
    from sqlalchemy import select

    return await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character_id))


def _format_seconds(seconds: float) -> str:
    """Без завершающей точки — её ставит вызывающий текст (иначе на стыке
    получается двойная точка: «~3.6 мин..», патч 43)."""
    if seconds >= 60:
        return f"~{seconds / 60:.1f} мин"
    return f"~{seconds:.0f} сек"


async def _blocked_reason(db, character, peer_id: int, now: datetime) -> str | None:
    """Общие гейты для открытия меню маунта и для подтверждения координат:
    None — можно ехать, иначе — текст отказа."""
    from services import death_service, movement_service

    if death_service.is_dead(character, now):
        return "☠ Сначала очнись."
    if pvp_handlers.has_active_battle(peer_id):
        return "Сначала разберись с открытым боем."
    if in_any_battle(peer_id):
        return "В бою не до маунта."
    if world_handlers.is_busy(peer_id):
        return "Сначала закончи то, что начал."
    if movement_service.is_traveling(character, now):
        return "🚶 Ты уже в пути пешком."
    if await mount_service.active_travel(db, character.id) is not None:
        return "🐎 Ты уже в пути на маунте."
    return None


@labeler.message(text=[kb.BTN_MOUNT])
async def open_mounts(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        reason = await _blocked_reason(db, character, peer_id, now)
        if reason is not None:
            await message.answer(reason)
            return
        owned = await mount_service.owned_mounts(db, character.id)
        if not owned:
            await message.answer("У тебя пока нет маунтов.")
            return
        # Пока в игре ровно один маунт (Пепельный скакун) — выбора между
        # несколькими не требуется; структура owned_mounts готова на будущее.
        # Патч 35, аудит: когда маунтов станет больше одного, список выбора
        # ЗДЕСЬ подпадает под общее правило (см. bot/keyboards/appraiser.py) —
        # кнопка на маунт допустима, только если их конечное небольшое число
        # (маунты — фиксированный контент-каталог, не накопительный инвентарь).
        mount = owned[0]
        pos_x, pos_y = character.pos_x, character.pos_y
        safe = bool((character.ui_flags or {}).get("safe_route"))
        targets = await _quick_targets(db, character)

    await _dispenser.set(peer_id, MountCoordState.COORD_INPUT, mount_id=mount.mount_id)
    await message.answer(
        f"{mount.emoji} {mount.name} готов в путь.\n"
        f"Ты в ({pos_x}; {pos_y}). Куда направиться? Пришли координаты в формате X:Y "
        f"(не дальше {wc.WORLD_RADIUS} клеток от Монолита, например 12:-20).\n\n"
        f"{_route_line(safe)}",
        keyboard=_route_keyboard(safe, targets),
    )


async def _quick_targets(db, character) -> list[tuple[str, int, int]]:
    """Быстрые цели для маунта (2026-10-19): квест и живой след события -
    кнопкой, без набора координат. Своя клетка не предлагается."""
    from services import scene_event_service, story_service

    targets = []
    quest = await story_service.quest_destination(db, character)
    if quest is not None:
        targets.append(("📜 " + quest[0], quest[1], quest[2]))
    trail = await scene_event_service.get_trail(db, character.id)
    if trail is not None and scene_event_service.trail_alive(trail):
        targets.append(("🐾 К следу", trail.x, trail.y))
    here = (character.pos_x, character.pos_y)
    return [t for t in targets if (t[1], t[2]) != here]


def _route_line(safe: bool) -> str:
    return (
        "🛡 Путь: безопасный - в обход колец опаснее цели, дольше."
        if safe else "➡️ Путь: прямой - кратчайший, через любые кольца."
    )


def _route_keyboard(safe: bool, targets: list[tuple[str, int, int]] | None = None) -> str:
    from vkbottle import Keyboard, KeyboardButtonColor, Text

    keyboard = Keyboard(inline=True)
    for label, x, y in targets or []:
        keyboard.add(
            Text(f"{label} ({x}; {y})", payload={"type": "mount_go", "x": x, "y": y}),
            color=KeyboardButtonColor.PRIMARY,
        )
        keyboard.row()
    keyboard.add(
        Text("➡️ Сделать прямым" if safe else "🛡 Сделать безопасным", payload={"type": "mount_route_toggle"}),
        color=KeyboardButtonColor.SECONDARY,
    )
    return keyboard.get_json()


@labeler.message(payload_contains={"type": "mount_route_toggle"})
async def route_toggle(message: Message) -> None:
    """Прямой/безопасный путь из чата (2026-10-15) - та же настройка, что
    переключатель на карте мини-аппа (ui_flags.safe_route). Ожидание
    координат не сбрасывается (см. CoordCancelMiddleware)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        flags = dict(character.ui_flags or {})
        flags["safe_route"] = not bool(flags.get("safe_route"))
        character.ui_flags = flags  # новый dict: JSON-поле не следит за изменением на месте
        safe = flags["safe_route"]
        await db.commit()
        targets = await _quick_targets(db, character)
    await message.answer(f"{_route_line(safe)} Пришли координаты.", keyboard=_route_keyboard(safe, targets))


@labeler.message(payload_contains={"type": "mount_go"}, state=MountCoordState.COORD_INPUT)
@activity_action
async def quick_target(message: Message) -> None:
    """Кнопка быстрой цели (квест, след) - то же, что прислать её координаты."""
    payload = message.get_payload_json() or {}
    x, y = payload.get("x"), payload.get("y")
    if not isinstance(x, int) or not isinstance(y, int):
        return
    await _travel_to(message, x, y)


@labeler.message(TEXT_ONLY, _looks_like_coords, state=MountCoordState.COORD_INPUT)
@activity_action
async def coord_input(message: Message) -> None:
    peer_id = message.peer_id
    mount_id = (message.state_peer.payload.get("mount_id") if message.state_peer else None)
    if mount_id is None:
        await _dispenser.delete(peer_id)
        return
    coords = parse_coords(message.text)
    if coords is None:
        await message.answer("Не понял координаты. Формат: X:Y или X Y (например 12:-20).")
        return
    await _travel_to(message, *coords)


async def _travel_to(message: Message, to_x: int, to_y: int) -> None:
    peer_id = message.peer_id
    mount_id = (message.state_peer.payload.get("mount_id") if message.state_peer else None)
    if mount_id is None:
        await _dispenser.delete(peer_id)
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            await _dispenser.delete(peer_id)
            return
        now = datetime.now(timezone.utc)
        reason = await _blocked_reason(db, character, peer_id, now)
        if reason is not None:
            await _dispenser.delete(peer_id)
            await message.answer(reason)
            return
        if not grid.in_bounds(to_x, to_y):
            await message.answer(
                f"Эти координаты за краем мира: он кончается в {wc.WORLD_RADIUS} клетках от Монолита. "
                "Попробуй ещё раз."
            )
            return
        if (to_x, to_y) == (character.pos_x, character.pos_y):
            await message.answer("Ты уже здесь. Назови другую клетку.")
            return
        from services import pk_service

        if grid.city_region_at(to_x, to_y) is not None and pk_service.city_banned(character):
            await message.answer(pk_service.CITY_BAN_TEXT)
            return
        # Безопасный путь - как выбран на карте мини-аппа (настройка персонажа).
        safe = bool((character.ui_flags or {}).get("safe_route"))
        seconds = await start_travel_and_notify(db, character, peer_id, mount_id, to_x, to_y, now, safe=safe)
        assert seconds is not None  # гейты выше уже всё проверили


async def start_travel_and_notify(
    db, character, peer_id: int, mount_id: str, to_x: int, to_y: int,
    now: datetime | None = None, safe: bool = False,
) -> float:
    """Начать поездку и сказать об этом в чат — ОДНА точка для обоих способов
    отправки маунта: из чата (coord_input) и с карты мини-аппа
    (bot/miniapp_map_api.py::handle_post_send_mount).

    Раньше карта повторяла эти три шага у себя, и расхождение между путями
    было вопросом времени: игрок отправлял маунта с карты и не получал в чат
    ничего. Проверки прав/границ остаются на вызывающем (они у путей разные:
    чат отвечает текстом, карта — кодом ошибки), но сам запуск и оповещение
    теперь физически один и тот же код.

    Коммит делает вызывающий: у карты и чата разные транзакционные границы.
    """
    from_x, from_y = character.pos_x, character.pos_y
    # Уезжает - вложенный экран клетки (озеро, рудник) и снасть в воде
    # остаются тут. С карты маунт отправляют, не отойдя от воды, и экран
    # озера ехал вместе с игроком (2026-10-19).
    if character.screen is not None:
        await screen_service.set_screen(db, character, None)
    if character.fishing_cast_at is not None:
        from bot.handlers import fishing as fishing_handlers
        from services import fishing_service

        fishing_handlers.cancel_bite(peer_id)
        fishing_service.clear_cast(character)
    path = mount_service.route(from_x, from_y, to_x, to_y, safe)
    travel = await mount_service.start_travel(db, character, mount_id, to_x, to_y, _rng, now, safe=safe)
    seconds = mount_service.total_travel_seconds(mount_id, len(path))
    await db.commit()
    await notify_travel_started(
        peer_id, to_x, to_y, seconds,
        mount_service.trip_ambush_chance(mount_id, from_x, from_y, to_x, to_y, path=path),
        travel=travel, safe=safe,
    )
    return seconds


async def notify_travel_started(
    peer_id: int, to_x: int, to_y: int, seconds: float, ambush_chance: float, icon: str = "🐎",
    travel=None, safe: bool = False,
) -> None:
    """Сообщение о начале пути на маунте + клавиатура ожидания — общая точка
    для обоих способов отправки маунта (патч 31, фикс 1): из чата (coord_input
    выше) и с карты мини-аппа (bot/miniapp_map_api.py::handle_post_send_mount,
    который раньше не слал в чат ничего вообще — MountTravel создавался
    молча, игрок не понимал, что путь начался, и старая клавиатура оставалась).

    Патч 40, баг 2, п.1: поездка НАЧАЛАСЬ — состояние ожидания координат не
    должно её пережить. coord_input снимает его на своём пути, но отправка
    с карты идёт мимо coord_input вообще — снимаем здесь, в общей точке, не
    завязываясь на то, каким способом маунт был отправлен."""
    if _dispenser is not None:
        await _dispenser.delete(peer_id)
    if _bot_api is None:
        return
    text = (
        f"{icon} Путь начат{' безопасной дорогой' if safe else ''}: ({to_x}; {to_y}), {_format_seconds(seconds)}.\n"
        f"Шанс нападения в пути: {round(ambush_chance * 100)}%."
    )
    try:
        resp = await _bot_api.messages.send(
            peer_id=peer_id, message=text, random_id=0, keyboard=kb.mount_travel_keyboard()
        )
    except Exception:  # noqa: BLE001 - сеть/VK могут бросить что угодно
        # Поездка на этот момент УЖЕ записана в БД, и падение отправки не
        # должно её отменять или ронять HTTP-запрос с карты. Но и молчать
        # нельзя: именно так и выглядела жалоба «с карты не приходит ничего»,
        # а в логах не было ни строчки.
        logger.exception("Не удалось отправить в чат сообщение о начале пути ({})", peer_id)
        return
    # Это же сообщение дальше правится по мере движения (scan): где ты сейчас.
    try:
        _travel_message[peer_id] = int(resp)
    except (TypeError, ValueError):
        pass


def _travel_text(travel, now: datetime) -> str:
    left = mount_service.remaining_seconds(travel, now)
    path = mount_service.path_of(travel)
    x, y = path[travel.cell_index - 1] if travel.cell_index else (travel.from_x, travel.from_y)
    icon = "🐎"
    cells = mount_service.cells_left(travel)
    return (
        f"{icon} В пути: ({x}; {y}) → ({travel.to_x}; {travel.to_y}), "
        f"осталось {cells} кл., {_format_seconds(left)}."
    )


# Сообщение «в пути» - одно на поездку: сообщение о начале пути правится по
# мере движения (текущая клетка, сколько осталось). Кнопки «Остановиться» и
# «Осмотреться» - на обычной клавиатуре внизу (kb.mount_travel_keyboard).


async def send_progress(peer_id: int, travel) -> None:
    """Новое сообщение «в пути» (после боя-нападения) - дальше правится оно."""
    if _bot_api is None:
        return
    try:
        resp = await _bot_api.messages.send(
            peer_id=peer_id, message=_travel_text(travel, datetime.now(timezone.utc)), random_id=0,
            keyboard=kb.mount_travel_keyboard(),
        )
        _travel_message[peer_id] = int(resp)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить сообщение пути ({})", peer_id)


async def close_progress(peer_id: int, text: str) -> None:
    """Путь кончился (прибытие, нападение, остановка): итог вместо отсчёта."""
    msg_id = _travel_message.pop(peer_id, None)
    _countdown_edited.pop(peer_id, None)
    _progress_cell.pop(peer_id, None)
    if msg_id is None or _bot_api is None:
        return
    try:
        await _bot_api.messages.edit(peer_id=peer_id, message_id=msg_id, message=text)
    except Exception:  # noqa: BLE001
        logger.debug("Не удалось закрыть сообщение пути для {}", peer_id)


async def offer_continue(peer_id: int, travel_id: int) -> None:
    """Патч 25, п.7: победа над нападением в пути — предложение продолжить
    (оставшееся время «заморожено» с момента нападения, бой в счёт не идёт;
    resume_travel пересчитает arrives_at от момента нажатия кнопки)."""
    from models import MountTravel

    async with get_session_factory()() as db:
        travel = await db.get(MountTravel, travel_id)
        if travel is None:
            return
        left = mount_service.frozen_remaining_seconds(travel)

    _pending_continue[peer_id] = travel_id
    await _bot_api.messages.send(
        peer_id=peer_id,
        message=f"Нападавший повержен. Дорога зовёт дальше - осталось {_format_seconds(left)}.",
        random_id=0,
        keyboard=kb.continue_travel_keyboard(travel_id),
    )


async def _recover_stranded(peer_id: int) -> None:
    """Патч 40, баг 2, доп.: «Продолжить путь» нажата, а данных о поездке
    нет — не оставлять игрока висеть без кнопок, вернуть на текущую клетку
    обычной клавиатурой карты."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        has_mount = await mount_service.has_any_mount(db, character.id)
        pos = (character.pos_x, character.pos_y)
    await _bot_api.messages.send(
        peer_id=peer_id,
        message="Путь прерван - продолжать нечего. Ты остаёшься на месте.",
        random_id=0,
        keyboard=kb.movement_keyboard(*pos, peer_id, has_mount=has_mount),
    )


@labeler.message(payload_contains={"type": "continue_travel"})
@activity_action
async def continue_travel(message: Message) -> None:
    peer_id = message.peer_id
    pending_id = _pending_continue.get(peer_id)
    if pending_id is None:
        await _recover_stranded(peer_id)
        return
    payload = message.get_payload_json() or {}
    if payload.get("travel") != pending_id:
        return
    _pending_continue.pop(peer_id, None)

    from models import MountTravel

    async with get_session_factory()() as db:
        travel = await db.get(MountTravel, pending_id)
        if travel is None:
            await _recover_stranded(peer_id)
            return
        await mount_service.resume_travel(db, travel)
        await db.commit()

    await send_progress(peer_id, travel)


async def stop_and_notify(peer_id: int, travel_id: int | None = None) -> str | None:
    """Остановиться там, где стоишь: одна точка для кнопки в чате, «Остаться
    здесь» после боя и кнопки на карте мини-аппа. None - остановились,
    иначе текст отказа."""
    after_ambush = travel_id is not None and _pending_continue.get(peer_id) == travel_id
    if in_any_battle(peer_id) or pvp_handlers.has_active_battle(peer_id):
        return "Сначала разберись с боем."
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return "Персонаж не найден."
        travel = await mount_service.active_travel(db, character.id)
        if travel is None or (travel_id is not None and travel.id != travel_id):
            return "Ты сейчас не в пути."
        if not await mount_service.stop_travel(db, travel, character, after_ambush=after_ambush):
            return "Сейчас не остановиться."
        await db.commit()
    _pending_continue.pop(peer_id, None)
    await close_progress(peer_id, f"⏹ Остановка на ({character.pos_x}; {character.pos_y}).")
    await send_cell_screen(peer_id, "⏹ Ты сходишь с пути.")
    return None


async def send_cell_screen(peer_id: int, header: str) -> None:
    """Экран клетки, где персонаж стоит: город - площадь, иначе сводка
    клетки с клавиатурой движения (как после прибытия)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        stats = await _stats(db, character.id)
        wallet = await wallet_service.get_wallet(db, character.id)
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        quest_line = await story_service.quest_summary_line(db, character)
        group_block = await group_texts.group_summary_block(db, character.id)
        has_mount = await mount_service.has_any_mount(db, character.id)
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is not None:
            await screen_service.set_screen(db, character, None)
            is_foreign = region != character.region
            mentor_badge = not is_foreign and await story_service.mentor_badge_active(db, character)
            await db.commit()
            await _bot_api.messages.send(
                peer_id=peer_id, message=f"{header}\n\n{REGION_TITLES[region]}", random_id=0,
                attachment=hub_attachment(region),
                keyboard=kb.city_square_keyboard(character, mentor_badge, has_mount=has_mount, is_foreign=is_foreign),
            )
            return
        await db.commit()
    text = f"{header}\n\n" + location_summary(
        character, stats, _rng, wallet.farm_currency, gear_bonus.get("vit", 0), quest_line,
        wallet.donate_currency, group_block,
    )
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0, attachment=location_attachment(character),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
    )
    await world_handlers.send_cell_buttons(peer_id, character)


@labeler.message(text=[kb.BTN_STOP_TRAVEL])
@activity_action
async def stop_button(message: Message) -> None:
    reason = await stop_and_notify(message.peer_id)
    if reason is not None:
        await message.answer(reason)


@labeler.message(payload_contains={"type": "stop_travel"})
@activity_action
async def stay_here(message: Message) -> None:
    payload = message.get_payload_json() or {}
    travel_id = payload.get("travel")
    if not isinstance(travel_id, int):
        return
    reason = await stop_and_notify(message.peer_id, travel_id)
    if reason is not None:
        await message.answer(reason)


def is_paused(peer_id: int) -> bool:
    """Персонаж занят - поездка ждёт: бой (свой или PvP, в том числе когда
    на него напали в пути), исследование, отдых. Иначе он уезжал бы с
    клетки посреди боя."""
    return in_any_battle(peer_id) or pvp_handlers.has_active_battle(peer_id) or world_handlers.is_busy(peer_id)


# peer_id -> когда последний раз правили сообщение «в пути»: скан идёт раз в
# пару секунд (значок на карте не должен отставать), а VK править чаще не к чему.
_countdown_edited: dict[int, datetime] = {}
# peer_id -> клетка пути, показанная в сообщении: правим сразу, как она сменилась.
_progress_cell: dict[int, int] = {}


async def scan() -> None:
    """Батч-проход (main.py, раз в TRAVEL_STEP_SCAN_SECONDS): двигает всех в
    пути по клеткам, разыгрывает нападения на новых клетках, завершает
    прибывших и обновляет отсчёт. Один job на всех - по образцу
    bot/handlers/respawn.py::scan."""
    if _bot_api is None:
        return
    from sqlalchemy import select

    from models import MountTravel
    from services import death_service

    now = datetime.now(timezone.utc)
    sf = get_session_factory()

    ambush_starts = []
    arrivals = []
    daily_announce = []
    countdowns = []

    async with sf() as db:
        rows = (await db.scalars(select(MountTravel).where(MountTravel.status == "traveling"))).all()
        vkid_map: dict[int, int] = {}
        if rows:
            vkid_map = dict((
                await db.execute(
                    select(Character.id, User.vk_id).join(User, User.id == Character.user_id)
                    .where(Character.id.in_({t.character_id for t in rows}))
                )
            ).all())

        for travel in rows:
            peer_id = vkid_map.get(travel.character_id)
            character = await db.get(Character, travel.character_id)
            if peer_id is None or character is None:
                continue
            if death_service.is_dead(character, now):
                # Погиб в пути не от нападения маунта (например, в PvP) -
                # поездка кончилась вместе с ним.
                await mount_service.cancel_travel(db, travel)
                continue
            step = mount_service.advance(travel, character, _rng, now, paused=is_paused(peer_id))
            if step.cells:
                from services import daily_service

                # «Странник» и гильдейское задание на клетки: каждая клетка
                # верхом засчитывается (2026-10-14/15; раньше - одна за поездку).
                daily_announce.append((peer_id, await daily_service.record_cell_moved(
                    db, character, step.cells,
                )))
            if step.moved:
                from bot.handlers import guild as guild_handlers  # избегаем цикла импортов

                # Башня гильдии замечает и тех, кто проезжает мимо.
                await guild_handlers.on_arrival(db, character)
                # Группе - только когда всадник остановился (2026-10-15): на
                # каждой клетке пути весть «теперь на твоей клетке» была спамом.
                if step.arrived or step.ambushed:
                    from bot.handlers import group as group_handlers

                    await group_handlers.notify_arrival(db, character)

            if step.ambushed:
                stats = await _stats(db, character.id)
                gear_bonus = await item_service.compute_gear_bonus(db, character.id)
                buff_modifiers = await scene_event_service.solo_modifiers(
                    db, character, await preset_service.resolve_active_modifiers(db, character),
                )
                # Моб - по клетке, где напали: персонаж и правда на ней стоит.
                dist = grid.monolith_distance(character.pos_x, character.pos_y)
                cell_region = region_for(character.pos_x, character.pos_y)
                encounter = encounters.spawn_mob(
                    combat_handlers.MOB_ID, cell_region, character.level, dist, _rng
                )
                ambush_starts.append((peer_id, character, stats, gear_bonus, buff_modifiers, travel.id, encounter))
                continue

            if step.arrived:
                from services import trial_service

                if character.subclass is not None:
                    await trial_service.record_cell_moved(db, character)
                stats = await _stats(db, character.id)
                wallet = await wallet_service.get_wallet(db, character.id)
                gear_bonus = await item_service.compute_gear_bonus(db, character.id)
                quest_line = await story_service.quest_summary_line(db, character)
                group_block = await group_texts.group_summary_block(db, character.id)
                region = grid.city_region_at(travel.to_x, travel.to_y)
                mentor_badge = False
                is_foreign = False
                if region is not None:
                    # Патч 39: прибытие в город на маунте — всегда корневой экран
                    # (площадь), а не сохранённый квартал.
                    await screen_service.set_screen(db, character, None)
                    is_foreign = region != character.region
                    mentor_badge = not is_foreign and await story_service.mentor_badge_active(db, character)
                has_mount = await mount_service.has_any_mount(db, character.id)
                arrivals.append(
                    (peer_id, character, stats, wallet.farm_currency, wallet.donate_currency,
                     quest_line, gear_bonus, region, mentor_badge, is_foreign, group_block, has_mount)
                )
                continue

            if _live_countdown:
                # Правим сообщение «в пути», как только сменилась клетка (но не
                # чаще раза в TRAVEL_EDIT_MIN_SECONDS), и раз в отсчёт - время.
                last = _countdown_edited.get(peer_id)
                since = (now - last).total_seconds() if last is not None else None
                moved = _progress_cell.get(peer_id) != travel.cell_index
                if since is None or since >= mc.TRAVEL_COUNTDOWN_UPDATE_SECONDS or (
                    moved and since >= mc.TRAVEL_EDIT_MIN_SECONDS
                ):
                    _countdown_edited[peer_id] = now
                    _progress_cell[peer_id] = travel.cell_index
                    countdowns.append((peer_id, travel))

        await db.commit()

    for peer_id, character, stats, gear_bonus, buff_modifiers, travel_id, encounter in ambush_starts:
        await close_progress(peer_id, f"⚠ Путь прерван нападением на ({character.pos_x}; {character.pos_y}).")
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=f"⚠ ({character.pos_x}; {character.pos_y}): на пути внезапно возникает опасность - ты встаёшь.",
            random_id=0,
        )
        await combat_handlers.start_mount_ambush_encounter(
            peer_id, character, stats, gear_bonus, buff_modifiers, travel_id, encounter,
        )

    from bot.handlers import world as world_handlers  # избегаем цикла импортов

    for daily_peer, daily_progress in daily_announce:
        await world_handlers._announce_daily(daily_peer, daily_progress)
    for (peer_id, character, stats, farm_currency, donate_currency, quest_line, gear_bonus,
         region, mentor_badge, is_foreign, group_block, has_mount) in arrivals:
        await close_progress(peer_id, f"🏁 Путь окончен: ({character.pos_x}; {character.pos_y}).")
        if region is not None:
            text = (
                foreign_city_entry_text(REGION_TITLES[region]) if is_foreign
                else f"🐎 Ты прибываешь к воротам: {REGION_TITLES[region]}"
            )
            await _bot_api.messages.send(
                peer_id=peer_id,
                message=text,
                random_id=0,
                attachment=hub_attachment(region),
                keyboard=kb.city_square_keyboard(character, mentor_badge, has_mount=has_mount, is_foreign=is_foreign),
            )
            continue
        vit_bonus = gear_bonus.get("vit", 0)
        text = "🐎 Ты прибываешь на место.\n\n" + location_summary(
            character, stats, _rng, farm_currency, vit_bonus, quest_line, donate_currency, group_block,
        )
        await _bot_api.messages.send(
            peer_id=peer_id, message=text, random_id=0,
            attachment=location_attachment(character),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
        )
        # Патч 58: прибытие на маунте — такой же вход на клетку, как пеший,
        # и кнопка «К воде» обязана приходить и здесь. Раньше не приходила:
        # вызов стоял только на пеших путях в bot/handlers/world.py.
        await world_handlers.send_cell_buttons(peer_id, character)

    for peer_id, travel in countdowns:
        msg_id = _travel_message.get(peer_id)
        if msg_id is None:
            continue
        try:
            await _bot_api.messages.edit(
                peer_id=peer_id, message_id=msg_id, message=_travel_text(travel, now),
            )
        except Exception:
            logger.debug("Не удалось обновить отсчёт пути для {}", peer_id)
