"""Классовые испытания во всех PvE-боях, не только в соло (2026-10-24, владелец:
«во все бои все должно работать»).

Соло-бой ведёт свой BattleTracker (bot/handlers/combat.py). Здесь - то же для
группового боя, этапа рейда и этапа разлома: по трекеру на каждого участника,
врагами считается другая сторона. Этап рейда или разлома - отдельный бой:
победа на нём - победа для испытаний.

observe() - после каждого хода, settle() - в конце боя или этапа: отчёты уходят
в trial_service.record_battle, в ответ - какие баффы открылись у кого.
В памяти: перезапуск посреди боя просто теряет незаконченный бой.
"""

from __future__ import annotations

from loguru import logger

from game.combat.battle_report import BattleTracker

#: session_id -> {character_id: трекер}
_trackers: dict[int, dict[int, BattleTracker]] = {}


def observe(session_id: int, combatants: dict, result, participants) -> None:
    """Ход разрешён: обновить трекеры участников (создать, кого ещё нет).
    participants - id бойцов, они же id персонажей (группа, рейд), или
    {id бойца: id персонажа}, если не совпадают (мировой босс)."""
    if combatants is None:
        return
    pairs = participants.items() if isinstance(participants, dict) else ((c, c) for c in participants)
    by_cid = _trackers.setdefault(session_id, {})
    died = set(result.deaths)
    for fid, cid in pairs:
        me = combatants.get(fid)
        if me is None:
            continue
        tracker = by_cid.get(cid)
        if tracker is None:
            enemies = {c.id for c in combatants.values() if c.side != me.side}
            # Здоровье до первого хода: трекер создаётся уже после него.
            before = next((r.hp_before for r in result.hit_renders if r.target_id == fid), me.current_hp)
            level = max((combatants[e].level for e in enemies if e in combatants), default=0)
            tracker = by_cid[cid] = BattleTracker(fid, None, level, me.max_hp, before, enemy_ids=enemies)
        else:
            # Призванные посреди боя враги (мельница, поле) - тоже враги.
            tracker.enemy_ids |= {c.id for c in combatants.values() if c.side != me.side}
        tracker.update(result, me.current_hp, died_ids=died)


def drop(session_id: int) -> None:
    _trackers.pop(session_id, None)


async def settle(session_id: int, won: bool) -> dict[int, list[str]]:
    """Бой или этап окончен: отчёты в испытания. {character_id: [buff_id]}."""
    from models import Character
    from services import subclass_service, trial_service
    from services.db import get_session_factory

    by_cid = _trackers.pop(session_id, None) or {}
    if not by_cid:
        return {}
    opened: dict[int, list[str]] = {}
    try:
        async with get_session_factory()() as db:
            for cid, tracker in by_cid.items():
                character = await db.get(Character, cid)
                if character is None or subclass_service.buff_pool(character) is None:
                    continue
                buffs = await trial_service.record_battle(db, character, tracker.finalize(won))
                if buffs:
                    opened[cid] = buffs
            await db.commit()
    except Exception:  # noqa: BLE001 - испытания не должны ронять бой или переход этапа
        logger.exception("Испытания: отчёт боя {} не записан", session_id)
        return {}
    return opened


def opened_text(buff_ids: list[str]) -> str:
    from services import trial_service

    return "\n".join(f"📖 Испытание пройдено. Открыт бафф: {trial_service.buff_name(b)}." for b in buff_ids)
