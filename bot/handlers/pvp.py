"""Открытое PvP на карте (патч 22): осмотреться, /напасть, дуэли и массовые бои.

Архитектура:
  - Дуэль (1×1, последовательные ходы) — game.combat.duel_engine.DuelEngine,
    существовал и раньше, здесь только подключение.
  - Массовый бой (N vs M, одновременный резолв) — ОТДЕЛЬНЫЙ TickEngine
    (не combat.py's _engine: там PLAYER_ID=1/MOB_ID=2 фиксированы под ровно
    одного игрока и одного моба; здесь комбатанты — реальные character.id,
    участников может быть много с обеих сторон).
  - Battle (этот модуль) — лёгкий реестр "кто с кем дерётся и на чьей
    стороне" поверх обоих движков: движки ничего не знают про peer_id/VK,
    Battle связывает character_id <-> peer_id и считает урон по парам для
    пропорционального дележа трофеев в массовых боях.

ВАЖНО: боевые кнопки (BTN_PVP_ATTACK, payload {"type":"pvp_skill"}) НАМЕРЕННО
отличаются от PvE (BTN_ATTACK/{"type":"skill"} из bot/handlers/combat.py) —
см. комментарий в bot/keyboards/pvp.py про порядок диспетчеризации vkbottle.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message

from bot import dailies_texts, editable_message
from bot.handlers import combat as combat_handlers
from bot.handlers import respawn as respawn_handlers
from bot.handlers import stats_window
from bot.keyboards import world as kb
from bot.keyboards.items import no_keyboard
from bot.keyboards.pvp import (
    BTN_PVP_ATTACK,
    BTN_PVP_ITEM,
    join_side_keyboard,
    pvp_combat_keyboard,
    pvp_items_keyboard,
    pvp_waiting_keyboard,
)
from bot.pvp_texts import AFK_TARGET_TEXT, ALONE_ON_CELL, CITY_NO_PVP_TEXT, NOTHING_TO_TAKE
from game.combat import balance_config as bc
from game.combat import display, elixir_effects
from game.combat.base_skills import BASE_SKILL_DEFS
from game.combat.duel_engine import DuelEngine, DuelResult, DuelState
from game.combat.resolver import TickResult
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    CombatantState,
    DeclaredAction,
    EffectKind,
    Stats,
    build_combatant,
)
from game.combat.skills import DEFENSIVE_SKILLS
from game.combat.tick_engine import TickEngine
from game.economy import elixir_config as ec
from game.world import grid
from models import Character, CharacterStats
from services import (
    admin_service, daily_service, death_service, elixir_service, item_service, mount_service, preset_service,
    pvp_service, trophy_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_duel_engine: DuelEngine | None = None
_mass_engine: TickEngine | None = None
_bot_api = None
_rng = random.Random()

_next_battle_id = -1  # отрицательные id — отдельное пространство от peer_id (combat.py's _engine)


@dataclass
class Participant:
    character_id: int
    peer_id: int
    name: str
    base_class: str
    class_title: str


@dataclass
class Battle:
    battle_type: str  # "duel" | "mass"
    location: tuple[int, int]
    participants: dict[int, Participant] = field(default_factory=dict)   # character_id -> Participant
    side_of: dict[int, int] = field(default_factory=dict)                # character_id -> 0/1
    damage_by_pair: dict[tuple[int, int], int] = field(default_factory=dict)  # (attacker, victim) -> total
    join_queue: list[tuple[Participant, "CombatantState"]] = field(default_factory=list)
    last_combatants: dict[int, "CombatantState"] = field(default_factory=dict)  # снимок на конец последнего хода


_battles: dict[int, Battle] = {}
_peer_battle: dict[int, int] = {}
# peer_id -> battle_id, ждём выбора стороны (текстом "1"/"2") для этого боя
_pending_join_prompt: dict[int, int] = {}
# Патч 31, п.6: battle_id -> character_id'ы, уже объявившие действие в ТЕКУЩЕМ
# (ещё не резолвленном) окне группового PvP — клавиатура убирается у них до
# следующего тика. Отдельно от game.combat.tick_engine.ActionStore (тот же
# набор, но целиком в памяти этого процесса) — нужен только для решения
# «показывать ли боевые кнопки», не участвует в самом резолве хода.
_declared_this_tick: dict[int, set[int]] = {}


def setup(duel_engine: DuelEngine, mass_engine: TickEngine, bot_api) -> None:
    global _duel_engine, _mass_engine, _bot_api
    _duel_engine = duel_engine
    _mass_engine = mass_engine
    _bot_api = bot_api


def has_active_battle(peer_id: int) -> bool:
    return peer_id in _peer_battle


def rebuild_keyboard(peer_id: int) -> str | None:
    """Патч 25: актуальная боевая клавиатура для игрока в PvP-бою, без
    прерывания боя — общая для /клавиатура и PvP-ветки /застрял (там бой
    НЕ прерывается, только пересобирается клавиатура — защита от абьюза).
    None — peer_id ни в какой активной PvP-битве.

    Патч 31, п.6: боевые кнопки — ТОЛЬКО тому, чей сейчас ход. В дуэли это
    duel.current_actor_id (здесь читается ВНЕ колбэка резолва хода, поэтому
    не имеет проблемы устаревания значения, описанной в _render_duel); в
    групповом бою — все, кто ещё не объявил действие в текущем окне
    (_declared_this_tick)."""
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return None
    battle = _battles.get(battle_id)
    if battle is None:
        return None
    participant = next((p for p in battle.participants.values() if p.peer_id == peer_id), None)
    if participant is None:
        return None
    if battle.battle_type == "duel":
        duel = _duel_engine.duels.get(battle_id) if _duel_engine else None
        combatant = duel.combatants.get(participant.character_id) if duel else None
        if combatant is None or not combatant.alive:
            return pvp_waiting_keyboard()
        if duel is not None and participant.character_id != duel.current_actor_id:
            return pvp_waiting_keyboard()
    else:
        session = _mass_engine.sessions.get(battle_id) if _mass_engine else None
        combatant = (
            session.combatants.get(participant.character_id) if session
            else battle.last_combatants.get(participant.character_id)
        )
        if combatant is None or not combatant.alive:
            return pvp_waiting_keyboard()
        if participant.character_id in _declared_this_tick.get(battle_id, set()):
            return pvp_waiting_keyboard()
    return pvp_combat_keyboard(participant.base_class, combatant.cooldowns)


def _new_battle_id() -> int:
    global _next_battle_id
    battle_id = _next_battle_id
    _next_battle_id -= 1
    return battle_id


# --- Общие мелкие хелперы ---


async def _still_dead(db, character: Character) -> bool:
    now = datetime.now(timezone.utc)
    if death_service.respawn_if_ready(character, now):
        await db.commit()
    return death_service.is_dead(character, now)


def _participant(character: Character, peer_id: int) -> Participant:
    return Participant(
        character_id=character.id, peer_id=peer_id, name=character.name,
        base_class=character.base_class, class_title=pvp_service.class_title(character),
    )


async def _build_combatant_for(db, character: Character) -> CombatantState:
    stats_row = await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )
    gear_bonus = await item_service.compute_gear_bonus(db, character.id)
    buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
    stats = Stats(
        strength=stats_row.strength + gear_bonus.get("str", 0),
        agility=stats_row.agility + gear_bonus.get("agi", 0),
        intellect=stats_row.intellect + gear_bonus.get("int", 0),
        vitality=stats_row.vitality + gear_bonus.get("vit", 0),
        will=stats_row.will + gear_bonus.get("wil", 0),
    )
    primary = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    # Патч 22: перед PvP-боем ОБА восстанавливаются до полного HP — build_combatant
    # всегда стартует с current_hp=max_hp, что ровно и нужно (никакого переноса
    # текущего HP из vitals_service, как в PvE).
    return build_combatant(
        id=character.id, side=0, kind="character", name=character.name,
        level=character.level, stats=stats, primary_stat=primary,
        subclass_id=character.subclass, buff_modifiers=buff_modifiers,
    )


def _character_id_for_peer(battle: Battle, peer_id: int) -> int | None:
    for cid, p in battle.participants.items():
        if p.peer_id == peer_id:
            return cid
    return None


def _live_state(battle_id: int, battle: Battle) -> dict[int, CombatantState]:
    if battle.battle_type == "duel":
        duel = _duel_engine.duels.get(battle_id)
        return duel.combatants if duel is not None else {}
    session = _mass_engine.sessions.get(battle_id)
    return session.combatants if session is not None else {}


def _format_transfer_line(moved: dict[str, int]) -> str | None:
    if not moved:
        return None
    parts = []
    for trophy_def in reversed(trophy_service.trophy_defs_ordered()):
        amount = moved.get(trophy_def.id)
        if not amount:
            continue
        suffix = f" ×{amount}" if amount > 1 else ""
        parts.append(f"{trophy_def.emoji} {trophy_def.name}{suffix}")
    if not parts:
        return None
    return "Забираешь трофеи: " + ", ".join(parts) + "."


# --- Осмотреться / резолв цели ---


def _battles_at(x: int, y: int) -> list[tuple[int, Battle]]:
    return [(bid, b) for bid, b in _battles.items() if b.location == (x, y)]


async def _scene_at(db, character: Character) -> tuple[list[Character], list[tuple[int, Battle]]]:
    others = await pvp_service.others_at(db, character)
    battles = _battles_at(character.pos_x, character.pos_y)
    busy_ids = {cid for _, b in battles for cid in b.participants}
    # Патч 33, ч.3: AFK (нет действий AFK_TIMEOUT_MINUTES) исключён из
    # «Осмотреться»/нумерации целей — уже идущий бой это НЕ трогает (busy_ids
    # выше — отдельная причина, AFK-статус там не проверяется намеренно).
    solo = [c for c in others if c.id not in busy_ids and not pvp_service.is_afk(c)]
    return solo, battles


async def _afk_target_named(db, character: Character, target: str) -> bool:
    """True — target (по имени; числа никогда не указывают на AFK — они не
    нумеруются вовсе) совпадает с игроком на клетке, который сейчас AFK.
    Только чтобы attack_command показал отдельный лорный текст вместо
    общего "нет такой цели" (патч 33, ч.3)."""
    if target.isdigit():
        return False
    others = await pvp_service.others_at(db, character)
    battles = _battles_at(character.pos_x, character.pos_y)
    busy_ids = {cid for _, b in battles for cid in b.participants}
    lowered = target.lower()
    return any(
        c.id not in busy_ids and pvp_service.is_afk(c) and c.name.lower() == lowered
        for c in others
    )


def _class_line(c: Character) -> str:
    title = daily_service.title_name(c)
    name = f"{c.name} «{title}»" if title else c.name
    return f"{name} · {c.level} ур. · {pvp_service.class_title(c)}"


def _battle_scene_line(battle: Battle) -> str:
    side0 = [p.name for cid, p in battle.participants.items() if battle.side_of.get(cid) == 0]
    side1 = [p.name for cid, p in battle.participants.items() if battle.side_of.get(cid) == 1]
    return f"⚔️ Бой: {' и '.join(side0)} vs {' и '.join(side1)}"


# Патч 35, аудит: список игроков на клетке — ТЕКСТ, без единой инлайн-кнопки
# (цель называют числом/именем через attack_command), поэтому лимит клавиатуры
# VK тут не при чём даже на людной клетке. Длина сообщения теоретически растёт
# с числом игроков на клетке, но лимит VK на текст (4096 симв.) недостижим на
# практике при разумной плотности игроков.
def _scene_text(solo: list[Character], battles: list[tuple[int, Battle]]) -> str:
    if not solo and not battles:
        return ALONE_ON_CELL
    lines = ["👁 Ты оглядываешься.", "", "Здесь есть кто-то ещё:"]
    idx = 1
    for c in solo:
        lines.append(f"{idx}. {_class_line(c)}")
        idx += 1
    for _, battle in battles:
        lines.append(f"{idx}. {_battle_scene_line(battle)}")
        idx += 1
    return "\n".join(lines)


async def _resolve_target(db, character: Character, target: str):
    """Возвращает (Character, None) — цель-игрок, (None, (battle_id, Battle))
    — идущий бой, (None, None) — цель не найдена."""
    solo, battles = await _scene_at(db, character)
    if target.isdigit():
        n = int(target)
        if 1 <= n <= len(solo):
            return solo[n - 1], None
        battle_idx = n - len(solo) - 1
        if 0 <= battle_idx < len(battles):
            return None, battles[battle_idx]
        return None, None
    lowered = target.lower()
    for c in solo:
        if c.name.lower() == lowered:
            return c, None
    return None, None


def _battle_roster_text(battle_id: int, battle: Battle) -> str:
    combatants = _live_state(battle_id, battle)
    by_side: dict[int, list[str]] = {0: [], 1: []}
    for cid, p in battle.participants.items():
        c = combatants.get(cid)
        if c is None:
            continue
        hp_pct = round(100 * c.current_hp / c.max_hp) if c.max_hp else 0
        by_side.setdefault(battle.side_of.get(cid, 0), []).append(
            f"{p.name} · {c.level} ур. · {p.class_title} ({hp_pct}% HP)"
        )
    lines = ["⚔️ Бой:", f"Сторона 1: {', '.join(by_side.get(0, []))}", f"Сторона 2: {', '.join(by_side.get(1, []))}"]
    return "\n".join(lines)


@labeler.message(text=[kb.BTN_LOOK_AROUND])
async def look_around(message: Message) -> None:
    peer_id = message.peer_id
    if has_active_battle(peer_id):
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if await _still_dead(db, character):
            await message.answer("☠ Сначала очнись.")
            return
        # Патч 33, ч.2: города полностью мирные — кнопка и так не показывается
        # в городской клавиатуре (bot/keyboards/world.py::city_menu_keyboard),
        # это защита от устаревшей клавиатуры.
        if grid.city_region_at(character.pos_x, character.pos_y) is not None:
            return
        solo, battles = await _scene_at(db, character)
    await message.answer(_scene_text(solo, battles))


@labeler.message(text=["/топ", "/top"])
async def leaderboard_command(message: Message) -> None:
    """Топ-10 по PvP-победам + место игрока, если он вне десятки (патч 22, п.7)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        entries = await pvp_service.leaderboard(db, limit=10)
        rank = await pvp_service.rank_of(db, character)

    lines = ["🏆 ЛУЧШИЕ ИЗ МЕЧЕНЫХ", ""]
    for entry in entries:
        name = f"{entry.name} «{entry.title}»" if entry.title else entry.name
        lines.append(f"{entry.rank}. {name} — {entry.wins} побед / {entry.losses} поражений")
    if rank > len(entries):
        lines.append("—")
        lines.append(f"Ты: {rank} место — {character.pvp_wins} / {character.pvp_losses}")
    await message.answer("\n".join(lines))


# --- /напасть, /attack ---


@labeler.message(text=["/напасть <target>", "/attack <target>"])
async def attack_command(message: Message, target: str) -> None:
    peer_id = message.peer_id
    if has_active_battle(peer_id):
        await message.answer("Ты уже дерёшься.")
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if await _still_dead(db, character):
            await message.answer("☠ Сначала очнись.")
            return
        # Патч 33, ч.2: PvP запрещено во ВСЕХ городах — и в своём, и в чужом
        # (отменяет патч 26, где чужой город был ареной без защиты).
        if grid.city_region_at(character.pos_x, character.pos_y) is not None:
            await message.answer(CITY_NO_PVP_TEXT)
            return

        victim, battle_entry = await _resolve_target(db, character, target)
        if victim is None and battle_entry is None:
            if await _afk_target_named(db, character, target):
                await message.answer(AFK_TARGET_TEXT)
            else:
                await message.answer("Здесь нет такой цели.")
            return

        if battle_entry is not None:
            battle_id, battle = battle_entry
            _pending_join_prompt[peer_id] = battle_id
            await message.answer(
                f"{_battle_roster_text(battle_id, battle)}\n\nК кому присоединиться? Напиши 1 или 2.",
                keyboard=join_side_keyboard(battle_id),
            )
            return

        victim_peer_id = await onboarding_svc.vk_id_for_character(db, victim.id)
        if victim_peer_id is None:
            await message.answer("Здесь нет такой цели.")
            return
        await _start_forced_duel(db, character, peer_id, victim, victim_peer_id)


async def _start_forced_duel(
    db, attacker: Character, attacker_peer_id: int, victim: Character, victim_peer_id: int
) -> None:
    if combat_handlers.has_active_encounter(victim_peer_id):
        await combat_handlers.interrupt_for_pvp(victim_peer_id)
        await _bot_api.messages.send(
            peer_id=victim_peer_id, message="⚔️ На тебя напали! Бой с тварью прерван.", random_id=0,
        )

    attacker_combatant = await _build_combatant_for(db, attacker)
    victim_combatant = await _build_combatant_for(db, victim)
    # Патч 30, баг 3: _build_combatant_for всегда ставит side=0 — без явного
    # разведения сторон здесь оба комбатанта дуэли остаются на стороне 0, и
    # _default_enemy_target (фильтр "side != моей") ни для кого не находит
    # цель, из-за чего ЛЮБОЕ атакующее действие молча отбрасывается ДО
    # вызова duel_engine.act. Ходы при этом всё равно идут по таймеру
    # (_on_timeout не проверяет наличие цели) — отсюда "счётчик растёт, но
    # никто не может походить".
    attacker_combatant.side = 0
    victim_combatant.side = 1

    session_id = _new_battle_id()
    battle = Battle(
        battle_type="duel",
        location=(attacker.pos_x, attacker.pos_y),
        participants={
            attacker.id: _participant(attacker, attacker_peer_id),
            victim.id: _participant(victim, victim_peer_id),
        },
        side_of={attacker.id: 0, victim.id: 1},
    )
    _battles[session_id] = battle
    _peer_battle[attacker_peer_id] = session_id
    _peer_battle[victim_peer_id] = session_id

    first_id = _duel_engine.start_duel(session_id, attacker_combatant, victim_combatant)
    duel = _duel_engine.duels[session_id]
    intro = f"⚔️ {attacker.name} нападает на {victim.name}! Первым ходит {duel.combatants[first_id].name}."
    board = _render_duel(duel, [], finished=False)

    # Патч 31, п.6: боевая клавиатура — только тому, кто ходит первым;
    # второй игрок ждёт с убранными кнопками, чтобы не жать их вне очереди.
    for cid, participant in battle.participants.items():
        combatant = duel.combatants[cid]
        if cid == first_id:
            text = f"{board}\n\n▶️ Твой ход!"
            keyboard = pvp_combat_keyboard(participant.base_class, combatant.cooldowns)
        else:
            text = f"{board}\n\n⏳ Ход противника. Ожидание..."
            keyboard = pvp_waiting_keyboard()
        await _bot_api.messages.send(
            peer_id=participant.peer_id, message=f"{intro}\n\n{text}", random_id=0, keyboard=keyboard,
        )


def _render_duel(
    duel: DuelState, lines: list[str], finished: bool, next_actor_id: int | None = None,
) -> str:
    """finished — явно передаётся вызывающим (DuelResult.finished), а не
    читается из duel.finished: в колбэке on_turn_resolved этот флаг движок
    выставляет только ПОСЛЕ вызова колбэка, так что на последнем ходу
    duel.finished ещё False, даже когда бой уже фактически завершён.

    next_actor_id — та же история (патч 31, п.6): duel.current_actor_id
    внутри on_duel_turn_resolved ещё указывает на актёра ТОЛЬКО ЧТО
    завершившегося хода — turn_number движок инкрементирует уже ПОСЛЕ
    колбэка. Вызывающий, знающий реального следующего актёра, передаёт его
    явно; на живых вызовах вне колбэка (старт дуэли, /клавиатура) — None,
    тогда используется duel.current_actor_id как есть (там он корректен)."""
    a_id, b_id = duel.order
    a, b = duel.combatants[a_id], duel.combatants[b_id]
    header = f"⚔️ ДУЭЛЬ — ход {duel.turn_number}"
    a_line = f"{a.name}: {display.health_bar(a.current_hp, a.max_hp)}"
    b_line = f"{b.name}: {display.health_bar(b.current_hp, b.max_hp)}"
    actor_id = next_actor_id if next_actor_id is not None else duel.current_actor_id
    turn_line = "" if finished else f"Ходит: {duel.combatants[actor_id].name}"
    log = " ".join(lines) if lines else "Бой начался."
    parts = [header, a_line, b_line]
    if turn_line:
        parts.append(turn_line)
    parts.append("")
    parts.append(log)
    return "\n".join(parts)


# --- Присоединение к идущему бою ---


@labeler.message(payload_contains={"type": "pvp_join"})
async def join_via_button(message: Message) -> None:
    payload = message.get_payload_json() or {}
    await _handle_join_choice(message, payload.get("session_id"), payload.get("side"))


@labeler.message(text=["1", "2"])
async def join_via_text(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _pending_join_prompt.get(peer_id)
    if battle_id is None:
        return  # не ждём выбора стороны — не наш текст, оставляем как есть
    await _handle_join_choice(message, battle_id, int(message.text))


async def _handle_join_choice(message: Message, battle_id, side) -> None:
    peer_id = message.peer_id
    if not isinstance(battle_id, int) or side not in (1, 2):
        return
    _pending_join_prompt.pop(peer_id, None)
    if has_active_battle(peer_id):
        await message.answer("Ты уже дерёшься.")
        return
    battle = _battles.get(battle_id)
    if battle is None:
        await message.answer("Этот бой уже закончился.")
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if await _still_dead(db, character):
            await message.answer("☠ Сначала очнись.")
            return
        if (character.pos_x, character.pos_y) != battle.location:
            await message.answer("Ты уже не на той клетке.")
            return
        combatant = await _build_combatant_for(db, character)
        participant = _participant(character, peer_id)

    combatant.side = side - 1

    if battle.battle_type == "duel":
        battle.join_queue.append((participant, combatant))
        _peer_battle[peer_id] = battle_id
        await message.answer(
            "Ты готовишься вступить в бой — присоединишься, как только закончится текущий ход."
        )
        return

    _join_mass_battle_now(battle_id, battle, participant, combatant)
    await message.answer(
        f"⚔️ Ты вступаешь в бой на стороне {side}!",
        keyboard=pvp_combat_keyboard(participant.base_class, {}),
    )


def _join_mass_battle_now(battle_id: int, battle: Battle, participant: Participant, combatant: CombatantState) -> None:
    session = _mass_engine.sessions.get(battle_id)
    if session is None:
        return
    battle.participants[participant.character_id] = participant
    battle.side_of[participant.character_id] = combatant.side
    session.add(combatant)
    _peer_battle[participant.peer_id] = battle_id


async def _convert_duel_to_mass(session_id: int, battle: Battle) -> None:
    duel = _duel_engine.duels.pop(session_id, None)
    if duel is None:
        return
    try:
        _duel_engine.scheduler.remove_job(_duel_engine._job_id(session_id))
    except Exception:
        pass

    state = CombatSessionState(session_id=session_id, mode=CombatMode.PVP_GROUP)
    for cid, combatant in duel.combatants.items():
        combatant.side = battle.side_of.get(cid, combatant.side)
        state.add(combatant)

    joined_now = list(battle.join_queue)
    battle.join_queue.clear()
    for participant, combatant in joined_now:
        battle.participants[participant.character_id] = participant
        battle.side_of[participant.character_id] = combatant.side
        state.add(combatant)
        _peer_battle[participant.peer_id] = session_id

    battle.battle_type = "mass"
    battle.last_combatants = dict(state.combatants)
    _mass_engine.start_session(state)

    for p in battle.participants.values():
        await _bot_api.messages.send(
            peer_id=p.peer_id,
            message="⚔️ В бой вступает третий! Теперь это массовая схватка — все стороны действуют "
            "одновременно, ход — 1 минута.\n\n" + _render_mass(state, []),
            random_id=0,
            keyboard=pvp_combat_keyboard(p.base_class, state.combatants[p.character_id].cooldowns),
        )


# --- Ходы дуэли ---


@labeler.message(text=[BTN_PVP_ATTACK])
async def pvp_attack(message: Message) -> None:
    await _pvp_action(message, DeclaredAction(type=ActionType.ATTACK))


@labeler.message(payload_contains={"type": "pvp_skill"})
async def pvp_skill(message: Message) -> None:
    payload = message.get_payload_json() or {}
    skill_id = payload.get("id")
    if skill_id not in BASE_SKILL_DEFS:
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
        # Патч 30, баг 2: бой активен — без клавиатуры игрок теряет кнопки.
        participant = battle.participants.get(cid)
        keyboard = pvp_combat_keyboard(participant.base_class, combatant.cooldowns) if participant else None
        await message.answer(f"⏳ Навык ещё не готов (КД {cd}).", keyboard=keyboard)
        return
    await _pvp_action(message, DeclaredAction(type=ActionType.SKILL, skill_id=skill_id))


async def _pvp_action(message: Message, action: DeclaredAction) -> None:
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
        target = _default_enemy_target(battle_id, battle, cid)
        if target is None:
            return
        action = action.model_copy(update={"target_id": target})

    if battle.battle_type == "duel":
        try:
            await _duel_engine.act(battle_id, cid, action)
        except (KeyError, ValueError):
            pass
        return

    # Патч 31, п.6: в групповом PvP клавиатура убирается сразу после
    # объявления действия, до резолва окна — иначе игрок мог жать кнопки
    # повторно, не понимая, что действие уже принято.
    _declared_this_tick.setdefault(battle_id, set()).add(cid)
    try:
        await _mass_engine.declare_action(battle_id, cid, action)
    except (KeyError, ValueError):
        _declared_this_tick.get(battle_id, set()).discard(cid)
        return
    # Если declare_action резолвнул тик досрочно (все объявили), on_mass_tick_resolved
    # уже очистил _declared_this_tick[battle_id] и разослал новую клавиатуру —
    # отдельное подтверждение здесь было бы лишним/устаревшим сообщением.
    if cid in _declared_this_tick.get(battle_id, set()):
        participant = battle.participants.get(cid)
        if participant is not None:
            await _bot_api.messages.send(
                peer_id=participant.peer_id,
                message="✅ Действие принято. Ожидание остальных...",
                random_id=0,
                keyboard=pvp_waiting_keyboard(),
            )


def _default_enemy_target(battle_id: int, battle: Battle, cid: int) -> int | None:
    combatants = _live_state(battle_id, battle)
    me = combatants.get(cid)
    if me is None:
        return None
    enemies = [c.id for c in combatants.values() if c.side != me.side and c.alive]
    if not enemies:
        return None
    return _rng.choice(enemies)


# --- Предметы в бою (патч 30, баг 3, п.3): зелья/эликсиры работают в PvP по
# тем же правилам, что и в PvE (патч 16) — лечебные тратят ход, боевые
# эликсиры бесплатны с лимитом ELIXIR_PER_BATTLE_LIMIT/бой, недоступны под
# контролем. Payload {"type": "pvp_use_item"} НАМЕРЕННО отличается от PvE
# {"type": "use_item"} — см. докстринг bot/keyboards/pvp.py. ---


def _battle_board_text(battle_id: int, battle: Battle, lines: list[str]) -> str:
    if battle.battle_type == "duel":
        duel = _duel_engine.duels.get(battle_id)
        return _render_duel(duel, lines, finished=False) if duel is not None else "\n".join(lines)
    session = _mass_engine.sessions.get(battle_id)
    return _render_mass(session, lines) if session is not None else "\n".join(lines)


@labeler.message(text=[BTN_PVP_ITEM])
async def pvp_open_items(message: Message) -> None:
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
    participant = battle.participants.get(cid)
    if combatant is None or participant is None:
        return
    battle_kb = pvp_combat_keyboard(participant.base_class, combatant.cooldowns)
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
    await editable_message.send_or_edit(
        _bot_api, "pvp_combat_item", peer_id, text, pvp_items_keyboard(visible)
    )


@labeler.message(payload_contains={"type": "pvp_use_item"})
async def pvp_use_item(message: Message) -> None:
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
    participant = battle.participants.get(cid)
    if combatant is None or participant is None:
        return
    battle_kb = pvp_combat_keyboard(participant.base_class, combatant.cooldowns)
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
        _bot_api, "pvp_combat_item", peer_id, f"Использовано: {elixir.emoji} {elixir.name}.", no_keyboard()
    )

    if elixir.category == "heal":
        # Лечебное зелье — тратит ход, как обычное действие (см. _pvp_action:
        # здесь НЕ вызываем его напрямую — цель для ITEM всегда сам актёр,
        # а _pvp_action всегда подставляет ВРАЖЕСКУЮ цель для не-defensive).
        action = DeclaredAction(type=ActionType.ITEM, item_id=elixir_id, target_id=cid)
        try:
            if battle.battle_type == "duel":
                await _duel_engine.act(battle_id, cid, action)
            else:
                await _mass_engine.declare_action(battle_id, cid, action)
        except (KeyError, ValueError):
            pass
        return

    # Боевой эликсир — бесплатное действие: эффект сразу, ход не тратится.
    line = elixir_effects.apply_combat_elixir(combatant, elixir_id)
    combatant.combat_elixirs_used += 1
    text = f"{line} Твой ход.\n\n{_battle_board_text(battle_id, battle, [])}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0,
        keyboard=pvp_combat_keyboard(participant.base_class, combatant.cooldowns),
    )


# --- Колбэки дуэльного движка ---


async def on_duel_turn_resolved(session_id: int, turn: int, result: DuelResult) -> None:
    # ПРИМЕЧАНИЕ: duel_engine вызывает этот колбэк ДО pop из self.duels и ДО
    # простановки state.finished — на последнем ходу дуэль ещё присутствует
    # в _duel_engine.duels, поэтому duel почти никогда не None здесь (кроме
    # гонки с ручной конверсией); используем result.finished, а не duel.finished.
    battle = _battles.get(session_id)
    if battle is None:
        return
    duel = _duel_engine.duels.get(session_id)
    # Патч 31, п.6: следующий актёр — order[turn_number % 2], НЕ
    # duel.current_actor_id (см. докстринг _render_duel выше — тот всё ещё
    # указывает на актёра только что резолвленного хода в этой точке).
    next_actor_id = duel.order[duel.turn_number % 2] if duel is not None else None

    for p in battle.participants.values():
        combatant = duel.combatants.get(p.character_id) if duel is not None else None
        text = (
            _render_duel(duel, result.lines, finished=result.finished, next_actor_id=next_actor_id)
            if duel is not None
            else "\n".join(result.lines)
        )
        if result.finished or combatant is None:
            keyboard = kb.waiting_keyboard()
        elif p.character_id == next_actor_id:
            text += "\n\n▶️ Твой ход!"
            keyboard = pvp_combat_keyboard(p.base_class, combatant.cooldowns)
        else:
            text += "\n\n⏳ Ход противника. Ожидание..."
            keyboard = pvp_waiting_keyboard()
        await _bot_api.messages.send(peer_id=p.peer_id, message=text, random_id=0, keyboard=keyboard)

    if result.finished:
        return  # on_duel_finished разрулит исход и очистку

    if battle.join_queue:
        await _convert_duel_to_mass(session_id, battle)


async def on_duel_finished(session_id: int, result: DuelResult) -> None:
    battle = _battles.pop(session_id, None)
    if battle is None:
        return
    for p in battle.participants.values():
        _peer_battle.pop(p.peer_id, None)

    if result.draw or result.winner_id is None:
        async with get_session_factory()() as db:
            await pvp_service.log_battle(db, "duel", list(battle.participants), [])
            await db.commit()
        # Патч 30: лимит ходов — отдельный лорный текст от "взаимного истощения".
        draw_text = (
            bc.PVP_DRAW_TURN_LIMIT_TEXT if result.draw_reason == "turn_limit"
            else "🤝 Ничья: взаимное истощение. Трофеи остаются при каждом."
        )
        for p in battle.participants.values():
            await _bot_api.messages.send(
                peer_id=p.peer_id, message=draw_text, random_id=0, keyboard=kb.waiting_keyboard(),
            )
        return

    winner_cid = result.winner_id
    loser_cid = next(cid for cid in battle.participants if cid != winner_cid)
    await _finish_duel(battle, winner_cid, loser_cid)


async def _finish_duel(battle: Battle, winner_cid: int, loser_cid: int) -> None:
    winner_p = battle.participants[winner_cid]
    loser_p = battle.participants[loser_cid]

    async with get_session_factory()() as db:
        winner = await db.get(Character, winner_cid)
        loser = await db.get(Character, loser_cid)
        if winner is None or loser is None:
            return
        pvp_service.record_win(winner)
        pvp_service.record_loss(loser)
        no_reward = pvp_service.no_reward_for_kill(winner.level, loser.level)
        moved = {} if no_reward else await trophy_service.transfer_all(db, loser.id, winner.id)
        death_service.apply_pvp_death(loser)
        await admin_service.log_death(db, loser, "pvp")
        respawn_handlers.register_pvp_death(loser_p.peer_id)
        await pvp_service.log_battle(db, "duel", [winner_cid, loser_cid], [winner_cid])
        daily_progress = await daily_service.record_pvp_win(db, winner)
        winner_pos = (winner.pos_x, winner.pos_y)
        winner_has_mount = await mount_service.has_any_mount(db, winner.id)
        await db.commit()

    win_text = f"🏆 Ты побеждаешь {loser_p.name}!"
    if no_reward:
        win_text += f"\n\n{NOTHING_TO_TAKE}"
    else:
        line = _format_transfer_line(moved)
        if line:
            win_text += f"\n\n{line}"
    daily_notice = dailies_texts.progress_notice(daily_progress)
    if daily_notice:
        win_text += f"\n\n{daily_notice}"
    await _bot_api.messages.send(
        peer_id=winner_p.peer_id, message=win_text, random_id=0,
        keyboard=kb.movement_keyboard(*winner_pos, winner_p.peer_id, has_mount=winner_has_mount),
    )
    for c in daily_progress.completed:
        await stats_window.notify_levelup(winner_p.peer_id, c.levels_gained, c.new_level)
    await _bot_api.messages.send(
        peer_id=loser_p.peer_id,
        message=f"☠ Тебя побеждает {winner_p.name}. Ты уходишь во тьму.",
        random_id=0, keyboard=kb.waiting_keyboard(),
    )


# --- Массовый бой: рендер + колбэки тик-движка ---


def _render_mass(session: CombatSessionState, lines: list[str]) -> str:
    header = f"⚔️ БОЙ — ход {session.tick_number}"
    side_lines = []
    for side in (0, 1):
        members = [c for c in session.combatants.values() if c.side == side]
        roster = ", ".join(f"{c.name} {display.health_bar(c.current_hp, c.max_hp)}" for c in members)
        side_lines.append(f"Сторона {side + 1}: {roster}")
    log = " ".join(lines) if lines else "Бой продолжается."
    return "\n".join([header, *side_lines, "", log])


async def on_mass_tick_resolved(session_id: int, tick: int, result: TickResult) -> None:
    battle = _battles.get(session_id)
    if battle is None:
        return
    # Патч 31, п.6: новое окно открылось — все живые снова могут объявлять.
    _declared_this_tick.pop(session_id, None)
    for hit in result.hits:
        if hit.source_id == hit.target_id:
            continue
        key = (hit.source_id, hit.target_id)
        battle.damage_by_pair[key] = battle.damage_by_pair.get(key, 0) + hit.amount

    session = _mass_engine.sessions.get(session_id)
    if session is not None:
        battle.last_combatants = dict(session.combatants)
    text = _render_mass(session, result.lines) if session is not None else "\n".join(result.lines)

    for cid, participant in battle.participants.items():
        combatant = battle.last_combatants.get(cid)
        keyboard = (
            pvp_combat_keyboard(participant.base_class, combatant.cooldowns)
            if combatant is not None and combatant.alive
            else pvp_waiting_keyboard()
        )
        await _bot_api.messages.send(peer_id=participant.peer_id, message=text, random_id=0, keyboard=keyboard)


async def on_mass_battle_finished(session_id: int, result: TickResult) -> None:
    battle = _battles.pop(session_id, None)
    _declared_this_tick.pop(session_id, None)
    if battle is None:
        return
    for p in battle.participants.values():
        _peer_battle.pop(p.peer_id, None)

    combatants = battle.last_combatants
    dead_ids = [cid for cid in battle.participants if cid in combatants and not combatants[cid].alive]
    survivor_ids = [cid for cid in battle.participants if cid in combatants and combatants[cid].alive]

    async with get_session_factory()() as db:
        characters: dict[int, Character] = {}
        for cid in battle.participants:
            character = await db.get(Character, cid)
            if character is not None:
                characters[cid] = character

        winner_ids: list[int] = []
        daily_progress_by_cid: dict[int, object] = {}
        if not result.draw:
            winner_ids = list(survivor_ids)
            for cid in winner_ids:
                if cid in characters:
                    pvp_service.record_win(characters[cid])
                    daily_progress_by_cid[cid] = await daily_service.record_pvp_win(db, characters[cid])
            for cid in dead_ids:
                if cid in characters:
                    pvp_service.record_loss(characters[cid])

        transfer_lines: dict[int, list[str]] = {}
        for victim_cid in dead_ids:
            victim = characters.get(victim_cid)
            if victim is None:
                continue
            shares: dict[int, float] = {}
            for attacker_cid in survivor_ids:
                dmg = battle.damage_by_pair.get((attacker_cid, victim_cid), 0)
                if dmg <= 0:
                    continue
                attacker = characters.get(attacker_cid)
                if attacker is None or pvp_service.no_reward_for_kill(attacker.level, victim.level):
                    continue
                shares[attacker_cid] = dmg
            moved = await trophy_service.split_among(db, victim_cid, shares) if shares else {}
            for winner_cid, drop in moved.items():
                line = _format_transfer_line(drop)
                if line:
                    transfer_lines.setdefault(winner_cid, []).append(f"{victim.name}: {line}")
            death_service.apply_pvp_death(victim)
            await admin_service.log_death(db, victim, "pvp")
            respawn_handlers.register_pvp_death(battle.participants[victim_cid].peer_id)

        await pvp_service.log_battle(db, "mass", list(battle.participants), winner_ids)
        has_mount_by_cid = {
            cid: await mount_service.has_any_mount(db, cid) for cid in survivor_ids if cid in characters
        }
        await db.commit()
        positions = {cid: (c.pos_x, c.pos_y) for cid, c in characters.items()}

    # Патч 30: ничья (взаимное истощение ИЛИ лимит ходов) — раньше этот случай
    # никак не отличался от обычного финала, и выжившие получали "ты
    # победил", даже когда бой на самом деле закончился вничью.
    draw_text = (
        bc.PVP_DRAW_TURN_LIMIT_TEXT if result.draw_reason == "turn_limit"
        else "🤝 Ничья: взаимное истощение. Трофеи остаются при каждом."
    )
    for cid, participant in battle.participants.items():
        if result.draw:
            if cid in survivor_ids:
                pos = positions.get(cid, (0, 0))
                keyboard = kb.movement_keyboard(
                    *pos, participant.peer_id, has_mount=has_mount_by_cid.get(cid, False)
                )
            else:
                keyboard = kb.waiting_keyboard()
            await _bot_api.messages.send(
                peer_id=participant.peer_id, message=draw_text, random_id=0, keyboard=keyboard,
            )
        elif cid in survivor_ids:
            text = "🏆 Бой окончен — твоя сторона побеждает!"
            lines = transfer_lines.get(cid, [])
            if lines:
                text += "\n\n" + "\n".join(lines)
            daily_progress = daily_progress_by_cid.get(cid)
            daily_notice = dailies_texts.progress_notice(daily_progress) if daily_progress else None
            if daily_notice:
                text += f"\n\n{daily_notice}"
            pos = positions.get(cid, (0, 0))
            await _bot_api.messages.send(
                peer_id=participant.peer_id, message=text, random_id=0,
                keyboard=kb.movement_keyboard(
                    *pos, participant.peer_id, has_mount=has_mount_by_cid.get(cid, False)
                ),
            )
            if daily_progress:
                for c in daily_progress.completed:
                    await stats_window.notify_levelup(participant.peer_id, c.levels_gained, c.new_level)
        elif cid in dead_ids:
            await _bot_api.messages.send(
                peer_id=participant.peer_id,
                message="☠ Тебя одолели в бою. Ты уходишь во тьму.",
                random_id=0, keyboard=kb.waiting_keyboard(),
            )
