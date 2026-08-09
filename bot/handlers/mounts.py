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

import random
import re
from datetime import datetime, timezone

from loguru import logger
from vkbottle import BaseStateGroup
from vkbottle.bot import BotLabeler, Message

from bot.handlers import combat as combat_handlers
from bot.handlers import pvp as pvp_handlers
from bot.handlers import world as world_handlers
from bot.keyboards import world as kb
from bot.onboarding_texts import REGION_TITLES
from bot.world_texts import foreign_city_entry_text, hub_attachment
from bot.world_summary import location_attachment, location_summary
from game.world import encounters, grid
from game.world import world_config as wc
from game.world.location_types import region_for
from models import Character, CharacterStats, User
from services import (
    item_service,
    mount_service,
    preset_service,
    story_service,
    wallet_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_bot_api = None
_dispenser = None
_live_countdown = True
_rng = random.Random()

# peer_id -> conversation_message_id последнего сообщения "в пути" (live-отсчёт)
_travel_message: dict[int, int] = {}
# peer_id -> id поездки, ожидающей подтверждения "Продолжить путь"
_pending_continue: dict[int, int] = {}

_COORD_RE = re.compile(r"^\s*(-?\d+)\s*[:;]\s*(-?\d+)\s*$")


class MountCoordState(BaseStateGroup):
    COORD_INPUT = "mount_coord_input"


def setup(bot, bot_api, live_countdown: bool = True) -> None:
    global _bot_api, _dispenser, _live_countdown
    _bot_api = bot_api
    _dispenser = bot.state_dispenser
    _live_countdown = live_countdown


async def _stats(db, character_id: int) -> CharacterStats:
    from sqlalchemy import select

    return await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character_id))


def _format_seconds(seconds: float) -> str:
    if seconds >= 60:
        return f"~{seconds / 60:.1f} мин."
    return f"~{seconds:.0f} сек."


async def _blocked_reason(db, character, peer_id: int, now: datetime) -> str | None:
    """Общие гейты для открытия меню маунта и для подтверждения координат:
    None — можно ехать, иначе — текст отказа."""
    from services import death_service, movement_service

    if death_service.is_dead(character, now):
        return "☠ Сначала очнись."
    if pvp_handlers.has_active_battle(peer_id):
        return "Сначала разберись с открытым боем."
    if combat_handlers.has_active_encounter(peer_id):
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

    await _dispenser.set(peer_id, MountCoordState.COORD_INPUT, mount_id=mount.mount_id)
    await message.answer(
        f"{mount.emoji} {mount.name} готов в путь.\n"
        f"Ты в ({pos_x}; {pos_y}). Куда направиться? Пришли координаты в формате X:Y "
        f"(в пределах {wc.BOUNDS_MIN}..{wc.BOUNDS_MAX} по обеим осям, например 12:-30)."
    )


@labeler.message(state=MountCoordState.COORD_INPUT)
async def coord_input(message: Message) -> None:
    peer_id = message.peer_id
    mount_id = (message.state_peer.payload.get("mount_id") if message.state_peer else None)
    if mount_id is None:
        await _dispenser.delete(peer_id)
        return
    match = _COORD_RE.match(message.text or "")
    if match is None:
        await message.answer("Не понял координаты. Формат: X:Y (например 12:-30).")
        return
    to_x, to_y = int(match.group(1)), int(match.group(2))

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
                f"Эти координаты за пределами обжитых земель ({wc.BOUNDS_MIN}..{wc.BOUNDS_MAX}). "
                "Попробуй ещё раз."
            )
            return
        if (to_x, to_y) == (character.pos_x, character.pos_y):
            await message.answer("Ты уже здесь. Назови другую клетку.")
            return
        travel = await mount_service.start_travel(db, character, mount_id, to_x, to_y, _rng, now)
        cells = max(abs(to_x - character.pos_x), abs(to_y - character.pos_y))
        seconds = mount_service.total_travel_seconds(mount_id, cells)
        await db.commit()

    await _dispenser.delete(peer_id)
    await notify_travel_started(peer_id, to_x, to_y, seconds, mount_service.ambush_chance(mount_id))


async def notify_travel_started(peer_id: int, to_x: int, to_y: int, seconds: float, ambush_chance: float) -> None:
    """Сообщение о начале пути на маунте + клавиатура ожидания — общая точка
    для обоих способов отправки маунта (патч 31, фикс 1): из чата (coord_input
    выше) и с карты мини-аппа (bot/miniapp_map_api.py::handle_post_send_mount,
    который раньше не слал в чат ничего вообще — MountTravel создавался
    молча, игрок не понимал, что путь начался, и старая клавиатура оставалась)."""
    if _bot_api is None:
        return
    text = (
        f"🐎 Путь начат: ({to_x}; {to_y}), {_format_seconds(seconds)}.\n"
        f"Шанс нападения в пути: {round(ambush_chance * 100)}%."
    )
    resp = await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, keyboard=kb.waiting_keyboard())
    try:
        _travel_message[peer_id] = int(resp)
    except (TypeError, ValueError):
        pass


def _travel_text(travel, now: datetime) -> str:
    left = mount_service.remaining_seconds(travel, now)
    return f"🐎 В пути... осталось {_format_seconds(left)}"


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
        message=f"Нападавший повержен. Дорога зовёт дальше — осталось {_format_seconds(left)}.",
        random_id=0,
        keyboard=kb.continue_travel_keyboard(travel_id),
    )


@labeler.message(payload_contains={"type": "continue_travel"})
async def continue_travel(message: Message) -> None:
    peer_id = message.peer_id
    pending_id = _pending_continue.get(peer_id)
    if pending_id is None:
        return
    payload = message.get_payload_json() or {}
    if payload.get("travel") != pending_id:
        return
    _pending_continue.pop(peer_id, None)

    from models import MountTravel

    async with get_session_factory()() as db:
        travel = await db.get(MountTravel, pending_id)
        if travel is None:
            return
        await mount_service.resume_travel(db, travel)
        await db.commit()

    resp = await _bot_api.messages.send(
        peer_id=peer_id, message=_travel_text(travel, datetime.now(timezone.utc)),
        random_id=0, keyboard=kb.waiting_keyboard(),
    )
    try:
        _travel_message[peer_id] = int(resp)
    except (TypeError, ValueError):
        pass


async def scan() -> None:
    """Батч-проход (main.py, периодический job): кто наткнулся на нападение,
    кто прибыл, у кого просто идёт время (live-отсчёт). Один job на всех —
    по образцу bot/handlers/respawn.py::scan."""
    if _bot_api is None:
        return
    now = datetime.now(timezone.utc)
    sf = get_session_factory()

    ambush_starts = []
    arrivals = []
    countdowns = []

    async with sf() as db:
        result = await mount_service.scan(db, now)
        all_ids = {t.character_id for t in (result.ambushed + result.arrived + result.still_traveling)}
        vkid_map: dict[int, int] = {}
        if all_ids:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(Character.id, User.vk_id)
                    .join(User, User.id == Character.user_id)
                    .where(Character.id.in_(all_ids))
                )
            ).all()
            vkid_map = dict(rows)

        for travel in result.ambushed:
            peer_id = vkid_map.get(travel.character_id)
            character = await db.get(Character, travel.character_id)
            if peer_id is None or character is None:
                continue
            stats = await _stats(db, character.id)
            gear_bonus = await item_service.compute_gear_bonus(db, character.id)
            buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
            dist = grid.chebyshev_distance(travel.to_x, travel.to_y)
            # Патч 32, баг 4: регион — по клетке нападения (куда едет маунт),
            # не по домашнему региону игрока (см. bot/handlers/combat.py).
            cell_region = region_for(travel.to_x, travel.to_y)
            encounter = encounters.spawn_mob(
                combat_handlers.MOB_ID, cell_region, character.level, dist, _rng
            )
            ambush_starts.append((peer_id, character, stats, gear_bonus, buff_modifiers, travel.id, encounter))

        for travel in result.arrived:
            peer_id = vkid_map.get(travel.character_id)
            character = await db.get(Character, travel.character_id)
            if peer_id is None or character is None:
                continue
            character.pos_x, character.pos_y = travel.to_x, travel.to_y
            from services import daily_service, trial_service

            if character.subclass is not None:
                await trial_service.record_cell_moved(db, character)
            await daily_service.record_cell_moved(db, character)
            stats = await _stats(db, character.id)
            wallet = await wallet_service.get_wallet(db, character.id)
            gear_bonus = await item_service.compute_gear_bonus(db, character.id)
            quest_line = await story_service.quest_summary_line(db, character)
            region = grid.city_region_at(travel.to_x, travel.to_y)
            mentor_badge = False
            is_foreign = False
            if region is not None:
                is_foreign = region != character.region
                mentor_badge = not is_foreign and await story_service.mentor_badge_active(db, character)
            arrivals.append(
                (peer_id, character, stats, wallet.farm_currency, wallet.donate_currency,
                 quest_line, gear_bonus, region, mentor_badge, is_foreign)
            )

        if _live_countdown:
            for travel in result.still_traveling:
                peer_id = vkid_map.get(travel.character_id)
                if peer_id is not None:
                    countdowns.append((peer_id, travel))

        await db.commit()

    for peer_id, character, stats, gear_bonus, buff_modifiers, travel_id, encounter in ambush_starts:
        _travel_message.pop(peer_id, None)
        await _bot_api.messages.send(
            peer_id=peer_id,
            message="🐎 На пути внезапно возникает опасность — маунт спотыкается и встаёт.",
            random_id=0,
        )
        await combat_handlers.start_mount_ambush_encounter(
            peer_id, character, stats, gear_bonus, buff_modifiers, travel_id, encounter,
        )

    for (peer_id, character, stats, farm_currency, donate_currency, quest_line, gear_bonus,
         region, mentor_badge, is_foreign) in arrivals:
        _travel_message.pop(peer_id, None)
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
                keyboard=kb.city_menu_keyboard(character, mentor_badge, has_mount=True, is_foreign=is_foreign),
            )
            continue
        vit_bonus = gear_bonus.get("vit", 0)
        text = "🐎 Ты прибываешь на место.\n\n" + location_summary(
            character, stats, _rng, farm_currency, vit_bonus, quest_line, donate_currency
        )
        await _bot_api.messages.send(
            peer_id=peer_id, message=text, random_id=0,
            attachment=location_attachment(character),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=True),
        )

    for peer_id, travel in countdowns:
        msg_id = _travel_message.get(peer_id)
        if msg_id is None:
            continue
        try:
            await _bot_api.messages.edit(
                peer_id=peer_id, conversation_message_id=msg_id, message=_travel_text(travel, now),
            )
        except Exception:
            logger.debug("Не удалось обновить отсчёт пути для {}", peer_id)
