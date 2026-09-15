"""Рейд «Кукольный театр» (патч 53) — три этапа поверх ОБЩЕГО с групповым PvE
tick_engine (свой экземпляр TickEngine, см. main.py — session_id-пространство
не пересекается ни с чем другим, т.к. движок отдельный). Один battle_id живёт
ВСЮ попытку рейда (все три этапа) — только участники/мобы/раунд меняются,
_peer_battle не перестраивается между этапами.

Оркестрация механик боссов (порядок Вельдов, окна прерывания/фазы Хирурга) —
здесь; чистая логика самих механик — game/combat/raid_bosses.py."""

import asyncio
import random
from dataclasses import dataclass, field

from vkbottle.bot import BotLabeler, Message

from bot import dailies_texts, editable_message, group_texts, raid_key_texts, raid_texts as rt
from bot.handlers import respawn as respawn_handlers
from bot.handlers import stats_window
from bot.handlers.group_combat import MemberCombatInput, build_member_inputs
from bot.keyboards import raid as kb
from bot.keyboards.items import no_keyboard
from bot.keyboards.world import movement_keyboard
from game.combat import balance_config as bc
from game.combat import battle_log, display, elixir_effects, raid_bosses
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
from game.economy import raid_config as rc
from models import Character
from services import (
    daily_service,
    elixir_service,
    encounter_service,
    item_service,
    mount_service,
    quest_service,
    raid_combat_service,
    trophy_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_engine: TickEngine | None = None
_bot_api = None

_next_battle_id = -1


@dataclass
class Participant:
    character_id: int
    peer_id: int
    name: str
    base_class: str
    subclass_id: str | None


@dataclass
class RaidBattle:
    group_id: int | None
    participants: dict[int, Participant]
    member_inputs: list[MemberCombatInput]
    rng: random.Random
    stage: int = 1
    mob_ids: set[int] = field(default_factory=set)
    last_combatants: dict[int, object] = field(default_factory=dict)
    # --- Этап 2: Вельды ---
    veld_combatant_ids: dict[str, int] = field(default_factory=dict)
    veld_killed_order: list[str] = field(default_factory=list)
    veld_violations: int = 0
    # --- Этап 3: Хирург ---
    surgeon_ai: "raid_bosses.SurgeonAI | None" = None
    surgeon_id: int | None = None
    surgeon_phase3_hp_at_start: int | None = None
    surgeon_phase3_failed: bool = False


_battles: dict[int, RaidBattle] = {}
_peer_battle: dict[int, int] = {}
_declared_this_tick: dict[int, set[int]] = {}
_chosen_target: dict[int, int] = {}
_character_in_raid: set[int] = set()


def setup(engine: TickEngine, bot_api) -> None:
    global _engine, _bot_api
    _engine = engine
    _bot_api = bot_api


def has_active_raid(character_id: int) -> bool:
    return character_id in _character_in_raid


# --- Построение боевых участников (свежие каждый этап — как и групповой PvE) ---


def _build_player_combatants(state: CombatSessionState, member_inputs: list[MemberCombatInput]) -> None:
    for m in member_inputs:
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
        # Между этапами HP восстанавливается ПОЛНОСТЬЮ, включая погибших на
        # предыдущем этапе (текст патча) — новый CombatantState стартует с
        # полным HP всегда, не с current_hp предыдущего боя.
        combatant.current_hp = combatant.max_hp
        state.add(combatant)


def _start_stage_session(battle_id: int, battle: RaidBattle) -> CombatSessionState:
    state = CombatSessionState(session_id=battle_id, mode=CombatMode.PVE, is_raid=True)
    _build_player_combatants(state, battle.member_inputs)

    if battle.stage == 1:
        mobs = raid_bosses.build_stage1_mobs(start_id=20_000_000)
        for m in mobs:
            state.add(m)
        battle.mob_ids = {m.id for m in mobs}
    elif battle.stage == 2:
        velds = raid_bosses.build_veld_mobs(start_id=20_100_000)
        for m in velds.values():
            state.add(m)
        battle.mob_ids = {m.id for m in velds.values()}
        battle.veld_combatant_ids = {vid: c.id for vid, c in velds.items()}
        battle.veld_killed_order = []
        battle.veld_violations = 0
    else:
        surgeon = raid_bosses.build_surgeon(id=20_200_000)
        ai = raid_bosses.SurgeonAI()
        surgeon.scripted_hit = ai
        state.add(surgeon)
        battle.mob_ids = {surgeon.id}
        battle.surgeon_ai = ai
        battle.surgeon_id = surgeon.id
        battle.surgeon_phase3_hp_at_start = None
        battle.surgeon_phase3_failed = False

    for p in battle.participants.values():
        enemies = list(battle.mob_ids)
        if enemies:
            _chosen_target[p.character_id] = enemies[0]
    return state


_STAGE_APPEAR_TEXT = {1: rt.STAGE1_APPEAR_TEXT, 2: rt.STAGE2_APPEAR_TEXT, 3: rt.STAGE3_APPEAR_TEXT}
_STAGE_LOOT_MULT = {1: rc.STAGE1_LOOT_MULT, 2: rc.STAGE2_LOOT_MULT, 3: rc.STAGE3_LOOT_MULT}
_STAGE_LOOT_FLOOR = {1: "uncommon", 2: "rare", 3: "epic"}


async def start_raid(group_id: int | None, member_inputs: list[MemberCombatInput], rng: random.Random) -> None:
    global _next_battle_id
    battle_id = _next_battle_id
    _next_battle_id -= 1

    participants = {
        m.character.id: Participant(
            character_id=m.character.id, peer_id=m.peer_id, name=m.character.name,
            base_class=m.character.base_class, subclass_id=m.character.subclass,
        )
        for m in member_inputs
    }
    battle = RaidBattle(group_id=group_id, participants=participants, member_inputs=member_inputs, rng=rng)
    _battles[battle_id] = battle
    for cid, p in participants.items():
        _peer_battle[p.peer_id] = battle_id
        _character_in_raid.add(cid)

    state = _start_stage_session(battle_id, battle)
    _engine.start_session(state)

    for p in participants.values():
        await _bot_api.messages.send(
            peer_id=p.peer_id,
            message=f"{rt.PROLOGUE_TEXT}\n\n{_STAGE_APPEAR_TEXT[1]}",
            random_id=0,
        )
    await _broadcast_board(battle_id, battle, None)


def _live_state(battle_id: int, battle: RaidBattle) -> dict:
    state = _engine.sessions.get(battle_id)
    if state is not None:
        battle.last_combatants = dict(state.combatants)
    return battle.last_combatants


def _character_id_for_peer(battle: RaidBattle, peer_id: int) -> int | None:
    for cid, p in battle.participants.items():
        if p.peer_id == peer_id:
            return cid
    return None


def _enemies_of(battle_id: int, battle: RaidBattle, cid: int) -> list[int]:
    combatants = _live_state(battle_id, battle)
    me = combatants.get(cid)
    if me is None:
        return []
    return [c.id for c in combatants.values() if c.side != me.side and c.alive]


def _resolve_chosen_target(battle_id: int, battle: RaidBattle, cid: int) -> int | None:
    combatants = _live_state(battle_id, battle)
    target_id = _chosen_target.get(cid)
    target = combatants.get(target_id) if target_id is not None else None
    if target is not None and target.alive:
        return target_id
    enemies = _enemies_of(battle_id, battle, cid)
    fallback = enemies[0] if enemies else None
    if fallback is not None:
        _chosen_target[cid] = fallback
    return fallback


def _target_line(battle_id: int, battle: RaidBattle, cid: int) -> str:
    combatants = _live_state(battle_id, battle)
    target_id = _chosen_target.get(cid)
    target = combatants.get(target_id) if target_id is not None else None
    if target is None or not target.alive:
        return ""
    hp_pct = round(100 * target.current_hp / target.max_hp) if target.max_hp else 0
    return f"🎯 Цель: {target.name} ({hp_pct}% HP)"


def _render_board(state: CombatSessionState, result: TickResult | None = None) -> str:
    return battle_log.render_tick(state, result or TickResult(), viewer_side=0)


async def _broadcast_board(
    battle_id: int, battle: RaidBattle, result: TickResult | None, notices: dict[int, str] | None = None,
) -> None:
    state = _engine.sessions.get(battle_id)
    text = _render_board(state, result) if state is not None else ""
    notices = notices or {}
    for cid, p in battle.participants.items():
        combatant = _live_state(battle_id, battle).get(cid)
        keyboard = (
            kb.raid_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id)
            if combatant is not None and combatant.alive
            else kb.raid_waiting_keyboard()
        )
        personal = text
        notice = notices.get(cid)
        if notice:
            personal = f"{notice}\n\n{personal}"
        target_line = _target_line(battle_id, battle, cid)
        if target_line and combatant is not None and combatant.alive:
            personal = f"{personal}\n{target_line}"
        await _bot_api.messages.send(peer_id=p.peer_id, message=personal, random_id=0, keyboard=keyboard)


# --- Действия боя (атака/навык) ---


@labeler.message(text=["⚔️ Ударить"])
async def raid_attack(message: Message) -> None:
    await _raid_action(message, DeclaredAction(type=ActionType.ATTACK))


@labeler.message(payload_contains={"type": "raid_skill"})
async def raid_skill(message: Message) -> None:
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
        keyboard = kb.raid_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id) if p else None
        await message.answer(f"⏳ Навык ещё не готов (КД {cd}).", keyboard=keyboard)
        return
    await _raid_action(message, DeclaredAction(type=ActionType.SKILL, skill_id=skill_id))


async def _raid_action(message: Message, action: DeclaredAction) -> None:
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
                random_id=0, keyboard=kb.raid_waiting_keyboard(),
            )


# --- Выбор цели (бесплатное действие, как в массовом PvP/групповом PvE) ---


@labeler.message(payload_contains={"type": "raid_open_target"})
async def raid_open_target(message: Message) -> None:
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
        _bot_api, "raid_target", peer_id, "\n".join(lines), kb.raid_target_keyboard(mob_ids),
    )


@labeler.message(payload_contains={"type": "raid_target_pick"})
async def raid_pick_target(message: Message) -> None:
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
    await editable_message.send_or_edit(_bot_api, "raid_target", peer_id, f"🎯 Новая цель: {target.name}.", no_keyboard())
    board = f"🎯 Цель: {target.name}.\n\n{_render_board(_engine.sessions.get(battle_id))}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=board, random_id=0,
        keyboard=kb.raid_combat_keyboard(p.base_class, me.cooldowns, subclass_id=p.subclass_id),
    )


@labeler.message(payload_contains={"type": "raid_target_back"})
async def raid_target_back(message: Message) -> None:
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
    await editable_message.send_or_edit(_bot_api, "raid_target", peer_id, "Возврат в бой.", no_keyboard())
    await _bot_api.messages.send(
        peer_id=peer_id, message=_render_board(_engine.sessions.get(battle_id)), random_id=0,
        keyboard=kb.raid_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id),
    )


# --- Предметы в бою ---


@labeler.message(payload_contains={"type": "raid_open_items"})
async def raid_open_items(message: Message) -> None:
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
    battle_kb = kb.raid_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id)
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
    await editable_message.send_or_edit(_bot_api, "raid_item", peer_id, text, kb.raid_items_keyboard(visible))


@labeler.message(payload_contains={"type": "raid_use_item"})
async def raid_use_item(message: Message) -> None:
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
    battle_kb = kb.raid_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id)
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
        _bot_api, "raid_item", peer_id, f"Использовано: {elixir.emoji} {elixir.name}.", no_keyboard()
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
        keyboard=kb.raid_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id),
    )


# --- Резолв тика: механики боссов + награды ---


async def _kill_random_survivor(battle_id: int, battle: RaidBattle) -> int | None:
    """Гарантированная гибель одного случайного ЖИВОГО участника (провал
    окна прерывания/фазы проверки урона Хирурга) — HP обнуляется НАПРЯМУЮ,
    в обход обычного резолва тика (см. game/combat/raid_bosses.py — этот
    приём уже описан там для сценария лайфстила, тот же принцип). Возвращает
    id погибшего (для лога/дальнейшей проверки вайпа) или None, если живых
    уже не осталось (не должно происходить, но не падать)."""
    state = _engine.sessions.get(battle_id)
    if state is None:
        return None
    alive_players = [c for c in state.combatants.values() if c.kind == "character" and c.alive]
    if not alive_players:
        return None
    victim = battle.rng.choice(alive_players)
    victim.current_hp = 0
    return victim.id


async def on_raid_tick_resolved(session_id: int, tick: int, result: TickResult) -> None:
    battle = _battles.get(session_id)
    if battle is None:
        return
    _declared_this_tick.pop(session_id, None)
    state = _engine.sessions.get(session_id)
    extra_lines: list[str] = []
    scripted_death_ids: list[int] = []

    if battle.stage == 2 and state is not None:
        dead_veld_ids = [vid for vid, cid in battle.veld_combatant_ids.items() if cid in result.deaths]
        if dead_veld_ids:
            dead_veld_ids.sort(key=lambda vid: rc.VELD_ORDER.index(vid))
            outcome = raid_bosses.check_veld_kill_order(
                state.combatants, battle.veld_combatant_ids, dead_veld_ids,
                battle.veld_killed_order, battle.veld_violations,
            )
            battle.veld_violations = outcome.violations
            extra_lines.extend(outcome.lines)

    if battle.stage == 3 and state is not None and battle.surgeon_id is not None:
        surgeon = state.combatants.get(battle.surgeon_id)
        ai = battle.surgeon_ai
        if surgeon is not None and ai is not None and surgeon.alive:
            # Окно прерывания (первый ход ИЛИ только что открыто фазой 2) —
            # проверяем результат ЭТОГО тика (control_landed_by).
            if ai.awaiting_interrupt:
                if result.control_landed_by:
                    extra_lines.append("Инструмент выбит из руки. Хирург отступает на шаг.")
                    ai.close_interrupt_window()
                else:
                    victim_id = await _kill_random_survivor(session_id, battle)
                    if victim_id is not None:
                        victim_name = battle.participants.get(victim_id)
                        extra_lines.append(
                            f"{rt.SURGEON_INTERRUPT_FAIL_DEATH_LINE} {victim_name.name if victim_name else ''}"
                            f" падает замертво."
                        )
                        scripted_death_ids.append(victim_id)
                    ai.close_interrupt_window()
            elif tick == 1:
                extra_lines.append(rt.SURGEON_PREPARE_FIRST_TEXT)
                ai.open_interrupt_window()
            elif ai.phase == 1 and surgeon.current_hp <= surgeon.max_hp * rc.SURGEON_PHASE2_HP_THRESHOLD:
                ai.phase = 2
                extra_lines.append(rt.SURGEON_PREPARE_PHASE2_TEXT)
                ai.open_interrupt_window()
            elif (
                ai.phase == 2
                and ai.phase3_turns_left is None
                and not battle.surgeon_phase3_failed
                and surgeon.current_hp <= surgeon.max_hp * rc.SURGEON_PHASE3_HP_THRESHOLD
            ):
                ai.enter_phase3()
                battle.surgeon_phase3_hp_at_start = surgeon.current_hp
                extra_lines.append(rt.SURGEON_PHASE3_TEXT)
            elif ai.phase3_turns_left is not None:
                ai.phase3_turns_left -= 1
                if ai.phase3_turns_left <= 0:
                    dealt = (battle.surgeon_phase3_hp_at_start or surgeon.current_hp) - surgeon.current_hp
                    ai.phase3_turns_left = None
                    if dealt >= rc.SURGEON_PHASE3_DAMAGE_REQUIRED:
                        extra_lines.append("Хирург вздрагивает — механизм не успел довершить работу.")
                    else:
                        battle.surgeon_phase3_failed = True
                        extra_lines.append(rt.SURGEON_PHASE3_FAIL_TEXT)
            elif battle.surgeon_phase3_failed:
                victim_id = await _kill_random_survivor(session_id, battle)
                if victim_id is not None:
                    scripted_death_ids.append(victim_id)

    if scripted_death_ids and state is not None:
        alive_players_left = [c for c in state.combatants.values() if c.kind == "character" and c.alive]
        if not alive_players_left:
            # Вайп сценарной гибелью — TickEngine об этом не узнает сам
            # (HP обнулён В ОБХОД resolve_tick), поэтому завершаем ЯВНО:
            # abort_session — единственный ПУБЛИЧНЫЙ метод движка для этого
            # (снимает job таймера, освобождает session_id), дальше —
            # собственная логика вайпа этого модуля.
            _engine.abort_session(session_id)
            await _finish_wipe(session_id, battle)
            return

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
            mob_level = raid_bosses.BOSS_LEVEL
            rewards = await raid_combat_service.reward_mob_kill(
                db, characters, mob_level, battle.rng, _STAGE_LOOT_MULT[battle.stage],
            )
            for r in rewards:
                p = battle.participants.get(r.character_id)
                if p is None:
                    continue
                lines = [display.xp_delta_line(r.xp_gained, premium=r.xp_premium_applied)]
                drop_line = trophy_service.format_drop_line(r.trophies)
                if drop_line:
                    lines.append(drop_line)
                for item in r.items_dropped:
                    lines.append(item_service.format_drop_announcement(item))
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
                notices[r.character_id] = "\n".join(lines)
                if r.levels_gained > 0:
                    await stats_window.notify_levelup(p.peer_id, r.levels_gained, r.new_level)
            for character in characters:
                await quest_service.record_kill(db, character)
            await db.commit()

    if extra_lines:
        for cid in battle.participants:
            notices[cid] = "\n".join(extra_lines) + (f"\n\n{notices[cid]}" if cid in notices else "")

    await _broadcast_board(session_id, battle, result, notices)


async def on_raid_battle_finished(session_id: int, result: TickResult) -> None:
    battle = _battles.get(session_id)
    if battle is None:
        return
    if result.winner_side != 0:
        await _finish_wipe(session_id, battle)
        return
    await _advance_or_finish(session_id, battle)


async def _advance_or_finish(session_id: int, battle: RaidBattle) -> None:
    """Этап зачищен (сторона игроков победила). stage<3 — пауза 5-10 сек +
    переход к следующему этапу; stage==3 — рейд пройден целиком."""
    stage_cleared = battle.stage
    if stage_cleared >= 3:
        await _finish_victory(session_id, battle)
        return

    transition_text = rt.STAGE1_TO_STAGE2_TEXT if stage_cleared == 1 else rt.STAGE2_TO_STAGE3_TEXT
    for p in battle.participants.values():
        await _bot_api.messages.send(
            peer_id=p.peer_id, message=transition_text, random_id=0, keyboard=kb.raid_waiting_keyboard(),
        )
    await asyncio.sleep(
        battle.rng.uniform(rc.STAGE_TRANSITION_PAUSE_MIN_SECONDS, rc.STAGE_TRANSITION_PAUSE_MAX_SECONDS)
    )

    battle.stage += 1
    state = _start_stage_session(session_id, battle)
    _engine.start_session(state)
    for p in battle.participants.values():
        await _bot_api.messages.send(
            peer_id=p.peer_id, message=_STAGE_APPEAR_TEXT[battle.stage], random_id=0,
        )
    await _broadcast_board(session_id, battle, None)


async def _grant_stage_clear_bonus(battle: RaidBattle) -> None:
    """Гарантированный предмет за этап — ОДНОМУ случайному живому участнику
    (текст патча). Плюс, на этапе 3, Скальпель Хирурга — ВСЕГДА, тоже
    одному случайному участнику (независимый розыгрыш)."""
    async with get_session_factory()() as db:
        candidates = []
        for cid in battle.participants:
            character = await db.get(Character, cid)
            if character is not None:
                candidates.append(character)
        if not candidates:
            return
        winner = battle.rng.choice(candidates)
        item = await raid_combat_service.grant_guaranteed_item(
            db, winner, raid_bosses.BOSS_LEVEL, battle.rng, _STAGE_LOOT_FLOOR[battle.stage],
        )
        winner_peer = battle.participants[winner.id].peer_id
        await db.commit()
    try:
        await _bot_api.messages.send(
            peer_id=winner_peer, message=item_service.format_drop_announcement(item), random_id=0,
        )
    except Exception:
        pass

    if battle.stage == 3:
        async with get_session_factory()() as db:
            scalpel_winner = battle.rng.choice(candidates)
            scalpel_winner = await db.get(Character, scalpel_winner.id)
            scalpel = await item_service.grant_unique_item(db, scalpel_winner, rc.RAID_UNIQUE_ITEM_ID)
            peer_id = battle.participants[scalpel_winner.id].peer_id
            await db.commit()
        try:
            await _bot_api.messages.send(
                peer_id=peer_id,
                message=f"🔴 Тебе достаётся {scalpel.name} — Скальпель Хирурга.",
                random_id=0,
            )
        except Exception:
            pass


async def _finish_victory(session_id: int, battle: RaidBattle) -> None:
    await _grant_stage_clear_bonus(battle)
    await _cleanup_and_return(session_id, battle, rt.EPILOGUE_TEXT, defeated=False)


async def _finish_wipe(session_id: int, battle: RaidBattle) -> None:
    await _cleanup_and_return(session_id, battle, rt.RAID_DEFEAT_TEXT, defeated=True)


async def _cleanup_and_return(session_id: int, battle: RaidBattle, text: str, *, defeated: bool) -> None:
    """И победа, и поражение возвращают всех к Монолиту (0;0) — позиция
    персонажей не менялась на всём протяжении рейда, поэтому достаточно
    показать обычную клавиатуру перемещения ИМЕННО для этой клетки."""
    _battles.pop(session_id, None)
    _declared_this_tick.pop(session_id, None)
    combatants = battle.last_combatants
    state = _engine.sessions.get(session_id)
    if state is not None:
        combatants = dict(state.combatants)
    for p in battle.participants.values():
        _peer_battle.pop(p.peer_id, None)
        _chosen_target.pop(p.character_id, None)
        _character_in_raid.discard(p.character_id)

    async with get_session_factory()() as db:
        has_mount_by_cid = {}
        defeats: dict[int, object] = {}
        for cid, p in battle.participants.items():
            character = await db.get(Character, cid)
            if character is None:
                continue
            character.pos_x, character.pos_y = rc.MONOLITH_COORDS
            combatant = combatants.get(cid)
            survived = combatant is not None and combatant.alive and not defeated
            if survived:
                has_mount_by_cid[cid] = await mount_service.has_any_mount(db, cid)
            else:
                defeats[cid] = (await encounter_service.resolve_defeat(db, character), character.respawn_at)
        await db.commit()

    for cid, p in battle.participants.items():
        if cid in has_mount_by_cid:
            await _bot_api.messages.send(
                peer_id=p.peer_id, message=text, random_id=0,
                keyboard=movement_keyboard(*rc.MONOLITH_COORDS, p.peer_id, has_mount=has_mount_by_cid.get(cid, False)),
            )
        elif cid in defeats:
            defeat, respawn_at = defeats[cid]
            await _bot_api.messages.send(peer_id=p.peer_id, message=text, random_id=0, keyboard=kb.raid_waiting_keyboard())
            await respawn_handlers.register_death(p.peer_id, respawn_at, defeat.xp_lost)
