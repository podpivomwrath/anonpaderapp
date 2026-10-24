"""Исследование клетки: соло и группой, итог (бой или событие), события с
выбором, горстка пепла и Пепельная Песнь.

Перенесено из bot/handlers/world.py без изменений логики (2026-10-21, шаг 4
нарезки). Общее состояние мира и помощники (планировщики, _rng, ожидающие
события, клавиатуры экранов) по-прежнему живут в world.py - здесь к ним
обращаются через модуль, чтобы копия была одна и тесты подменяли их там же.
Отметка «исследует» - bot/explore_rest.py.
"""

import asyncio
import random
from datetime import datetime, timezone
from vkbottle.bot import BotLabeler, Message
from bot import (
    ash_handful_state,
    dailies_texts,
    group_texts,
    mining_texts,
    raid_key_texts,
)
from bot.activity import activity_action
from bot.battle_keyboard import in_any_battle
from bot.handlers import combat as combat_handlers
from bot.handlers import group_combat as group_combat_handlers
from bot.handlers import scene_events as scene_event_handlers
from bot.handlers import group_events as group_event_handlers
from bot.handlers import stats_window
from bot.handlers import world_boss as world_boss_handlers
from bot.handlers import guild as guild_handlers
from bot.pvp_texts import SIEGE_NO_EXPLORE_TEXT
from bot.keyboards import mining as mining_kb
from bot.keyboards import world as kb
from bot.keyboards.group_explore import group_ready_keyboard
from bot.world_summary import location_attachment
from bot import explore_rest, pending_activity
from bot.world_texts import (
    event_attachment,
)
from game.combat import display
from game.economy import fishing as game_fishing
from game.world import flavor, grid, scene_events
from game.world import events as event_pool
from game.world import world_config as wc
from game.world.location_types import region_for
from models import Character
from services import (
    guild_service,
    ash_service,
    daily_service,
    death_service,
    event_service,
    fishing_service,
    group_explore_service,
    guild_siege_service,
    guild_territory_service,
    group_service,
    item_service,
    herb_service,
    mining_service,
    mount_service,
    movement_service,
    preset_service,
    scene_event_service,
    rift_service,
    song_service,
    story_service,
    trial_service,
    trophy_service,
    wallet_service,
    world_boss_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory
from bot.handlers import world

labeler = BotLabeler()
labeler.vbml_ignore_case = True


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
        if await world._check_still_dead(db, character, now):
            await message.answer("☠ Сначала очнись.")
            return
        if in_any_battle(peer_id):
            await message.answer("⚔️ Ты уже в бою.")
            return
        if world._in_mine_digging(character):
            await message.answer(
                mining_texts.busy_text(mining_service.remaining_seconds(character))
            )
            return
        if explore_rest.exploring(peer_id):
            await message.answer("🔍 Ты уже осматриваешься...")
            return
        if explore_rest.resting(peer_id):
            await message.answer("🛏️ Ты отдыхаешь. Дай себе минуту.")
            return
        if movement_service.is_traveling(character, now):
            left = movement_service.remaining_seconds(character, now)
            await message.answer(f"🚶 В пути... осталось ~{left:.0f} сек.", keyboard=kb.walking_keyboard())
            return
        if await mount_service.active_travel(db, character.id) is not None:
            await message.answer(world.MOUNT_BUSY_TEXT)
            return
        if grid.city_region_at(character.pos_x, character.pos_y) is not None:
            await message.answer("В городе безопасно. Исследовать можно только за воротами.")
            return
        # Гильдии: за час до осады на клетке не дерутся - и не исследуют,
        # исследование может затянуть в бой с мобом к самому началу осады.
        if await guild_siege_service.lock_at(db, character.pos_x, character.pos_y) is not None:
            await message.answer(SIEGE_NO_EXPLORE_TEXT)
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
                if group_combat_handlers.is_group_fighting(snapshot.id) or \
                        group_event_handlers.has_group_event(snapshot.id):
                    await message.answer("Твоя группа уже в деле. Дождись, пока они закончат.")
                    return
                cohort_ids = {m.id for m in cohort}
                queue = group_explore_service.start_or_join(
                    snapshot.id, (character.pos_x, character.pos_y), cohort_ids, character.id,
                )
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
                            await world._bot_api.messages.send(peer_id=their_peer_id, message=notice, random_id=0)
                        except Exception:
                            pass
                    await message.answer(notice, keyboard=group_ready_keyboard())
                    return
                # Состав - из очереди, а не все на клетке (2026-10-13):
                # отменивший участие оставался в составе, и его утаскивало
                # в событие. Без отменивших готов один - идёт сам.
                cohort = [m for m in cohort if m.id in queue.cohort]
                if len(cohort) <= 1:
                    group_explore_service.clear(snapshot.id)
                if len(cohort) > 1:
                    # Все участники на клетке готовы: групповое событие (решают
                    # все разом) или, чаще, групповой бой. Пепла в групповом
                    # исследовании нет (патч 51, ч.3).
                    group_explore_service.clear(snapshot.id)
                    # Гильдии: групповое исследование - тоже исследование клетки
                    # для каждого (десятина владельцу, закладка знамени).
                    # Обрывки Песни и замечания (2026-10-13): раньше группа шла
                    # сразу в событие или бой, и лор не видел никто - Песнь в
                    # группе не собиралась. Теперь каждый получает своё «ты
                    # осматриваешься» со своим обрывком, и тот идёт в его Песнь.
                    look_around: list[tuple[int, str]] = []
                    explore_dailies: list[tuple[int, object]] = []
                    for m in cohort:
                        member_character = await db.get(Character, m.id)
                        if member_character is None:
                            continue
                        member_peer_id = await onboarding_svc.vk_id_for_character(db, m.id)
                        if member_peer_id is not None and explore_rest.resting(member_peer_id):
                            # Страховка: группа ушла - отдых не доигрывается.
                            await explore_rest.stop(explore_rest.REST, member_peer_id)
                        tithe = await guild_territory_service.on_exploration(db, member_character)
                        await herb_service.spawn(db, world._rng, (member_character.pos_x, member_character.pos_y))
                        if member_peer_id is not None:
                            guild_handlers.remember_tithe(member_peer_id, member_character, tithe)
                        # Ежедневки «исследуй» - и в группе, каждому (2026-10-13).
                        member_daily = await daily_service.record_exploration(db, member_character)
                        text = "🔍 Группа осматривается вокруг..."
                        member_peer = await onboarding_svc.vk_id_for_character(db, m.id)
                        # Несобранная горстка сгорает при новом исследовании - и в группе.
                        if member_peer is not None and ash_handful_state.clear(member_peer):
                            text = f"{ASH_BURNED_LINE}\n\n{text}"
                        fragment = flavor.explore_fragment(world._rng)
                        if fragment is not None:
                            text += f"\n\n{fragment.text}"
                            if fragment.song_index is not None:
                                await song_service.record_seen(db, member_character, fragment.song_index)
                        if member_peer is not None:
                            look_around.append((member_peer, text))
                            explore_dailies.append((member_peer, member_daily))
                    # Сеть - только после фиксации (см. выше про idle in transaction).
                    await db.commit()
                    for member_peer, member_daily in explore_dailies:
                        await world._announce_daily(member_peer, member_daily)
                    for member_peer, text in look_around:
                        try:
                            await world._bot_api.messages.send(
                                peer_id=member_peer, message=text, random_id=0, keyboard=kb.waiting_keyboard(),
                            )
                        except Exception:
                            pass
                    # Поиск длится, как в соло (2026-10-17): раньше бой или
                    # событие группы начинались мгновенно. Пока ищут - все
                    # «исследуют»: уйти с клетки или начать другое нельзя.
                    searching = [p for p, _text in look_around]
                    with explore_rest.group_search(searching):
                        await asyncio.sleep(world._rng.uniform(wc.EXPLORE_SECONDS_MIN, wc.EXPLORE_SECONDS_MAX))
                    region = region_for(character.pos_x, character.pos_y)
                    dist = grid.monolith_distance(character.pos_x, character.pos_y)
                    if await group_event_handlers.maybe_start(
                        db, snapshot.id, snapshot.leader_character_id, cohort, region, dist,
                        grid.ring_tier(character.pos_x, character.pos_y), world._rng,
                    ):
                        return
                    story = await world.group_story_mobs(db, cohort, world._rng)
                    await group_combat_handlers.start_ready_group(
                        db, snapshot.id, cohort, region, dist, world._rng,
                        mob_encounters=story[0] if story else None, story_quest_id=story[1] if story else None,
                    )
                    return

        # ux-patch-5: обрывок Песни / событие — ВНУТРЬ сообщения исследования
        # (~50%), отдельным сообщением больше не шлём.
        fragment = flavor.explore_fragment(world._rng)
        if fragment is not None and fragment.song_index is not None:
            # патч 25, п.6: отмечаем обрывок увиденным для прогресса Песни
            await song_service.record_seen(db, character, fragment.song_index)
            await db.commit()

    # патч 25, п.4: несобранная горстка пепла сгорает при новом исследовании
    ash_burned = ash_handful_state.clear(peer_id)
    delay = world._rng.uniform(wc.EXPLORE_SECONDS_MIN, wc.EXPLORE_SECONDS_MAX)
    await explore_rest.start(explore_rest.EXPLORE, peer_id, delay)
    # Кнопки убираем до появления моба.
    text = "🔍 Ты осматриваешься вокруг..."
    if ash_burned:
        text = f"{ASH_BURNED_LINE}\n\n{text}"
    if fragment is not None:
        text += f"\n\n{fragment.text}"
    await message.answer(text, keyboard=kb.waiting_keyboard())
    world._explore_scheduler.schedule(peer_id, delay)


QUEUE_READY_HINT = "👥 Все, кто остался на клетке, готовы - нажми «🔍 Исследовать», чтобы начать."


async def ready_hint_peers(db, character_ids: set[int]) -> list[int]:
    """Кому сказать «нажми ещё раз»: очередь собралась без ушедшего, но сама
    по себе не стартует - старт идёт от нажатия."""
    peers = [await onboarding_svc.vk_id_for_character(db, cid) for cid in character_ids]
    return [p for p in peers if p is not None]


async def send_ready_hint(peer_ids: list[int]) -> None:
    for their_peer_id in peer_ids:
        try:
            await world._bot_api.messages.send(peer_id=their_peer_id, message=QUEUE_READY_HINT, random_id=0)
        except Exception:
            pass


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
        ready = group_explore_service.cancel(snapshot.id, character.id)
        hint_peers = await ready_hint_peers(db, ready)
        has_mount = await mount_service.has_any_mount(db, character.id)
    await message.answer(
        "Ты вышел из очереди исследования. Передумаешь - нажми «🔍 Исследовать» снова.",
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
    )
    await send_ready_hint(hint_peers)


@labeler.message(text=[kb.BTN_ASH_HANDFUL])
async def collect_ash_handful(message: Message) -> None:
    """Патч 25, п.4: сбор одноразовой находки — устаревшая кнопка (уже
    собрано/сгорело при следующем «Исследовать») молча игнорируется."""
    peer_id = message.peer_id
    if not ash_handful_state.is_pending(peer_id):
        # Кнопка живёт в чате и после «Исследовать» остаётся видна - ответить,
        # а не молчать.
        await message.answer(ASH_BURNED_LINE)
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        # Ушёл с клетки - горстка осталась там (2026-10-24).
        if not ash_handful_state.is_here(peer_id, (character.pos_x, character.pos_y)):
            ash_handful_state.clear(peer_id)
            await message.answer(ASH_BURNED_LINE)
            return
        stats = await world._get_stats(db, character.id)
        result = await ash_service.collect(db, character, stats, world._rng)
        ash_handful_state.clear(peer_id)
        has_mount = await mount_service.has_any_mount(db, character.id)
        await db.commit()

    text = "У ног - горстка пепла, слишком плотная для простой золы. В ней блестит."
    xp_line = display.xp_delta_line(result.xp, premium=result.xp_premium_applied)
    if xp_line:  # на 60 уровне опыта нет - и строки нет
        text += "\n\n" + xp_line
    drop_line = trophy_service.format_drop_line(result.trophies, source="ash_handful")
    if drop_line is not None:
        text += f"\n{drop_line}"
    if result.item is not None:
        text += f"\n\n{item_service.format_drop_announcement(result.item)}"
    if result.raid_key_dropped:
        text += f"\n{raid_key_texts.raid_key_drop_line()}"
    if result.group_kick is not None and result.group_kick.kicked_character_id == character.id:
        text += f"\n\n{group_texts.level_gap_kick_self_line()}"
    # Сводку локации заново не шлём: игрок на той же клетке, она только что
    # была выше (2026-10-13). Клавиатура карты остаётся рабочей.
    await message.answer(
        text, keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
    )
    await stats_window.notify_levelup(peer_id, result.levels_gained, result.new_level)
    await group_texts.notify_group_kick(world._bot_api, result.group_kick)


async def handle_explore_done(peer_id: int) -> None:
    """Колбэк планировщика: исследование закончено — два исхода (патч 13, ч.3):
    50% бой, 50% событие с выбором (событие всегда даёт результат, патч 10).
    Флейвор (Песнь/замечания) больше не бывает самостоятельным исходом — он
    остался только внутри сообщения ожидания "Ты осматриваешься..." (patch-5),
    которое уже показано раньше и не пересекается с этим исходом."""
    await explore_rest.stop(explore_rest.EXPLORE, peer_id)
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
        stats = await world._get_stats(db, character.id)

        outcome_kind = "combat" if world._rng.random() < wc.EXPLORE_COMBAT_CHANCE else "event"
        # Патч 110: след события обрывается на этой клетке - вместо обычного
        # исхода его финал. Событие со сценами - средний/глубокий слой.
        scene_event = None
        scene_mult = 1.0
        trail = await scene_event_service.take_trail_here(db, character)
        if trail is not None:
            trail_def = scene_events.content().trails.get(trail.kind)
            scene_event = scene_events.event_by_id(trail_def.finale) if trail_def else None
            scene_mult = scene_events.trail_reward_mult(trail.cells)
        elif outcome_kind == "event":
            tier = scene_events.roll_tier(world._rng)
            if tier != "light":
                live_trail = await scene_event_service.get_trail(db, character.id)
                scene_event = scene_events.pick_event(
                    world._rng, tier, grid.ring_tier(character.pos_x, character.pos_y),
                    region_for(character.pos_x, character.pos_y), character.level,
                    no_trails=live_trail is not None and scene_event_service.trail_alive(live_trail),
                )
        if scene_event is not None:
            outcome_kind = "scene"
        # Патч 59: завершённое исследование ЛЮБОГО игрока подбрасывает руду в
        # случайный неполный рудник. Рудники — общий ресурс, который наполняет
        # активность всего сервера, а не персональный кран.
        await mining_service.spawn_ore(db, world._rng)
        # 2026-10-21: и траву - на случайную клетку карты, не на эту.
        await herb_service.spawn(db, world._rng, (character.pos_x, character.pos_y))
        # Патч 104: тот же принцип для мировых боссов - счётчик наполняет
        # активность всего сервера.
        new_boss = await world_boss_service.record_exploration(db, world._rng)
        # Разломы: тот же счётчик активности, но без объявления.
        await rift_service.record_exploration(db, world._rng)
        daily_progress = await daily_service.record_exploration(db, character)
        guild_outcome = await guild_territory_service.on_exploration(db, character)
        await db.commit()
        if new_boss is not None:
            world_boss_handlers.on_spawned(new_boss.id)
        await guild_handlers.after_exploration(peer_id, character, guild_outcome)
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await scene_event_service.solo_modifiers(
            db, character, await preset_service.resolve_active_modifiers(db, character),
        )

        event = None
        song_can_read = False
        fish_offer = None
        empty_fisher = False
        summary_bits = None
        if outcome_kind == "event":
            event = event_pool.random_event(world._rng)
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
                    multiplier = world._roll_fish_offer_multiplier(character)
                    fish_offer = world._FishOffer(
                        multiplier=multiplier,
                        gold=await fishing_service.bag_value(
                            db, character.id, multiplier,
                            game_fishing.ring_tier(character.pos_x, character.pos_y),
                        ),
                        weight_label=game_fishing.format_kg(bag_grams),
                    )
            if event.id == "ash_altar":
                # патч 25, п.6: доп. выбор «Прочесть Песнь», только если собрана
                song_can_read = await song_service.can_read(db, character.id)

    notice = dailies_texts.progress_notice(daily_progress)
    if notice:
        await world._bot_api.messages.send(peer_id=peer_id, message=notice, random_id=0)
    for c in daily_progress.completed:
        await stats_window.notify_levelup(peer_id, c.levels_gained, c.new_level)

    if outcome_kind == "combat":
        # В зоне цели сюжетного шага первый же бой - его враг (2026-10-11).
        async with get_session_factory()() as story_db:
            quest = await world.story_fight_quest(story_db, character)
        if quest is not None:
            if quest.arrival_text:
                await world._bot_api.messages.send(
                    peer_id=peer_id, message=story_service.format_text(quest.arrival_text, character), random_id=0,
                )
            await combat_handlers.start_story_encounter(
                peer_id, character, stats, gear_bonus, buff_modifiers,
                quest.id, quest.chain_length, world._story_enemy(quest, character, combat_handlers.MOB_ID),
            )
            return
        await combat_handlers.start_encounter(peer_id, character, stats, gear_bonus, buff_modifiers)
        return

    if outcome_kind == "scene":
        await world._drop_pending_event(peer_id)
        await scene_event_handlers.start(peer_id, scene_event, scene_mult)
        return
    scene_event_handlers.cancel(peer_id)

    if event is not None and event.ore_vein:
        # У жилы нет выбора: либо берёшься за кирку, либо уходишь. Сначала
        # сводка локации (она возвращает рабочую нижнюю клавиатуру), сверху —
        # отдельное инлайн-сообщение с кнопкой добычи.
        farm_currency, donate_currency, quest_line, group_block, has_mount = summary_bits
        await world._bot_api.messages.send(
            peer_id=peer_id,
            message=world._map_text(character, stats, farm_currency, gear_bonus,
                              quest_line, donate_currency, group_block),
            random_id=0, attachment=location_attachment(character),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id,
                                          has_mount=has_mount),
        )
        vein_token = f"{random.getrandbits(48):x}"
        await pending_activity.offer_vein(peer_id, vein_token, (character.pos_x, character.pos_y))
        await world._bot_api.messages.send(
            peer_id=peer_id,
            message=f"{event.title}" + chr(10) * 2 + event.text,
            random_id=0,
            attachment=event_attachment(event.id),
            keyboard=mining_kb.event_vein_keyboard(event.id, vein_token),
        )
        from bot.handlers import herbs as herb_handlers  # цикл импортов

        await herb_handlers.notify(peer_id, character)
        return

    if empty_fisher:
        farm_currency, donate_currency, quest_line, group_block, has_mount = summary_bits
        await world._bot_api.messages.send(
            peer_id=peer_id,
            message=f"{event.title}" + chr(10) * 2 + event.empty_text,
            random_id=0, attachment=event_attachment(event.id),
        )
        await world._bot_api.messages.send(
            peer_id=peer_id,
            message=world._map_text(character, stats, farm_currency, gear_bonus,
                              quest_line, donate_currency, group_block),
            random_id=0, attachment=location_attachment(character),
            keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id,
                                          has_mount=has_mount),
        )
        from bot.handlers import herbs as herb_handlers  # цикл импортов

        await herb_handlers.notify(peer_id, character)
        return

    world._pending_events[peer_id] = event.id
    body = event.text
    if fish_offer is not None:
        # Цена принадлежит ЭТОМУ показу события: запоминаем ровно ту,
        # которую сейчас увидит игрок, и по ней потом и продаём.
        world._pending_fish_offers[peer_id] = fish_offer.multiplier
        body = body.format(gold=fish_offer.gold, weight=fish_offer.weight_label)
    await pending_activity.remember_event(
        peer_id, event.id, fish_offer.multiplier if fish_offer is not None else None,
    )
    text = f"{event.title}" + chr(10) * 2 + body
    await world._bot_api.messages.send(
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
    pending_event_id = await world._pending_event_id(peer_id)
    if pending_event_id is None:
        return
    payload = message.get_payload_json() or {}
    if payload.get("event") != pending_event_id:
        return
    event = event_pool.event_by_id(pending_event_id)
    choice_idx = payload.get("choice")
    if event is None or not isinstance(choice_idx, int) or not (0 <= choice_idx < len(event.choices)):
        return
    fish_multiplier = world._pending_fish_offers.get(peer_id)
    await world._drop_pending_event(peer_id)

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        stats = await world._get_stats(db, character.id)
        outcome = event_service.pick_outcome(world._rng, event.choices[choice_idx].outcomes)
        choice_label = event.choices[choice_idx].label
        fish_sale_line = None
        fish_sold = None
        if outcome.fish_buyer:
            # Продаём по цене, ПОКАЗАННОЙ игроку. Если множителя нет (бот
            # перезапустился между показом и ответом), сделка не состоится:
            # взять цену заново значило бы продать не по той, что обещали.
            if fish_multiplier is None:
                await message.answer(
                    "Рыбак уже ушёл - и с ним его цена."
                )
                return
            gold, grams = await fishing_service.sell_bag(
                db, character, fish_multiplier, game_fishing.ring_tier(character.pos_x, character.pos_y),
            )
            fish_sold = gold > 0
            if gold:
                fish_sale_line = (
                    f"🧺 Продано {game_fishing.format_kg(grams)} рыбы за "
                    f"{guild_service.gold_label(character, gold, 'зол.')}"
                )
        choice_code = trial_service.EVENT_CHOICE_CODES.get(choice_label)
        result = await event_service.apply_outcome(
            db, character, stats, outcome, world._rng, event_id=event.id, choice_code=choice_code,
            fish_sold=fish_sold,
        )
        wallet = await wallet_service.get_wallet(db, character.id)
        farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await scene_event_service.solo_modifiers(
            db, character, await preset_service.resolve_active_modifiers(db, character),
        )
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
    tithe_line = guild_handlers.take_tithe_line(peer_id)
    if tithe_line:
        result_text += f"\n{tithe_line}"
    if result.group_kick is not None and result.group_kick.kicked_character_id == character.id:
        result_text += f"\n\n{group_texts.level_gap_kick_self_line()}"
    await message.answer(result_text, keyboard=kb.waiting_keyboard())
    # патч 14, ч.2.3: событие — тоже источник опыта, левелап не должен теряться
    await stats_window.notify_levelup(peer_id, result.levels_gained, result.new_level)
    await group_texts.notify_group_kick(world._bot_api, result.group_kick)
    daily_notice = dailies_texts.progress_notice_from(result.daily_completed, result.daily_streak_notice)
    if daily_notice:
        await message.answer(daily_notice)
    for c in result.daily_completed:
        await stats_window.notify_levelup(peer_id, c.levels_gained, c.new_level)
        await group_texts.notify_group_kick(world._bot_api, c.group_kick)
    if ash_service.roll_appears(world._rng):
        ash_handful_state.mark(peer_id, (character.pos_x, character.pos_y))
    await message.answer(
        world._map_text(character, stats, farm_currency, gear_bonus, quest_line, donate_currency, group_block),
        attachment=location_attachment(character),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=has_mount),
    )
    if ash_handful_state.is_pending(peer_id):
        await message.answer(kb.ASH_OFFER_TEXT, keyboard=kb.ash_handful_keyboard())
    await world._maybe_send_monolith_button(peer_id, character)
    from bot.handlers import herbs as herb_handlers  # цикл импортов

    await herb_handlers.notify(peer_id, character)


SONG_READ_SCENE = (
    "Ты читаешь Песнь целиком, от первой строки до последней. Целиком её не читали много лет.\n\n"
    "Пепел вокруг алтаря поднимается столбом, густеет, и на месте золы встаёт конь из пепла "
    "и багрового света. Он не дышит, бьёт копытом и ждёт седока.\n\n"
    "Хранитель Списков вписал тебе звание."
)


@labeler.message(payload_contains={"type": "read_song"})
async def read_song(message: Message) -> None:
    """Патч 25, п.6: доп. выбор у Пепельного алтаря — только если Песнь
    собрана полностью и ещё не прочитана (устаревшее нажатие игнорируется)."""
    peer_id = message.peer_id
    pending_event_id = await world._pending_event_id(peer_id)
    if pending_event_id != "ash_altar":
        return
    await world._drop_pending_event(peer_id)

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        if not await song_service.can_read(db, character.id):
            return
        await song_service.read_song(db, character)
        stats = await world._get_stats(db, character.id)
        wallet = await wallet_service.get_wallet(db, character.id)
        farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        quest_line = await story_service.quest_summary_line(db, character)
        group_block = await group_texts.group_summary_block(db, character.id)
        await db.commit()

    await message.answer(SONG_READ_SCENE, keyboard=kb.waiting_keyboard())
    await message.answer(
        world._map_text(character, stats, farm_currency, gear_bonus, quest_line, donate_currency, group_block),
        attachment=location_attachment(character),
        keyboard=kb.movement_keyboard(character.pos_x, character.pos_y, peer_id, has_mount=True),
    )
    await world._maybe_send_monolith_button(peer_id, character)
