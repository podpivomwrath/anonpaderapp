"""Групповой PvE-бой (патч 51, ч.4) поверх ОБЩЕГО с соло-PvE tick_engine
(game/combat/tick_engine.py, mode=PVE, is_raid=True — тот же класс уже
документирует поддержку "PvE (соло/группа)"). Сессии — отдельное пространство
id (отрицательные, как battle_id в bot/handlers/pvp.py) от peer_id-сессий
соло-боя (bot/handlers/combat.py), чтобы не пересекаться в TickEngine.sessions.

Мобов столько же, сколько участников (1 к 1), уровень — по максимальному в
группе (services/group_combat_service.py::spawn_mobs). Резолв одновременный,
таймер хода 1 минута (не походил — пропуск, без вылета из боя — уже
реализовано в TickEngine через is_raid). Опыт делится пропорционально
уровню среди живых на момент гибели каждого моба; лут — независимый бросок
каждому (services/group_combat_service.py::reward_mob_kill)."""

import random
from dataclasses import dataclass, field

from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message

from bot import dailies_texts, editable_message, group_texts, raid_key_texts
from bot.handlers import respawn as respawn_handlers
from bot.handlers import stats_window
from bot.keyboards.group_combat import (
    BTN_GROUP_ATTACK,
    BTN_GROUP_ITEM,
    BTN_GROUP_TARGET,
    group_combat_keyboard,
    group_items_keyboard,
    group_target_keyboard,
    group_waiting_keyboard,
)
from bot.keyboards.items import no_keyboard
from bot.keyboards.world import movement_keyboard
from game.combat import balance_config as bc
from game.combat import battle_log, display, elixir_effects
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
from game.combat.skills import DEFENSIVE_SKILLS
from game.combat.tick_engine import TickEngine
from game.economy import elixir_config as ec
from models import Character, CharacterStats
from services import (
    daily_service,
    elixir_service,
    encounter_service,
    group_combat_service,
    item_service,
    mount_service,
    preset_service,
    quest_service,
    trophy_service,
    vitals_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_engine: TickEngine | None = None
_bot_api = None
_rng = random.Random()

_next_battle_id = -1


@dataclass
class Participant:
    character_id: int
    peer_id: int
    name: str
    base_class: str
    subclass_id: str | None


@dataclass
class GroupBattle:
    group_id: int
    participants: dict[int, Participant]  # character_id -> Participant
    mob_ids: set[int]
    last_combatants: dict[int, object] = field(default_factory=dict)


_battles: dict[int, GroupBattle] = {}
_peer_battle: dict[int, int] = {}
_declared_this_tick: dict[int, set[int]] = {}
_chosen_target: dict[int, int] = {}  # character_id -> mob_id
_active_group_ids: set[int] = set()  # группы, у которых сейчас идёт бой (bot/handlers/group_explore.py::is блокировка)


def is_group_fighting(group_id: int) -> bool:
    return group_id in _active_group_ids


@dataclass
class MemberCombatInput:
    character: Character
    stats: CharacterStats
    gear_bonus: dict[str, int]
    buff_modifiers: dict[str, float]
    peer_id: int


def setup(engine: TickEngine, bot_api) -> None:
    global _engine, _bot_api
    _engine = engine
    _bot_api = bot_api


def has_active_group_battle(peer_id: int) -> bool:
    return peer_id in _peer_battle


async def build_member_inputs(db, members: list[Character]) -> list[MemberCombatInput]:
    """Собирает всё нужное для постройки боевых участников — вызывающий код
    (bot/handlers/group_explore.py) уже держит db-сессию открытой в момент
    старта боя, поэтому здесь просто читаем, не открываем свою."""
    result = []
    for character in members:
        stats = await db.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
        peer_id = await onboarding_svc.vk_id_for_character(db, character.id)
        if peer_id is None:
            continue
        result.append(MemberCombatInput(character, stats, gear_bonus, buff_modifiers, peer_id))
    return result


async def start_group_encounter(
    group_id: int, members_input: list[MemberCombatInput], region: str, dist: int, rng: random.Random,
) -> None:
    global _next_battle_id
    battle_id = _next_battle_id
    _next_battle_id -= 1

    state = CombatSessionState(session_id=battle_id, mode=CombatMode.PVE, is_raid=True)
    participants: dict[int, Participant] = {}
    for m in members_input:
        bonus = m.gear_bonus
        stats = Stats(
            strength=m.stats.strength + bonus.get("str", 0),
            agility=m.stats.agility + bonus.get("agi", 0),
            intellect=m.stats.intellect + bonus.get("int", 0),
            vitality=m.stats.vitality + bonus.get("vit", 0),
            will=m.stats.will + bonus.get("wil", 0),
        )
        primary = bc.PRIMARY_STAT_BY_CLASS[m.character.base_class]
        combatant = build_combatant(
            id=m.character.id, side=0, kind="character", name=m.character.name,
            level=m.character.level, stats=stats, primary_stat=primary,
            subclass_id=m.character.subclass, buff_modifiers=m.buff_modifiers,
        )
        combatant.current_hp = vitals_service.current_hp(m.character, m.stats, bonus.get("vit", 0))
        state.add(combatant)
        participants[m.character.id] = Participant(
            character_id=m.character.id, peer_id=m.peer_id, name=m.character.name,
            base_class=m.character.base_class, subclass_id=m.character.subclass,
        )

    mob_encounters = group_combat_service.spawn_mobs(
        [m.character for m in members_input], region, dist, rng, start_id=10_000_000,
    )
    for enc in mob_encounters:
        state.add(enc.combatant)

    battle = GroupBattle(
        group_id=group_id, participants=participants,
        mob_ids={enc.combatant.id for enc in mob_encounters},
    )
    _battles[battle_id] = battle
    _active_group_ids.add(group_id)
    for p in participants.values():
        _peer_battle[p.peer_id] = battle_id
        enemies = list(battle.mob_ids)
        if enemies:
            _chosen_target[p.character_id] = enemies[0]

    _engine.start_session(state)

    mob_names = ", ".join(enc.combatant.name for enc in mob_encounters)
    flavor = mob_encounters[0].flavor if mob_encounters else ""
    for p in participants.values():
        await _bot_api.messages.send(
            peer_id=p.peer_id,
            message=f"⚠️ Группа входит в бой: {mob_names}\n\n{flavor}",
            random_id=0,
        )
    await _broadcast_board(battle_id, battle, None)


def _live_state(battle_id: int, battle: GroupBattle) -> dict:
    state = _engine.sessions.get(battle_id)
    if state is not None:
        battle.last_combatants = dict(state.combatants)
    return battle.last_combatants


def _character_id_for_peer(battle: GroupBattle, peer_id: int) -> int | None:
    for cid, p in battle.participants.items():
        if p.peer_id == peer_id:
            return cid
    return None


def _enemies_of(battle_id: int, battle: GroupBattle, cid: int) -> list[int]:
    combatants = _live_state(battle_id, battle)
    me = combatants.get(cid)
    if me is None:
        return []
    return [c.id for c in combatants.values() if c.side != me.side and c.alive]


def _default_enemy_target(battle_id: int, battle: GroupBattle, cid: int) -> int | None:
    enemies = _enemies_of(battle_id, battle, cid)
    return _rng.choice(enemies) if enemies else None


def _resolve_chosen_target(battle_id: int, battle: GroupBattle, cid: int) -> int | None:
    combatants = _live_state(battle_id, battle)
    target_id = _chosen_target.get(cid)
    target = combatants.get(target_id) if target_id is not None else None
    if target is not None and target.alive:
        return target_id
    fallback = _default_enemy_target(battle_id, battle, cid)
    if fallback is not None:
        _chosen_target[cid] = fallback
    return fallback


def _target_line(battle_id: int, battle: GroupBattle, cid: int) -> str:
    combatants = _live_state(battle_id, battle)
    target_id = _chosen_target.get(cid)
    target = combatants.get(target_id) if target_id is not None else None
    if target is None or not target.alive:
        return ""
    hp_pct = round(100 * target.current_hp / target.max_hp) if target.max_hp else 0
    return f"🎯 Цель: {target.name} ({hp_pct}% HP)"


def _render_board(state: CombatSessionState, result: TickResult | None = None) -> str:
    """Патч 51, ч.5: общий формат с соло-PvE (game/combat/battle_log.py) —
    "своя сторона"/"противник" + HP-полосы внизу. Игроки в групповом PvE
    всегда side=0, мобы side=1 — viewer_side=0 одинаков для всех участников."""
    return battle_log.render_tick(state, result or TickResult(), viewer_side=0)


async def _broadcast_board(
    battle_id: int, battle: GroupBattle, result: TickResult | None, notices: dict[int, str] | None = None,
) -> None:
    state = _engine.sessions.get(battle_id)
    text = _render_board(state, result) if state is not None else ""
    notices = notices or {}
    for cid, p in battle.participants.items():
        combatant = _live_state(battle_id, battle).get(cid)
        keyboard = (
            group_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id)
            if combatant is not None and combatant.alive
            else group_waiting_keyboard()
        )
        personal = text
        notice = notices.get(cid)
        if notice:
            personal = f"{notice}\n\n{personal}"
        target_line = _target_line(battle_id, battle, cid)
        if target_line and combatant is not None and combatant.alive:
            personal = f"{personal}\n{target_line}"
        await _bot_api.messages.send(peer_id=p.peer_id, message=personal, random_id=0, keyboard=keyboard)


@labeler.message(text=[BTN_GROUP_ATTACK])
async def group_attack(message: Message) -> None:
    await _group_action(message, DeclaredAction(type=ActionType.ATTACK))


@labeler.message(payload_contains={"type": "group_pve_skill"})
async def group_skill(message: Message) -> None:
    payload = message.get_payload_json() or {}
    skill_id = payload.get("id")
    if not isinstance(skill_id, str):
        return
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None:
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    if combatant is not None and combatant.is_on_cooldown(skill_id):
        cd = combatant.cooldowns.get(skill_id, 0)
        p = battle.participants.get(cid)
        keyboard = group_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id) if p else None
        await message.answer(f"⏳ Навык ещё не готов (КД {cd}).", keyboard=keyboard)
        return
    await _group_action(message, DeclaredAction(type=ActionType.SKILL, skill_id=skill_id))


async def _group_action(message: Message, action: DeclaredAction) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None:
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return

    is_defensive = action.type == ActionType.SKILL and action.skill_id in DEFENSIVE_SKILLS
    if not is_defensive:
        target = _resolve_chosen_target(battle_id, battle, cid)
        if target is None:
            return
        action = action.model_copy(update={"target_id": target})

    _declared_this_tick.setdefault(battle_id, set()).add(cid)
    try:
        await _engine.declare_action(battle_id, cid, action)
    except (KeyError, ValueError):
        _declared_this_tick.get(battle_id, set()).discard(cid)
        return
    if cid in _declared_this_tick.get(battle_id, set()):
        p = battle.participants.get(cid)
        if p is not None:
            await _bot_api.messages.send(
                peer_id=p.peer_id, message="✅ Действие принято. Ожидание остальных...",
                random_id=0, keyboard=group_waiting_keyboard(),
            )


# --- Выбор цели (бесплатное действие, как в массовом PvP патча 38) ---


@labeler.message(text=[BTN_GROUP_TARGET])
async def group_open_target(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None:
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    mob_ids = _enemies_of(battle_id, battle, cid)
    if not mob_ids:
        return
    combatants = _live_state(battle_id, battle)
    current_id = _chosen_target.get(cid)
    lines = ["🎯 Выбор цели", ""]
    for i, mob_id in enumerate(mob_ids, start=1):
        mob = combatants[mob_id]
        hp_pct = round(100 * mob.current_hp / mob.max_hp) if mob.max_hp else 0
        lines.append(f"{i}. {mob.name} · {hp_pct}% HP")
    lines.append("")
    current = combatants.get(current_id) if current_id is not None else None
    lines.append(f"Текущая цель: {current.name if current is not None else '—'}")
    await editable_message.send_or_edit(
        _bot_api, "group_pve_target", peer_id, "\n".join(lines), group_target_keyboard(mob_ids),
    )


@labeler.message(payload_contains={"type": "group_pve_target_pick"})
async def group_pick_target(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    target_id = payload.get("target")
    if not isinstance(target_id, int):
        return
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None:
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatants = _live_state(battle_id, battle)
    me = combatants.get(cid)
    target = combatants.get(target_id)
    if me is None or target is None or target.side == me.side or not target.alive:
        return
    _chosen_target[cid] = target_id
    p = battle.participants.get(cid)
    if p is None:
        return
    await editable_message.send_or_edit(
        _bot_api, "group_pve_target", peer_id, f"🎯 Новая цель: {target.name}.", no_keyboard(),
    )
    board = f"🎯 Цель: {target.name}.\n\n{_render_board(_engine.sessions.get(battle_id))}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=board, random_id=0,
        keyboard=group_combat_keyboard(p.base_class, me.cooldowns, subclass_id=p.subclass_id),
    )


@labeler.message(payload_contains={"type": "group_pve_target_back"})
async def group_target_back(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None:
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    p = battle.participants.get(cid)
    if combatant is None or p is None:
        return
    await editable_message.send_or_edit(_bot_api, "group_pve_target", peer_id, "Возврат в бой.", no_keyboard())
    await _bot_api.messages.send(
        peer_id=peer_id, message=_render_board(_engine.sessions.get(battle_id)), random_id=0,
        keyboard=group_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id),
    )


# --- Предметы в бою (лечебные тратят ход; боевые эликсиры — бесплатны, лимит/бой) ---


@labeler.message(text=[BTN_GROUP_ITEM])
async def group_open_items(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None:
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    p = battle.participants.get(cid)
    if combatant is None or p is None:
        return
    battle_kb = group_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id)
    if combatant.has_effect(EffectKind.FREEZE):
        await message.answer("Скован — не до зелий сейчас. ❄️", keyboard=battle_kb)
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        stock = await elixir_service.get_stock(db, character.id)

    if not stock:
        await message.answer("🎒 В сумке пусто.", keyboard=battle_kb)
        return

    limit_reached = combatant.combat_elixirs_used >= ec.ELIXIR_PER_BATTLE_LIMIT
    visible = [(d, count) for d, count in stock if d.category == "heal" or not limit_reached]
    text = "🎒 Что использовать?"
    if limit_reached and any(d.category == "combat" for d, _ in stock):
        text += "\n\nБольше твоё тело не выдержит за один бой — боевые эликсиры недоступны."
    await editable_message.send_or_edit(_bot_api, "group_pve_item", peer_id, text, group_items_keyboard(visible))


@labeler.message(payload_contains={"type": "group_pve_use_item"})
async def group_use_item(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None:
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    payload = message.get_payload_json() or {}
    elixir_id = payload.get("id")
    elixir = elixir_service.elixir_def(elixir_id) if isinstance(elixir_id, str) else None
    if elixir is None:
        return

    combatant = _live_state(battle_id, battle).get(cid)
    p = battle.participants.get(cid)
    if combatant is None or p is None:
        return
    battle_kb = group_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id)
    if combatant.has_effect(EffectKind.FREEZE):
        await message.answer("Скован — не до зелий сейчас. ❄️", keyboard=battle_kb)
        return
    if elixir.category == "combat" and combatant.combat_elixirs_used >= ec.ELIXIR_PER_BATTLE_LIMIT:
        await message.answer("Больше твоё тело не выдержит за один бой.", keyboard=battle_kb)
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        consumed = await elixir_service.consume(db, character.id, elixir_id)
        await db.commit()
    if not consumed:
        await message.answer("Этого зелья больше нет в сумке.", keyboard=battle_kb)
        return

    await editable_message.send_or_edit(
        _bot_api, "group_pve_item", peer_id, f"Использовано: {elixir.emoji} {elixir.name}.", no_keyboard()
    )

    if elixir.category == "heal":
        action = DeclaredAction(type=ActionType.ITEM, item_id=elixir_id, target_id=cid)
        _declared_this_tick.setdefault(battle_id, set()).add(cid)
        try:
            await _engine.declare_action(battle_id, cid, action)
        except (KeyError, ValueError):
            _declared_this_tick.get(battle_id, set()).discard(cid)
        return

    line = elixir_effects.apply_combat_elixir(combatant, elixir_id)
    combatant.combat_elixirs_used += 1
    text = f"{line} Твой ход.\n\n{_render_board(_engine.sessions.get(battle_id))}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0,
        keyboard=group_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id),
    )


# --- Резолв тика / завершение боя ---


async def on_group_tick_resolved(session_id: int, tick: int, result: TickResult) -> None:
    battle = _battles.get(session_id)
    if battle is None:
        return
    _declared_this_tick.pop(session_id, None)

    dead_mob_ids = [cid for cid in result.deaths if cid in battle.mob_ids]
    notices: dict[int, str] = {}
    if dead_mob_ids:
        async with get_session_factory()() as db:
            alive_char_ids = [
                cid for cid, c in _live_state(session_id, battle).items()
                if c.side == 0 and c.alive and cid in battle.participants
            ]
            characters = []
            for cid in alive_char_ids:
                character = await db.get(Character, cid)
                if character is not None:
                    characters.append(character)
            for mob_id in dead_mob_ids:
                mob = battle.last_combatants.get(mob_id)
                mob_level = mob.level if mob is not None else 1
                mob_name = mob.name if mob is not None else "Враг"
                rewards = await group_combat_service.reward_mob_kill(db, characters, mob_level, _rng)
                for r in rewards:
                    p = battle.participants.get(r.character_id)
                    if p is None:
                        continue
                    lines = [f"💀 {mob_name} повержен(а)!"]
                    lines.append(display.xp_delta_line(r.xp_gained, premium=r.xp_premium_applied))
                    drop_line = trophy_service.format_drop_line(r.trophies)
                    if drop_line:
                        lines.append(drop_line)
                    if r.item_dropped is not None:
                        lines.append(item_service.format_drop_announcement(r.item_dropped))
                    if r.raid_key_dropped:
                        lines.append(raid_key_texts.raid_key_drop_line())
                    if r.group_kick is not None and r.group_kick.kicked_character_id == r.character_id:
                        lines.append(group_texts.level_gap_kick_self_line())
                    character = next((c for c in characters if c.id == r.character_id), None)
                    if character is not None and r.trophies:
                        daily_progress = await daily_service.record_trophies(db, character, r.trophies)
                        daily_notice = dailies_texts.progress_notice(daily_progress)
                        if daily_notice:
                            lines.append(daily_notice)
                        for c in daily_progress.completed:
                            await stats_window.notify_levelup(p.peer_id, c.levels_gained, c.new_level)
                            await group_texts.notify_group_kick(_bot_api, c.group_kick)
                    notices[r.character_id] = "\n".join(lines)
                    if r.levels_gained > 0:
                        await stats_window.notify_levelup(p.peer_id, r.levels_gained, r.new_level)
                    await group_texts.notify_group_kick(_bot_api, r.group_kick)
                # квестовый прогресс "убей N" — по одному разу за моба, каждому живому
                for character in characters:
                    await quest_service.record_kill(db, character)
            await db.commit()

    await _broadcast_board(session_id, battle, result, notices)


async def on_group_battle_finished(session_id: int, result: TickResult) -> None:
    battle = _battles.pop(session_id, None)
    _declared_this_tick.pop(session_id, None)
    if battle is None:
        return
    _active_group_ids.discard(battle.group_id)
    for p in battle.participants.values():
        _peer_battle.pop(p.peer_id, None)
        _chosen_target.pop(p.character_id, None)

    combatants = battle.last_combatants
    survivor_ids = [cid for cid in battle.participants if cid in combatants and combatants[cid].alive]
    dead_ids = [cid for cid in battle.participants if cid in combatants and not combatants[cid].alive]

    async with get_session_factory()() as db:
        has_mount_by_cid = {}
        positions = {}
        defeats: dict[int, object] = {}
        for cid, p in battle.participants.items():
            character = await db.get(Character, cid)
            if character is None:
                continue
            positions[cid] = (character.pos_x, character.pos_y)
            if cid in survivor_ids:
                has_mount_by_cid[cid] = await mount_service.has_any_mount(db, cid)
            else:
                defeats[cid] = (await encounter_service.resolve_defeat(db, character), character.respawn_at)
        await db.commit()

    for cid, p in battle.participants.items():
        if cid in survivor_ids:
            pos = positions.get(cid, (0, 0))
            await _bot_api.messages.send(
                peer_id=p.peer_id, message="🏆 Группа побеждает! Тварь оседает пеплом.", random_id=0,
                keyboard=movement_keyboard(*pos, p.peer_id, has_mount=has_mount_by_cid.get(cid, False)),
            )
        elif cid in dead_ids and cid in defeats:
            defeat, respawn_at = defeats[cid]
            await respawn_handlers.register_death(p.peer_id, respawn_at, defeat.xp_lost)
