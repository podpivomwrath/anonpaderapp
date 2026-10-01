"""Осада в чате: сбор участников в назначенный час, бой, итог.

Бой - массовое PvP (bot/handlers/pvp.py) с гарнизоном на стороне
защитников. В бой встают все свободные участники обеих гильдий, кто стоит
на клетке к началу; опоздавшие вступают через «Осмотреться» - только на
сторону своей гильдии.
"""

from loguru import logger
from sqlalchemy import select

from bot.activity import blocked_reason
from bot.handlers import guild as guild_handlers
from bot.keyboards import world as kb
from models import Character, Guild, GuildSiege
from services import (
    death_service,
    guild_siege_service,
    mount_service,
    onboarding_service,
)
from services.db import get_session_factory

GARRISON_FIRST_ID = -10_000


async def _gather(db, guild_id: int, x: int, y: int) -> list[tuple[Character, int]]:
    rows = (
        await db.scalars(
            select(Character).where(Character.guild_id == guild_id, Character.pos_x == x, Character.pos_y == y)
        )
    ).all()
    result = []
    for character in rows:
        peer = await onboarding_service.vk_id_for_character(db, character.id)
        if peer is None or death_service.is_dead(character):
            continue
        if await blocked_reason(db, character, peer):
            continue
        result.append((character, peer))
    return result


async def start(siege_id: int) -> None:
    from bot.handlers import pvp as pvp_handlers  # избегаем цикла импортов

    async with get_session_factory()() as db:
        siege = await db.get(GuildSiege, siege_id)
        if siege is None or siege.status != "scheduled":
            return
        siege.status = "running"
        attacker = await db.get(Guild, siege.attacker_guild_id)
        defender = await db.get(Guild, siege.defender_guild_id)
        attackers = await _gather(db, siege.attacker_guild_id, siege.x, siege.y)
        defenders = await _gather(db, siege.defender_guild_id, siege.x, siege.y)
        garrison = await guild_siege_service.garrison(db, siege, GARRISON_FIRST_ID)
        await db.commit()
        a_id, d_id = attacker.id, defender.id
        titles = (f"⚔️ [{attacker.tag}]", f"🛡 [{defender.tag}]")
        x, y = siege.x, siege.y

    if not attackers or (not defenders and not garrison):
        async with get_session_factory()() as db:
            outcome = await guild_siege_service.finish(
                db, siege_id, attackers_won=bool(attackers), attackers_present=bool(attackers),
            )
            await db.commit()
        text = f"🏰 {outcome.text}"
        if attackers and not defenders and not garrison:
            text = f"🏰 Под стенами ({x}; {y}) никого: {outcome.text}"
        await guild_handlers.notify_guild(a_id, text)
        await guild_handlers.notify_guild(d_id, text)
        return

    intro = (
        f"🏰 Осада ({x}; {y}) началась! {titles[0]} штурмует, {titles[1]} держит стены"
        + (f" вместе с гарнизоном ({len(garrison)})." if garrison else ".")
    )
    try:
        await pvp_handlers.start_siege_battle(
            siege_id, (x, y), attackers, defenders, garrison, titles, (a_id, d_id), intro,
        )
    except Exception:
        logger.exception("Осада {}: бой не начался", siege_id)
        async with get_session_factory()() as db:
            siege = await db.get(GuildSiege, siege_id)
            siege.status = "cancelled"
            siege.result = "Осада сорвалась."
            await db.commit()
        return
    others = (
        f"🏰 Осада ({x}; {y}) началась. Успеешь дойти - вступай через «Осмотреться» на клетке."
    )
    present = {peer for _c, peer in attackers + defenders}
    async with get_session_factory()() as db:
        for guild_id in (a_id, d_id):
            peers = [p for p in await guild_handlers.guild_service.peers_of(db, guild_id) if p not in present]
            guild_handlers.notify_peers(peers, others)


async def on_siege_battle_finished(battle, result, dead_ids: list[int], survivor_ids: list[int]) -> None:
    from bot.handlers import pvp as pvp_handlers  # избегаем цикла импортов
    from bot.handlers import respawn as respawn_handlers  # избегаем цикла импортов

    pvp_handlers.release_participants(battle)
    attackers_won = not result.draw and result.winner_side == 0
    async with get_session_factory()() as db:
        for cid in dead_ids:
            character = await db.get(Character, cid)
            if character is not None:
                # Смерть в осаде - только ожидание возрождения: трофеи не
                # переходят, опыт не теряется. Цена осады - земля.
                death_service.apply_pvp_death(character)
                respawn_handlers.register_pvp_death(battle.participants[cid].peer_id)
        outcome = await guild_siege_service.finish(db, battle.siege_id, attackers_won=attackers_won)
        has_mount = {cid: await mount_service.has_any_mount(db, cid) for cid in survivor_ids}
        positions = {}
        for cid in survivor_ids:
            character = await db.get(Character, cid)
            if character is not None:
                positions[cid] = (character.pos_x, character.pos_y)
        await db.commit()
        a_id, d_id = outcome.siege.attacker_guild_id, outcome.siege.defender_guild_id

    text = f"🏰 {outcome.text}"
    for cid, participant in battle.participants.items():
        if cid in survivor_ids:
            pos = positions.get(cid, battle.location)
            keyboard = kb.movement_keyboard(*pos, participant.peer_id, has_mount=has_mount.get(cid, False))
            await guild_handlers.send(participant.peer_id, text, keyboard=keyboard)
        else:
            await guild_handlers.send(
                participant.peer_id, f"☠ Ты пал под стенами.\n\n{text}", keyboard=kb.waiting_keyboard(),
            )
    present = {p.peer_id for p in battle.participants.values()}
    async with get_session_factory()() as db:
        for guild_id in (a_id, d_id):
            peers = [p for p in await guild_handlers.guild_service.peers_of(db, guild_id) if p not in present]
            guild_handlers.notify_peers(peers, text)
