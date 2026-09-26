"""Мир: меню города (наставник/рынок/ворота), перемещение по сетке, исследование.

Формат (world-patch-1): за воротами открывается интерфейс карты (перемещение +
исследование), а не сразу бой. Бой начинается только по кнопке «Исследовать»
после случайной задержки 5-10 сек.

Позиция и статус (в пути/мёртв) хранятся на Character; в памяти — активная
боевая сессия (bot.handlers.combat, ключ = vk_id), таймеры перемещения и
исследования (game.world.scheduler) и множество исследующих сейчас игроков.
"""

import asyncio
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message

from bot import (
    ash_handful_state,
    craft_button_state,
    dailies_texts,
    fishing_texts,
    group_texts,
    mining_texts,
    raid_key_texts,
    raid_texts,
)
from bot.activity import activity_action
from bot.battle_keyboard import active_battle_keyboard, in_any_battle
from bot.handlers import appraiser as appraiser_handlers
from bot.handlers import combat as combat_handlers
from bot.handlers import elixir_shop as elixir_shop_handlers
from bot.handlers import group_combat as group_combat_handlers
from bot.handlers import inventory as inventory_handlers
from bot.handlers import pvp as pvp_handlers
from bot.handlers import raid_combat as raid_combat_handlers
from bot.handlers import stats_window
from bot.keyboards import fishing as fishing_kb
from bot.keyboards import mining as mining_kb
from bot.keyboards import raid as raid_kb
from bot.keyboards import world as kb
from bot.keyboards.group_explore import group_ready_keyboard
from bot.onboarding_texts import REGION_TITLES
from bot.world_summary import location_attachment, location_summary
from bot import pending_activity
from bot.world_texts import (
    FOREIGN_NPC_REJECTION,
    act_attachment,
    city_square_text,
    event_attachment,
    foreign_city_entry_text,
    hub_attachment,
    market_quarter_text,
    mentor_attachment,
    mentor_intro,
    mentor_name,
    mentor_praise,
    tavern_text,
)
from game.combat import display
from game.economy import fishing as game_fishing
from game.economy import fishing_config as fc
from game.economy import mining
from game.economy import premium_config as pc
from game.economy import raid_config as raid_cfg
from game.economy import story_config as sc
from game.world import encounters, flavor, grid
from game.world import events as event_pool
from game.world import world_config as wc
from game.world.location_types import region_for
from game.world.scheduler import PeerScheduler
from models import Character, CharacterStats, MountTravel, User
from services import (
    ash_service,
    daily_service,
    death_service,
    event_service,
    fishing_service,
    group_explore_service,
    group_service,
    item_service,
    mining_service,
    mount_service,
    movement_service,
    premium_service,
    preset_service,
    quest_service,
    raid_service,
    screen_service,
    song_service,
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
#: Пауза между сообщениями служебной рассылки (VK лимитирует темп).
SERVICE_NOTICE_DELAY_SECONDS = 0.06

_pending_events: dict[int, str] = {}

#: Патч 58: множитель цены рыбака на показанное сейчас предложение. Живёт
#: рядом с _pending_events и очищается вместе с ним — цена принадлежит
#: КОНКРЕТНОМУ показу события, и переиспользовать её на следующем нельзя.
_pending_fish_offers: dict[int, float] = {}


@dataclass
class _FishOffer:
    multiplier: float
    gold: int
    weight_label: str


def _roll_fish_offer_multiplier(character) -> float:
    """Наценка рыбака по кольцу КЛЕТКИ, где выпал ивент."""
    tier = game_fishing.ring_tier(character.pos_x, character.pos_y)
    low, high = fc.BUYER_EVENT_MARKUP[tier]
    return _rng.uniform(low, high)



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


async def resume_after_restart() -> dict[str, int]:
    """Возвращает в строй занятия, оборванные перезапуском (патч 98).

    Звать ПОСЛЕ setup, когда планировщики уже запущены. Возвращает, сколько
    чего возобновлено - для строки в логе.

    Пеший переход хранится в базе целиком, пропадала только задача «прибыл».
    Исследование и отдых жили в памяти целиком - их отметку держит Redis
    (bot/pending_activity.py). В обоих случаях завершение досылается ровно
    тогда, когда оно и должно было прийти, а если срок уже прошёл - сразу.
    Игрок не видит ничего, кроме слегка опоздавшего сообщения.
    """
    resumed = {"travel": 0, "explore": 0, "rest": 0}
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(User.vk_id, Character.travel_arrives_at)
                .join(Character, Character.user_id == User.id)
                .where(Character.travel_arrives_at.is_not(None))
            )
        ).all()
    for peer_id, arrives_at in rows:
        # Postgres отдаёт дату с поясом, SQLite (тесты) - без. Время в базе
        # всегда пишется в UTC, так что пустой пояс и есть UTC.
        if arrives_at.tzinfo is None:
            arrives_at = arrives_at.replace(tzinfo=timezone.utc)
        _travel_scheduler.schedule(peer_id, max(0.0, (arrives_at - now).total_seconds()))
        resumed["travel"] += 1

    for kind, peer_id, left in await pending_activity.pending():
        if kind == "explore":
            _exploring.add(peer_id)
            _explore_scheduler.schedule(peer_id, left)
        else:
            _resting.add(peer_id)
            _rest_scheduler.schedule(peer_id, left)
        resumed[kind] += 1
    return resumed


async def _get_stats(db, character_id: int) -> CharacterStats:
    return await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character_id))


def _map_text(
    character, stats, farm_currency: int, gear_bonus: dict | None = None,
    quest_line: str | None = None, donate_currency: int = 0, group_block: str | None = None,
) -> str:
    """Единая сводка клетки — ВСЕГДА самостоятельное сообщение (ux-patch-10)."""
    vit_bonus = (gear_bonus or {}).get("vit", 0)
    return location_summary(
        character, stats, _rng, farm_currency, vit_bonus, quest_line, donate_currency, group_block,
    )


async def _maybe_send_monolith_button(peer_id: int, character) -> None:
    """Патч 53: на клетке Монолита (0;0) — лорный текст + кнопка «Прикоснуться»
    ОТДЕЛЬНЫМ сообщением С ИНЛАЙН-клавиатурой (не заменяет нижнюю reply-
    клавиатуру перемещения, которая осталась от только что отправленной
    сводки локации — VK различает reply/inline клавиатуры на уровне
    сообщения, см. bot/keyboards/raid.py::touch_monolith_keyboard).
    Не показывается, если персонаж уже в рейде/лобби (устаревшая ситуация —
    не должна произойти при обычном потоке, но не дублировать кнопку)."""
    if (character.pos_x, character.pos_y) != raid_cfg.MONOLITH_COORDS:
        return
    if raid_combat_handlers.has_active_raid(character.id):
        return
    await _bot_api.messages.send(
        peer_id=peer_id, message=raid_texts.MONOLITH_CALL_TEXT, random_id=0,
        keyboard=raid_kb.touch_monolith_keyboard(),
    )


async def maybe_send_lake_button(peer_id: int, character) -> None:
    """Патч 58: при ВХОДЕ на клетку с озером — кнопка «К воде» отдельным
    сообщением с инлайн-клавиатурой, как «Прикоснуться» у Монолита выше.

    Строго один раз на вход: после исследования, события или отдыха на той же
    клетке кнопка не повторяется (bot/craft_button_state.py), иначе она
    засоряла бы чат на каждое действие. Вход к воде при этом никуда не
    девается — остаётся команда «Озеро», подсказка про неё есть в сводке
    локации. При возвращении на клетку кнопка приходит снова.
    """
    lake = game_fishing.lake_at(character.pos_x, character.pos_y)
    if lake is None:
        # Клетка без озера сбрасывает отметку: иначе возвращение на то же
        # озеро не отличалось бы от «остался на нём» и кнопка не пришла бы.
        craft_button_state.leave(peer_id, craft_button_state.LAKE)
        return
    if not craft_button_state.should_send(
        peer_id, craft_button_state.LAKE, character.pos_x, character.pos_y
    ):
        return
    craft_button_state.mark_sent(
        peer_id, craft_button_state.LAKE, character.pos_x, character.pos_y
    )
    await _bot_api.messages.send(
        peer_id=peer_id, message=fishing_texts.LAKE_HINT_LINE, random_id=0,
        keyboard=fishing_kb.approach_lake_keyboard(),
    )


async def mining_service_abandon(character) -> None:
    """Сохраняет в БД обнуление добычи при уходе с клетки (патч 59)."""
    async with get_session_factory()() as db:
        fresh = await db.get(type(character), character.id)
        if fresh is not None and await mining_service.abandon_if_elsewhere(db, fresh):
            await db.commit()


async def maybe_send_mine_button(peer_id: int, character) -> None:
    """Патч 59: при ВХОДЕ на клетку с рудником — кнопка «В выработку» отдельным
    сообщением, ровно как у озера, и ровно один раз на вход.

    Здесь же игрок узнаёт, сколько в жиле руды, ещё до спуска: это именно тот
    запрос в БД, который синхронная сводка локации сделать не может.
    """
    lake_like = mining.mine_at(character.pos_x, character.pos_y)
    if lake_like is None:
        craft_button_state.leave(peer_id, craft_button_state.MINE)
        return
    if not craft_button_state.should_send(
        peer_id, craft_button_state.MINE, character.pos_x, character.pos_y
    ):
        return
    craft_button_state.mark_sent(
        peer_id, craft_button_state.MINE, character.pos_x, character.pos_y
    )
    async with get_session_factory()() as db:
        ore_left = await mining_service.ore_in_mine(db, lake_like.id)
    stock = f"руды в жиле: {ore_left}" if ore_left else "жила пуста"
    await _bot_api.messages.send(
        peer_id=peer_id,
        message=f"⛏ {lake_like.name} - {stock}.",
        random_id=0,
        keyboard=mining_kb.approach_mine_keyboard(),
    )


async def _deliver_daily_notice(peer_id: int, character) -> None:
    """Патч 23: доставка уведомления о сбросе дня/стрике/награде за вход,
    отложенного в onboarding_service.get_character (транзиентный атрибут,
    не персистентный — читаем и сразу гасим)."""
    notice = getattr(character, "_daily_notice", None)
    if notice is None:
        return
    character._daily_notice = None
    for line in notice.lines:
        await _bot_api.messages.send(peer_id=peer_id, message=line, random_id=0)


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
        # Патч 36: уровень квестового врага — по клетке цели (как у обычных
        # мобов), не напрямую по уровню игрока — раньше сильно прокачанный
        # игрок, вернувшийся за старым сюжетным шагом, получал named-врага
        # своего текущего уровня вместо уровня, уместного для той локации.
        target_x = quest.target_x if quest.target_x is not None else character.pos_x
        target_y = quest.target_y if quest.target_y is not None else character.pos_y
        level = grid.mob_level_at(target_x, target_y, character.level)
        image = quest.named_enemy.image or encounters.base_mob_image(quest.named_enemy.base_mob_id)
        encounter = encounters.spawn_named_enemy(
            combat_handlers.MOB_ID, quest.named_enemy.name, quest.named_enemy.flavor,
            level, mult, image=image,
        )
        await combat_handlers.start_story_encounter(
            peer_id, character, stats, gear_bonus, buff_modifiers,
            quest.id, quest.chain_length, encounter,
        )
    else:
        # сцена без боя — цель считается достигнутой сразу
        await story_service.mark_ready(db, character, quest.id)
        await db.commit()
        # патч 21, п.1: игрок не в разговоре с наставником — пингуем сами
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=f"📜 {mentor_name(character.region)} ждёт тебя в городе.",
            random_id=0,
        )
    return True


async def _render_city_screen(db, character, screen: str | None) -> tuple[str, str] | None:
    """Патч 39: город разбит на кварталы (Главная площадь = screen None,
    "tavern", "market_quarter") — единый рендер и для входа/навигации, и для
    восстановления (/клавиатура, рестарт бота, см. _screen_keyboard ниже).
    None — персонаж сейчас не в городе (эти экраны существуют только там).
    Таверна недоступна в чужом городе (патч 26/39) — откатываемся на площадь
    вместо того, чтобы падать в пустой экран."""
    region = grid.city_region_at(character.pos_x, character.pos_y)
    if region is None:
        return None
    is_foreign = region != character.region
    if screen == "tavern" and not is_foreign:
        return tavern_text(region), kb.tavern_keyboard(character)
    if screen == "market_quarter":
        return market_quarter_text(region, is_foreign), kb.market_quarter_keyboard(is_foreign)
    has_mount = await mount_service.has_any_mount(db, character.id)
    mentor_badge = not is_foreign and await story_service.mentor_badge_active(db, character)
    text = foreign_city_entry_text(REGION_TITLES[region]) if is_foreign else city_square_text(region)
    return text, kb.city_square_keyboard(character, mentor_badge, has_mount=has_mount, is_foreign=is_foreign)


async def show_location(message: Message, db, character) -> None:
    """Показывает текущий контекст персонажа: город / клетка карты / в пути / мёртв."""
    await _deliver_daily_notice(message.peer_id, character)
    now = datetime.now(timezone.utc)

    if await _check_still_dead(db, character, now):
        minutes_left = (character.respawn_at - now).total_seconds() / 60
        await message.answer(f"☠ Ты ещё не очнулся. Осталось ~{minutes_left:.1f} мин.")
        return

    if movement_service.resolve_arrival(character, now):
        if character.subclass is not None:
            await trial_service.record_cell_moved(db, character)
        await daily_service.record_cell_moved(db, character)
        await db.commit()

    if movement_service.is_traveling(character, now):
        left = movement_service.remaining_seconds(character, now)
        await message.answer(f"🚶 В пути... осталось ~{left:.0f} сек.")
        return

    if in_any_battle(message.peer_id):
        await message.answer("⚔️ Ты в бою - реши его исход.")
        return

    region = grid.city_region_at(character.pos_x, character.pos_y)
    if region is not None:
        # Патч 39: show_location — всегда "свежий" показ города, корневой
        # экран (Главная площадь), а не сохранённый квартал.
        await screen_service.set_screen(db, character, None)
        text, keyboard = await _render_city_screen(db, character, None)
        await message.answer(text, attachment=hub_attachment(region), keyboard=keyboard)
        return

    has_mount = await mount_service.has_any_mount(db, character.id)
    stats = await _get_stats(db, character.id)
    if await _maybe_trigger_story(message.peer_id, db, character, stats):
        return

    wallet = await wallet_service.get_wallet(db, character.id)
    farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
    gear_bonus = await item_service.compute_gear_bonus(db, character.id)
    quest_line = await story_service.quest_summary_line(db, character)
    group_block = await group_texts.group_summary_block(db, character.id)
    await message.answer(
        _map_text(character, stats, farm_currency, gear_bonus, quest_line, donate_currency, group_block),
        attachment=location_attachment(character),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, message.peer_id, has_mount=has_mount),
    )
    await _maybe_send_monolith_button(message.peer_id, character)
    await maybe_send_lake_button(message.peer_id, character)
    # Патч 59: уход с клетки обнуляет незаконченную добычу.
    await mining_service_abandon(character)
    await maybe_send_mine_button(message.peer_id, character)


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
            has_mount = await mount_service.has_any_mount(db, character.id)
            await message.answer(
                "Ты уже за городом.",
                keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, message.peer_id, has_mount=has_mount),
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
        # Патч 37: покинутые за воротами экраны (скупщик/лавка/инвентарь)
        # существуют только в городе — сбрасываем, чтобы не застрять на них.
        await screen_service.set_screen(db, character, None)
        stats = await _get_stats(db, character.id)
        wallet = await wallet_service.get_wallet(db, character.id)
        farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        quest_line = await story_service.quest_summary_line(db, character)
        group_block = await group_texts.group_summary_block(db, character.id)
        has_mount = await mount_service.has_any_mount(db, character.id)
        await db.commit()
        await _deliver_daily_notice(message.peer_id, character)
        # ux-patch-10 п.1: сводка локации — всегда отдельное сообщение
        await message.answer("Ты выходишь за ворота.", keyboard=kb.waiting_keyboard())
        await message.answer(
            _map_text(character, stats, farm_currency, gear_bonus, quest_line, donate_currency, group_block),
            attachment=location_attachment(character),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, message.peer_id, has_mount=has_mount),
        )
        await _maybe_send_monolith_button(message.peer_id, character)
        await maybe_send_lake_button(message.peer_id, character)
        # Патч 59: уход с клетки обнуляет незаконченную добычу.
        await mining_service_abandon(character)
        await maybe_send_mine_button(message.peer_id, character)


ASH_BURNED_LINE = "Пепел разнесло ветром."


@labeler.message(text=[kb.BTN_EXPLORE])
@activity_action
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
        if in_any_battle(peer_id):
            await message.answer("⚔️ Ты уже в бою.")
            return
        if mining_service.is_digging(character):
            await message.answer(
                mining_texts.busy_text(mining_service.remaining_seconds(character))
            )
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

        # Патч 51, ч.3: групповое исследование — только если на ЭТОЙ клетке
        # ещё есть хотя бы один другой участник группы (иначе — обычное
        # соло-исследование ниже, включая события, как и раньше).
        snapshot = await group_service.get_group_snapshot(db, character.id)
        if snapshot is not None:
            cohort = group_explore_service.co_located_members(
                snapshot.members, character.pos_x, character.pos_y
            )
            if len(cohort) > 1:
                if group_combat_handlers.is_group_fighting(snapshot.id):
                    await message.answer("Твоя группа уже в деле. Дождись, пока они закончат.")
                    return
                cohort_ids = {m.id for m in cohort}
                queue = group_explore_service.start_or_join(
                    snapshot.id, (character.pos_x, character.pos_y), cohort_ids, character.id,
                )
                if queue is None:
                    await message.answer("Твоя группа уже в деле. Дождись, пока они закончат.")
                    return
                notice = f"👥 {character.name} готов к исследованию ({len(queue.ready)}/{len(queue.cohort)})."
                if not group_explore_service.is_ready_to_start(queue):
                    other_peer_ids = []
                    for m in cohort:
                        if m.id == character.id:
                            continue
                        their_peer_id = await onboarding_svc.vk_id_for_character(db, m.id)
                        if their_peer_id is not None:
                            other_peer_ids.append(their_peer_id)
                    await db.commit()
                    # Патч 51, ч.3, фикс: рассылка остальным участникам кохорта
                    # раньше шла ВНУТРИ открытой транзакции вперемешку с БД-
                    # чтениями — если сеть к VK зависала на любом шаге, транзакция
                    # (уже "грязная" из-за get_character's last_active_at) висела
                    # бесконечно (idle in transaction), блокируя всех остальных
                    # игроков на UPDATE characters.last_active_at (см. инцидент
                    # после деплоя патча 51). Явно закрываем сессию ДО сетевых
                    # вызовов — соединение возвращается в пул немедленно, а не
                    # когда/если завершатся все messages.send.
                    await db.close()
                    for their_peer_id in other_peer_ids:
                        try:
                            await _bot_api.messages.send(peer_id=their_peer_id, message=notice, random_id=0)
                        except Exception:
                            pass
                    await message.answer(notice, keyboard=group_ready_keyboard())
                    return
                # Все участники на клетке готовы — только бои в групповом
                # исследовании (без событий/обрывков Песни/пепла, патч 51, ч.3).
                group_explore_service.clear(snapshot.id)
                region = region_for(character.pos_x, character.pos_y)
                dist = grid.chebyshev_distance(character.pos_x, character.pos_y)
                await group_combat_handlers.start_ready_group(
                    db, snapshot.id, cohort, region, dist, _rng,
                )
                return

        # ux-patch-5: обрывок Песни / событие — ВНУТРЬ сообщения исследования
        # (~50%), отдельным сообщением больше не шлём.
        fragment = flavor.explore_fragment(_rng)
        if fragment is not None and fragment.song_index is not None:
            # патч 25, п.6: отмечаем обрывок увиденным для прогресса Песни
            await song_service.record_seen(db, character, fragment.song_index)
            await db.commit()

    # патч 25, п.4: несобранная горстка пепла сгорает при новом исследовании
    ash_burned = ash_handful_state.clear(peer_id)
    _exploring.add(peer_id)
    delay = _rng.uniform(wc.EXPLORE_SECONDS_MIN, wc.EXPLORE_SECONDS_MAX)
    # Кнопки убираем до появления моба.
    text = "🔍 Ты осматриваешься вокруг..."
    if ash_burned:
        text = f"{ASH_BURNED_LINE}\n\n{text}"
    if fragment is not None:
        text += f"\n\n{fragment.text}"
    await message.answer(text, keyboard=kb.waiting_keyboard())
    _explore_scheduler.schedule(peer_id, delay)
    await pending_activity.remember("explore", peer_id, delay)


@labeler.message(payload_contains={"type": "group_explore_cancel"})
async def group_explore_cancel(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        snapshot = await group_service.get_group_snapshot(db, character.id)
        if snapshot is None:
            return
        group_explore_service.cancel(snapshot.id, character.id)
        has_mount = await mount_service.has_any_mount(db, character.id)
    await message.answer(
        "Ты вышел из очереди исследования.",
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
    )


@labeler.message(text=[kb.BTN_ASH_HANDFUL])
async def collect_ash_handful(message: Message) -> None:
    """Патч 25, п.4: сбор одноразовой находки — устаревшая кнопка (уже
    собрано/сгорело при следующем «Исследовать») молча игнорируется."""
    peer_id = message.peer_id
    if not ash_handful_state.is_pending(peer_id):
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        stats = await _get_stats(db, character.id)
        result = await ash_service.collect(db, character, stats, _rng)
        ash_handful_state.clear(peer_id)
        wallet = await wallet_service.get_wallet(db, character.id)
        farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        quest_line = await story_service.quest_summary_line(db, character)
        group_block = await group_texts.group_summary_block(db, character.id)
        has_mount = await mount_service.has_any_mount(db, character.id)
        await db.commit()

    text = (
        "У ног - горстка пепла, слишком плотная для простой золы. В ней что-то есть.\n\n"
        + display.xp_delta_line(result.xp, premium=result.xp_premium_applied)
    )
    drop_line = trophy_service.format_drop_line(result.trophies, source="ash_handful")
    if drop_line is not None:
        text += f"\n{drop_line}"
    if result.item is not None:
        text += f"\n\n{item_service.format_drop_announcement(result.item)}"
    if result.raid_key_dropped:
        text += f"\n{raid_key_texts.raid_key_drop_line()}"
    if result.group_kick is not None and result.group_kick.kicked_character_id == character.id:
        text += f"\n\n{group_texts.level_gap_kick_self_line()}"
    await message.answer(text, keyboard=kb.waiting_keyboard())
    await stats_window.notify_levelup(peer_id, result.levels_gained, result.new_level)
    await group_texts.notify_group_kick(_bot_api, result.group_kick)
    await message.answer(
        _map_text(character, stats, farm_currency, gear_bonus, quest_line, donate_currency, group_block),
        attachment=location_attachment(character),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
    )
    await _maybe_send_monolith_button(peer_id, character)


async def handle_explore_done(peer_id: int) -> None:
    """Колбэк планировщика: исследование закончено — два исхода (патч 13, ч.3):
    50% бой, 50% событие с выбором (событие всегда даёт результат, патч 10).
    Флейвор (Песнь/замечания) больше не бывает самостоятельным исходом — он
    остался только внутри сообщения ожидания "Ты осматриваешься..." (patch-5),
    которое уже показано раньше и не пересекается с этим исходом."""
    _exploring.discard(peer_id)
    await pending_activity.forget("explore", peer_id)
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        if death_service.is_dead(character) or movement_service.is_traveling(character):
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is not None:
            return  # успел вернуться в город
        if in_any_battle(peer_id):
            return
        stats = await _get_stats(db, character.id)

        outcome_kind = "combat" if _rng.random() < wc.EXPLORE_COMBAT_CHANCE else "event"
        # Патч 59: завершённое исследование ЛЮБОГО игрока подбрасывает руду в
        # случайный неполный рудник. Рудники — общий ресурс, который наполняет
        # активность всего сервера, а не персональный кран.
        await mining_service.spawn_ore(db, _rng)
        daily_progress = await daily_service.record_exploration(db, character)
        await db.commit()
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db, character)

        event = None
        song_can_read = False
        fish_offer = None
        empty_fisher = False
        summary_bits = None
        if outcome_kind == "event":
            event = event_pool.random_event(_rng)
            if event.ore_vein:
                # Жила разрешается сразу, значит сводка локации нужна прямо
                # здесь — иначе игрок останется с клавиатурой ожидания.
                wallet = await wallet_service.get_wallet(db, character.id)
                summary_bits = (
                    wallet.farm_currency, wallet.donate_currency,
                    await story_service.quest_summary_line(db, character),
                    await group_texts.group_summary_block(db, character.id),
                    await mount_service.has_any_mount(db, character.id),
                )
            if event.fish_trade:
                bag_grams = await fishing_service.bag_total_grams(db, character.id)
                if bag_grams <= 0:
                    # Продавать нечего: короткая сцена без выбора, сразу назад
                    # к панели локации. Данные для неё собираем здесь, пока
                    # сессия открыта.
                    empty_fisher = True
                    wallet = await wallet_service.get_wallet(db, character.id)
                    summary_bits = (
                        wallet.farm_currency, wallet.donate_currency,
                        await story_service.quest_summary_line(db, character),
                        await group_texts.group_summary_block(db, character.id),
                        await mount_service.has_any_mount(db, character.id),
                    )
                else:
                    # Патч 58: цена рыбака разыгрывается СЕЙЧАС, при показе, и
                    # зависит от кольца КЛЕТКИ, а не от места вылова. Иначе
                    # игрок соглашался бы на сделку вслепую, а весь смысл —
                    # тащить улов туда, где опаснее и дороже.
                    multiplier = _roll_fish_offer_multiplier(character)
                    fish_offer = _FishOffer(
                        multiplier=multiplier,
                        gold=await fishing_service.bag_value(db, character.id, multiplier),
                        weight_label=game_fishing.format_kg(bag_grams),
                    )
            if event.id == "ash_altar":
                # патч 25, п.6: доп. выбор «Прочесть Песнь», только если собрана
                song_can_read = await song_service.can_read(db, character.id)

    notice = dailies_texts.progress_notice(daily_progress)
    if notice:
        await _bot_api.messages.send(peer_id=peer_id, message=notice, random_id=0)
    for c in daily_progress.completed:
        await stats_window.notify_levelup(peer_id, c.levels_gained, c.new_level)

    if outcome_kind == "combat":
        await combat_handlers.start_encounter(peer_id, character, stats, gear_bonus, buff_modifiers)
        return

    if event is not None and event.ore_vein:
        # У жилы нет выбора: либо берёшься за кирку, либо уходишь. Сначала
        # сводка локации (она возвращает рабочую нижнюю клавиатуру), сверху —
        # отдельное инлайн-сообщение с кнопкой добычи.
        farm_currency, donate_currency, quest_line, group_block, has_mount = summary_bits
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=_map_text(character, stats, farm_currency, gear_bonus,
                              quest_line, donate_currency, group_block),
            random_id=0, attachment=location_attachment(character),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id,
                                          has_mount=has_mount),
        )
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=f"{event.title}" + chr(10) * 2 + event.text,
            random_id=0,
            keyboard=mining_kb.event_vein_keyboard(event.id),
        )
        return

    if empty_fisher:
        farm_currency, donate_currency, quest_line, group_block, has_mount = summary_bits
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=f"{event.title}" + chr(10) * 2 + event.empty_text,
            random_id=0, attachment=event_attachment(event.id),
        )
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=_map_text(character, stats, farm_currency, gear_bonus,
                              quest_line, donate_currency, group_block),
            random_id=0, attachment=location_attachment(character),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id,
                                          has_mount=has_mount),
        )
        return

    _pending_events[peer_id] = event.id
    body = event.text
    if fish_offer is not None:
        # Цена принадлежит ЭТОМУ показу события: запоминаем ровно ту,
        # которую сейчас увидит игрок, и по ней потом и продаём.
        _pending_fish_offers[peer_id] = fish_offer.multiplier
        body = body.format(gold=fish_offer.gold, weight=fish_offer.weight_label)
    text = f"{event.title}" + chr(10) * 2 + body
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0,
        attachment=event_attachment(event.id),
        keyboard=kb.event_choice_keyboard(event, song_extra=song_can_read),
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
    fish_multiplier = _pending_fish_offers.pop(peer_id, None)

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        stats = await _get_stats(db, character.id)
        outcome = event_service.pick_outcome(_rng, event.choices[choice_idx].outcomes)
        choice_label = event.choices[choice_idx].label
        fish_sale_line = None
        if outcome.fish_buyer:
            # Продаём по цене, ПОКАЗАННОЙ игроку. Если множителя нет (бот
            # перезапустился между показом и ответом), сделка не состоится:
            # взять цену заново значило бы продать не по той, что обещали.
            if fish_multiplier is None:
                await message.answer(
                    "Рыбак уже ушёл - и с ним его цена."
                )
                return
            gold, grams = await fishing_service.sell_bag(db, character, fish_multiplier)
            if gold:
                fish_sale_line = (
                    f"🧺 Продано {game_fishing.format_kg(grams)} рыбы за {gold} зол."
                )
        choice_code = trial_service.EVENT_CHOICE_CODES.get(choice_label)
        result = await event_service.apply_outcome(
            db, character, stats, outcome, _rng, event_id=event.id, choice_code=choice_code
        )
        wallet = await wallet_service.get_wallet(db, character.id)
        farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
        quest_line = await story_service.quest_summary_line(db, character)
        group_block = await group_texts.group_summary_block(db, character.id)
        has_mount = await mount_service.has_any_mount(db, character.id)
        await db.commit()

    if result.is_combat:
        await message.answer(result.text)
        await combat_handlers.start_encounter(peer_id, character, stats, gear_bonus, buff_modifiers)
        return

    # ux-patch-10 п.1: сводка локации — всегда отдельное сообщение
    result_text = result.text
    if fish_sale_line:
        result_text += chr(10) * 2 + fish_sale_line
    if result.group_kick is not None and result.group_kick.kicked_character_id == character.id:
        result_text += f"\n\n{group_texts.level_gap_kick_self_line()}"
    await message.answer(result_text, keyboard=kb.waiting_keyboard())
    # патч 14, ч.2.3: событие — тоже источник опыта, левелап не должен теряться
    await stats_window.notify_levelup(peer_id, result.levels_gained, result.new_level)
    await group_texts.notify_group_kick(_bot_api, result.group_kick)
    daily_notice = dailies_texts.progress_notice_from(result.daily_completed, result.daily_streak_notice)
    if daily_notice:
        await message.answer(daily_notice)
    for c in result.daily_completed:
        await stats_window.notify_levelup(peer_id, c.levels_gained, c.new_level)
        await group_texts.notify_group_kick(_bot_api, c.group_kick)
    if ash_service.roll_appears(_rng):
        ash_handful_state.mark(peer_id)
    await message.answer(
        _map_text(character, stats, farm_currency, gear_bonus, quest_line, donate_currency, group_block),
        attachment=location_attachment(character),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
    )
    await _maybe_send_monolith_button(peer_id, character)


SONG_READ_SCENE = (
    "Ты произносишь Песнь целиком - впервые за много лет она звучит от начала до конца.\n\n"
    "Пепел вокруг алтаря приходит в движение. Он поднимается столбом, уплотняется, обретает "
    "форму - и на месте золы стоит конь, сотканный из пепла и багрового света. Он не дышит. "
    "Он просто ждёт.\n\n"
    "Списки пополнились новой строкой. Не именем - званием."
)


@labeler.message(payload_contains={"type": "read_song"})
async def read_song(message: Message) -> None:
    """Патч 25, п.6: доп. выбор у Пепельного алтаря — только если Песнь
    собрана полностью и ещё не прочитана (устаревшее нажатие игнорируется)."""
    peer_id = message.peer_id
    pending_event_id = _pending_events.get(peer_id)
    if pending_event_id != "ash_altar":
        return
    _pending_events.pop(peer_id, None)

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        if not await song_service.can_read(db, character.id):
            return
        await song_service.read_song(db, character)
        stats = await _get_stats(db, character.id)
        wallet = await wallet_service.get_wallet(db, character.id)
        farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        quest_line = await story_service.quest_summary_line(db, character)
        group_block = await group_texts.group_summary_block(db, character.id)
        await db.commit()

    await message.answer(SONG_READ_SCENE, keyboard=kb.waiting_keyboard())
    await message.answer(
        _map_text(character, stats, farm_currency, gear_bonus, quest_line, donate_currency, group_block),
        attachment=location_attachment(character),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=True),
    )
    await _maybe_send_monolith_button(peer_id, character)


# --- Отдых (combat-patch-2, п.3): вне боя, 8-12 сек, HP → полное ---


@labeler.message(text=[kb.BTN_REST])
@activity_action
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
        if in_any_battle(peer_id):
            await message.answer("В бою не отдохнёшь.")
            return
        if mining_service.is_digging(character):
            await message.answer(
                mining_texts.busy_text(mining_service.remaining_seconds(character))
            )
            return
        if peer_id in _resting:
            await message.answer("🛏️ Ты уже отдыхаешь.")
            return
        if peer_id in _exploring or movement_service.is_traveling(character, now):
            await message.answer("Сначала закончи то, что начал.")
            return

    _resting.add(peer_id)
    # Патч 50: Метка Хранителя — отдых вдвое быстрее.
    if premium_service.is_premium(character):
        delay = _rng.uniform(pc.REST_SECONDS_MIN, pc.REST_SECONDS_MAX)
    else:
        delay = _rng.uniform(wc.REST_SECONDS_MIN, wc.REST_SECONDS_MAX)
    # отдых — кнопки убираем на время (чистка шума)
    await message.answer(flavor.rest_start(), keyboard=kb.waiting_keyboard())
    _rest_scheduler.schedule(peer_id, delay)
    await pending_activity.remember("rest", peer_id, delay)


async def handle_rest_done(peer_id: int) -> None:
    """Колбэк планировщика: отдых окончен — HP восстановлено, кнопки возвращены."""
    if peer_id not in _resting:
        return  # отдых прерван (напр. пришёл бой — задел на будущее)
    _resting.discard(peer_id)
    await pending_activity.forget("rest", peer_id)
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        if death_service.is_dead(character) or in_any_battle(peer_id):
            return
        stats = await _get_stats(db, character.id)
        vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
        max_hp = vitals_service.max_hp(character, stats, vit_bonus)
        hp_before = vitals_service.current_hp(character, stats, vit_bonus)
        vitals_service.restore_full(character)
        if character.subclass is not None:
            await trial_service.record_rest(db, character)
        await daily_service.record_rest(db, character)
        has_mount = await mount_service.has_any_mount(db, character.id)
        await db.commit()
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is not None:
            # Патч 39: отдых начинается из Таверны — после него возвращаемся
            # туда же (character.screen), а не сбрасываем на площадь.
            _, keyboard = await _render_city_screen(db, character, character.screen)
        else:
            keyboard = kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount)
    await _deliver_daily_notice(peer_id, character)
    text = f"{flavor.rest_done()}\n{display.hp_delta_line(hp_before, max_hp, max_hp)}"
    await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, keyboard=keyboard)


@labeler.message(text=kb.MOVEMENT_TEXTS)
@activity_action
async def move(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        if await _check_still_dead(db, character, now):
            await message.answer("☠ Сначала очнись.")
            return
        if in_any_battle(message.peer_id):
            await message.answer("Сначала разберись с боем.")
            return
        if mining_service.is_digging(character):
            await message.answer(
                mining_texts.busy_text(mining_service.remaining_seconds(character))
            )
            return
        if message.peer_id in _exploring:
            await message.answer("🔍 Ты осматриваешься - подожди.")
            return
        if message.peer_id in _resting:
            await message.answer("🛏️ Ты отдыхаешь. Дай себе минуту.")
            return
        if movement_service.resolve_arrival(character, now):
            if character.subclass is not None:
                await trial_service.record_cell_moved(db, character)
            await daily_service.record_cell_moved(db, character)
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
        if not grid.in_bounds(character.pos_x + dx, character.pos_y + dy):
            # Патч 31, п.7: за границей карты (-50..50) — лорный отказ вместо
            # движения, позиция и клавиатура не меняются.
            has_mount = await mount_service.has_any_mount(db, character.id)
            await message.answer(
                flavor.world_edge_line(_rng),
                keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, message.peer_id, has_mount=has_mount),
            )
            return
        # Патч 53: уходит с клетки Монолита — если состоял в рейд-лобби, это
        # уменьшает знаменатель готовности (текст патча), тот же принцип, что
        # и "вышел из группы" (см. services/group_service.py).
        if (character.pos_x, character.pos_y) == raid_cfg.MONOLITH_COORDS:
            await raid_service.leave_lobby_if_present(db, character.id)
        travel_seconds = movement_service.start_travel(character, dx, dy, now)
        await db.commit()
        # в пути — кнопки убираем, вернём по прибытии (чистка визуального шума)
        await message.answer(flavor.travel_line(_rng), keyboard=kb.waiting_keyboard())
        _travel_scheduler.schedule(message.peer_id, travel_seconds)


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
        await daily_service.record_cell_moved(db, character)
        await db.commit()
        await _deliver_daily_notice(peer_id, character)
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is not None:
            # Патч 39: прибытие в город — всегда корневой экран (площадь).
            await screen_service.set_screen(db, character, None)
            text, keyboard = await _render_city_screen(db, character, None)
            await _bot_api.messages.send(
                peer_id=peer_id, message=text, random_id=0, attachment=hub_attachment(region), keyboard=keyboard,
            )
            return
        has_mount = await mount_service.has_any_mount(db, character.id)
        stats = await _get_stats(db, character.id)
        if await _maybe_trigger_story(peer_id, db, character, stats):
            return
        wallet = await wallet_service.get_wallet(db, character.id)
        farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
        quest_line = await story_service.quest_summary_line(db, character)
        group_block = await group_texts.group_summary_block(db, character.id)
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=_map_text(
                character, stats, farm_currency, quest_line=quest_line,
                donate_currency=donate_currency, group_block=group_block,
            ),
            random_id=0,
            attachment=location_attachment(character),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
        )
        await _maybe_send_monolith_button(peer_id, character)
        await maybe_send_lake_button(peer_id, character)
        # Патч 59: уход с клетки обнуляет незаконченную добычу.
        await mining_service_abandon(character)
        await maybe_send_mine_button(peer_id, character)


@labeler.message(text=[kb.BTN_MENTOR, kb.BTN_MENTOR_BADGE])
async def talk_to_mentor(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # наставник только в городе

        if region != character.region:
            # патч 26: чужой город — наставник недоступен вовсе
            await message.answer(FOREIGN_NPC_REJECTION)
            return

        progress = await quest_service.get_or_assign(db, character)
        if progress is None:
            await db.commit()
            return

        if progress.is_new:
            await db.commit()
            await message.answer(mentor_intro(region), attachment=mentor_attachment(region))
            return

        if progress.status == "ready":
            result = await quest_service.turn_in(db, character)
            # патч 18: квест 1.1 — начало сюжета; продвигаем указатель за него
            # и добавляем текст-переход (Сера бросает флягу и т.д.)
            transition_text = await story_service.advance_after_first_quest(db, character)
            await db.commit()
            text = mentor_praise(region)
            if result is not None and result.xp_reward > 0:
                text += "\n\n" + flavor.quest_reward_line(result.xp_reward, result.xp_premium_applied)
                if result.levels_gained > 0:
                    text += "\n" + flavor.levelup_line(result.new_level, _rng)
                if result.group_kick is not None and result.group_kick.kicked_character_id == character.id:
                    text += f"\n\n{group_texts.level_gap_kick_self_line()}"
            if transition_text:
                text += "\n\n" + transition_text
            await message.answer(text)
            # патч 14, ч.2.3: квест — тоже источник опыта, левелап не должен теряться
            if result is not None:
                await stats_window.notify_levelup(message.peer_id, result.levels_gained, result.new_level)
                await group_texts.notify_group_kick(_bot_api, result.group_kick)
            return

        if progress.status == "completed":
            # патч 18: квест 1.1 закрыт — дальше сюжет ведёт story_service
            stats = await _get_stats(db, character.id)
            story_result = await story_service.visit_mentor(db, character, stats)
            await db.commit()
            if story_result is None:
                await message.answer("- У меня для тебя пока больше ничего нет. Возвращайся позже.")
                return
            story_text = story_result.text
            if (
                story_result.group_kick is not None
                and story_result.group_kick.kicked_character_id == character.id
            ):
                story_text += f"\n\n{group_texts.level_gap_kick_self_line()}"
            await message.answer(story_text, attachment=act_attachment(story_result.act_image))
            if story_result.levels_gained > 0:
                await stats_window.notify_levelup(
                    message.peer_id, story_result.levels_gained, story_result.new_level
                )
                await group_texts.notify_group_kick(_bot_api, story_result.group_kick)
            return

        # активен, но ещё не выполнен
        await message.answer(
            f"- Ты уже здесь? Дело ещё не закончено - {progress.progress_label}: "
            f"{progress.progress}/{progress.target_count}."
        )


@labeler.message(text=[kb.BTN_MARKET])
async def visit_market(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is not None and region != character.region:
            # патч 26: рынок недоступен в чужом городе
            await message.answer(FOREIGN_NPC_REJECTION)
            return
    await message.answer("Торговцы раскладывают товар. Скоро здесь можно будет торговать.")


# --- Патч 39: кварталы города — переходы между Площадью/Таверной/Торговым квартаром ---


@labeler.message(text=[kb.BTN_TAVERN])
async def open_tavern(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # таверна только в городе
        if region != character.region:
            # Таверна — не для чужаков (в отличие от Торгового квартала), в
            # отличие от старого личного меню (Отдых/Характеристики и т.п.
            # раньше работали и в чужом городе — патч 39 сознательно это
            # ужесточает: см. текст патча, часть 2).
            await message.answer(FOREIGN_NPC_REJECTION)
            return
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
        text, keyboard = await _render_city_screen(db, character, "tavern")
    await message.answer(text, keyboard=keyboard)


@labeler.message(text=[kb.BTN_MARKET_QUARTER])
async def open_market_quarter(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # торговый квартал только в городе
        await screen_service.set_screen(db, character, "market_quarter")
        await db.commit()
        text, keyboard = await _render_city_screen(db, character, "market_quarter")
    await message.answer(text, keyboard=keyboard)


@labeler.message(text=[kb.BTN_SQUARE_BACK])
async def back_to_square(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return
        await screen_service.set_screen(db, character, None)
        await db.commit()
        text, keyboard = await _render_city_screen(db, character, None)
    await message.answer(text, attachment=hub_attachment(region), keyboard=keyboard)


@labeler.message(text=["/квест", "/quest"])
async def quest_reminder(message: Message) -> None:
    """Напоминание текущей сюжетной цели (патч 18, п.5 патча 21)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        text = await story_service.quest_reminder_text(db, character, mentor_name(character.region))
    # Патч 30, баг 2: справочная команда не должна стирать боевую клавиатуру.
    await message.answer(text, keyboard=active_battle_keyboard(message.peer_id))


STUCK_LINE = "Ты встряхиваешься и приходишь в себя."


def is_busy(peer_id: int) -> bool:
    """Патч 25, п.7: занят исследованием/отдыхом — используется мунтами,
    чтобы не начинать поездку поверх незавершённого действия."""
    return peer_id in _exploring or peer_id in _resting


# Патч 37: рестроители клавиатуры+текста вложенных экранов, по имени
# character.screen — общая точка для /клавиатура и восстановления после
# рестарта бота. Каждый модуль сам решает, относится ли к нему текущий
# экран (None, если нет) — см. их rebuild().
_SCREEN_REBUILDERS = (
    appraiser_handlers.rebuild,
    elixir_shop_handlers.rebuild,
    inventory_handlers.rebuild,
)


async def _screen_keyboard(db, character) -> str | None:
    """Патч 37: если персонаж на вложенном экране (скупщик/лавка/инвентарь и
    т.п.) — его СОБСТВЕННАЯ клавиатура, а не корневая городская/карточная.
    Патч 39: "tavern"/"market_quarter" — кварталы города, тоже вложенные
    экраны, но живут прямо в этом модуле (не отдельный handler-файл), см.
    _render_city_screen."""
    if character.screen is None:
        return None
    if character.screen in ("tavern", "market_quarter"):
        result = await _render_city_screen(db, character, character.screen)
        return result[1] if result is not None else None
    if character.screen == "raid_list":
        return raid_kb.raid_list_keyboard()
    # Патч 59: экраны ремёсел. Без них /клавиатура возвращала клавиатуру карты
    # поверх открытого экрана, а в забое это было прямым застреванием: кнопки
    # «Бросить кирку» на карте нет, а все остальные отвечают «ты в забое».
    if character.screen == "mine":
        if mining_service.is_digging(character):
            return mining_kb.digging_keyboard()
        mine = mining_service.mine_at(character)
        left = await mining_service.ore_in_mine(db, mine.id) if mine is not None else 0
        return mining_kb.mine_keyboard(left > 0)
    if character.screen == "lake":
        if fishing_service.is_casting(character):
            return fishing_kb.casting_keyboard()
        return fishing_kb.lake_keyboard()
    for rebuild in _SCREEN_REBUILDERS:
        result = await rebuild(db, character)
        if result is not None:
            _, keyboard = result
            return keyboard
    return None


async def _current_keyboard(db, character, peer_id: int, now: datetime) -> str:
    """Патч 25, п.5: клавиатура под текущее состояние игрока — общая для
    /клавиатура и финала /застрял. Порядок проверок = приоритет состояний.
    Патч 37: вложенный экран (character.screen) — ниже приоритетом, чем
    бой/перемещение/смерть, поэтому бой всегда перебивает сохранённый экран
    скупщика/лавки/инвентаря, как и раньше (правило патча 30 не отменяется)."""
    battle_kb = active_battle_keyboard(peer_id)
    if battle_kb is not None:
        return battle_kb
    if peer_id in _exploring or peer_id in _resting or movement_service.is_traveling(character, now):
        return kb.waiting_keyboard()
    if await mount_service.active_travel(db, character.id) is not None:
        return kb.waiting_keyboard()
    if await _check_still_dead(db, character, now):
        return kb.waiting_keyboard()
    screen_kb = await _screen_keyboard(db, character)
    if screen_kb is not None:
        return screen_kb
    region = grid.city_region_at(character.pos_x, character.pos_y)
    if region is not None:
        _, keyboard = await _render_city_screen(db, character, character.screen)
        return keyboard
    has_mount = await mount_service.has_any_mount(db, character.id)
    return kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount)


async def broadcast_service_notice(text: str) -> int:
    """Служебная рассылка всем игрокам + АКТУАЛЬНАЯ клавиатура каждому.

    Живёт здесь, потому что здесь же живёт _current_keyboard: смысл рассылки
    после сброса состояний не в тексте, а именно в клавиатуре — у игрока,
    которого сбросило из пути или из боя, внизу висит клавиатура ожидания,
    и без новой он остаётся «в зависании» даже после того, как БД уже чистая.

    Возвращает число игроков, которым сообщение ушло. Ошибка отправки одному
    не прерывает рассылку: один заблокировавший бота не должен лишать
    остальных возможности играть дальше.
    """
    if _bot_api is None:
        return 0
    now = datetime.now(timezone.utc)
    sent = 0
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(Character.id, User.vk_id)
                .join(User, User.id == Character.user_id)
                .where(Character.creation_state.is_(None), Character.is_banned.is_(False))
            )
        ).all()
        for character_id, peer_id in rows:
            character = await db.get(Character, character_id)
            if character is None:
                continue
            try:
                keyboard = await _current_keyboard(db, character, peer_id, now)
                await _bot_api.messages.send(
                    peer_id=peer_id, message=text, random_id=0, keyboard=keyboard,
                )
                sent += 1
            except Exception:  # noqa: BLE001 - один недоступный не рвёт рассылку
                logger.warning("Не удалось доставить служебное сообщение игроку {}", peer_id)
            # VK ограничивает скорость отправки сообществу; пауза дешевле, чем
            # ловить 429 на середине рассылки.
            await asyncio.sleep(SERVICE_NOTICE_DELAY_SECONDS)
    return sent


@labeler.message(text=["/клавиатура", "/keyboard"])
async def keyboard_command(message: Message) -> None:
    """Патч 25, п.5: пересобрать и прислать актуальную клавиатуру, ничего не
    прерывая — работает всегда, включая PvP."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        keyboard = await _current_keyboard(db, character, message.peer_id, now)
    await message.answer("Обновляю клавиатуру.", keyboard=keyboard)


@labeler.message(text=["/ключ"])
async def raid_key_command(message: Message) -> None:
    """Патч 45, ч.4: осмотреть Ключ Монолита — пока без функционала, только
    флейвор-текст."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if character.raid_keys <= 0:
            await message.answer("У тебя нет Ключа Монолита.")
            return
        await message.answer(raid_key_texts.RAID_KEY_USE_TEXT)


def activity_state(peer_id: int) -> str:
    """Грубая текстовая метка активности по in-memory состоянию — для /баг
    снапшота и админки (патч 27, части 2.3 и 3). Перемещение/поездка на
    маунте не отсюда — это в Character/MountTravel, проверяются вызывающим."""
    if in_any_battle(peer_id):
        return "в бою"
    if pvp_handlers.rebuild_keyboard(peer_id) is not None:
        return "в PvP-бою"
    if peer_id in _exploring:
        return "в исследовании"
    if peer_id in _resting:
        return "отдыхает"
    return "в городе/на карте"


async def force_unstick(db, character, peer_id: int, *, admin_override: bool = False) -> bool:
    """Аварийный выход из зависшей активности (патч 25, п.5). Общая логика
    /застрял и админского «Сбросить активности» — по умолчанию (admin_override=
    False, игрок сам себе жмёт /застрял) PvP НЕ прерывает (защита от абьюза),
    там только позволяет пересобрать боевую клавиатуру у вызывающего и
    возвращает True — вызывающий должен сам обработать этот случай отдельно,
    остальные состояния ниже в этом случае НЕ трогаются.

    admin_override=True (патч 39: bot/miniapp_admin_api.py, только с
    админ-панели) — снимает ВСЕ состояния без исключений, PvP включая: боец
    помечается погибшим в своём бою (pvp_handlers.force_defeat), а не
    блокирует сброс остального, как раньше (был баг — PvP-ветка делала
    ранний return ДО перемещения/маунта/исследования/отдыха, так что если
    что-то из этого тоже зависло одновременно с PvP, сброс не долечивал
    ничего). Возвращает False в этом режиме всегда — вызывающий не должен
    дополнительно ветвиться на PvP."""
    # Патч 37: /застрял всегда возвращает на корневой экран (город/карта) —
    # даже если PvP не даёт прервать сам бой, застрявший вложенный экран
    # (скупщик/лавка/инвентарь) сбрасывается.
    await screen_service.set_screen(db, character, None)
    if (raid_combat_handlers.has_active_battle(peer_id)
            or group_combat_handlers.has_active_group_battle(peer_id)):
        return True  # restore the battle UI; never escape a raid via /stuck
    if pvp_handlers.rebuild_keyboard(peer_id) is not None:
        if not admin_override:
            return True
        pvp_handlers.force_defeat(peer_id)
    if combat_handlers.has_active_encounter(peer_id):
        # безнаградный/безштрафной аборт — тот же путь, что и прерывание PvE открытым PvP
        await combat_handlers.interrupt_for_pvp(peer_id)
        travel_id = combat_handlers.pop_mount_ambush(peer_id)
        if travel_id is not None:
            # бой-нападение прерван вручную — поездка не должна зависнуть в ambushed
            travel = await db.get(MountTravel, travel_id)
            if travel is not None:
                await mount_service.cancel_travel(db, travel)
    _exploring.discard(peer_id)
    _resting.discard(peer_id)
    # Запись в Redis снимается вместе с отметкой в памяти. Иначе сброшенный
    # отдых воскрес бы после следующего деплоя и вылечил бы бесплатно.
    await pending_activity.forget("explore", peer_id)
    await pending_activity.forget("rest", peer_id)
    now = datetime.now(timezone.utc)
    if movement_service.is_traveling(character, now):
        movement_service.cancel_travel(character)
    # Патч 39: отменяем ЛЮБОЙ активный статус маунт-поездки, не только
    # "traveling" — active_travel() возвращает и "ambushed" (нападение в
    # пути, чей бой потерян/прерван), а тот раньше не снимался ВООБЩЕ НИЧЕМ
    # (ни этой функцией, ни admin_service.reset_activity_db) — см. живой
    # баг игрока 24815750/char 15: кнопка маунта была заблокирована навсегда.
    active_mount_travel = await mount_service.active_travel(db, character.id)
    if active_mount_travel is not None:
        await mount_service.cancel_travel(db, active_mount_travel)
    return False


@labeler.message(text=["/застрял", "/stuck"])
async def stuck_command(message: Message) -> None:
    """Патч 25, п.5: аварийный выход из зависшей активности. PvP НЕ прерывает
    (защита от абьюза) — там только пересобирает боевую клавиатуру."""
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if await force_unstick(db, character, peer_id):
            await db.commit()  # патч 37: сброс character.screen должен сохраниться и в PvP-ветке
            await message.answer(STUCK_LINE, keyboard=active_battle_keyboard(peer_id))
            return
        now = datetime.now(timezone.utc)
        await db.commit()
        keyboard = await _current_keyboard(db, character, peer_id, now)
    await message.answer(STUCK_LINE, keyboard=keyboard)
