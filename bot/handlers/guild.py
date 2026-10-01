"""Гильдии в чате: уведомления, фоновые задачи, Страж цитадели.

Управление гильдией живёт в мини-аппе (вкладка «Гильдия»): состав, казна,
стройка, древо - это таблицы, а не разговор. В чате - то, что происходит
в поле: закладка знамени, тревога башни, осады, заходы к Стражу.
"""

import asyncio
import random

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot.activity import activity_action, blocked_reason
from bot.keyboards.world import empty_keyboard
from game.economy import guild_config as gc
from game.world import encounters
from models import Character, GuildBoss
from services import (
    guild_boss_service,
    guild_season_service,
    guild_service,
    guild_siege_service,
    guild_territory_service,
    item_service,
    onboarding_service,
    preset_service,
    title_service,
)
from services.db import get_session_factory

labeler = BotLabeler()

_bot_api = None
_rng = random.Random()
_tasks: set[asyncio.Task] = set()

BTN_BOSS_ATTACK = "⚔️ Бить Стража"

#: peer_id -> id персонажа в заходе к Стражу; урон за заход; известное здоровье.
_fighter: dict[int, int] = {}
_attempt_damage: dict[int, int] = {}
_known_hp: dict[int, int] = {}


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def send(peer_id: int, text: str, **kwargs) -> None:
    if _bot_api is None:
        return
    try:
        await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, **kwargs)
    except Exception:
        logger.exception("Не удалось отправить гильдейское сообщение {}", peer_id)


async def send_many(peers: list[int], text: str) -> None:
    for peer in peers:
        await send(peer, text)
        await asyncio.sleep(0.05)


def notify_peers(peers: list[int], text: str) -> None:
    if peers:
        _spawn(send_many(list(peers), text))


async def notify_guild(guild_id: int, text: str, min_rank: str | None = None) -> None:
    async with get_session_factory()() as db:
        peers = await guild_service.peers_of(db, guild_id, min_rank=min_rank)
    notify_peers(peers, text)


# --- Поле: исследование и прибытие -------------------------------------------------


async def after_exploration(peer_id: int, character: Character, outcome) -> None:
    """Закладка знамени: вехи прогресса и завершение."""
    if outcome is None:
        return
    if outcome.claimed is not None:
        cell = outcome.claimed
        text = f"🚩 Знамя встало! ({cell.x}; {cell.y}) - теперь земля гильдии. Здесь можно строить базу."
        await notify_guild(cell.guild_id, text)
        return
    if outcome.claim_progress is not None:
        done, need = outcome.claim_progress
        marks = {need // 4, need // 2, need * 3 // 4}
        if done in marks:
            await send(peer_id, f"🚩 Закладка знамени: {done}/{need} исследований.")


async def on_arrival(db, character: Character) -> None:
    """Чужой зашёл на клетку с башней - офицеры владельца узнают."""
    alarm = await guild_territory_service.on_cell_enter(db, character)
    if alarm is None:
        return
    who = f"[{alarm.intruder_guild}] {alarm.intruder}" if alarm.intruder_guild else alarm.intruder
    notify_peers(alarm.peers, f"🗼 Башня на ({alarm.x}; {alarm.y}): чужой на нашей земле - {who}.")


# --- Фоновые задачи ------------------------------------------------------------------


async def tick_job() -> None:
    """Раз в 30 секунд: стройка, закладки, осады, Страж."""
    from bot.handlers import guild_siege  # избегаем цикла импортов

    try:
        async with get_session_factory()() as db:
            built = await guild_territory_service.complete_due(db)
            expired = await guild_territory_service.expire_claims(db)
            gather, start = await guild_siege_service.due(db)
            bosses = await guild_boss_service.expire_due(db)
            await db.commit()
            expired_info = [(c.guild_id, c.x, c.y) for c in expired]
            gather_info = [(s.id, s.attacker_guild_id, s.defender_guild_id, s.x, s.y) for s in gather]
            start_ids = [s.id for s in start]
        for guild_id, text in built:
            await notify_guild(guild_id, f"🏗 {text}")
        for guild_id, x, y in expired_info:
            await notify_guild(guild_id, f"🚩 Закладка знамени на ({x}; {y}) сорвалась: не успели.")
        for _sid, attacker_id, defender_id, x, y in gather_info:
            text = (
                f"🏰 Через {gc.SIEGE_GATHER_MINUTES} мин. осада ({x}; {y}). Собирайтесь на клетке: "
                f"драки и исследования там до начала запрещены."
            )
            await notify_guild(attacker_id, text)
            await notify_guild(defender_id, text)
        for siege_id in start_ids:
            await guild_siege.start(siege_id)
        for result in bosses:
            await _boss_finished(result)
    except Exception:
        logger.exception("Гильдии: сбой фоновой задачи")


async def shaft_job() -> None:
    try:
        async with get_session_factory()() as db:
            mined = await guild_territory_service.shaft_tick(db, _rng)
            await db.commit()
        if mined:
            logger.info("Гильдейские шахты добыли {} руды", mined)
    except Exception:
        logger.exception("Гильдии: сбой шахт")


async def season_job() -> None:
    """Раз в сутки ночью: итог сезона (первого числа) и снимок владений."""
    try:
        async with get_session_factory()() as db:
            result = await guild_season_service.close_if_due(db)
            await guild_season_service.snapshot(db)
            await db.commit()
        if result is not None and result.winner is not None:
            await notify_guild(
                result.winner.id,
                f"👑 Гильдия - лучшая в сезоне {result.season}! Венец сезона на месяц, "
                f"титул «{title_service.name_of(gc.SEASON_TITLE_ID)}» каждому и 💎 {gc.SEASON_GEMS_TO_TREASURY} в казну.",
            )
    except Exception:
        logger.exception("Гильдии: сбой сезона")


# --- Команда «Гильдия» --------------------------------------------------------------


@labeler.message(text=["Гильдия", "гильдия"])
async def guild_command(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        guild = await guild_service.guild_of(db, character)
        if guild is None:
            await message.answer(
                "🏰 Ты не в гильдии. Вступить или основать свою можно в мини-аппе: раздел «Гильдия»."
            )
            return
        member = await guild_service.membership(db, character.id)
        count = await guild_service.member_count(db, guild.id)
        counts = await guild_territory_service.territory_counts(db, guild.id)
        sieges = await guild_siege_service.active_of(db, guild.id)
        boss = await guild_boss_service.active_boss(db, guild.id)
    lines = [
        f"🏰 [{guild.tag}] {guild.name} - {guild.level} ур.",
        f"Слава: {guild.fame}/{gc.fame_to_next(guild.level)}. Участников: {count}/{gc.member_cap(guild.level)}.",
        f"Ты - {gc.RANK_TITLES[member.rank].lower()}.",
        f"Земли: клеток {counts['cells']}, рудников {counts['mines']}.",
    ]
    for siege in sieges:
        when = siege.starts_at.astimezone(guild_siege_service._TZ).strftime("%d.%m %H:%M")
        role = "наступаем" if siege.attacker_guild_id == guild.id else "обороняемся"
        lines.append(f"⚔️ Осада ({siege.x}; {siege.y}), {role}: {when} МСК.")
    if boss is not None:
        lines.append(f"🗿 Страж цитадели призван: {boss.hp}/{boss.max_hp}. Команда «Страж».")
    lines.append("Управление - в мини-аппе, раздел «Гильдия».")
    await message.answer("\n".join(lines))


# --- Страж цитадели --------------------------------------------------------------------


def boss_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(Text(BTN_BOSS_ATTACK, payload={"type": "guild_boss_attack"}), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()


@labeler.message(text=["Страж", "страж"])
async def boss_status(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None or character.creation_state is not None or character.guild_id is None:
            return
        boss = await guild_boss_service.active_boss(db, character.guild_id)
        if boss is None:
            await message.answer("🗿 Страж цитадели не призван.")
            return
        cooldown = await guild_boss_service.cooldown_minutes(db, boss, character.id)
    here = (character.pos_x, character.pos_y) == (boss.x, boss.y)
    text = f"🗿 Страж цитадели ({boss.x}; {boss.y}): {boss.hp}/{boss.max_hp} здоровья."
    if cooldown:
        text += f"\nСледующий заход через {cooldown} мин."
    if here and not cooldown:
        await message.answer(text, keyboard=boss_keyboard())
    else:
        await message.answer(text)


@labeler.message(payload_contains={"type": "guild_boss_attack"})
@activity_action
async def boss_attack(message: Message) -> None:
    from sqlalchemy import select

    from bot.handlers import combat as combat_handlers  # избегаем цикла импортов
    from models import CharacterStats

    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None or character.creation_state is not None or character.guild_id is None:
            return
        reason = await blocked_reason(db, character, peer_id)
        if reason:
            await message.answer(reason)
            return
        boss = await guild_boss_service.active_boss(db, character.guild_id)
        if boss is None:
            await message.answer("🗿 Стража больше нет.")
            return
        check = await guild_boss_service.start_attempt(db, character, boss.id)
        if not check.ok:
            await message.answer(check.reason)
            return
        stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        buff_modifiers = await preset_service.resolve_active_modifiers(db, character)
        await db.commit()
        boss_pk, boss_hp, max_hp = boss.id, boss.hp, boss.max_hp

    combatant = guild_boss_service.build_combatant(combat_handlers.MOB_ID, boss_hp, max_hp)
    encounter = encounters.Encounter(
        combatant=combatant,
        flavor=f"Каменный страж не отвечает на удары. У тебя {gc.BOSS_ATTEMPT_TURNS} ходов, у него {boss_hp}/{max_hp}.",
    )
    _fighter[peer_id] = character.id
    _known_hp[peer_id] = boss_hp
    _attempt_damage[peer_id] = 0
    # Отрицательный id - тот же бой, что у мирового босса, но ходы ведёт
    # этот модуль (bot/handlers/world_boss.py::on_tick передаёт сюда).
    await combat_handlers.start_world_boss_encounter(
        peer_id, character, stats, gear_bonus, buff_modifiers, -boss_pk, encounter,
    )


async def boss_on_tick(peer_id: int, tick: int, result) -> None:
    from bot.handlers import combat as combat_handlers  # избегаем цикла импортов
    from bot.handlers import world_boss as world_boss_handlers  # избегаем цикла импортов

    state = combat_handlers._engine.sessions.get(peer_id)
    marker = combat_handlers.world_boss_of(peer_id)
    character_id = _fighter.get(peer_id)
    if state is None or marker is None or character_id is None:
        return
    boss_pk = -marker
    mob = state.combatants[combat_handlers.MOB_ID]
    dealt = max(0, _known_hp.get(peer_id, mob.max_hp) - mob.current_hp)
    finished_result = None
    async with get_session_factory()() as db:
        damage = await guild_boss_service.apply_damage(db, boss_pk, character_id, dealt)
        if damage.killed_now:
            boss = await db.get(GuildBoss, boss_pk)
            finished_result = await guild_boss_service.distribute(db, boss)
        await db.commit()
    _attempt_damage[peer_id] = _attempt_damage.get(peer_id, 0) + damage.dealt
    _known_hp[peer_id] = damage.hp
    mob.current_hp = damage.hp
    finished = damage.over or tick >= gc.BOSS_ATTEMPT_TURNS or result.finished
    board = combat_handlers.render_board(state, result)
    board = board.replace(board.split("\n", 1)[0], f"🗿 СТРАЖ - ход {tick}/{gc.BOSS_ATTEMPT_TURNS}", 1)
    board += f"\n\n🗡 Урон за заход: {_attempt_damage[peer_id]}"
    if damage.my_total > _attempt_damage[peer_id]:
        board += f"\n📊 Вклад в Стража: {damage.my_total}"
    if not finished:
        await send(peer_id, board, keyboard=combat_handlers.rebuild_keyboard(peer_id))
        return
    await send(peer_id, board, keyboard=empty_keyboard())
    if finished_result is not None:
        await _boss_finished(finished_result)
        return
    _fighter.pop(peer_id, None)
    _known_hp.pop(peer_id, None)
    _attempt_damage.pop(peer_id, None)
    await world_boss_handlers._close_attempt(peer_id, boss_gone=damage.over)


def forget(peer_id: int) -> None:
    _fighter.pop(peer_id, None)
    _known_hp.pop(peer_id, None)
    _attempt_damage.pop(peer_id, None)


async def _boss_finished(result) -> None:
    from bot.handlers import combat as combat_handlers  # избегаем цикла импортов
    from bot.handlers import world_boss as world_boss_handlers  # избегаем цикла импортов

    boss = result.boss
    fighting = [
        peer for peer, marker in combat_handlers.world_boss_fighters().items() if marker == -boss.id
    ]
    for peer in fighting:
        combat_handlers.end_world_boss_fight(peer)
    status = "повержен" if boss.status == "killed" else "уходит, недобитый"
    text = (
        f"🗿 Страж цитадели {status}! Гильдии: +{result.fame} славы, {result.treasury_gold} золота "
        f"в казну, {result.ore} руды на склад."
    )
    async with get_session_factory()() as db:
        peers = await guild_service.peers_of(db, boss.guild_id)
        personal = {
            await onboarding_service.vk_id_for_character(db, g.character_id): g for g in result.granted
        }
    for peer in peers:
        got = personal.get(peer)
        extra = f"\nТвой урон: {got.damage}, золото: +{got.gold}." if got else ""
        if got and got.net_gold != got.gold:
            extra += f" После налога: {got.net_gold}."
        await send(peer, text + extra)
        await asyncio.sleep(0.05)
    for peer in fighting:
        forget(peer)
        await world_boss_handlers._close_attempt(peer, boss_gone=True, got_result=True)


async def announce_boss(guild_id: int, x: int, y: int) -> None:
    await notify_guild(
        guild_id,
        f"🗿 Страж цитадели призван на ({x}; {y})! Бить его можно раз в час, "
        f"{gc.BOSS_LIFETIME_HOURS} ч. Команда «Страж».",
    )

