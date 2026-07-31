"""Мир: меню города (наставник/рынок/ворота), перемещение по сетке, исследование.

Формат (world-patch-1): за воротами открывается интерфейс карты (перемещение +
исследование), а не сразу бой. Бой начинается только по кнопке «Исследовать»
после случайной задержки 5-10 сек.

Позиция и статус (в пути/мёртв) хранятся на Character; в памяти — активная
боевая сессия (bot.handlers.combat, ключ = vk_id), таймеры перемещения и
исследования (game.world.scheduler) и множество исследующих сейчас игроков.
"""

import random
from datetime import datetime, timezone

from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message

from bot.handlers import combat as combat_handlers
from bot.handlers import stats_window
from bot.keyboards import world as kb
from bot.onboarding_texts import REGION_TITLES
from bot.world_summary import location_summary
from bot.world_texts import event_attachment, hub_attachment, mentor_intro, mentor_praise
from game.combat import display
from game.economy import story_config as sc
from game.world import encounters, events as event_pool
from game.world import flavor, grid
from game.world import world_config as wc
from game.world.scheduler import PeerScheduler
from models import CharacterStats
from services import (
    death_service,
    event_service,
    experience_service,
    item_service,
    movement_service,
    preset_service,
    quest_service,
    story_service,
    trial_service,
    trophy_service,
    vitals_service,
    wallet_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_travel_scheduler: PeerScheduler | None = None
_explore_scheduler: PeerScheduler | None = None
_rest_scheduler: PeerScheduler | None = None
_bot_api = None
_rng = random.Random()

# Игроки, у которых сейчас идёт исследование клетки (5-10 сек до появления моба).
_exploring: set[int] = set()
# Игроки, которые сейчас отдыхают (8-12 сек до восстановления HP).
_resting: set[int] = set()
# peer_id -> id события с выбором, ожидающего ответа (патч 9, блок 1)
_pending_events: dict[int, str] = {}



def setup(
    travel_scheduler: PeerScheduler,
    explore_scheduler: PeerScheduler,
    rest_scheduler: PeerScheduler,
    bot_api,
) -> None:
    global _travel_scheduler, _explore_scheduler, _rest_scheduler, _bot_api
    _travel_scheduler = travel_scheduler
    _explore_scheduler = explore_scheduler
    _rest_scheduler = rest_scheduler
    _bot_api = bot_api


async def _get_stats(db, character_id: int) -> CharacterStats:
    return await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character_id))


def _map_text(character, stats, farm_currency: int, gear_bonus: dict | None = None) -> str:
    """Единая сводка клетки — ВСЕГДА самостоятельное сообщение (ux-patch-10)."""
    vit_bonus = (gear_bonus or {}).get("vit", 0)
    return location_summary(character, stats, _rng, farm_currency, vit_bonus)


async def _check_still_dead(db, character, now: datetime) -> bool:
    """Снимает respawn_at, если время вышло; True — персонаж всё ещё мёртв."""
    if death_service.respawn_if_ready(character, now):
        await db.commit()
    return death_service.is_dead(character, now)


async def _maybe_trigger_story(peer_id: int, db, character, stats) -> bool:
    """Патч 18: игрок вошёл в радиус цели активного сюжетного шага — показать
    сцену прибытия и начать сюжетный бой (если задан named_enemy) вместо
    обычной сводки клетки. True — триггер сработал, вызывающий не должен
    показывать обычную карту в этом ответе."""
    quest = await story_service.check_zone_trigger(db, character)
    if quest is None:
        return False
    if quest.arrival_text:
        await _bot_api.messages.send(
            peer_id=peer_id, message=story_service.format_text(quest.arrival_text, character), random_id=0
        )
    if quest.named_enemy is not None:
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
        mult = quest.named_enemy.stat_mult or sc.NAMED_ENEMY_STAT_MULT_DEFAULT
        encounter = encounters.spawn_named_enemy(
            combat_handlers.MOB_ID, quest.named_enemy.name, quest.named_enemy.flavor,
            character.level, mult,
        )
        await combat_handlers.start_story_encounter(
            peer_id, character, stats, gear_bonus, buff_modifiers,
            quest.id, quest.chain_length, encounter,
        )
    else:
        # сцена без боя — цель считается достигнутой сразу
        await story_service.mark_ready(db, character, quest.id)
        await db.commit()
    return True


async def show_location(message: Message, db, character) -> None:
    """Показывает текущий контекст персонажа: город / клетка карты / в пути / мёртв."""
    now = datetime.now(timezone.utc)

    if await _check_still_dead(db, character, now):
        minutes_left = (character.respawn_at - now).total_seconds() / 60
        await message.answer(f"☠ Ты ещё не очнулся. Осталось ~{minutes_left:.1f} мин.")
        return

    if movement_service.resolve_arrival(character, now):
        if character.subclass is not None:
            await trial_service.record_cell_moved(db, character)
        await db.commit()

    if movement_service.is_traveling(character, now):
        left = movement_service.remaining_seconds(character, now)
        await message.answer(f"🚶 В пути... осталось ~{left:.0f} сек.")
        return

    if combat_handlers.has_active_encounter(message.peer_id):
        await message.answer("⚔️ Ты в бою — реши его исход.")
        return

    region = grid.city_region_at(character.pos_x, character.pos_y)
    if region is not None:
        await message.answer(
            f"Ты в городе: {REGION_TITLES[region]}",
            attachment=hub_attachment(region),
            keyboard=kb.city_menu_keyboard(character),
        )
        return

    stats = await _get_stats(db, character.id)
    if await _maybe_trigger_story(message.peer_id, db, character, stats):
        return

    farm_currency = (await wallet_service.get_wallet(db, character.id)).farm_currency
    gear_bonus = await item_service.compute_gear_bonus(db, character.id)
    await message.answer(
        _map_text(character, stats, farm_currency, gear_bonus),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y),
    )


@labeler.message(text=[kb.BTN_GATE])
async def gate_exit(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        if await _check_still_dead(db, character, now):
            await message.answer("☠ Сначала очнись.")
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            await message.answer(
                "Ты уже за городом.",
                keyboard=kb.movement_keyboard(character.pos_x, character.pos_y),
            )
            return
        await message.answer(
            "Куда направишься?",
            keyboard=kb.gate_direction_keyboard(character.pos_x, character.pos_y),
        )


@labeler.message(payload_contains={"type": "gate_dir"})
async def gate_exit_direction(message: Message) -> None:
    """Ответ на выбор направления при выходе из города (патч 17, п.2)."""
    payload = message.get_payload_json() or {}
    dx, dy = payload.get("dx"), payload.get("dy")
    if not isinstance(dx, int) or not isinstance(dy, int):
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # уже вышел раньше — устаревшая клавиатура
        nx, ny = character.pos_x + dx, character.pos_y + dy
        if not grid.in_bounds(nx, ny):
            return  # защитная проверка на случай устаревшей клавиатуры
        character.pos_x, character.pos_y = nx, ny
        stats = await _get_stats(db, character.id)
        farm_currency = (await wallet_service.get_wallet(db, character.id)).farm_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        await db.commit()
        # ux-patch-10 п.1: сводка локации — всегда отдельное сообщение
        await message.answer("Ты выходишь за ворота.", keyboard=kb.waiting_keyboard())
        await message.answer(
            _map_text(character, stats, farm_currency, gear_bonus),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y),
        )


@labeler.message(text=[kb.BTN_EXPLORE])
async def explore(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        if await _check_still_dead(db, character, now):
            await message.answer("☠ Сначала очнись.")
            return
        if combat_handlers.has_active_encounter(peer_id):
            await message.answer("⚔️ Ты уже в бою.")
            return
        if peer_id in _exploring:
            await message.answer("🔍 Ты уже осматриваешься...")
            return
        if peer_id in _resting:
            await message.answer("🛏️ Ты отдыхаешь. Дай себе минуту.")
            return
        if movement_service.is_traveling(character, now):
            left = movement_service.remaining_seconds(character, now)
            await message.answer(f"🚶 В пути... осталось ~{left:.0f} сек.")
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is not None:
            await message.answer("В городе безопасно. Исследовать можно только за воротами.")
            return

    _exploring.add(peer_id)
    delay = _rng.uniform(wc.EXPLORE_SECONDS_MIN, wc.EXPLORE_SECONDS_MAX)
    # ux-patch-5: обрывок Песни / событие — ВНУТРЬ сообщения исследования (~50%),
    # отдельным сообщением больше не шлём. Кнопки убираем до появления моба.
    text = "🔍 Ты осматриваешься вокруг..."
    fragment = flavor.explore_fragment(_rng)
    if fragment is not None:
        text += f"\n\n{fragment}"
    await message.answer(text, keyboard=kb.waiting_keyboard())
    _explore_scheduler.schedule(peer_id, delay)


async def handle_explore_done(peer_id: int) -> None:
    """Колбэк планировщика: исследование закончено — два исхода (патч 13, ч.3):
    50% бой, 50% событие с выбором (событие всегда даёт результат, патч 10).
    Флейвор (Песнь/замечания) больше не бывает самостоятельным исходом — он
    остался только внутри сообщения ожидания "Ты осматриваешься..." (patch-5),
    которое уже показано раньше и не пересекается с этим исходом."""
    _exploring.discard(peer_id)
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        if death_service.is_dead(character) or movement_service.is_traveling(character):
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is not None:
            return  # успел вернуться в город
        if combat_handlers.has_active_encounter(peer_id):
            return
        stats = await _get_stats(db, character.id)

        outcome_kind = "combat" if _rng.random() < wc.EXPLORE_COMBAT_CHANCE else "event"
        farm_currency = (await wallet_service.get_wallet(db, character.id)).farm_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db, character)

    if outcome_kind == "combat":
        await combat_handlers.start_encounter(peer_id, character, stats, gear_bonus, buff_modifiers)
        return

    event = event_pool.random_event(_rng)
    _pending_events[peer_id] = event.id
    text = f"{event.title}\n\n{event.text}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0,
        attachment=event_attachment(event.id), keyboard=kb.event_choice_keyboard(event),
    )


@labeler.message(payload_contains={"type": "event_choice"})
async def event_choice(message: Message) -> None:
    """Ответ на кнопку события исследования. event/choice в payload сверяются
    с _pending_events — устаревшее нажатие (после уже разрешённого события
    или повторный клик) молча игнорируется."""
    peer_id = message.peer_id
    pending_event_id = _pending_events.get(peer_id)
    if pending_event_id is None:
        return
    payload = message.get_payload_json() or {}
    if payload.get("event") != pending_event_id:
        return
    event = event_pool.event_by_id(pending_event_id)
    choice_idx = payload.get("choice")
    if event is None or not isinstance(choice_idx, int) or not (0 <= choice_idx < len(event.choices)):
        return
    _pending_events.pop(peer_id, None)

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        stats = await _get_stats(db, character.id)
        outcome = event_service.pick_outcome(_rng, event.choices[choice_idx].outcomes)
        choice_label = event.choices[choice_idx].label
        choice_code = trial_service.EVENT_CHOICE_CODES.get(choice_label)
        result = await event_service.apply_outcome(
            db, character, stats, outcome, _rng, event_id=event.id, choice_code=choice_code
        )
        farm_currency = (await wallet_service.get_wallet(db, character.id)).farm_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
        await db.commit()

    if result.is_combat:
        await message.answer(result.text)
        await combat_handlers.start_encounter(peer_id, character, stats, gear_bonus, buff_modifiers)
        return

    # ux-patch-10 п.1: сводка локации — всегда отдельное сообщение
    await message.answer(result.text, keyboard=kb.waiting_keyboard())
    # патч 14, ч.2.3: событие — тоже источник опыта, левелап не должен теряться
    await stats_window.notify_levelup(peer_id, result.levels_gained, result.new_level)
    await message.answer(
        _map_text(character, stats, farm_currency, gear_bonus),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y),
    )


# --- Отдых (combat-patch-2, п.3): вне боя, 8-12 сек, HP → полное ---


@labeler.message(text=[kb.BTN_REST])
async def rest(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        if await _check_still_dead(db, character, now):
            await message.answer("☠ Сначала очнись.")
            return
        if combat_handlers.has_active_encounter(peer_id):
            await message.answer("В бою не отдохнёшь.")
            return
        if peer_id in _resting:
            await message.answer("🛏️ Ты уже отдыхаешь.")
            return
        if peer_id in _exploring or movement_service.is_traveling(character, now):
            await message.answer("Сначала закончи то, что начал.")
            return

    _resting.add(peer_id)
    delay = _rng.uniform(wc.REST_SECONDS_MIN, wc.REST_SECONDS_MAX)
    # отдых — кнопки убираем на время (чистка шума)
    await message.answer(flavor.rest_start(), keyboard=kb.waiting_keyboard())
    _rest_scheduler.schedule(peer_id, delay)


async def handle_rest_done(peer_id: int) -> None:
    """Колбэк планировщика: отдых окончен — HP восстановлено, кнопки возвращены."""
    if peer_id not in _resting:
        return  # отдых прерван (напр. пришёл бой — задел на будущее)
    _resting.discard(peer_id)
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        if death_service.is_dead(character) or combat_handlers.has_active_encounter(peer_id):
            return
        stats = await _get_stats(db, character.id)
        vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
        max_hp = vitals_service.max_hp(character, stats, vit_bonus)
        hp_before = vitals_service.current_hp(character, stats, vit_bonus)
        vitals_service.restore_full(character)
        if character.subclass is not None:
            await trial_service.record_rest(db, character)
        await db.commit()
        region = grid.city_region_at(character.pos_x, character.pos_y)
        keyboard = (
            kb.city_menu_keyboard(character)
            if region is not None
            else kb.movement_keyboard(character.pos_x, character.pos_y)
        )
    text = f"{flavor.rest_done()}\n{display.hp_delta_line(hp_before, max_hp, max_hp)}"
    await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, keyboard=keyboard)


@labeler.message(text=kb.MOVEMENT_TEXTS)
async def move(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        if await _check_still_dead(db, character, now):
            await message.answer("☠ Сначала очнись.")
            return
        if combat_handlers.has_active_encounter(message.peer_id):
            await message.answer("Сначала разберись с боем.")
            return
        if message.peer_id in _exploring:
            await message.answer("🔍 Ты осматриваешься — подожди.")
            return
        if message.peer_id in _resting:
            await message.answer("🛏️ Ты отдыхаешь. Дай себе минуту.")
            return
        if movement_service.resolve_arrival(character, now):
            if character.subclass is not None:
                await trial_service.record_cell_moved(db, character)
            await db.commit()
            await show_location(message, db, character)
            return
        if movement_service.is_traveling(character, now):
            left = movement_service.remaining_seconds(character, now)
            await message.answer(f"🚶 В пути... осталось ~{left:.0f} сек.")
            return
        direction = kb.resolve_direction(character.pos_x, character.pos_y, message.text)
        if direction is None:
            return  # устаревшая клавиатура — кнопка больше не подходит к позиции
        dx, dy = direction
        movement_service.start_travel(character, dx, dy, now)
        await db.commit()
        # в пути — кнопки убираем, вернём по прибытии (чистка визуального шума)
        await message.answer(flavor.travel_line(_rng), keyboard=kb.waiting_keyboard())
        _travel_scheduler.schedule(message.peer_id, wc.CELL_TRAVEL_SECONDS)


async def handle_arrival(peer_id: int) -> None:
    """Колбэк планировщика: время в пути истекло — показываем клетку/город (без боя)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        if not movement_service.resolve_arrival(character):
            return  # игрок уже сам разрешил прибытие более ранним действием
        if character.subclass is not None:
            await trial_service.record_cell_moved(db, character)
        await db.commit()
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is not None:
            await _bot_api.messages.send(
                peer_id=peer_id,
                message=f"Ты выходишь к воротам: {REGION_TITLES[region]}",
                random_id=0,
                attachment=hub_attachment(region),
                keyboard=kb.city_menu_keyboard(character),
            )
            return
        stats = await _get_stats(db, character.id)
        if await _maybe_trigger_story(peer_id, db, character, stats):
            return
        farm_currency = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=_map_text(character, stats, farm_currency),
            random_id=0,
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y),
        )


@labeler.message(text=[kb.BTN_MENTOR])
async def talk_to_mentor(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # наставник только в городе

        if region != character.region:
            # чужой регион: только флейвор, квест не назначаем и не принимаем
            await message.answer(mentor_intro(region))
            return

        progress = await quest_service.get_or_assign(db, character)
        if progress is None:
            await db.commit()
            return

        if progress.is_new:
            await db.commit()
            await message.answer(mentor_intro(region))
            return

        if progress.status == "ready":
            result = await quest_service.turn_in(db, character)
            # патч 18: квест 1.1 — начало сюжета; продвигаем указатель за него
            # и добавляем текст-переход (Сера бросает флягу и т.д.)
            transition_text = await story_service.advance_after_first_quest(db, character)
            await db.commit()
            text = mentor_praise(region)
            if result is not None and result.xp_reward > 0:
                text += "\n\n" + flavor.quest_reward_line(result.xp_reward)
                if result.levels_gained > 0:
                    text += "\n" + flavor.levelup_line(result.new_level, _rng)
            if transition_text:
                text += "\n\n" + transition_text
            await message.answer(text)
            # патч 14, ч.2.3: квест — тоже источник опыта, левелап не должен теряться
            if result is not None:
                await stats_window.notify_levelup(message.peer_id, result.levels_gained, result.new_level)
            return

        if progress.status == "completed":
            # патч 18: квест 1.1 закрыт — дальше сюжет ведёт story_service
            stats = await _get_stats(db, character.id)
            story_result = await story_service.visit_mentor(db, character, stats)
            await db.commit()
            if story_result is None:
                await message.answer("— У меня для тебя пока больше ничего нет. Возвращайся позже.")
                return
            await message.answer(story_result.text)
            if story_result.levels_gained > 0:
                await stats_window.notify_levelup(
                    message.peer_id, story_result.levels_gained, story_result.new_level
                )
            return

        # активен, но ещё не выполнен
        await message.answer(
            f"— Ты уже здесь? Дело ещё не закончено — {progress.progress_label}: "
            f"{progress.progress}/{progress.target_count}."
        )


@labeler.message(text=[kb.BTN_MARKET])
async def visit_market(message: Message) -> None:
    await message.answer("Торговцы раскладывают товар. Скоро здесь можно будет торговать.")


@labeler.message(text=["/квест", "/quest"])
async def quest_reminder(message: Message) -> None:
    """Патч 18: напоминание текущей сюжетной цели."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        text = await story_service.quest_reminder_text(db, character)
    await message.answer(text)
