"""Мировые боссы (патч 104): заход, ходы с общим здоровьем, итог.

Заход - обычный соло-бой из bot/handlers/combat.py (те же кнопки атаки,
навыков, эликсиров), только босс не бьёт, а ходы ведёт этот модуль:
  - после каждого хода нанесённый урон сразу списывается с общего здоровья
    в БД, и боец в бою получает актуальное здоровье - так видно и чужой урон;
  - заход кончается через ATTEMPT_TURNS ходов, отступлением или когда босса
    не стало (убит этим или чужим заходом, ушёл по времени);
  - убийство разыгрывает пул ровно один раз: его разыгрывает тот ход,
    который перевёл босса в killed под блокировкой строки.
"""

import asyncio
import random
from datetime import datetime, timezone

from loguru import logger
from vkbottle.bot import BotLabeler, Message

from bot import world_boss_texts as texts
from bot.activity import activity_action, blocked_reason
from bot.keyboards import world_boss as kb
from bot.keyboards.world import empty_keyboard
from bot.vk_media import photo_attachment
from game.economy import world_boss_config as wbc
from game.world import encounters, world_boss
from models import WorldBoss
from services import (
    item_service,
    onboarding_service,
    preset_service,
    world_boss_service,
)
from services.db import get_session_factory

labeler = BotLabeler()

_bot_api = None
_rng = random.Random()

#: peer_id -> id персонажа в заходе
_fighter: dict[int, int] = {}
#: peer_id -> общее здоровье босса, известное этому заходу после прошлого хода
_known_hp: dict[int, int] = {}
#: peer_id -> урон, который лёг на босса за этот заход
_attempt_damage: dict[int, int] = {}
#: фоновые рассылки - ссылка нужна, иначе задачу может собрать сборщик мусора
_tasks: set[asyncio.Task] = set()


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def _spawn_task(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _send(peer_id: int, text: str, **kwargs) -> None:
    try:
        await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, **kwargs)
    except Exception:
        logger.exception("Мировой босс: не удалось отправить сообщение {}", peer_id)


def _attachment(boss: WorldBoss) -> str | None:
    image = world_boss.boss_def(boss.boss_id).image
    return photo_attachment(image) if image else None


# --- Появление ----------------------------------------------------------------


def on_spawned(boss_pk: int) -> None:
    """Зовётся после коммита исследования, которое выпустило босса."""
    _spawn_task(announce(boss_pk))


async def announce(boss_pk: int) -> None:
    async with get_session_factory()() as db:
        boss = await db.get(WorldBoss, boss_pk)
        if boss is None:
            return
        recipients = await world_boss_service.announce_recipients(db, boss)
    logger.info(
        "Мировой босс {} ({}): кольцо {}, клетка ({};{}), оповещаю {}",
        boss.id, boss.boss_id, boss.ring, boss.x, boss.y, len(recipients),
    )
    text = texts.announce_text(boss)
    for peer_id in recipients:
        await _send(peer_id, text, attachment=_attachment(boss))
        await asyncio.sleep(0.05)  # лимит сообщений сообщества


async def maybe_send_here_button(peer_id: int, character) -> None:
    """При входе на клетку с боссом - кнопка захода отдельным сообщением,
    как у рудника. Молчит, если босса тут нет."""
    async with get_session_factory()() as db:
        boss = await world_boss_service.active_boss(db)
        if boss is None or (character.pos_x, character.pos_y) != (boss.x, boss.y):
            return
        cooldown = await world_boss_service.cooldown_minutes(db, boss, character.id)
    text = texts.here_text(boss)
    if not world_boss.can_attack(character.level, boss.ring):
        await _send(peer_id, text + "\n" + texts.refusal_text("level", ring=boss.ring))
        return
    if cooldown:
        await _send(peer_id, text + "\n" + texts.refusal_text("cooldown", cooldown))
        return
    await _send(peer_id, text, keyboard=kb.attack_keyboard())


# --- Команда и кнопка ---------------------------------------------------------


@labeler.message(text=texts.COMMANDS)
async def status_command(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        boss = await world_boss_service.active_boss(db)
        my_damage = cooldown = 0
        allowed = False
        if boss is not None:
            allowed = world_boss.can_attack(character.level, boss.ring)
            my_damage = (await world_boss_service.damage_by_character(db, boss.id)).get(character.id, 0)
            cooldown = await world_boss_service.cooldown_minutes(db, boss, character.id)
    text = texts.status_text(boss, my_damage, cooldown, allowed)
    here = boss is not None and (character.pos_x, character.pos_y) == (boss.x, boss.y)
    if here and allowed and not cooldown:
        await message.answer(text, keyboard=kb.attack_keyboard())
    else:
        await message.answer(text)


@labeler.message(payload_contains={"type": "world_boss_attack"})
@activity_action
async def attack(message: Message) -> None:
    from sqlalchemy import select

    from bot.handlers import combat as combat_handlers  # избегаем цикла импортов
    from models import CharacterStats

    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        reason = await blocked_reason(db, character, peer_id)
        if reason:
            await message.answer(reason)
            return
        boss = await world_boss_service.active_boss(db)
        if boss is None:
            await message.answer(texts.refusal_text("gone"))
            return
        check = await world_boss_service.start_attempt(db, character, boss.id)
        if not check.ok:
            await message.answer(texts.refusal_text(check.reason, check.minutes_left, boss.ring))
            return
        stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
        await db.commit()
        boss_pk, boss_hp = boss.id, boss.hp

    boss_def = world_boss.boss_def(boss.boss_id)
    combatant = world_boss.build_combatant(
        combat_handlers.MOB_ID, boss_def, boss.ring, boss_hp, boss.max_hp,
    )
    encounter = encounters.Encounter(
        combatant=combatant, flavor=texts.intro_text(boss, boss_def.flavor),
        image=boss_def.image or None,
    )
    _fighter[peer_id] = character.id
    _known_hp[peer_id] = boss_hp
    _attempt_damage[peer_id] = 0
    await combat_handlers.start_world_boss_encounter(
        peer_id, character, stats, gear_bonus, buff_modifiers, boss_pk, encounter,
    )


# --- Ходы ----------------------------------------------------------------------


async def on_tick(peer_id: int, tick: int, result) -> None:
    """Ход разрешён движком. Списываем урон с общего здоровья и решаем,
    продолжается ли заход."""
    from bot.handlers import combat as combat_handlers  # избегаем цикла импортов

    state = combat_handlers._engine.sessions.get(peer_id)
    boss_pk = combat_handlers.world_boss_of(peer_id)
    character_id = _fighter.get(peer_id)
    if state is None or boss_pk is None or character_id is None:
        return
    mob = state.combatants[combat_handlers.MOB_ID]
    dealt = max(0, _known_hp.get(peer_id, mob.max_hp) - mob.current_hp)

    granted = None
    async with get_session_factory()() as db:
        damage = await world_boss_service.apply_damage(db, boss_pk, character_id, dealt)
        if damage.killed_now:
            boss = await db.get(WorldBoss, boss_pk)
            granted = await world_boss_service.distribute(db, boss, _rng)
        await db.commit()

    if combat_handlers.world_boss_of(peer_id) is None and not damage.killed_now:
        # Пока ход писался в БД, заход уже закрыли снаружи (босса добил
        # чужой ход, он ушёл по времени) - итог игроку уже отправлен.
        return
    _attempt_damage[peer_id] = _attempt_damage.get(peer_id, 0) + damage.dealt
    _known_hp[peer_id] = damage.hp
    # Здоровье бойца = общее: так в логе видно и то, что сняли другие.
    # Ноль не ставим, пока бой идёт, - движок счёл бы босса убитым.
    mob.current_hp = damage.hp

    finished = damage.over or tick >= wbc.ATTEMPT_TURNS or result.finished
    board = combat_handlers.render_board(state, result)
    board = board.replace(board.split("\n", 1)[0], texts.turn_header(tick), 1)
    if not finished:
        await _send(peer_id, board, keyboard=combat_handlers.rebuild_keyboard(peer_id))
        return

    await _send(peer_id, board, keyboard=empty_keyboard())
    await _close_attempt(peer_id, boss_gone=damage.over)
    if damage.killed_now:
        await _finish_boss(boss_pk, granted)


async def leave(peer_id: int) -> None:
    """Кнопка отступления: заход кончается сразу, урон уже записан."""
    await _close_attempt(peer_id, boss_gone=False)


async def _close_attempt(peer_id: int, boss_gone: bool) -> None:
    from bot.handlers import combat as combat_handlers  # избегаем цикла импортов
    from bot.handlers import world as world_handlers  # избегаем цикла импортов

    boss_pk = combat_handlers.world_boss_of(peer_id)
    combat_handlers.end_world_boss_fight(peer_id)
    character_id = _fighter.pop(peer_id, None)
    _known_hp.pop(peer_id, None)
    dealt = _attempt_damage.pop(peer_id, 0)
    async with get_session_factory()() as db:
        total = 0
        if boss_pk is not None and character_id is not None:
            total = (await world_boss_service.damage_by_character(db, boss_pk)).get(character_id, 0)
        character = await onboarding_service.get_character(db, peer_id)
        if character is None:
            return
        keyboard = await world_handlers._current_keyboard(
            db, character, peer_id, datetime.now(timezone.utc)
        )
    await _send(peer_id, texts.attempt_over_text(dealt, total, boss_gone), keyboard=keyboard)


# --- Конец босса ------------------------------------------------------------------


async def _finish_boss(boss_pk: int, granted) -> None:
    """Босс убит или ушёл: закрываем чужие заходы и рассылаем итоги."""
    from bot.handlers import combat as combat_handlers  # избегаем цикла импортов

    for peer_id, fighting_pk in combat_handlers.world_boss_fighters().items():
        if fighting_pk == boss_pk:
            await _close_attempt(peer_id, boss_gone=True)

    async with get_session_factory()() as db:
        boss = await db.get(WorldBoss, boss_pk)
        peers = {
            got.character_id: await onboarding_service.vk_id_for_character(db, got.character_id)
            for got in granted or []
        }
    if boss is None:
        return
    logger.info(
        "Мировой босс {} закончился ({}), участников {}", boss.id, boss.status, len(granted or []),
    )
    total = sum(got.damage for got in granted or [])
    await _notify_results(boss, granted or [], peers, total)


async def _notify_results(boss: WorldBoss, granted, peers: dict[int, int | None], total: int) -> None:
    from bot import group_texts
    from bot.handlers import stats_window

    for got in granted:
        peer_id = peers.get(got.character_id)
        if peer_id is None:
            continue
        await _send(peer_id, texts.end_text(boss, got, total), attachment=_attachment(boss))
        if got.levels_gained:
            await stats_window.notify_levelup(peer_id, got.levels_gained, got.new_level)
        await group_texts.notify_group_kick(_bot_api, got.group_kick)
        await asyncio.sleep(0.05)


async def expire_job() -> None:
    """Раз в минуту: боссы, у которых вышло время, уходят и раздают часть пула."""
    try:
        async with get_session_factory()() as db:
            ended = await world_boss_service.expire_due(db, _rng)
            await db.commit()
    except Exception:
        logger.exception("Мировой босс: не удалось закрыть истёкших")
        return
    for boss, granted in ended:
        await _finish_boss(boss.id, granted)
