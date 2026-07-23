"""PvE-бой поверх tick_engine: атака, навыки класса (КД в ходах), побег, предмет.

Активная встреча — запись в TickEngine.sessions с ключом vk_id (один игрок —
одна одновременная встреча). PLAYER_ID/MOB_ID фиксированы: в сессии всегда
ровно два участника. Класс игрока для боевой клавиатуры — в _encounter_class.
"""

import random

from vkbottle import BaseStateGroup  # noqa: F401  (совместимость импортов)
from vkbottle.bot import BotLabeler, Message

from bot.keyboards.world import (
    BTN_ATTACK,
    BTN_FLEE,
    BTN_ITEM,
    combat_keyboard,
    empty_keyboard,
    movement_keyboard,
)
from bot.onboarding_texts import REGION_TITLES
from game.combat import balance_config as bc
from game.combat import display
from game.combat.base_skills import BASE_SKILL_DEFS
from game.combat.resolver import TickResult
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    Stats,
    build_combatant,
)
from game.combat.tick_engine import TickEngine
from bot.world_summary import location_summary
from game.world import encounters
from game.world import flavor as world_flavor
from services import encounter_service, trophy_service, vitals_service, wallet_service
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
# колбэк смерти игрока (world.on_player_defeat): убрать кнопки, текст, запустить респавн
on_defeat_hook = None

PLAYER_ID = 1
MOB_ID = 2

FLEE_SUCCESS_CHANCE = 0.5


def setup(engine: TickEngine, bot_api) -> None:
    global _engine, _bot_api
    _engine = engine
    _bot_api = bot_api


def has_active_encounter(peer_id: int) -> bool:
    return peer_id in _engine.sessions


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
        vitals_service.set_hp(character, stats, hp)
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


async def start_encounter(peer_id: int, character, char_stats) -> None:
    stats = Stats(
        strength=char_stats.strength,
        agility=char_stats.agility,
        intellect=char_stats.intellect,
        vitality=char_stats.vitality,
        will=char_stats.will,
    )
    primary = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    player = build_combatant(
        id=PLAYER_ID, side=0, kind="character", name=character.name,
        level=character.level, stats=stats, primary_stat=primary,
        subclass_id=character.subclass,
    )
    # HP переносится между боями (отдых/респавн лечат) — не всегда полное
    player.current_hp = vitals_service.current_hp(character, char_stats)
    # уровень моба клампится под игрока в диапазон зоны (world-patch-1)
    encounter = encounters.spawn_mob(MOB_ID, character.region, character.level, _rng)
    state = CombatSessionState(session_id=peer_id, mode=CombatMode.PVE)
    state.add(player)
    state.add(encounter.combatant)
    _encounter_class[peer_id] = character.base_class
    _encounter_mob_level[peer_id] = encounter.combatant.level
    _last_player_hp[peer_id] = player.current_hp
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


async def on_tick_resolved(session_id: int, tick: int, result: TickResult) -> None:
    state = _engine.sessions.get(session_id)
    if state is None:
        return  # бой уже завершён этим ходом — сообщение отправит on_battle_finished
    _last_player_hp[session_id] = state.combatants[PLAYER_ID].current_hp
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

        if result.winner_side == 0:  # игрок выиграл — сохраняем остаток HP
            if final_hp is not None:
                vitals_service.set_hp(character, stats, final_hp)
            outcome = await encounter_service.resolve_victory(db, character, mob_level, _rng)
            farm_currency = (await wallet_service.get_wallet(db, character.id)).farm_currency
            await db.commit()
            new_level = outcome.new_level
            levels = outcome.levels_gained
        else:  # моб выиграл или ничья — смерть игрока (авто-респавн по таймеру)
            defeat = await encounter_service.resolve_defeat(db, character)
            await db.commit()
            respawn_at = character.respawn_at
            xp_lost = defeat.xp_lost

    if result.winner_side == 0:
        # ux-patch-5: финальное сообщение цикла — итоги боя + сводка локации со
        # шкалой опыта, к ней прикреплены кнопки следующего действия.
        text = "🏆 Победа! Тварь оседает пеплом."
        drop_line = trophy_service.format_drop_line(outcome.trophies_gained)
        if drop_line is not None:
            text += f"\n{drop_line}"
        if outcome.quest_progress is not None:
            text += f"\n📜 {outcome.quest_label}: {outcome.quest_progress}/{outcome.quest_target}"
            if outcome.quest_ready:
                text += "\nВозвращайся к наставнику."
        # лорный левелап (может быть несколько уровней за раз)
        if levels > 0:
            text += "\n\n" + world_flavor.levelup_line(new_level, _rng)
        text += "\n\n" + location_summary(character, _rng, farm_currency)
        await _bot_api.messages.send(
            peer_id=peer_id, message=text, random_id=0, keyboard=movement_keyboard()
        )
    elif on_defeat_hook is not None:
        # смерть: убрать кнопки, атмосферный текст (+ штраф опыта); респавн — автоматически
        await on_defeat_hook(peer_id, respawn_at, xp_lost)


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
    if not has_active_encounter(message.peer_id):
        return
    await message.answer("🎒 В сумке пусто.")


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
        await message.answer("🏃 Ты срываешься прочь — и темнота глотает твой след.",
                             keyboard=movement_keyboard())
        return
    await message.answer("🏃 Уйти не вышло — оно снова между тобой и спасением.")
    try:
        await _engine.declare_action(
            message.peer_id, PLAYER_ID, DeclaredAction(type=ActionType.SKIP)
        )
    except (KeyError, ValueError):
        pass
