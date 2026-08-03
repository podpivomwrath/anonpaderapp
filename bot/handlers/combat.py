"""PvE-бой поверх tick_engine: атака, навыки класса (КД в ходах), побег, предмет.

Активная встреча — запись в TickEngine.sessions с ключом vk_id (один игрок —
одна одновременная встреча). PLAYER_ID/MOB_ID фиксированы: в сессии всегда
ровно два участника. Класс игрока для боевой клавиатуры — в _encounter_class.
"""

import random

from vkbottle import BaseStateGroup  # noqa: F401  (совместимость импортов)
from vkbottle.bot import BotLabeler, Message

from bot import dailies_texts, editable_message
from bot.handlers import stats_window
from bot.keyboards.combat_items import combat_items_keyboard
from bot.keyboards.items import item_choice_keyboard, no_keyboard
from bot.keyboards.world import (
    BTN_ATTACK,
    BTN_FLEE,
    BTN_ITEM,
    combat_keyboard,
    empty_keyboard,
    movement_keyboard,
    waiting_keyboard,
)
from bot.onboarding_texts import REGION_TITLES
from bot.vk_media import photo_attachment
from bot.world_texts import mentor_name
from game.combat import balance_config as bc
from game.combat import display
from game.combat import elixir_effects
from game.combat.base_skills import BASE_SKILL_DEFS
from game.combat.battle_report import BattleTracker
from game.combat import formulas
from game.combat.resolver import TickResult
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
    Stats,
    build_combatant,
)
from game.combat.tick_engine import TickEngine
from bot.world_summary import location_summary
from game.economy import elixir_config as ec
from game.world import encounters, grid
from game.world import flavor as world_flavor
from services import (
    elixir_service,
    encounter_service,
    item_service,
    preset_service,
    story_service,
    trial_service,
    trophy_service,
    vitals_service,
    wallet_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_engine: TickEngine | None = None
_bot_api = None
_rng = random.Random()

# peer_id -> base_class игрока (для отрисовки боевой клавиатуры)
_encounter_class: dict[int, str] = {}
# peer_id -> текущее HP игрока (обновляется каждый ход, для сохранения после боя)
_last_player_hp: dict[int, int] = {}
# peer_id -> уровень моба текущей встречи (для опыта за килл)
_encounter_mob_level: dict[int, int] = {}
# peer_id -> id предмета, ожидающего решения Надеть/В инвентарь (патч 11, блок 2)
_pending_item_choice: dict[int, int] = {}
# peer_id -> сводка текущего боя для трекера классовых испытаний (патч 12)
_battle_trackers: dict[int, BattleTracker] = {}
# peer_id -> (quest_id, оставшихся боёв в цепочке) для сюжетных встреч (патч 18)
_story_encounter: dict[int, tuple[str, int]] = {}
# колбэк смерти игрока (world.on_player_defeat): убрать кнопки, текст, запустить респавн
on_defeat_hook = None

PLAYER_ID = 1
MOB_ID = 2

FLEE_SUCCESS_CHANCE = 0.5

VICTORY_PHOTO_ID = "457239033"  # иллюстрация победы над мобом (альбом группы VK)


def setup(engine: TickEngine, bot_api) -> None:
    global _engine, _bot_api
    _engine = engine
    _bot_api = bot_api


def has_active_encounter(peer_id: int) -> bool:
    return peer_id in _engine.sessions


async def _get_position(peer_id: int) -> tuple[int, int]:
    """Текущая позиция игрока — для клавиатуры карты после побега (патч 17)."""
    from services.onboarding_service import get_character

    async with get_session_factory()() as db:
        character = await get_character(db, peer_id)
    return (character.pos_x, character.pos_y) if character is not None else (0, 0)


async def _persist_hp(peer_id: int, hp: int) -> None:
    """Сохранить текущее HP игрока в БД (после боя/побега)."""
    from sqlalchemy import select

    from models import CharacterStats
    from services.onboarding_service import get_character

    sf = get_session_factory()
    async with sf() as db:
        character = await get_character(db, peer_id)
        if character is None:
            return
        stats = await db.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
        vitals_service.set_hp(character, stats, hp, vit_bonus)
        await db.commit()


def _combat_kb(state: CombatSessionState, peer_id: int) -> str:
    base_class = _encounter_class.get(peer_id, "warrior")
    player = state.combatants[PLAYER_ID]
    return combat_keyboard(base_class, player.cooldowns)


def _render(state: CombatSessionState, lines: list[str]) -> str:
    player = state.combatants[PLAYER_ID]
    mob = state.combatants[MOB_ID]
    header = f"⚔️ БОЙ — ход {state.tick_number}"
    mob_line = f"{mob.name}: {display.health_bar(mob.current_hp, mob.max_hp)}"
    player_line = f"Ты: {display.health_bar(player.current_hp, player.max_hp)} [{player.name}]"
    log = " ".join(lines) if lines else "Перед тобой враг. Действуй."
    return f"{header}\n{mob_line}\n{player_line}\n\n{log}"


async def start_encounter(
    peer_id: int, character, char_stats, gear_bonus: dict[str, int] | None = None,
    buff_modifiers: dict[str, float] | None = None,
    forced_encounter: encounters.Encounter | None = None,
) -> None:
    """gear_bonus (патч 11, блок 2) — сумма статов надетой экипировки,
    прибавляется к собственным статам ДО построения боевого участника.
    buff_modifiers (патч 14, ч.3) — stat_modifiers активного пресета баффов.
    forced_encounter (патч 18) — сюжетный named-враг вместо случайного спавна
    (см. start_story_encounter); обычный поток вызывает без этого аргумента."""
    bonus = gear_bonus or {}
    stats = Stats(
        strength=char_stats.strength + bonus.get("str", 0),
        agility=char_stats.agility + bonus.get("agi", 0),
        intellect=char_stats.intellect + bonus.get("int", 0),
        vitality=char_stats.vitality + bonus.get("vit", 0),
        will=char_stats.will + bonus.get("wil", 0),
    )
    primary = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    player = build_combatant(
        id=PLAYER_ID, side=0, kind="character", name=character.name,
        level=character.level, stats=stats, primary_stat=primary,
        subclass_id=character.subclass, buff_modifiers=buff_modifiers,
    )
    # HP переносится между боями (отдых/респавн лечат) — не всегда полное
    player.current_hp = vitals_service.current_hp(character, char_stats, bonus.get("vit", 0))
    if forced_encounter is not None:
        encounter = forced_encounter
    else:
        # уровень моба клампится под игрока в диапазон зоны (world-patch-1);
        # кольцо бестиария — по ТЕКУЩЕЙ клетке игрока, не по домашнему региону (патч 15)
        dist = grid.chebyshev_distance(character.pos_x, character.pos_y)
        encounter = encounters.spawn_mob(MOB_ID, character.region, character.level, dist, _rng)
    state = CombatSessionState(session_id=peer_id, mode=CombatMode.PVE)
    state.add(player)
    state.add(encounter.combatant)
    _encounter_class[peer_id] = character.base_class
    _encounter_mob_level[peer_id] = encounter.combatant.level
    _last_player_hp[peer_id] = player.current_hp
    _battle_trackers[peer_id] = BattleTracker(
        PLAYER_ID, MOB_ID, encounter.combatant.level, player.max_hp, player.current_hp
    )
    if character.subclass is not None:
        async with get_session_factory()() as db:
            from services.onboarding_service import get_character  # избегаем цикла импортов

            fresh = await get_character(db, peer_id)
            if fresh is not None:
                await trial_service.record_combat_started(db, fresh)
                await db.commit()
    _engine.start_session(state)
    # флейвор моба перед боем + боевой интерфейс
    await _bot_api.messages.send(
        peer_id=peer_id,
        message=f"⚠️ {encounter.combatant.name}\n\n{encounter.flavor}",
        random_id=0,
    )
    await _bot_api.messages.send(
        peer_id=peer_id, message=_render(state, []), random_id=0,
        keyboard=_combat_kb(state, peer_id),
    )


async def start_story_encounter(
    peer_id: int, character, char_stats, gear_bonus, buff_modifiers,
    quest_id: str, chain_remaining: int, encounter: encounters.Encounter,
) -> None:
    """Сюжетный бой (патч 18): named-враг (или рядовой преследователь на
    промежуточном шаге цепочки — квест 2.2 «Свидетель») вместо случайного
    спавна. on_battle_finished завершит квест (story_service.mark_ready)
    при победе в ПОСЛЕДНЕМ бою цепочки (chain_remaining, отсчёт с этого боя,
    доходит до 1); поражение просто сбрасывает цепочку — квест остаётся
    активным, триггер можно вызвать заново."""
    _story_encounter[peer_id] = (quest_id, chain_remaining)
    await start_encounter(
        peer_id, character, char_stats, gear_bonus, buff_modifiers, forced_encounter=encounter
    )


async def on_tick_resolved(session_id: int, tick: int, result: TickResult) -> None:
    state = _engine.sessions.get(session_id)
    if state is None:
        return  # бой уже завершён этим ходом — сообщение отправит on_battle_finished
    _last_player_hp[session_id] = state.combatants[PLAYER_ID].current_hp
    tracker = _battle_trackers.get(session_id)
    if tracker is not None:
        tracker.update(result, state.combatants[PLAYER_ID].current_hp, MOB_ID in result.deaths)
    # ux-patch-7: боевая клавиатура — ТОЛЬКО пока бой активен. На завершающем ходу
    # лог финального удара уходит без боевых кнопок (сводку/смерть с нужной
    # клавиатурой пришлёт on_battle_finished) — иначе кнопки боя мелькают.
    keyboard = empty_keyboard() if result.finished else _combat_kb(state, session_id)
    await _bot_api.messages.send(
        peer_id=session_id, message=_render(state, result.lines), random_id=0,
        keyboard=keyboard,
    )


async def on_battle_finished(session_id: int, result: TickResult) -> None:
    peer_id = session_id
    _encounter_class.pop(peer_id, None)
    mob_level = _encounter_mob_level.pop(peer_id, 1)
    final_hp = _last_player_hp.pop(peer_id, None)
    tracker = _battle_trackers.pop(peer_id, None)
    story_state = _story_encounter.pop(peer_id, None)  # (quest_id, остаток цепочки), патч 18
    battle_report = tracker.finalize(result.winner_side == 0) if tracker is not None else None
    sf = get_session_factory()
    async with sf() as db:
        from services.onboarding_service import get_character  # избегаем цикла импортов
        from sqlalchemy import select
        from models import CharacterStats

        character = await get_character(db, peer_id)
        if character is None:
            return
        stats = await db.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        vit_bonus = gear_bonus.get("vit", 0)

        if result.winner_side == 0:  # игрок выиграл — сохраняем остаток HP
            if final_hp is not None:
                vitals_service.set_hp(character, stats, final_hp, vit_bonus)
            outcome = await encounter_service.resolve_victory(
                db, character, mob_level, _rng, battle_report
            )
            old_item = None
            if outcome.item_dropped is not None:
                # старый предмет в этом слоте — для окна сравнения (ещё ДО коммита,
                # grant_from_kill только добавил новый в инвентарь, не экипировал)
                equipped = await item_service.get_equipped(db, character.id)
                old_item = equipped[outcome.item_dropped.slot]
            wallet = await wallet_service.get_wallet(db, character.id)
            farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
            quest_ready_now = story_state is not None and story_state[1] <= 1
            if quest_ready_now:
                # последний бой цепочки (или обычный одиночный сюжетный бой) —
                # цель достигнута, ждём разговора с наставником
                await story_service.mark_ready(db, character, story_state[0])
            await db.commit()
            new_level = outcome.new_level
            levels = outcome.levels_gained
            buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
            quest_line = await story_service.quest_summary_line(db, character)
        else:  # моб выиграл или ничья — смерть игрока (авто-респавн по таймеру)
            defeat = await encounter_service.resolve_defeat(db, character)
            await db.commit()
            respawn_at = character.respawn_at
            xp_lost = defeat.xp_lost

    if result.winner_side == 0 and story_state is not None and story_state[1] > 1:
        # эскорт (патч 18, квест «Свидетель»): ещё не последний бой цепочки —
        # короткое продолжение, СРАЗУ следующий бой, без сводки локации/итогов
        quest_id, remaining = story_state
        await _bot_api.messages.send(
            peer_id=peer_id,
            message="Один повержен — но погоня не отступает. Ещё один бросается наперерез.",
            random_id=0,
        )
        dist = grid.chebyshev_distance(character.pos_x, character.pos_y)
        next_encounter = encounters.spawn_mob(MOB_ID, character.region, character.level, dist, _rng)
        await start_story_encounter(
            peer_id, character, stats, gear_bonus, buff_modifiers, quest_id, remaining - 1, next_encounter,
        )
        return

    if result.winner_side == 0:
        # ux-patch-10 п.1: итоги боя — отдельное сообщение, сводка локации —
        # ВСЕГДА отдельным вторым сообщением, с кнопками следующего действия.
        text = "🏆 Победа! Тварь оседает пеплом."
        text += f"\n{display.xp_delta_line(outcome.xp_gained)}"
        drop_line = trophy_service.format_drop_line(outcome.trophies_gained)
        if drop_line is not None:
            text += f"\n{drop_line}"
        if outcome.quest_progress is not None:
            text += f"\n📜 {outcome.quest_label}: {outcome.quest_progress}/{outcome.quest_target}"
            if outcome.quest_ready:
                text += "\nВозвращайся к наставнику."
        # лорный левелап (может быть несколько уровней за раз) + рост макс. HP
        if levels > 0:
            old_level = new_level - levels
            old_tier = formulas.tier_for_level(old_level)
            old_max_hp = round(
                formulas.hp(old_level, stats.vitality + vit_bonus, formulas.tier_multiplier(old_tier))
            )
            new_max_hp = vitals_service.max_hp(character, stats, vit_bonus)
            text += "\n\n" + world_flavor.levelup_line(new_level, _rng)
            text += f"\n{display.max_hp_delta_line(old_max_hp, new_max_hp)}"
        await _bot_api.messages.send(
            peer_id=peer_id, message=text, random_id=0,
            attachment=photo_attachment(VICTORY_PHOTO_ID),
            keyboard=waiting_keyboard(),
        )

        # патч 14, ч.2.3: единая точка входа для левелапа — все источники опыта
        # (килл, квест, событие) зовут одну и ту же notify_levelup.
        await stats_window.notify_levelup(peer_id, levels, new_level)

        for buff_id in outcome.unlocked_buffs:
            # патч 12: испытание завершено — микробафф открыт навсегда
            await _bot_api.messages.send(
                peer_id=peer_id,
                message=f"📖 Испытание пройдено. Открыт бафф: {trial_service.buff_name(buff_id)}.",
                random_id=0,
            )

        daily_notice = dailies_texts.progress_notice_from(outcome.daily_completed, outcome.daily_streak_notice)
        if daily_notice:
            await _bot_api.messages.send(peer_id=peer_id, message=daily_notice, random_id=0)
        for c in outcome.daily_completed:
            await stats_window.notify_levelup(peer_id, c.levels_gained, c.new_level)

        if quest_ready_now:
            # патч 21, п.1: игрок не в разговоре с наставником — пингуем сами
            await _bot_api.messages.send(
                peer_id=peer_id,
                message=f"📜 {mentor_name(character.region)} ждёт тебя в городе.",
                random_id=0,
            )

        if outcome.item_dropped is not None:
            # ux-patch-11: окно сравнения — сводка локации откладывается до
            # решения игрока (Надеть/В инвентарь), как event_choice в патче 9.
            new_item = outcome.item_dropped
            _pending_item_choice[peer_id] = new_item.id
            announcement = item_service.format_drop_announcement(new_item)
            comparison = item_service.format_comparison(old_item, new_item)
            await editable_message.send_or_edit(
                _bot_api, "item_choice", peer_id, f"{announcement}\n\n{comparison}",
                item_choice_keyboard(new_item.id),
            )
            return

        await _bot_api.messages.send(
            peer_id=peer_id,
            message=location_summary(character, stats, _rng, farm_currency, vit_bonus, quest_line, donate_currency),
            random_id=0, keyboard=movement_keyboard(character.pos_x, character.pos_y),
        )
    elif on_defeat_hook is not None:
        # смерть: убрать кнопки, атмосферный текст (+ штраф опыта); респавн — автоматически
        await on_defeat_hook(peer_id, respawn_at, xp_lost)


@labeler.message(payload_contains={"type": "item_choice"})
async def item_choice(message: Message) -> None:
    """Ответ на окно сравнения (патч 11): payload несёт item_id — устаревшее
    нажатие (после уже разрешённого дропа) молча игнорируется, как event_choice."""
    peer_id = message.peer_id
    pending_item_id = _pending_item_choice.get(peer_id)
    if pending_item_id is None:
        return
    payload = message.get_payload_json() or {}
    if payload.get("item") != pending_item_id:
        return
    action = payload.get("action")
    if action not in ("equip", "keep"):
        return
    _pending_item_choice.pop(peer_id, None)

    async with get_session_factory()() as db:
        from services.onboarding_service import get_character  # избегаем цикла импортов
        from sqlalchemy import select
        from models import CharacterStats, Item

        character = await get_character(db, peer_id)
        if character is None:
            return
        stats = await db.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        if action == "equip":
            new_item = await db.get(Item, pending_item_id)
            old_item = await item_service.equip_item(db, character.id, pending_item_id)
            confirm_text = f"Надето. {item_service.stat_delta_line(old_item, new_item)}"
        else:
            confirm_text = "Убрано в инвентарь."
        wallet = await wallet_service.get_wallet(db, character.id)
        farm_currency, donate_currency = wallet.farm_currency, wallet.donate_currency
        vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
        quest_line = await story_service.quest_summary_line(db, character)
        await db.commit()

    # патч 13, ч.1: окно сравнения редактируется в финальный вид на месте;
    # ux-patch-10 п.1: сводка локации — всегда ОТДЕЛЬНОЕ следующее сообщение.
    await editable_message.send_or_edit(_bot_api, "item_choice", peer_id, confirm_text, no_keyboard())
    await message.answer(
        location_summary(character, stats, _rng, farm_currency, vit_bonus, quest_line, donate_currency),
        keyboard=movement_keyboard(character.pos_x, character.pos_y),
    )


# --- Действия игрока ---


@labeler.message(text=[BTN_ATTACK])
async def attack(message: Message) -> None:
    if not has_active_encounter(message.peer_id):
        return
    try:
        await _engine.declare_action(
            message.peer_id, PLAYER_ID, DeclaredAction(type=ActionType.ATTACK, target_id=MOB_ID)
        )
    except (KeyError, ValueError):
        pass


@labeler.message(payload_contains={"type": "skill"})
async def use_skill(message: Message) -> None:
    if not has_active_encounter(message.peer_id):
        return
    payload = message.get_payload_json() or {}
    skill_id = payload.get("id")
    if skill_id not in BASE_SKILL_DEFS:
        return
    state = _engine.sessions[message.peer_id]
    player = state.combatants[PLAYER_ID]
    if player.is_on_cooldown(skill_id):
        # нажатие на навык в КД — без траты хода
        cd = player.cooldowns.get(skill_id, 0)
        await message.answer(f"⏳ Навык ещё не готов (КД {cd}).")
        return
    try:
        await _engine.declare_action(
            message.peer_id, PLAYER_ID,
            DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=MOB_ID),
        )
    except (KeyError, ValueError):
        pass


@labeler.message(text=[BTN_ITEM])
async def use_item(message: Message) -> None:
    """Патч 16: список зелий/эликсиров с количеством. Под контролем — кнопка
    недоступна (ход и так пропускается); лимит эликсиров за бой — боевые
    просто не показываются в списке, с пояснением."""
    peer_id = message.peer_id
    if not has_active_encounter(peer_id):
        return
    state = _engine.sessions[peer_id]
    player = state.combatants[PLAYER_ID]
    if player.has_effect(EffectKind.FREEZE):
        await message.answer("Скован — не до зелий сейчас. ❄️")
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        stock = await elixir_service.get_stock(db, character.id)

    if not stock:
        await message.answer("🎒 В сумке пусто.")
        return

    limit_reached = player.combat_elixirs_used >= ec.ELIXIR_PER_BATTLE_LIMIT
    visible = [(d, count) for d, count in stock if d.category == "heal" or not limit_reached]
    text = "🎒 Что использовать?"
    if limit_reached and any(d.category == "combat" for d, _ in stock):
        text += "\n\nБольше твоё тело не выдержит за один бой — боевые эликсиры недоступны."
    await editable_message.send_or_edit(
        _bot_api, "combat_item", peer_id, text, combat_items_keyboard(visible)
    )


@labeler.message(payload_contains={"type": "use_item"})
async def use_combat_item(message: Message) -> None:
    peer_id = message.peer_id
    if not has_active_encounter(peer_id):
        return
    payload = message.get_payload_json() or {}
    elixir_id = payload.get("id")
    elixir = elixir_service.elixir_def(elixir_id) if isinstance(elixir_id, str) else None
    if elixir is None:
        return

    state = _engine.sessions[peer_id]
    player = state.combatants[PLAYER_ID]
    if player.has_effect(EffectKind.FREEZE):
        await message.answer("Скован — не до зелий сейчас. ❄️")
        return
    if elixir.category == "combat" and player.combat_elixirs_used >= ec.ELIXIR_PER_BATTLE_LIMIT:
        await message.answer("Больше твоё тело не выдержит за один бой.")
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        consumed = await elixir_service.consume(db, character.id, elixir_id)
        await db.commit()
    if not consumed:
        await message.answer("Этого зелья больше нет в сумке.")
        return

    await editable_message.send_or_edit(
        _bot_api, "combat_item", peer_id, f"Использовано: {elixir.emoji} {elixir.name}.", no_keyboard()
    )

    if elixir.category == "heal":
        # Лечебное зелье (патч 16) — тратит ход, как обычное действие
        try:
            await _engine.declare_action(
                peer_id, PLAYER_ID,
                DeclaredAction(type=ActionType.ITEM, item_id=elixir_id, target_id=PLAYER_ID),
            )
        except (KeyError, ValueError):
            pass
        return

    # Боевой эликсир (патч 16) — бесплатное действие: эффект накладывается
    # СРАЗУ, ход не тратится, игрок продолжает как обычно (атака/навык).
    line = elixir_effects.apply_combat_elixir(player, elixir_id)
    player.combat_elixirs_used += 1
    await _bot_api.messages.send(
        peer_id=peer_id, message=f"{line}\n\n{_render(state, [])}", random_id=0,
        keyboard=_combat_kb(state, peer_id),
    )


async def interrupt_for_pvp(peer_id: int) -> None:
    """Прерывает активный PvE-бой без наград/штрафа — жертву атаковали в
    открытом PvP (патч 22, п.3). HP на момент прерывания сохраняется в БД
    (тем же путём, что и обычный побег)."""
    if not has_active_encounter(peer_id):
        return
    hp = _engine.sessions[peer_id].combatants[PLAYER_ID].current_hp
    _engine.abort_session(peer_id)
    _encounter_class.pop(peer_id, None)
    _last_player_hp.pop(peer_id, None)
    _battle_trackers.pop(peer_id, None)
    await _persist_hp(peer_id, hp)


@labeler.message(text=[BTN_FLEE])
async def flee(message: Message) -> None:
    peer_id = message.peer_id
    if not has_active_encounter(peer_id):
        return
    if _rng.random() < FLEE_SUCCESS_CHANCE:
        # сохраняем остаток HP игрока перед выходом из боя
        hp = _engine.sessions[peer_id].combatants[PLAYER_ID].current_hp
        _engine.abort_session(peer_id)
        _encounter_class.pop(peer_id, None)
        _last_player_hp.pop(peer_id, None)
        await _persist_hp(peer_id, hp)
        pos_x, pos_y = await _get_position(peer_id)
        await message.answer("🏃 Ты срываешься прочь — и темнота глотает твой след.",
                             keyboard=movement_keyboard(pos_x, pos_y))
        return
    await message.answer("🏃 Уйти не вышло — оно снова между тобой и спасением.")
    try:
        await _engine.declare_action(
            message.peer_id, PLAYER_ID, DeclaredAction(type=ActionType.SKIP)
        )
    except (KeyError, ValueError):
        pass
