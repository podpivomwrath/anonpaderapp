"""Отдых (combat-patch-2, п.3): вне боя, 8-12 сек, HP до полного.

Перенесено из bot/handlers/world.py без изменений логики (2026-10-21, шаг 3
нарезки). Планировщик отдыха и общие помощники мира (смерть, экран города,
ежедневки) по-прежнему в world.py - здесь к ним обращаются через модуль.
Отметка «отдыхает» - bot/explore_rest.py.
"""

from datetime import datetime, timezone

from vkbottle.bot import BotLabeler, Message

from bot import explore_rest, mining_texts
from bot.activity import activity_action
from bot.battle_keyboard import in_any_battle
from bot.handlers import world
from bot.keyboards import world as kb
from game.combat import display
from game.economy import premium_config as pc
from game.world import flavor, grid
from game.world import world_config as wc
from services import (
    daily_service,
    death_service,
    group_explore_service,
    group_service,
    item_service,
    mining_service,
    mount_service,
    movement_service,
    premium_service,
    subclass_service,
    trial_service,
    vitals_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True

CITY_REST_TEXT = "В городе отдыхать незачем: здоровье здесь восстанавливается само."


@labeler.message(text=[kb.BTN_REST])
@activity_action
async def rest(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        if await world._check_still_dead(db, character, now):
            await message.answer("☠ Сначала очнись.")
            return
        if in_any_battle(peer_id):
            await message.answer("В бою не отдохнёшь.")
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is not None:
            # 2026-10-21: в городе отдыха нет - здоровье там восстанавливается
            # само. Кнопку убрали из Таверны; это ответ старой клавиатуре.
            screen = await world._render_city_screen(db, character, character.screen)
            await message.answer(CITY_REST_TEXT, keyboard=screen[1] if screen else None)
            return
        if world._in_mine_digging(character):
            await message.answer(
                mining_texts.busy_text(mining_service.remaining_seconds(character))
            )
            return
        if explore_rest.resting(peer_id):
            await message.answer("🛏️ Ты уже отдыхаешь.")
            return
        if explore_rest.exploring(peer_id) or movement_service.is_traveling(character, now):
            await message.answer("Сначала закончи то, что начал.")
            return
        if await mount_service.active_travel(db, character.id) is not None:
            await message.answer(world.MOUNT_BUSY_TEXT)
            return
        # Отдых - выход из очереди группового исследования (2026-10-13): иначе
        # группа уходила исследовать с отдыхающим, а отдых кончался посреди.
        hint_peers: list[int] = []
        rest_snapshot = await group_service.get_group_snapshot(db, character.id)
        if rest_snapshot is not None:
            queue = group_explore_service.get_queue(rest_snapshot.id)
            if queue is not None and character.id in queue.ready:
                still_ready = group_explore_service.cancel(rest_snapshot.id, character.id)
                hint_peers = await world.ready_hint_peers(db, still_ready)

    # Патч 50: Метка Хранителя — отдых вдвое быстрее.
    if premium_service.is_premium(character):
        delay = world._rng.uniform(pc.REST_SECONDS_MIN, pc.REST_SECONDS_MAX)
    else:
        delay = world._rng.uniform(wc.REST_SECONDS_MIN, wc.REST_SECONDS_MAX)
    await explore_rest.start(explore_rest.REST, peer_id, delay)
    # отдых — кнопки убираем на время (чистка шума)
    await message.answer(flavor.rest_start(), keyboard=kb.waiting_keyboard())
    if hint_peers:
        await message.answer("Ты вышел из очереди группового исследования.")
        await world.send_ready_hint(hint_peers)
    world._rest_scheduler.schedule(peer_id, delay)


async def handle_rest_done(peer_id: int) -> None:
    """Колбэк планировщика: отдых окончен — HP восстановлено, кнопки возвращены."""
    if not await explore_rest.stop(explore_rest.REST, peer_id):
        return  # отдых прерван (напр. пришёл бой — задел на будущее)
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        if death_service.is_dead(character) or in_any_battle(peer_id):
            return
        stats = await world._get_stats(db, character.id)
        vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
        max_hp = vitals_service.max_hp(character, stats, vit_bonus)
        hp_before = vitals_service.current_hp(character, stats, vit_bonus)
        vitals_service.restore_full(character)
        if subclass_service.buff_pool(character) is not None:
            await trial_service.record_rest(db, character)
        await daily_service.record_rest(db, character)
        has_mount = await mount_service.has_any_mount(db, character.id)
        await db.commit()
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is not None:
            # Отдых, начатый в городе до 2026-10-21 и доигранный после рестарта.
            _, keyboard = await world._render_city_screen(db, character, character.screen)
        else:
            keyboard = kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount)
    await world._deliver_daily_notice(peer_id, character)
    text = flavor.rest_done()
    if hp_before < max_hp:
        # При полном здоровье строка «+0 HP · 100% → 100%» - пустая.
        text += "\n" + display.hp_delta_line(hp_before, max_hp, max_hp)
    await world._bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, keyboard=keyboard)
