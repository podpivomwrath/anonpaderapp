"""Руины культа: забег в базе. Правила - game/ruins.py и
game/economy/ruins_config.py, чат - bot/handlers/ruins.py.

Всё, что меняет забег, идёт под блокировкой строки забега (lock): лидер
жмёт шаг, а остальные в ту же секунду подтверждают.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game import ruins as rules
from game.economy import loot
from game.economy import loot_config as lc
from game.economy import ruins_config as rc
from models import Character, CharacterStats, RuinMember, RuinRun

ACTIVE, DONE = "active", "done"
WALK, FIGHT, CLEARED = "walk", "fight", "cleared"
EXITED, WIPED, ABANDONED = "exited", "wiped", "abandoned"


class RuinsError(Exception):
    """Причина отказа - игроку."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime | None) -> datetime | None:
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


# --- Чтение -------------------------------------------------------------------


async def lock(db: AsyncSession, run_id: int) -> RuinRun | None:
    return await db.scalar(
        select(RuinRun).where(RuinRun.id == run_id).with_for_update().execution_options(populate_existing=True)
    )


async def members(db: AsyncSession, run_id: int, active_only: bool = True) -> list[RuinMember]:
    query = select(RuinMember).where(RuinMember.run_id == run_id)
    if active_only:
        query = query.where(RuinMember.active.is_(True))
    return list((await db.scalars(query.order_by(RuinMember.id).execution_options(populate_existing=True))).all())


async def membership(db: AsyncSession, character_id: int) -> RuinMember | None:
    """Строка участия в идущем забеге или None."""
    return await db.scalar(
        select(RuinMember).join(RuinRun, RuinRun.id == RuinMember.run_id)
        .where(RuinMember.character_id == character_id, RuinMember.active.is_(True), RuinRun.status == ACTIVE)
        .limit(1)
    )


async def active_runs(db: AsyncSession) -> list[RuinRun]:
    return list((await db.scalars(select(RuinRun).where(RuinRun.status == ACTIVE).order_by(RuinRun.id))).all())


def inside_query():
    """id персонажей внутри руин - для подзапросов (на клетке их нет)."""
    return (
        select(RuinMember.character_id).join(RuinRun, RuinRun.id == RuinMember.run_id)
        .where(RuinMember.active.is_(True), RuinRun.status == ACTIVE)
    )


def open_for(vk_id: int | None) -> bool:
    """Видит ли игрок руины: открыты всем или он в закрытой проверке."""
    if rc.OPEN:
        return True
    if vk_id is None:
        return False
    from config import get_settings

    return vk_id == get_settings().admin_vk_id or vk_id in rc.TESTER_VK_IDS


async def open_for_character(db: AsyncSession, character: Character) -> bool:
    if rc.OPEN:
        return True
    from models import User

    user = await db.get(User, character.user_id)
    return open_for(user.vk_id if user else None)


def touch(run: RuinRun, now: datetime | None = None) -> None:
    run.last_action_at = now or _now()


# --- Вход ---------------------------------------------------------------------


def entry_refusal(characters: list[Character]) -> str | None:
    if len(characters) > rc.MAX_PARTY:
        return f"В руины спускаются не больше {rc.MAX_PARTY} человек, а вас {len(characters)}."
    low = [c.name for c in characters if c.level < rc.MIN_LEVEL]
    if low:
        return f"В руины пускают с {rc.MIN_LEVEL} уровня. Не дорос: {', '.join(low)}."
    away = [c.name for c in characters if (c.pos_x, c.pos_y) != rc.ENTRY_CELL or c.travel_target_x is not None]
    if away:
        return f"Вся группа должна стоять у забоя. Нет на месте: {', '.join(away)}."
    return None


async def world_hp(db: AsyncSession, character: Character) -> tuple[int, int]:
    """(текущее, максимум) здоровья персонажа вне боя."""
    from services import item_service, vitals_service

    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    vit = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
    return vitals_service.current_hp(character, stats, vit), vitals_service.max_hp(character, stats, vit)


async def start(db: AsyncSession, leader: Character, characters: list[Character], rng: random.Random,
                now: datetime | None = None) -> RuinRun:
    """Группа спускается. Здоровье - то, с каким пришли: руины не лечат."""
    reason = entry_refusal(characters)
    if reason:
        raise RuinsError(reason)
    for c in characters:
        if await membership(db, c.id) is not None:
            raise RuinsError(f"{c.name} уже в руинах.")
    now = now or _now()
    layout = rules.generate(rng, 1)
    run = RuinRun(
        status=ACTIVE, leader_id=leader.id, floor=1, layout=layout, pos=layout["start"],
        visited=[layout["start"]], cleared=[layout["start"]], phase=WALK, deepest=1,
        started_at=now, last_action_at=now,
    )
    db.add(run)
    await db.flush()
    for c in characters:
        hp, _ = await world_hp(db, c)
        db.add(RuinMember(run_id=run.id, character_id=c.id, active=True, hp=max(1, hp),
                          dead=False, consumables_used=0, bag={}))
    await db.flush()
    return run


# --- Ходьба -------------------------------------------------------------------


def step_target(run: RuinRun, direction: str) -> int | None:
    return rules.exits(run.layout, run.pos).get(direction)


def propose(run: RuinRun, leader_id: int, direction: str, party: int, now: datetime | None = None) -> int:
    """Лидер выбрал направление. Вернёт комнату. Соло - шаг сразу (pending
    не ставится, вызывающий делает move)."""
    if run.phase != WALK:
        raise RuinsError("Сейчас не до шагов.")
    if run.leader_id != leader_id:
        raise RuinsError("Куда идти, решает лидер.")
    if run.pending:
        raise RuinsError("Группа ещё не двинулась на прошлый шаг.")
    target = step_target(run, direction)
    if target is None:
        raise RuinsError("Там глухая стена.")
    if party > 1:
        now = now or _now()
        run.pending = {"dir": direction, "to": target, "until": (now + timedelta(seconds=rc.MOVE_CONFIRM_SECONDS)).isoformat(),
                       "ok": [leader_id]}
    touch(run, now)
    return target


def confirm(run: RuinRun, character_id: int) -> None:
    """Участник подтвердил шаг (все ли - all_confirmed)."""
    if not run.pending:
        return
    ok = list(run.pending.get("ok", []))
    if character_id not in ok:
        ok.append(character_id)
    run.pending = {**run.pending, "ok": ok}


def all_confirmed(run: RuinRun, member_ids: list[int]) -> bool:
    return bool(run.pending) and set(member_ids) <= set(run.pending.get("ok", []))


def pending_due(run: RuinRun, now: datetime | None = None) -> bool:
    if not run.pending:
        return False
    return datetime.fromisoformat(run.pending["until"]) <= (now or _now())


def move(run: RuinRun, target: int) -> str:
    """Группа перешла в комнату. Вернёт её тип; с боем - фаза fight."""
    run.pending = None
    run.prev_pos = run.pos
    run.pos = target
    if target not in (run.visited or []):
        run.visited = [*(run.visited or []), target]
    kind = rules.room_kind(run.layout, target)
    if kind in rules.COMBAT_ROOMS and target not in (run.cleared or []):
        run.phase = FIGHT
    touch(run)
    return kind


async def snapshot_hp(db: AsyncSession, run: RuinRun) -> None:
    """Перед боем: здоровье на входе - его вернёт перезапуск посреди боя."""
    for m in await members(db, run.id):
        m.hp_before = m.hp


# --- Итоги боя ----------------------------------------------------------------


def _add(bag: dict, section: str, key: str, count: int) -> dict:
    bag = {k: dict(v) for k, v in (bag or {}).items()}
    part = bag.setdefault(section, {})
    part[key] = part.get(key, 0) + count
    return bag


async def room_won(db: AsyncSession, run: RuinRun, hp: dict[int, int], used: dict[int, int],
                   rng: random.Random) -> dict[int, dict]:
    """Комната зачищена. hp - здоровье после боя (0 - пал), used - зелий за
    этаж. Живые кладут в мешок трофеи; за босса - кубики рун и подъём павших.
    Вернёт находки: {id: {"trophies": {...}, "runes": [...]}}."""
    kind = rules.room_kind(run.layout, run.pos)
    run.cleared = [*(run.cleared or []), run.pos]
    found: dict[int, dict] = {}
    for m in await members(db, run.id):
        if m.character_id in hp:
            m.hp = hp[m.character_id]
            m.dead = m.hp <= 0
        if m.character_id in used:
            m.consumables_used = used[m.character_id]
        m.hp_before = None
        got: dict = {"trophies": {}, "runes": []}
        if not m.dead:
            drop = loot.roll_drop(rng, lc.ROLLS_BY_RING[rc.MOB_RING] * rc.ROOM_LOOT.get(kind, 1))
            bag = m.bag or {}
            for trophy_id, count in drop.items():
                bag = _add(bag, "trophies", trophy_id, count)
            got["trophies"] = drop
            if kind == rules.BOSS:
                from services import rune_service

                for _ in range(rules.roll_rune_dice(rng, run.floor)):
                    rune_id = rune_service.roll_rune(rng)
                    bag = _add(bag, "runes", rune_id, 1)
                    got["runes"].append(rune_id)
            m.bag = bag
        if kind == rules.BOSS and m.dead:
            m.dead = False
            m.hp = rc.RAISE_HP
            got["raised"] = True
        found[m.character_id] = got
    run.phase = CLEARED if kind == rules.BOSS else WALK
    touch(run)
    await db.flush()
    return found


async def next_floor(db: AsyncSession, run: RuinRun, rng: random.Random) -> None:
    """Лидер повёл глубже: новый этаж, лимит зелий заново."""
    if run.phase != CLEARED:
        raise RuinsError("Глубже - только после хозяина этажа.")
    run.floor += 1
    run.deepest = max(run.deepest or 1, run.floor)
    run.layout = rules.generate(rng, run.floor)
    run.pos = run.layout["start"]
    run.prev_pos = None
    run.visited = [run.pos]
    run.cleared = [run.pos]
    run.phase = WALK
    run.pending = None
    for m in await members(db, run.id):
        m.consumables_used = 0
    touch(run)
    await db.flush()


# --- Выход, гибель, изгнание ---------------------------------------------------


async def pay_out(db: AsyncSession, member: RuinMember) -> dict:
    """Мешок - персонажу: руны в сумку, трофеи к реликвиям."""
    from services import rune_service, trophy_service

    bag = member.bag or {}
    for rune_id, count in (bag.get("runes") or {}).items():
        await rune_service.grant(db, member.character_id, rune_id, count, reason="ruins")
    for trophy_id, count in (bag.get("trophies") or {}).items():
        await trophy_service.grant_specific(db, member.character_id, trophy_id, count)
    return bag


async def _set_world_hp(db: AsyncSession, member: RuinMember) -> None:
    from services import item_service, vitals_service

    character = await db.get(Character, member.character_id)
    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == member.character_id))
    if character is None or stats is None:
        return
    vit = (await item_service.compute_gear_bonus(db, member.character_id)).get("vit", 0)
    vitals_service.set_hp(character, stats, max(1, member.hp), vit)


async def exit_run(db: AsyncSession, run: RuinRun) -> dict[int, dict]:
    """Группа поднялась наверх живой: мешки выдаются. Вернёт мешки."""
    if run.phase != CLEARED:
        raise RuinsError("Выйти можно только после хозяина этажа.")
    paid = {}
    for m in await members(db, run.id):
        paid[m.character_id] = await pay_out(db, m)
        await _set_world_hp(db, m)
        m.active = False
        m.left_reason = EXITED
    _close(run, EXITED)
    await db.flush()
    return paid


def _close(run: RuinRun, outcome: str) -> None:
    run.status = DONE
    run.outcome = outcome
    run.finished_at = _now()
    run.pending = None
    run.vote = None


async def wipe(db: AsyncSession, run: RuinRun) -> list[int]:
    """Группа погибла: мешки сгорают. Вернёт, кто был внутри."""
    ids = []
    for m in await members(db, run.id):
        ids.append(m.character_id)
        m.bag = {}
        m.active = False
        m.left_reason = WIPED
    _close(run, WIPED)
    await db.flush()
    return ids


async def kick(db: AsyncSession, run: RuinRun, character_id: int) -> RuinMember | None:
    """Изгнан голосованием: выходит живым, мешок пропадает. Лидер изгнан -
    лидерство случайному из оставшихся (решение владельца)."""
    target = next((m for m in await members(db, run.id) if m.character_id == character_id), None)
    if target is None:
        return None
    await _set_world_hp(db, target)
    target.bag = {}
    target.active = False
    target.left_reason = "kicked"
    if run.pending:
        run.pending = {**run.pending, "ok": [c for c in run.pending.get("ok", []) if c != character_id]}
    left = [m for m in await members(db, run.id) if m.character_id != character_id]
    if run.leader_id == character_id and left:
        run.leader_id = random.choice(left).character_id
    if not left:
        _close(run, ABANDONED)
    await db.flush()
    return target


async def recover(db: AsyncSession) -> list[RuinRun]:
    """После перезапуска: бой комнаты жил в памяти - группа возвращается в
    комнату, откуда вошла, с тем здоровьем, с каким входила. Шаги и
    голосования сбрасываются."""
    runs = await active_runs(db)
    for run in runs:
        if run.phase == FIGHT:
            for m in await members(db, run.id):
                if m.hp_before is not None:
                    m.hp = m.hp_before
                    m.dead = m.hp <= 0
                    m.hp_before = None
            if run.prev_pos is not None:
                run.pos = run.prev_pos
            run.phase = WALK
        run.pending = None
        run.vote = None
    await db.flush()
    return runs


async def abandon_due(db: AsyncSession, now: datetime | None = None) -> list[tuple[int, list[int]]]:
    """Забеги без действий ABANDON_HOURS: мешки сгорают, все выходят живыми.
    Вернёт [(забег, участники)]."""
    now = now or _now()
    out = []
    for run in await active_runs(db):
        if run.phase == FIGHT or _aware(run.last_action_at) > now - timedelta(hours=rc.ABANDON_HOURS):
            continue
        ids = []
        for m in await members(db, run.id):
            await _set_world_hp(db, m)
            ids.append(m.character_id)
            m.bag = {}
            m.active = False
            m.left_reason = ABANDONED
        _close(run, ABANDONED)
        out.append((run.id, ids))
    await db.flush()
    return out
