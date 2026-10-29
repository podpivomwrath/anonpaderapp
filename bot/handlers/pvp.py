"""Открытое PvP на карте (патч 22): осмотреться, /напасть, дуэли и массовые бои.

Архитектура:
  - Любой бой игроков, и 1×1, и N vs M, - одновременный резолв на ОТДЕЛЬНОМ
    TickEngine (2026-10-29, владелец: дуэль переехала с duel_engine - два
    движка расходились в правилах, а очередь на вход в дуэль теряла игроков)
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

from bot import info_reply
from bot.keyboards import combat_modes
from bot.keyboards.combat_items import page_of
from bot.vk_media import photo_attachment
from bot import dailies_texts, editable_message
from bot.activity import ActivityBusy, activity_action, blocked_reason, transition
from bot.battle_keyboard import active_battle_keyboard, answer_battle_gone, in_any_battle
from bot.dispatch_rules import TEXT_ONLY
from bot.handlers import combat as combat_handlers
from bot.handlers import respawn as respawn_handlers
from bot.handlers import stats_window
from bot.keyboards import world as kb
from bot.keyboards.items import no_keyboard
from bot.keyboards.pvp import (
    BTN_PVP_ATTACK,
    BTN_PVP_ITEM,
    BTN_PVP_TARGET,
    join_side_keyboard,
    pvp_combat_keyboard,
    pvp_items_keyboard,
    pvp_target_keyboard,
    pvp_waiting_keyboard,
)
from bot.pvp_texts import (
    AFK_TARGET_TEXT,
    ALONE_ON_CELL,
    CITY_NO_PVP_TEXT,
    GATES_NO_PVP_TEXT,
    LAKE_NO_PVP_TEXT,
    MONOLITH_NO_PVP_TEXT,
    NOTHING_TO_TAKE,
    SIEGE_NO_PVP_TEXT,
    WORLD_BOSS_NO_PVP_TEXT,
)
from game.combat import balance_config as bc
from game.combat import battle_log, display, elixir_effects
from game.combat.base_skills import BASE_SKILL_DEFS
from game.combat.resolver import TickResult
from game.combat.session import (
    ActionType,
    CombatantState,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
    Stats,
    build_combatant,
)
from game.combat.skills import DEFENSIVE_SKILLS
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
from game.combat.tick_engine import TickEngine
from game.combat import consumable_limit
from game.economy import elixir_config as ec
from game.economy import fishing as game_fishing
from game.economy import premium_config as pc
from game.world import grid
from models import Character, CharacterStats
from services import pk_service, pts_service, pvp_shield, subclass_service, trial_service
from services import (
    admin_service,
    daily_service,
    death_service,
    elixir_service,
    fishing_service,
    guild_service,
    guild_siege_service,
    item_service,
    mining_service,
    mount_service,
    movement_service,
    premium_service,
    preset_service,
    pvp_service,
    trophy_service,
    world_boss_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory


#: Затухание лечения и щитов (shared_rules.recovery_mult) - в начале боя.
RECOVERY_INTRO = (
    f"Лечение и щиты слабеют с каждым ходом, на {bc.PVP_MAX_TURNS}-м ходу "
    f"от них остаётся {round(bc.PVP_RECOVERY_FLOOR * 100)}%."
)


#: Цель заказа в штольне (2026-10-29, владелец).
SHAFT_NO_PVP_TEXT = "Цель в штольне. В узком забое не подраться - жди, пока выйдет наверх."


def _in_shaft(character) -> bool:
    """Внутри штольни рудника (экран рудника открыт)."""
    return character.screen == "mine" and mining_service.is_safe_mine(character.pos_x, character.pos_y)


def _is_safe_craft_cell(character) -> bool:
    """Мирная клетка ремесла: озеро или рудник первых двух колец.

    Правило одно на все ремёсла сознательно — с 2026-10-22 мирные все озёра и рудники
    игрок должен помнить одно, а не по отдельному на каждое занятие.
    """
    return (
        fishing_service.is_safe_lake(character.pos_x, character.pos_y)
        or mining_service.is_safe_mine(character.pos_x, character.pos_y)
    )


async def _at_world_boss(db, character) -> bool:
    """Клетка живого мирового босса - без PvP (2026-10-22, владелец): все
    бьют чудовище, а не друг друга."""
    boss = await world_boss_service.active_boss(db)
    return boss is not None and (boss.x, boss.y) == (character.pos_x, character.pos_y)


labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»

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
    battle_type: str  # "mass" (с 2026-10-29 и 1×1 - тоже массовый бой)
    location: tuple[int, int]
    participants: dict[int, Participant] = field(default_factory=dict)   # character_id -> Participant
    side_of: dict[int, int] = field(default_factory=dict)                # character_id -> 0/1
    damage_by_pair: dict[tuple[int, int], int] = field(default_factory=dict)  # (attacker, victim) -> total
    last_combatants: dict[int, "CombatantState"] = field(default_factory=dict)  # снимок на конец последнего хода
    # Гильдии: бой - осада. Стороны подписаны тегами, опоздавшие встают
    # только к своей гильдии, итог считает bot/handlers/guild_siege.py.
    siege_id: int | None = None
    side_titles: tuple[str, str] | None = None
    side_guilds: tuple[int, int] | None = None
    # Арена (2026-10-18): тренировочный бой - без смерти, потерь и рейтинга,
    # с клетки не виден, вступить нельзя, итог - bot/handlers/arena.py.
    arena: bool = False


#: Картинка начала осады (2026-10-19).
SIEGE_PHOTO_ID = "457239249"

#: Бой арены ни на какой клетке не стоит: «Осмотреться» и вступление его не видят.
ARENA_LOCATION = (10**6, 10**6)
#: Итог боя арены (ставит bot/handlers/arena.py): (battle, winner_id | None) -> None.
on_arena_finished = None

_battles: dict[int, Battle] = {}
_peer_battle: dict[int, int] = {}
def draw_shield_left(character_id: int) -> int:
    """Сколько секунд ещё действует щит от нападения (0 - нет щита)."""
    return pvp_shield.left(character_id)[0]


def _grant_draw_shield(battle: "Battle", survivors) -> list[int]:
    """Ничья: щит выжившим с той стороны, на которую напали (сторона 1)."""
    if battle.siege_id is not None:
        return []
    shielded = [cid for cid in survivors if battle.side_of.get(cid) == 1]
    for cid in shielded:
        pvp_shield.grant(cid, pvp_shield.DRAW, bc.PVP_DRAW_SHIELD_SECONDS, cell=battle.location)
    return shielded


DRAW_SHIELD_LINE = f"🛡 Ничья: на тебя нельзя нападать {bc.PVP_DRAW_SHIELD_SECONDS // 60} мин., пока не ушёл с этой клетки."
# peer_id -> battle_id, ждём выбора стороны (текстом "1"/"2") для этого боя
_pending_join_prompt: dict[int, int] = {}
#: Последнее «Осмотреться»: peer -> (клетка, id игроков, id боёв) в том
#: порядке, в каком их пронумеровали. Пока игрок стоит на той же клетке,
#: «/напасть N» бьёт того, кто был под номером N, без нового осмотра
#: (2026-10-15, решение владельца).
_last_look: dict[int, tuple[tuple[int, int], list[int], list[int]]] = {}
# Патч 31, п.6: battle_id -> character_id'ы, уже объявившие действие в ТЕКУЩЕМ
# (ещё не резолвленном) окне группового PvP — клавиатура убирается у них до
# следующего тика. Отдельно от game.combat.tick_engine.ActionStore (тот же
# набор, но целиком в памяти этого процесса) — нужен только для решения
# «показывать ли боевые кнопки», не участвует в самом резолве хода.
_declared_this_tick: dict[int, set[int]] = {}
# Патч 38: character_id -> character_id выбранной цели, только в массовом
# PvP (дуэль — противник ровно один, выбор не нужен). Смена цели — бесплатное
# действие, не завязано на _declared_this_tick/TickEngine ни в каком виде.
_chosen_target: dict[int, int] = {}


def setup(mass_engine: TickEngine, bot_api) -> None:
    global _mass_engine, _bot_api
    _mass_engine = mass_engine
    _bot_api = bot_api


def has_active_battle(peer_id: int) -> bool:
    return peer_id in _peer_battle


def force_defeat(peer_id: int) -> bool:
    """Патч 39: админский экстренный сброс (bot/handlers/world.py::force_unstick,
    admin_override=True) — помечает бойца peer_id погибшим в ЕГО текущем
    PvP-бою (current_hp=0), не трогая структуры battle/session напрямую.
    Дуэльный или тиковый движок сам разрешит исход обычным путём на
    следующем ходу/тике (немедленно, если раньше действует соперник, иначе
    по истечении таймера хода) — вся логика смерти/наград/уведомлений уже
    существует и рассчитана именно на такое естественное угасание бойца,
    так что здесь ничего резолвить вручную не нужно. False — peer_id не в бою."""
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return False
    battle = _battles.get(battle_id)
    if battle is None:
        return False
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return False
    combatant = _live_state(battle_id, battle).get(cid)
    if combatant is None or not combatant.alive:
        return False
    combatant.current_hp = 0
    return True


def rebuild_keyboard(peer_id: int) -> str | None:
    """Патч 25: актуальная боевая клавиатура для игрока в PvP-бою, без
    прерывания боя — общая для /клавиатура и PvP-ветки /застрял (там бой
    НЕ прерывается, только пересобирается клавиатура — защита от абьюза).
    None — peer_id ни в какой активной PvP-битве.

    Патч 31, п.6: боевые кнопки - только тем, кто ещё не объявил действие в
    текущем окне (_declared_this_tick)."""
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return None
    battle = _battles.get(battle_id)
    if battle is None:
        return None
    participant = next((p for p in battle.participants.values() if p.peer_id == peer_id), None)
    if participant is None:
        return None
    session = _mass_engine.sessions.get(battle_id) if _mass_engine else None
    combatant = (
        session.combatants.get(participant.character_id) if session
        else battle.last_combatants.get(participant.character_id)
    )
    if combatant is None or not combatant.alive:
        return pvp_waiting_keyboard()
    if participant.character_id in _declared_this_tick.get(battle_id, set()):
        return pvp_waiting_keyboard()
    return pvp_combat_keyboard(participant.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id, show_target=True)


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
    buff_modifiers = dict(await preset_service.resolve_active_modifiers(db, character))
    if character.revenge_target_id is not None:
        bonus = pk_service.revenge_bonus(character, character.revenge_target_id)
        if bonus:
            buff_modifiers["revenge_vs"] = character.revenge_target_id
            buff_modifiers["revenge_bonus"] = bonus
    stats = Stats(
        strength=stats_row.strength + gear_bonus.get("str", 0),
        agility=stats_row.agility + gear_bonus.get("agi", 0),
        intellect=stats_row.intellect + gear_bonus.get("int", 0),
        vitality=stats_row.vitality + gear_bonus.get("vit", 0),
        will=stats_row.will + gear_bonus.get("wil", 0),
    )
    primary = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    pvp_bonus = guild_service.perk(character, "pvp_damage_pct") / 100
    gear_primary = bc.primary_stat_of(character)  # у мистика урон от Воли
    if pvp_bonus:
        # Древо гильдии: урон в PvP - через основную характеристику, как и
        # остальная сила персонажа.
        field_name = {"str": "strength", "agi": "agility", "int": "intellect", "wil": "will"}[gear_primary]
        setattr(stats, field_name, round(getattr(stats, field_name) * (1 + pvp_bonus)))
    # Патч 22: перед PvP-боем ОБА восстанавливаются до полного HP — build_combatant
    # всегда стартует с current_hp=max_hp, что ровно и нужно (никакого переноса
    # текущего HP из vitals_service, как в PvE).
    return build_combatant(
        id=character.id, side=0, kind="character", name=character.name,
        level=character.level, stats=stats, primary_stat=primary,
        subclass_id=character.subclass, buff_modifiers=buff_modifiers,
        base_class=character.base_class, gear_vit=gear_bonus.get("vit", 0),
    )


def _character_id_for_peer(battle: Battle, peer_id: int) -> int | None:
    for cid, p in list(battle.participants.items()):
        if p.peer_id == peer_id:
            return cid
    return None


def _live_state(battle_id: int, battle: Battle) -> dict[int, CombatantState]:
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


@labeler.message(text=[kb.BTN_LOOK_AROUND])
async def look_around(message: Message) -> None:
    peer_id = message.peer_id
    if in_any_battle(peer_id):
        # Кнопка со старой клавиатуры посреди боя: раньше молчали, и нажатие
        # уходило в пустоту. Отвечаем и возвращаем кнопки боя.
        await message.answer("⚔️ Ты в бою - оглядеться некогда.", keyboard=active_battle_keyboard(peer_id))
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if await _still_dead(db, character):
            await message.answer("☠ Сначала очнись.")
            return
        # Патч 58-59: озёра и рудники первых двух колец — мирные, как города.
        # Патч 33, ч.2: в городских клавиатурах кнопки нет - это защита от
        # устаревшей клавиатуры. Раньше здесь молча выходили, а на мирной
        # шахте или озере кнопка на клавиатуре есть: нажатие уходило в
        # пустоту (жалоба игрока). Теперь показываем, кто рядом, без номеров -
        # нападать здесь всё равно нельзя.
        safe_craft = _is_safe_craft_cell(character)
        at_boss = await _at_world_boss(db, character)
        if at_boss or grid.pvp_forbidden(character.pos_x, character.pos_y):
            solo, _battles = await _scene_at(db, character)
            await message.answer(_peaceful_scene_text(solo, await _guild_tags(db, solo),
                                                      busy=await _busy_marks(db, solo)))
            return
        from services import contract_service

        solo, battles = await _scene_at(db, character)
        hunted = await contract_service.hunted_ids(db, character.id)
        if safe_craft:
            # Озеро и рудник цель заказа не спасают (2026-10-25, владелец):
            # охотник видит её под номером, даже за удочкой или киркой. Бой
            # здесь (а он тут бывает только по заказу) видят все.
            # В штольне рудника цель заказа в безопасности: достать можно, только
            # когда выйдет наружу (2026-10-29, владелец). У озера защиты нет.
            targets = [c for c in solo if c.id in hunted and not _in_shaft(c)]
            if not targets and not (hunted and battles):
                await message.answer(_peaceful_scene_text(solo, await _guild_tags(db, solo), battles,
                                                          await _busy_marks(db, solo)))
                return
            solo = targets
        tags = await _guild_tags(db, solo)
        busy = await _busy_marks(db, solo)
        for c in solo:
            if c.id in hunted:
                busy[c.id] = " · 📜 цель заказа" + busy.get(c.id, "")
        _remember_look(peer_id, character, solo, battles)
    await message.answer(_scene_text(solo, battles, tags, busy))


def _peaceful_scene_text(solo: list[Character], tags: dict[int, str] | None = None,
                         battles: list | None = None, busy: dict[int, str] | None = None) -> str:
    """busy - кто чем занят (бой с мобами, рыбалка, забой): видно и на
    мирной клетке (2026-10-29, баг-репорт)."""
    if not solo and not battles:
        return "👁 Ты оглядываешься.\n\nТы один. Место мирное - здесь не нападают."
    lines = ["👁 Ты оглядываешься. Место мирное - здесь не нападают.", ""]
    if solo:
        lines.append("Рядом:")
        lines += [f"• {_class_line(c, tags)}{(busy or {}).get(c.id, '')}" for c in solo]
    if battles:
        # Бой на мирной клетке - только по заказу (2026-10-25).
        lines += ["", "Дерутся по заказу:"] if solo else ["Дерутся по заказу:"]
        lines += [f"• {_battle_scene_line(b)}" for _, b in battles]
    return "\n".join(lines)


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
        badge = pc.PREMIUM_BADGE + " " if entry.premium else ""
        name = f"{badge}{entry.name} «{entry.title}»" if entry.title else f"{badge}{entry.name}"
        lines.append(
            f"{entry.rank}. {name} - {entry.pts} PTS · {pts_service.rank_name(entry.pts)}"
            f" · {entry.wins} / {entry.losses}"
        )
    if (character.pvp_wins or 0) + (character.pvp_losses or 0) == 0:
        # Без боёв в таблице не стоят - и место не выдумываем (2026-10-15).
        lines.append("-")
        lines.append(f"Тебя пока нет в рейтинге: попадёшь после первого PvP-боя. У тебя {character.pts} PTS.")
    elif rank > len(entries):
        lines.append("-")
        lines.append(
            f"Ты: {rank} место - {character.pts} PTS · {pts_service.rank_name(character.pts)}"
            f" · {character.pvp_wins} / {character.pvp_losses}"
        )
    await info_reply.answer(message, "\n".join(lines))


# --- /напасть, /attack ---


@labeler.message(text=["/напасть <target>", "/attack <target>"])
@activity_action
async def attack_command(message: Message, target: str) -> None:
    peer_id = message.peer_id
    if in_any_battle(peer_id):
        await message.answer("Ты уже дерёшься.")
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        reason = await blocked_reason(db, character, peer_id)
        if reason:
            await message.answer(reason)
            return
        if await _still_dead(db, character):
            await message.answer("☠ Сначала очнись.")
            return
        # Патч 33, ч.2: PvP запрещено во ВСЕХ городах — и в своём, и в чужом
        # (отменяет патч 26, где чужой город был ареной без защиты).
        # Патч 58: озёра первых двух колец — первые мирные клетки вне
        # городов. Проверка стоит рядом с городской намеренно: это одно и то
        # же правило «здесь не нападают», и разъезжаться им нельзя.
        safe_craft = _is_safe_craft_cell(character)
        if grid.city_region_at(character.pos_x, character.pos_y) is not None:
            await message.answer(CITY_NO_PVP_TEXT)
            return
        if grid.at_city_gates(character.pos_x, character.pos_y):
            await message.answer(GATES_NO_PVP_TEXT)
            return
        if grid.is_monolith(character.pos_x, character.pos_y):
            await message.answer(MONOLITH_NO_PVP_TEXT)
            return
        if await _at_world_boss(db, character):
            await message.answer(WORLD_BOSS_NO_PVP_TEXT)
            return
        if await guild_siege_service.lock_at(db, character.pos_x, character.pos_y) is not None:
            await message.answer(SIEGE_NO_PVP_TEXT)
            return

        if target.strip().lower() == character.name.lower():
            await message.answer("На себя не нападают.")
            return
        victim, battle_entry = await _resolve_target(db, character, target, peer_id)
        if victim is None and battle_entry is None:
            if await _afk_target_named(db, character, target):
                await message.answer(AFK_TARGET_TEXT)
            elif target.isdigit() and _looked_entry(peer_id, character, int(target)) is not None:
                await message.answer(TARGET_GONE_TEXT)
            else:
                await message.answer("Здесь нет такой цели.")
            return

        if victim is not None:
            left, why = pvp_shield.left(victim.id)
            if left:
                await message.answer(f"🛡 {victim.name} под защитой {why} - ещё {left} сек.")
                return

        if safe_craft:
            # Мирная клетка (озеро, рудник): нападать можно только на цель
            # взятого заказа или вступить в бой, где она дерётся (2026-10-16;
            # 2026-10-24 запрещали, 2026-10-25 владелец вернул).
            from services import contract_service

            hunted = await contract_service.hunted_ids(db, character.id)
            allowed = victim.id in hunted if victim is not None else any(
                cid in hunted for cid in battle_entry[1].participants)
            if not allowed:
                await message.answer(LAKE_NO_PVP_TEXT)
                return
            if victim is not None and _in_shaft(victim):
                await message.answer(SHAFT_NO_PVP_TEXT)
                return

        if victim is not None and await _same_group(db, character, victim.id):
            await message.answer(GROUPMATE_NO_PVP_TEXT)
            return

        # Напал сам - свой щит теряешь: прячась за ним, не нападают.
        pvp_shield.drop(character.id)
        if battle_entry is not None:
            battle_id, battle = battle_entry
            # Согруппник уже в бою - сразу на его сторону, без вопроса
            # (2026-10-13). Согруппники на обеих сторонах - спрашиваем.
            side = await _groupmate_side(db, character, battle)
            if side is not None:
                await db.commit()  # своя сессия у вступления ждала бы эту строку
                await _handle_join_choice(message, battle_id, side)
                return
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


async def _start_forced_duel(db, attacker, attacker_peer_id, victim, victim_peer_id) -> None:
    from bot.handlers import raid_combat
    with transition([attacker_peer_id, victim_peer_id]):
        # Бой с мобами при исследовании (соло и группой) нападение обрывает;
        # рейд и разлом - нет (2026-10-15, решение владельца).
        if raid_combat.has_active_battle(victim_peer_id) or has_active_battle(victim_peer_id):
            raise ActivityBusy("Цель уже участвует в другом бою.")
        await db.flush()
        await db.refresh(victim)
        if (victim.pos_x, victim.pos_y) != (attacker.pos_x, attacker.pos_y):
            raise ActivityBusy("Цель уже ушла с этой клетки.")
        await _start_forced_duel_impl(db, attacker, attacker_peer_id, victim, victim_peer_id)


async def _start_forced_duel_impl(
    db, attacker: Character, attacker_peer_id: int, victim: Character, victim_peer_id: int
) -> None:
    from bot.handlers import group_combat

    # Напали в пути на соседнюю клетку - шаг сорван, бой здесь. Иначе
    # прибытие посреди боя присылало сводку клетки с кнопками движения,
    # и кнопок боя у жертвы не было (2026-10-15, жалоба игрока).
    if movement_service.is_traveling(victim):
        movement_service.cancel_travel(victim)
        await db.commit()
    ride = await mount_service.active_travel(db, victim.id)
    if ride is not None and await mount_service.stop_travel(db, ride, victim):
        await db.commit()
    # Напали за работой (по заказу на озере и в руднике, 2026-10-25): снасть
    # сматывается, кирка брошена, экран закрыт - после боя игрок на клетке.
    dropped = await _drop_craft_work(db, victim)
    if dropped is not None:
        await db.commit()
    if dropped:
        await _bot_api.messages.send(peer_id=victim_peer_id, message=f"⚔️ На тебя напали! {dropped}", random_id=0)

    if combat_handlers.has_active_encounter(victim_peer_id):
        await combat_handlers.interrupt_for_pvp(victim_peer_id)
        await _bot_api.messages.send(
            peer_id=victim_peer_id, message="⚔️ На тебя напали! Бой с тварью прерван.", random_id=0,
        )
    if group_combat.has_active_group_battle(victim_peer_id):
        # Группа, что дралась с мобами вместе с жертвой, целиком встаёт на её
        # сторону: бой сразу массовый (2026-10-15, решение владельца).
        roster = await group_combat.interrupt_for_pvp(victim_peer_id, notify=False)
        defenders = []
        for cid, peer in roster:
            if peer == attacker_peer_id:
                continue
            member = await db.get(Character, cid)
            if member is None:
                continue
            await db.refresh(member)
            if death_service.is_dead(member) or (member.pos_x, member.pos_y) != (attacker.pos_x, attacker.pos_y):
                continue
            if movement_service.is_traveling(member):
                movement_service.cancel_travel(member)
            defenders.append((member, peer))
        await db.commit()
        if len(defenders) > 1:
            await _start_group_ambush(db, attacker, attacker_peer_id, victim, defenders)
            return
        await _bot_api.messages.send(
            peer_id=victim_peer_id, message="⚔️ На тебя напали! Бой группы с мобами прерван.", random_id=0,
        )

    from bot.handlers import group as group_handlers  # избегаем цикла импортов

    await group_handlers.notify_attacked(db, victim, attacker)
    await _launch_duel(
        db, attacker, attacker_peer_id, victim, victim_peer_id,
        location=(attacker.pos_x, attacker.pos_y),
        intro=f"⚔️ {attacker.name} нападает на {victim.name}!",
    )


async def _drop_craft_work(db, victim: Character) -> str | None:
    """Обрывает рыбалку и добычу у того, на кого напали. Текст для него
    (пустой - только закрыли экран) или None, если он был не у воды и не в
    руднике."""
    from services import screen_service

    if victim.screen not in ("lake", "mine"):
        return None
    text = ""
    if fishing_service.is_casting(victim):  # неубранная в садок рыба уходит, как при уходе от воды
        fishing_service.clear_cast(victim)
        text = "Удочку пришлось смотать."
    if await mining_service.cancel_dig(db, victim):
        text = "Добычу пришлось бросить."
    await screen_service.set_screen(db, victim, None)
    return text


async def start_arena_duel(db, first: Character, first_peer: int, second: Character, second_peer: int) -> None:
    """Арена (2026-10-18): дуэль без потерь, оба с полным здоровьем."""
    await _launch_duel(
        db, first, first_peer, second, second_peer, location=ARENA_LOCATION, arena=True,
        intro=f"🏟 Арена: {first.name} против {second.name}! Бой тренировочный - ничего не теряется.",
    )


async def _launch_duel(
    db, attacker: Character, attacker_peer_id: int, victim: Character, victim_peer_id: int,
    location: tuple[int, int], intro: str, arena: bool = False,
) -> None:
    """Бой 1×1 - тот же тиковый движок, что и массовый (2026-10-29): оба
    объявляют действие одновременно, третий вступает сразу."""
    session_id = _new_battle_id()
    battle = Battle(battle_type="mass", location=location, arena=arena)
    state = CombatSessionState(session_id=session_id, mode=CombatMode.PVP_GROUP)
    # Стороны разводятся явно: _build_combatant_for ставит всем side=0.
    for side, character, peer in ((0, attacker, attacker_peer_id), (1, victim, victim_peer_id)):
        combatant = await _build_combatant_for(db, character)
        combatant.side = side
        state.add(combatant)
        battle.participants[character.id] = _participant(character, peer)
        battle.side_of[character.id] = side
        _peer_battle[peer] = session_id
    _battles[session_id] = battle
    battle.last_combatants = dict(state.combatants)
    _mass_engine.start_session(state)
    for cid in list(battle.participants):
        _init_target(session_id, battle, cid)
    intro = f"{intro} Оба действуют одновременно, ход - {round(bc.PVP_GROUP_TURN_SECONDS)} секунд. {RECOVERY_INTRO}"
    for p in list(battle.participants.values()):
        combatant = state.combatants[p.character_id]
        await _bot_api.messages.send(
            peer_id=p.peer_id, message=f"{intro}\n\n{_render_mass(state, [])}", random_id=0,
            keyboard=pvp_combat_keyboard(
                p.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id, show_target=True,
            ),
        )


async def _start_group_ambush(db, attacker: Character, attacker_peer_id: int, victim: Character,
                              defenders: list[tuple[Character, int]]) -> None:
    """Нападение на группу посреди её боя с мобами: сразу массовый бой -
    нападающий против всей группы на клетке."""
    battle_id = _new_battle_id()
    battle = Battle(battle_type="mass", location=(attacker.pos_x, attacker.pos_y))
    state = CombatSessionState(session_id=battle_id, mode=CombatMode.PVP_GROUP)
    for side, roster in ((0, [(attacker, attacker_peer_id)]), (1, defenders)):
        for character, peer in roster:
            combatant = await _build_combatant_for(db, character)
            combatant.side = side
            state.add(combatant)
            battle.participants[character.id] = _participant(character, peer)
            battle.side_of[character.id] = side
            _peer_battle[peer] = battle_id
    _battles[battle_id] = battle
    battle.last_combatants = dict(state.combatants)
    _mass_engine.start_session(state)
    for cid in list(battle.participants):
        _init_target(battle_id, battle, cid)
    names = ", ".join(c.name for c, _ in defenders)
    intro = (
        f"⚔️ {attacker.name} нападает на {victim.name} посреди боя с мобами! "
        f"Бой с мобами прерван без итога, вся группа ({names}) вступает в схватку. "
        f"Все действуют одновременно, ход - {round(bc.PVP_GROUP_TURN_SECONDS)} секунд. {RECOVERY_INTRO}"
    )
    for p in list(battle.participants.values()):
        board = intro + "\n\n" + _render_mass(state, [])
        target_line = _target_line(battle_id, battle, p.character_id)
        if target_line:
            board += f"\n{target_line}"
        combatant = state.combatants[p.character_id]
        await _bot_api.messages.send(
            peer_id=p.peer_id, message=board, random_id=0,
            keyboard=pvp_combat_keyboard(
                p.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id, show_target=True,
            ),
        )


# --- Присоединение к идущему бою ---


@labeler.message(payload_contains={"type": "pvp_join"})
async def join_via_button(message: Message) -> None:
    payload = message.get_payload_json() or {}
    await _handle_join_choice(message, payload.get("session_id"), payload.get("side"))


@labeler.message(TEXT_ONLY, text=["1", "2"])
async def join_via_text(message: Message) -> None:
    """Патч 42: TEXT_ONLY обязателен — "1"/"2" это ТАКЖЕ подписи кнопок в
    других экранах (скупщик "По предметам", выбор цели в масс-PvP). Без
    фильтра на payload это правило перехватывало нажатия ТЕХ кнопок (текст
    совпадал), даже когда игрок не ждёт выбора стороны — глушило их payload-
    обработчик целиком (баг-репорт #17: «1»/«2» не работали у скупщика)."""
    peer_id = message.peer_id
    battle_id = _pending_join_prompt.get(peer_id)
    if battle_id is None:
        return  # не ждём выбора стороны — не наш текст, оставляем как есть
    await _handle_join_choice(message, battle_id, int(message.text))


@activity_action
async def _handle_join_choice(message: Message, battle_id, side) -> None:
    peer_id = message.peer_id
    if not isinstance(battle_id, int) or side not in (1, 2):
        return
    _pending_join_prompt.pop(peer_id, None)
    if in_any_battle(peer_id):
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
        reason = await blocked_reason(db, character, peer_id)
        if reason:
            await message.answer(reason)
            return
        if await _still_dead(db, character):
            await message.answer("☠ Сначала очнись.")
            return
        if (character.pos_x, character.pos_y) != battle.location:
            await message.answer("Ты уже не на той клетке.")
            return
        # Против согруппника не вступают: его сторона - и твоя.
        mate_side = await _groupmate_side(db, character, battle)
        if mate_side is not None and battle.side_guilds is None:
            side = mate_side
        if battle.side_guilds is not None:
            if character.guild_id not in battle.side_guilds:
                await message.answer("Это осада - чужим в ней места нет.")
                return
            side = battle.side_guilds.index(character.guild_id) + 1
        combatant = await _build_combatant_for(db, character)
        if battle.siege_id is not None:
            combatant.stats = guild_siege_service.siege_modifiers(combatant.stats, character, side == 1)
            combatant.incoming_hit_hook = guild_siege_service.siege_guard(character)
        participant = _participant(character, peer_id)

    combatant.side = side - 1

    _join_mass_battle_now(battle_id, battle, participant, combatant)
    _init_target(battle_id, battle, participant.character_id)  # патч 38: автоцель при входе
    target_line = _target_line(battle_id, battle, participant.character_id)
    text = f"⚔️ Ты вступаешь в бой на стороне {side}!"
    if target_line:
        text += f"\n{target_line}"
    await message.answer(
        text, keyboard=pvp_combat_keyboard(
            participant.base_class, {}, show_target=True, subclass_id=combatant.subclass_id,
        ),
    )


def _join_mass_battle_now(battle_id: int, battle: Battle, participant: Participant, combatant: CombatantState) -> None:
    session = _mass_engine.sessions.get(battle_id)
    if session is None:
        return
    battle.participants[participant.character_id] = participant
    battle.side_of[participant.character_id] = combatant.side
    # Вступивший посреди боя лечится так же слабо, как все в этом ходу.
    combatant.recovery_mult = next(
        (getattr(c, "recovery_mult", 1.0) for c in session.combatants.values()), 1.0,
    )
    session.add(combatant)
    _peer_battle[participant.peer_id] = battle_id


async def start_siege_battle(
    siege_id: int, location: tuple[int, int],
    attackers: list[tuple[Character, int]], defenders: list[tuple[Character, int]],
    garrison: list[CombatantState], titles: tuple[str, str], guild_ids: tuple[int, int],
    intro: str,
) -> int:
    """Массовый бой осады: сторона 1 - осаждающие, сторона 2 - защитники и
    гарнизон. Возвращает id боя."""
    battle_id = _new_battle_id()
    battle = Battle(
        battle_type="mass", location=location, siege_id=siege_id,
        side_titles=titles, side_guilds=guild_ids,
    )
    state = CombatSessionState(session_id=battle_id, mode=CombatMode.PVP_GROUP)
    async with get_session_factory()() as db:
        for side, roster in ((0, attackers), (1, defenders)):
            for character, peer_id in roster:
                character = await db.get(Character, character.id)
                combatant = await _build_combatant_for(db, character)
                combatant.side = side
                combatant.stats = guild_siege_service.siege_modifiers(combatant.stats, character, side == 0)
                # Статы поменялись - здоровье пересчитываем от новой живучести.
                rebuilt = build_combatant(
                    id=combatant.id, side=side, kind="character", name=combatant.name,
                    level=combatant.level, stats=combatant.stats, primary_stat=combatant.primary_stat,
                    subclass_id=combatant.subclass_id, buff_modifiers=combatant.buff_modifiers,
                    base_class=combatant.base_class, gear_vit=combatant.gear_vit,
                )
                rebuilt.incoming_hit_hook = guild_siege_service.siege_guard(character)
                state.add(rebuilt)
                battle.participants[character.id] = _participant(character, peer_id)
                battle.side_of[character.id] = side
                _peer_battle[peer_id] = battle_id
    for guard in garrison:
        state.add(guard)
    _battles[battle_id] = battle
    battle.last_combatants = dict(state.combatants)
    _mass_engine.start_session(state)
    for cid in list(battle.participants):
        _init_target(battle_id, battle, cid)
    for p in list(battle.participants.values()):
        board = intro + "\n\n" + _render_mass(state, [])
        target_line = _target_line(battle_id, battle, p.character_id)
        if target_line:
            board += f"\n{target_line}"
        combatant = state.combatants[p.character_id]
        await _bot_api.messages.send(
            peer_id=p.peer_id, message=board, random_id=0, attachment=photo_attachment(SIEGE_PHOTO_ID),
            keyboard=pvp_combat_keyboard(
                p.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id, show_target=True,
            ),
        )
    return battle_id


def battle_at(location: tuple[int, int]) -> int | None:
    for battle_id, battle in _battles.items():
        if battle.location == location and battle.siege_id is not None:
            return battle_id
    return None


def drop_stale(peer_id: int) -> bool:
    """Снимает отметку «в бою», если самого боя уже нет. True - сняли."""
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None or battle_id in _battles:
        return False
    _peer_battle.pop(peer_id, None)
    return True


def release_participants(battle: Battle) -> None:
    for p in list(battle.participants.values()):
        _peer_battle.pop(p.peer_id, None)
        _chosen_target.pop(p.character_id, None)


# --- Ходы дуэли ---


@labeler.message(text=[BTN_PVP_ATTACK])
async def pvp_attack(message: Message) -> None:
    await _pvp_action(message, DeclaredAction(type=ActionType.ATTACK))


@labeler.message(payload_contains={"type": combat_modes.PVP.defend_payload})
async def pvp_defend(message: Message) -> None:
    await _pvp_action(message, DeclaredAction(type=ActionType.DEFEND))


@labeler.message(payload_contains={"type": "pvp_skill"})
async def pvp_skill(message: Message) -> None:
    payload = message.get_payload_json() or {}
    skill_id = payload.get("id")
    if skill_id not in BASE_SKILL_DEFS and skill_id not in SUBCLASS_SKILL_DEFS:
        return
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    if combatant is not None and combatant.is_on_cooldown(skill_id):
        cd = combatant.cooldowns.get(skill_id, 0)
        # Патч 30, баг 2: бой активен — без клавиатуры игрок теряет кнопки.
        participant = battle.participants.get(cid)
        keyboard = (
            pvp_combat_keyboard(participant.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id, show_target=battle.battle_type == "mass")
            if participant else None
        )
        await message.answer(f"⏳ Навык ещё не готов (КД {cd}).", keyboard=keyboard)
        return
    await _pvp_action(message, DeclaredAction(type=ActionType.SKILL, skill_id=skill_id))


async def _pvp_action(message: Message, action: DeclaredAction) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return

    is_defensive = action.type == ActionType.DEFEND or (
        action.type == ActionType.SKILL and action.skill_id in DEFENSIVE_SKILLS
    )
    if not is_defensive:
        # Патч 38: действие бьёт по ВЫБРАННОЙ игроком цели (см.
        # pvp_pick_target/_chosen_target), не по случайной.
        target = _resolve_chosen_target(battle_id, battle, cid)
        if target is None:
            return
        action = action.model_copy(update={"target_id": target})

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


def _enemies_of(battle_id: int, battle: Battle, cid: int) -> list[int]:
    """Живые враги cid, в порядке появления в бою (патч 38: тот же порядок,
    что видит игрок в списке выбора цели и что использует автоцель)."""
    combatants = _live_state(battle_id, battle)
    me = combatants.get(cid)
    if me is None:
        return []
    return [c.id for c in combatants.values() if c.side != me.side and c.alive]


def _init_target(battle_id: int, battle: Battle, cid: int) -> None:
    """Патч 38: цель назначается автоматически при входе в массовый бой —
    первый противник из списка (порядок появления в CombatSessionState)."""
    enemies = _enemies_of(battle_id, battle, cid)
    if enemies:
        _chosen_target[cid] = enemies[0]


def _resolve_chosen_target(battle_id: int, battle: Battle, cid: int) -> int | None:
    """Патч 38: выбранная игроком цель, если она ещё жива, иначе (защитный
    фолбэк — не должно случаться в норме, автопереключение уже происходит в
    on_mass_tick_resolved при гибели цели) обычный случайный враг."""
    combatants = _live_state(battle_id, battle)
    target_id = _chosen_target.get(cid)
    target = combatants.get(target_id) if target_id is not None else None
    if target is not None and target.alive:
        return target_id
    fallback = _default_enemy_target(battle_id, battle, cid)
    if fallback is not None:
        _chosen_target[cid] = fallback
    return fallback


def _target_line(battle_id: int, battle: Battle, cid: int) -> str:
    """Патч 38: «🎯 Цель: Мирэль (41% HP)» — показывается каждому участнику
    массового боя в его личную копию боевого сообщения."""
    combatants = _live_state(battle_id, battle)
    target_id = _chosen_target.get(cid)
    target = combatants.get(target_id) if target_id is not None else None
    if target is None or not target.alive:
        return ""
    hp_pct = round(100 * target.current_hp / target.max_hp) if target.max_hp else 0
    return f"🎯 Цель: {target.name} ({hp_pct}% HP)"


def _battle_board_text(battle_id: int, battle: Battle, lines: list[str]) -> str:
    session = _mass_engine.sessions.get(battle_id)
    return _render_mass(session, lines) if session is not None else "\n".join(lines)


# --- Выбор цели в массовом PvP (патч 38): бесплатное действие, не тратит
# ход и не занимает окно объявления действия (см. _pvp_action/_declared_this_tick
# — pvp_pick_target их вообще не трогает). Инлайн-подпанель через
# editable_message поверх боевой клавиатуры — тот же приём, что и у
# pvp_open_items/pvp_use_item ниже. Не показывается в дуэли (см. show_target
# в bot/keyboards/pvp.py::pvp_combat_keyboard) — противник там ровно один. ---


@labeler.message(text=[BTN_PVP_TARGET])
async def pvp_open_target(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None or battle.battle_type != "mass":
        return  # устаревшая клавиатура (дуэль/бой уже закончился) — молча игнорируем
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    enemy_ids = _enemies_of(battle_id, battle, cid)
    if not enemy_ids:
        return

    combatants = _live_state(battle_id, battle)
    current_id = _chosen_target.get(cid)
    lines = ["🎯 Выбор цели", ""]
    for i, enemy_id in enumerate(enemy_ids, start=1):
        enemy = combatants[enemy_id]
        p = battle.participants.get(enemy_id)
        class_title = p.class_title if p is not None else ""
        hp_pct = round(100 * enemy.current_hp / enemy.max_hp) if enemy.max_hp else 0
        lines.append(f"{i}. {enemy.name} · {enemy.level} ур. · {class_title} · {hp_pct}% HP")
    lines.append("")
    current = combatants.get(current_id) if current_id is not None else None
    lines.append(f"Текущая цель: {current.name if current is not None else '-'}")

    # Открытие окна - всегда новым сообщением внизу: иначе правилось бы
    # окно из прошлого боя, давно уехавшее вверх, и нажатие казалось мёртвым.
    editable_message.clear("pvp_target", peer_id)
    await editable_message.send_or_edit(
        _bot_api, "pvp_target", peer_id, "\n".join(lines), pvp_target_keyboard(enemy_ids),
    )


@labeler.message(payload_contains={"type": "pvp_target_pick"})
async def pvp_pick_target(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    target_cid = payload.get("target")
    if not isinstance(target_cid, int):
        return
    battle_id = _peer_battle.get(peer_id)
    if battle_id is None:
        return
    battle = _battles.get(battle_id)
    if battle is None or battle.battle_type != "mass":
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return

    combatants = _live_state(battle_id, battle)
    me = combatants.get(cid)
    target = combatants.get(target_cid)
    if me is None or target is None or target.side == me.side or not target.alive:
        return  # устаревший список (цель погибла/номер сместился) — молча игнорируем

    _chosen_target[cid] = target_cid
    participant = battle.participants.get(cid)
    if participant is None:
        return
    await editable_message.send_or_edit(
        _bot_api, "pvp_target", peer_id, f"🎯 Новая цель: {target.name}.", no_keyboard(),
    )
    board = f"🎯 Цель: {target.name}.\n\n{_battle_board_text(battle_id, battle, [])}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=board, random_id=0,
        keyboard=pvp_combat_keyboard(participant.base_class, me.cooldowns, subclass_id=me.subclass_id, show_target=True),
    )


@labeler.message(payload_contains={"type": "pvp_target_back"})
async def pvp_target_back(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    participant = battle.participants.get(cid)
    if combatant is None or participant is None:
        return
    await editable_message.send_or_edit(_bot_api, "pvp_target", peer_id, "Возврат в бой.", no_keyboard())
    await _bot_api.messages.send(
        peer_id=peer_id, message=_battle_board_text(battle_id, battle, []), random_id=0,
        keyboard=pvp_combat_keyboard(
            participant.base_class, combatant.cooldowns, show_target=battle.battle_type == "mass",
            subclass_id=combatant.subclass_id,
        ),
    )


# --- Предметы в бою (патч 30, баг 3, п.3): зелья/эликсиры работают в PvP по
# тем же правилам, что и в PvE (патч 16) — лечебные тратят ход, боевые
# эликсиры бесплатны с лимитом ELIXIR_PER_BATTLE_LIMIT/бой, недоступны под
# контролем. Payload {"type": "pvp_use_item"} НАМЕРЕННО отличается от PvE
# {"type": "use_item"} — см. докстринг bot/keyboards/pvp.py. ---


@labeler.message(payload_contains={"type": "pvp_items_page"})
@labeler.message(text=[BTN_PVP_ITEM])
async def pvp_open_items(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    participant = battle.participants.get(cid)
    if combatant is None or participant is None:
        return
    battle_kb = pvp_combat_keyboard(participant.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id, show_target=battle.battle_type == "mass")
    if battle.arena:
        # Арена - бой без потерь: тратить эликсиры здесь нельзя.
        await message.answer("🏟 На арене эликсиры не используются - бой тренировочный.", keyboard=battle_kb)
        return
    if combatant.has_effect(EffectKind.FREEZE):
        await message.answer("Скован - не до зелий сейчас. ❄️", keyboard=battle_kb)
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
    visible = consumable_limit.visible_stock(combatant, stock, limit_reached)
    text = consumable_limit.items_header(combatant)
    if limit_reached and any(d.category != "heal" for d, _ in stock):
        text += "\n\nБольше твоё тело не выдержит за один бой - боевые эликсиры недоступны."
    # Открытие окна - всегда новым сообщением внизу: иначе правилось бы
    # окно из прошлого боя, давно уехавшее вверх, и нажатие казалось мёртвым.
    page = page_of(message)
    if page is None:
        editable_message.clear("pvp_combat_item", peer_id)
    await editable_message.send_or_edit(
        _bot_api, "pvp_combat_item", peer_id, text, pvp_items_keyboard(visible, page or 0)
    )


@labeler.message(payload_contains={"type": "pvp_use_item"})
async def pvp_use_item(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
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
    battle_kb = pvp_combat_keyboard(participant.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id, show_target=battle.battle_type == "mass")
    if battle.arena:
        # Арена - бой без потерь: тратить эликсиры здесь нельзя.
        await message.answer("🏟 На арене эликсиры не используются - бой тренировочный.", keyboard=battle_kb)
        return
    if combatant.has_effect(EffectKind.FREEZE):
        await message.answer("Скован - не до зелий сейчас. ❄️", keyboard=battle_kb)
        return
    if consumable_limit.left(combatant) <= 0:
        await message.answer(consumable_limit.EXHAUSTED_TEXT, keyboard=battle_kb)
        return
    if elixir.category == "heal" and consumable_limit.heal_taken(combatant):
        await message.answer(consumable_limit.HEAL_TAKEN_TEXT, keyboard=battle_kb)
        return
    if elixir.category != "heal" and combatant.combat_elixirs_used >= ec.ELIXIR_PER_BATTLE_LIMIT:
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
    consumable_limit.spend(combatant)

    await editable_message.send_or_edit(
        _bot_api, "pvp_combat_item", peer_id, f"Использовано: {elixir.emoji} {elixir.name}.", no_keyboard()
    )

    # Боевой эликсир и (с 2026-10-14) лечебное зелье - бесплатное действие:
    # эффект сразу, ход не тратится.
    if elixir.category == "heal":
        line = elixir_effects.drink_heal(combatant, elixir_id)
        consumable_limit.mark_heal(combatant)
    else:
        line = elixir_effects.apply_combat_elixir(combatant, elixir_id, _live_state(battle_id, battle))
        combatant.combat_elixirs_used += 1
    if elixir.category in ("scroll", "heal"):
        await _tell_others(battle, cid, f"{participant.name}: {line}")
    text = f"{line} Твой ход.\n\n{_battle_board_text(battle_id, battle, [])}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0,
        keyboard=pvp_combat_keyboard(participant.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id),
    )


async def _tell_others(battle, cid: int, text: str) -> None:
    """Свиток действует на всю сторону (или на всех врагов) - видеть это
    должны все в бою, а не только прочитавший."""
    for other_id, other in list(battle.participants.items()):
        if other_id == cid:
            continue
        try:
            await _bot_api.messages.send(peer_id=other.peer_id, message=text, random_id=0)
        except Exception:
            pass  # игрок закрыл диалог с ботом - свиток всё равно сработал


# Нарезка (2026-10-22): этот блок живёт в bot.handlers.pvp_results.
# Старые адреса (pvp.X в других модулях и тестах) работают через ссылку.
from bot.handlers.pvp_results import (  # noqa: E402,F401
    _finish_duel,
    _notify_orderers,
    _render_mass,
    _render_mass_tick,
    on_mass_battle_finished,
    on_mass_tick_resolved,
)


# Нарезка (2026-10-22): этот блок живёт в bot.handlers.pvp_scene.
# Старые адреса (pvp.X в других модулях и тестах) работают через ссылку.
from bot.handlers.pvp_scene import (  # noqa: E402,F401
    GROUPMATE_NO_PVP_TEXT,
    TARGET_GONE_TEXT,
    _afk_target_named,
    _battle_roster_text,
    _battle_scene_line,
    _battles_at,
    _busy_marks,
    _class_line,
    _groupmate_side,
    _guild_tags,
    _looked_entry,
    _remember_look,
    _resolve_target,
    _same_group,
    _scene_at,
    _scene_text,
)
