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
from game import ruins_gifts as gifts_mod
from game import ruins_rooms
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
        return f"В руины спускаются до {rc.MAX_PARTY} человек, в группе {len(characters)}."
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


def exits_now(run: RuinRun) -> dict[str, int]:
    """Куда можно шагнуть сейчас. Обвал не пройден - только назад."""
    out = rules.exits(run.layout, run.pos)
    if rules.room_kind(run.layout, run.pos) == rules.CAVEIN and run.pos not in (run.cleared or []):
        out = {d: j for d, j in out.items() if j == run.prev_pos}
    return out


def propose(run: RuinRun, leader_id: int, direction: str, party: int, now: datetime | None = None) -> int:
    """Лидер выбрал направление. Вернёт комнату. Соло - шаг сразу (pending
    не ставится, вызывающий делает move)."""
    if run.phase not in (WALK, CLEARED):
        raise RuinsError("Сейчас идти нельзя - сначала закончите бой.")
    if run.leader_id != leader_id:
        raise RuinsError("Куда идти, решает лидер.")
    if run.pending:
        raise RuinsError("Группа ещё не пошла по прошлому шагу - ждём подтверждений.")
    if run.offer:
        raise RuinsError("Сначала выберите дар.")
    target = exits_now(run).get(direction)
    if target is None:
        raise RuinsError("Туда не пройти.")
    if party > 1:
        now = now or _now()
        run.pending = {"dir": direction, "to": target,
                       "until": (now + timedelta(seconds=rc.MOVE_CONFIRM_SECONDS)).isoformat(), "ok": [leader_id]}
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
    if boss_down(run) and not (run.extra or {}).get("boss_down"):
        run.extra = {**(run.extra or {}), "boss_down": True}  # забеги до 2026-11-05: флага не было
    run.pending = None
    run.prev_pos = run.pos
    run.pos = target
    if target not in (run.visited or []):
        run.visited = [*(run.visited or []), target]
    kind = rules.room_kind(run.layout, target)
    if kind in rules.COMBAT_ROOMS and target not in (run.cleared or []):
        run.phase = FIGHT
        run.extra = {**(run.extra or {}), "fight": {"kind": kind}}
    else:
        # После хозяина группа может пройтись по этажу (2026-11-05); лестницы
        # вниз и наверх - в его зале: вернулись туда - снова выбор.
        run.phase = CLEARED if boss_down(run) and target == run.layout.get("boss") else WALK
    touch(run)
    return kind


def boss_down(run: RuinRun) -> bool:
    """Хозяин этажа повержен (группа могла уйти из его зала)."""
    return run.phase == CLEARED or bool((run.extra or {}).get("boss_down"))


def room_open(run: RuinRun) -> bool:
    """В комнате ещё есть что выбрать (особая комната до выбора)."""
    return rules.room_kind(run.layout, run.pos) in rules.CHOICE_ROOMS and run.pos not in (run.cleared or [])


def _mark_cleared(run: RuinRun) -> None:
    if run.pos not in (run.cleared or []):
        run.cleared = [*(run.cleared or []), run.pos]


async def snapshot_hp(db: AsyncSession, run: RuinRun) -> None:
    """Перед боем: здоровье на входе - его вернёт перезапуск посреди боя."""
    for m in await members(db, run.id):
        m.hp_before = m.hp


# --- Здоровье вне боя ---------------------------------------------------------


async def max_hp(db: AsyncSession, character_id: int, gifts: list | None) -> int:
    """Максимум здоровья с дарами группы (Толстая шкура, Дурная кровь)."""
    character = await db.get(Character, character_id)
    if character is None:
        return 1
    _, top = await world_hp(db, character)
    bonus = gifts_mod.mods(gifts).get("max_hp_bonus", 0.0)
    return max(1, round(top * (1 + bonus)))


async def heal_alive(db: AsyncSession, run: RuinRun, share: float) -> None:
    for m in await members(db, run.id):
        if not m.dead:
            top = await max_hp(db, m.character_id, run.gifts)
            m.hp = min(top, m.hp + round(top * share))


async def hurt_alive(db: AsyncSession, run: RuinRun, share: float, only: set[int] | None = None) -> None:
    """Урон вне боя не убивает: до 1 HP."""
    for m in await members(db, run.id):
        if not m.dead and (only is None or m.character_id in only):
            top = await max_hp(db, m.character_id, run.gifts)
            m.hp = max(1, m.hp - round(top * share))


def floor_potions(run: RuinRun) -> int:
    """Зелий на этаж с дарами."""
    return rc.CONSUMABLES_PER_FLOOR + (1 if gifts_mod.has(run.gifts, "spare_vial") else 0)


def battle_potions_start(run: RuinRun, used_on_floor: int) -> int:
    """Сколько зелий «уже выпито» на старте боя: в бою лимит обычный (5),
    на этаже - floor_potions; Обет молчания и засада закрывают зелья."""
    from game.combat import consumable_limit

    kind = ((run.extra or {}).get("fight") or {}).get("kind")
    if gifts_mod.has(run.gifts, "vow_silence") or kind == rules.AMBUSH:
        return consumable_limit.LIMIT
    left = max(floor_potions(run) - used_on_floor, 0)
    return consumable_limit.LIMIT - min(consumable_limit.LIMIT, left)


def potions_closed_text(run: RuinRun, used_on_floor: int) -> str | None:
    """Своя причина, если руины закрыли зелья на этот бой. Иначе None:
    обычный лимит боя скажет о себе сам."""
    kind = ((run.extra or {}).get("fight") or {}).get("kind")
    if kind == rules.AMBUSH:
        return "‼️ ЗАСАДА: в этом бою до зелий не дотянуться ‼️\nВ следующем бою снова можно."
    if gifts_mod.has(run.gifts, "vow_silence"):
        return "🤐 Обет молчания: пока дар действует, зелья пить нельзя."
    if used_on_floor >= floor_potions(run):
        n = floor_potions(run)
        return f"🧪 Зелья на этаж кончились: {n} из {n}. На следующем этаже счёт заново."
    return None


# --- Дары ---------------------------------------------------------------------


def start_offer(run: RuinRun, tiers: tuple[str, ...], rng: random.Random, now: datetime | None = None,
                drop: str | None = None) -> list[str]:
    """Лидеру - три дара на выбор. Пусто - даров не осталось."""
    owned = [g for g in gifts_mod.ids(run.gifts) if g != drop]
    ids = gifts_mod.offer(rng, owned, tiers)
    if not ids:
        return []
    until = (now or _now()) + timedelta(seconds=rc.GIFT_SECONDS)
    run.offer = {"ids": ids, "until": until.isoformat(), "drop": drop}
    touch(run, now)
    return ids


def take_gift(run: RuinRun, gift_id: str) -> None:
    """Дар выбран: колодец снимает старый, новый - в список."""
    offer = run.offer or {}
    if gift_id not in offer.get("ids", []):
        raise RuinsError("Этот дар уже не предлагают.")
    # Дар - до конца этажа floor + GIFT_FLOORS - 1 (2026-11-06). Уже взятый
    # не дублируется, а продлевается.
    until = (run.floor or 1) + rc.GIFT_FLOORS - 1
    gifts = [g for g in run.gifts or [] if g["id"] not in (offer.get("drop"), gift_id)]
    gifts.append({"id": gift_id, "until": until})
    run.gifts = gifts
    run.offer = None
    touch(run)


def offer_due(run: RuinRun, now: datetime | None = None) -> bool:
    return bool(run.offer) and datetime.fromisoformat(run.offer["until"]) <= (now or _now())


def _curse_floor(run: RuinRun, rng: random.Random) -> str | None:
    pool = [g.id for g in gifts_mod.GIFTS if g.tier == gifts_mod.CURSED and g.id not in gifts_mod.ids(run.gifts)]
    if not pool:
        return None
    gift_id = rng.choice(pool)
    run.gifts = [*(run.gifts or []), {"id": gift_id, "floor": True}]
    return gift_id


# --- Особые комнаты -----------------------------------------------------------


def _roll_loot(rng: random.Random, rolls: int) -> dict[str, int]:
    return loot.roll_drop(rng, lc.ROLLS_BY_RING[rc.MOB_RING] * rolls)


def _bag_trophies(member: RuinMember, drop: dict[str, int]) -> None:
    bag = member.bag or {}
    for trophy_id, count in drop.items():
        bag = _add(bag, "trophies", trophy_id, count)
    member.bag = bag


def _take_trophies(member: RuinMember, count: int) -> bool:
    """Снять из мешка count реликвий, сначала дешёвые. False - не хватает."""
    from services import trophy_service

    bag = {k: dict(v) for k, v in (member.bag or {}).items()}
    trophies = bag.get("trophies") or {}
    if sum(trophies.values()) < count:
        return False
    for tdef in trophy_service.trophy_defs_ordered():
        while count and trophies.get(tdef.id):
            trophies[tdef.id] -= 1
            count -= 1
            if not trophies[tdef.id]:
                trophies.pop(tdef.id)
    bag["trophies"] = trophies
    member.bag = bag
    return True


async def trap(db: AsyncSession, run: RuinRun, rng: random.Random) -> dict[int, bool]:
    """Ловушка срабатывает сама при входе: каждый живой - бросок ловкости.
    Вернёт {id: увернулся}."""
    from services import item_service

    out = {}
    hit: set[int] = set()
    for m in await members(db, run.id):
        if m.dead:
            continue
        stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == m.character_id))
        agi = (stats.agility if stats else 0) + (await item_service.compute_gear_bonus(db, m.character_id)).get("agi", 0)
        dodged = rng.random() < ruins_rooms.dodge_chance(agi)
        out[m.character_id] = dodged
        if not dodged:
            hit.add(m.character_id)
    await hurt_alive(db, run, rc.TRAP_HIT, only=hit)
    _mark_cleared(run)
    touch(run)
    await db.flush()
    return out


async def choose(db: AsyncSession, run: RuinRun, leader_id: int, choice: str, rng: random.Random) -> dict:
    """Лидер выбрал, что делать в особой комнате. Вернёт {"lines": [ключи],
    "fight": тип или None, "offer": [дары], "loot": {id: добыча}, "curse"}."""
    if run.leader_id != leader_id:
        raise RuinsError("Решает лидер.")
    if run.phase != WALK or run.pending or run.offer:
        raise RuinsError("Сейчас не до этого.")
    kind = rules.room_kind(run.layout, run.pos)
    if not room_open(run):
        raise RuinsError("Здесь уже всё сделано.")
    result: dict = {"lines": [], "fight": None, "offer": [], "loot": {}}
    members_now = await members(db, run.id)
    event = rules.event_of(run.layout, run.pos)
    if kind == rules.WELL:
        if choice == "leave":
            result["lines"].append("leave")
        elif choice.startswith("drop:") and gifts_mod.has(run.gifts, choice[5:]):
            result["offer"] = start_offer(run, ruins_rooms.ANY, rng, drop=choice[5:])
            result["lines"].append("well")
        else:
            raise RuinsError("Сначала выберите, какой дар бросить в колодец.")
        _mark_cleared(run)
        touch(run)
        await db.flush()
        return result
    if choice not in ruins_rooms.choices(kind, event):
        raise RuinsError("Эта кнопка здесь не работает.")
    if kind == rules.CRYPT and choice == "raise" and not any(m.dead for m in members_now):
        raise RuinsError("Поднимать некого: все на ногах.")
    if kind == rules.CHAPEL and choice == "pray":
        poor = [m for m in members_now if not m.dead
                and sum(((m.bag or {}).get("trophies") or {}).values()) < rc.CHAPEL_PRICE]
        if poor:
            raise RuinsError(f"Чаша берёт только найденное здесь, внизу: нужно по {rc.CHAPEL_PRICE} реликвии "
                             "в мешке руин у каждого живого. Реликвии из сумки не в счёт.")
    effects = ruins_rooms.outcome(kind, choice, rng, event)
    if not effects:
        result["lines"].append("leave")
    for e in effects:
        if "line" in e:
            result["lines"].append(e["line"])
        if "hurt" in e:
            await hurt_alive(db, run, e["hurt"])
        if "heal" in e:
            await heal_alive(db, run, e["heal"])
        if "raise" in e:
            for m in members_now:
                if m.dead:
                    m.dead = False
                    m.hp = max(1, round(await max_hp(db, m.character_id, run.gifts) * e["raise"]))
        if "pay" in e:
            for m in members_now:
                if not m.dead:
                    _take_trophies(m, e["pay"])
        if "loot" in e:
            for m in members_now:
                if not m.dead:
                    drop = _roll_loot(rng, e["loot"])
                    _bag_trophies(m, drop)
                    result["loot"][m.character_id] = drop
        if "curse" in e:
            cursed = _curse_floor(run, rng)
            if cursed:
                result["curse"] = cursed
        if "offer" in e:
            result["offer"] = start_offer(run, tuple(e["offer"]), rng)
        if "fight" in e:
            result["fight"] = e["fight"]
            run.extra = {**(run.extra or {}), "fight": {"kind": e["fight"], "after": e.get("after")}}
            run.phase = FIGHT
    if not result["fight"]:
        _mark_cleared(run)
    touch(run)
    await db.flush()
    return result


# --- Итоги боя ----------------------------------------------------------------


def _add(bag: dict, section: str, key: str, count: int) -> dict:
    bag = {k: dict(v) for k, v in (bag or {}).items()}
    part = bag.setdefault(section, {})
    part[key] = part.get(key, 0) + count
    return bag


def _firsts(character: Character) -> list[int]:
    return list((character.ui_flags or {}).get("ruins_firsts") or [])


def fight_kind(run: RuinRun) -> str:
    """Тип текущего боя: из выбора в комнате или сама комната."""
    return ((run.extra or {}).get("fight") or {}).get("kind") or rules.room_kind(run.layout, run.pos)


async def room_won(db: AsyncSession, run: RuinRun, hp: dict[int, int], used: dict[int, int],
                   rng: random.Random, *, kills: int = 0, prayer_used: list[int] | None = None,
                   top_hp: dict[int, int] | None = None, bosses: int = 0,
                   common_kills: int = 0) -> dict[int, dict]:
    """Комната зачищена. hp - здоровье после боя (0 - пал), used - зелий
    выпито на этаже, top_hp - максимум здоровья в бою, bosses - сколько
    уникальных боссов было в зале, kills - убито всего, common_kills - из них
    рядовых. Живые кладут в мешок трофеи и руны с рядовых; за хозяина -
    кубики рун и подъём павших; за первого уникального - ларцы рун сразу.
    Убитые идут в задание наставника «убей N» и счётчик убийств, как в
    групповом бою в мире (2026-11-12: не шли).
    Вернёт находки: {id: {"trophies", "runes", "raised", "chests"}}."""
    from game.economy import brand_config as brc
    from services import (
        lootbox_service,
        premium_service,
        quest_service,
        resist_service,
        rune_service,
    )
    from services.group_combat_service import group_kills_share

    fight = (run.extra or {}).get("fight") or {}
    kind = fight.get("kind") or rules.room_kind(run.layout, run.pos)
    boss = kind == rules.BOSS
    _mark_cleared(run)
    extra = dict(run.extra or {})
    extra["kills"] = int(extra.get("kills", 0)) + kills
    extra["prayer"] = list(prayer_used if prayer_used is not None else extra.get("prayer") or [])
    extra.pop("fight", None)
    run.extra = extra
    top_hp = top_hp or {}
    rolls = rc.room_loot(kind, run.floor) + (1 if kind == rules.ELITE and gifts_mod.has(run.gifts, "usurer_mark") else 0)
    dice_bonus = (1 if gifts_mod.has(run.gifts, "greedy_palm") else 0) + (2 if gifts_mod.has(run.gifts, "heavy_bag") else 0)
    first_floor = boss and run.floor % 5 == 0
    found: dict[int, dict] = {}
    party = await members(db, run.id)
    kills_each = group_kills_share(kills, len(party))
    for m in party:
        if m.character_id in hp:
            m.hp = hp[m.character_id]
            m.dead = m.hp <= 0
        if m.character_id in used:
            m.consumables_used = used[m.character_id]
        if kills_each:
            killer = await db.get(Character, m.character_id)
            if killer is not None:
                killer.mobs_killed += kills_each
        m.hp_before = None
        top = top_hp.get(m.character_id) or await max_hp(db, m.character_id, run.gifts)
        got: dict = {"trophies": {}, "runes": []}
        if not m.dead:
            drop = _roll_loot(rng, rolls)
            _bag_trophies(m, drop)
            got["trophies"] = drop
            character = await db.get(Character, m.character_id)
            if character is not None:
                for _ in range(kills):
                    await quest_service.record_kill(db, character)
                # Руна с рядового моба (2026-11-12, владелец) - в мешок, как с хозяина.
                chance = rc.COMMON_RUNE_CHANCE * (brc.RUNE_DROP_MULT if premium_service.is_brand(character) else 1.0)
                for _ in range(common_kills):
                    if rng.random() < chance:
                        rune_id = rune_service.roll_rune(rng)
                        m.bag = _add(m.bag or {}, "runes", rune_id, 1)
                        got["runes"].append(rune_id)
            # Перстень Несгоревшего (2026-11-06, владелец): как с мобов
            # исследования - бросок за каждого убитого, сразу игроку, мимо мешка.
            if character is not None:
                for _ in range(kills):
                    ring = await resist_service.maybe_drop_ring(db, character, rng)
                    if ring is not None:
                        got["ring"] = ring
                        break
            if boss:
                bag = m.bag or {}
                dice = rc.rune_dice(run.floor) + dice_bonus
                # Клеймо Хранителя: кубик рун выпадает чаще.
                die = rc.rune_die_chance(run.floor) * (
                    brc.RUNE_DROP_MULT if character is not None and premium_service.is_brand(character) else 1.0)
                for _ in range(sum(1 for _ in range(dice) if rng.random() < die)):
                    rune_id = rune_service.roll_rune(rng)
                    bag = _add(bag, "runes", rune_id, 1)
                    got["runes"].append(rune_id)
                m.bag = bag
            if gifts_mod.has(run.gifts, "novice_flask"):
                m.hp = min(top, m.hp + round(top * rc.FLASK_HEAL))
        if boss and m.dead:
            m.dead = False
            m.hp = rc.RAISE_HP
            got["raised"] = True
        if boss:
            # Топ руин (2026-11-13): этаж пройден всеми, кто в забеге, и павшими тоже.
            m.floors = run.floor
            m.floors_at = _now()
        if boss and gifts_mod.has(run.gifts, "bandage"):
            m.hp = min(top, m.hp + round(top * rc.BANDAGE_HEAL))
        if first_floor:
            character = await db.get(Character, m.character_id)
            if character is not None and run.floor not in _firsts(character):
                flags = dict(character.ui_flags or {})
                flags["ruins_firsts"] = [*_firsts(character), run.floor]
                character.ui_flags = flags
                chests = rc.FIRST_KILL_CHESTS * max(1, bosses)
                for _ in range(chests):
                    await lootbox_service.grant_chest(db, character, character.daily_streak, lootbox_service.RUNE)
                got["chests"] = chests
        found[m.character_id] = got
    if boss and gifts_mod.has(run.gifts, "greedy_palm"):
        run.gifts = [g for g in run.gifts if g["id"] != "greedy_palm"]
    run.phase = CLEARED if boss else WALK
    if boss:
        run.extra = {**run.extra, "boss_down": True}
    after = fight.get("after") or {}
    if not boss and (kind == rules.ELITE or after.get("offer")):
        start_offer(run, tuple(after.get("offer") or ruins_rooms.GOOD), rng)
    touch(run)
    await db.flush()
    return found


async def next_floor(db: AsyncSession, run: RuinRun, rng: random.Random) -> None:
    """Лидер повёл глубже: новый этаж, лимит зелий заново, проклятие
    кладовой и «Чужая молитва» - заново."""
    if run.phase != CLEARED:
        raise RuinsError("Глубже - только после хозяина этажа.")
    run.floor += 1
    run.deepest = max(run.deepest or 1, run.floor)
    used = rules.once_rooms(run.layout or {"rooms": {}}, (run.extra or {}).get("once_rooms", []))
    run.extra = {**(run.extra or {}), "once_rooms": used}
    run.layout = rules.generate(rng, run.floor, used)
    run.pos = run.layout["start"]
    run.prev_pos = None
    run.visited = [run.pos]
    run.cleared = [run.pos]
    run.phase = WALK
    run.pending = None
    run.offer = None
    # Проклятия кладовой - на этаж, дары - до своего этажа (до 2026-11-06 срока
    # не было: такие дары считаются взятыми на том этаже, откуда уходят).
    kept = []
    for g in run.gifts or []:
        if g.get("floor"):
            continue
        until = g.get("until", run.floor - 1 + rc.GIFT_FLOORS)
        if until >= run.floor:
            kept.append({**g, "until": until})
    run.gifts = kept
    run.extra = {**{k: v for k, v in (run.extra or {}).items() if k != "boss_down"}, "prayer": []}
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


async def brand_salvage(db: AsyncSession, run: RuinRun, rng: random.Random) -> dict[int, dict[str, int]]:
    """Группа легла: что из мешка уносит носитель Клейма Хранителя - долю
    реликвий (руны сгорают). Ничего не выдаёт - выдача после штрафа смерти,
    чтобы штраф не съел спасённое. Звать до wipe(): он чистит мешки."""
    from game.economy import brand_config as brc
    from services import premium_service

    out: dict[int, dict[str, int]] = {}
    for m in await members(db, run.id):
        character = await db.get(Character, m.character_id)
        if character is None or not premium_service.is_brand(character):
            continue
        kept = {}
        for trophy_id, count in ((m.bag or {}).get("trophies") or {}).items():
            share = count * brc.WIPE_KEEP_SHARE
            n = int(share) + (1 if rng.random() < share - int(share) else 0)
            if n > 0:
                kept[trophy_id] = n
        if kept:
            out[m.character_id] = kept
    return out


async def grant_salvage(db: AsyncSession, character_id: int, kept: dict[str, int]) -> None:
    from services import trophy_service

    for trophy_id, count in kept.items():
        await trophy_service.grant_specific(db, character_id, trophy_id, count)


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
            run.phase = CLEARED if boss_down(run) and run.pos == run.layout.get("boss") else WALK
        run.pending = None
        run.vote = None
        if run.extra and run.extra.get("fight"):
            run.extra = {k: v for k, v in run.extra.items() if k != "fight"}
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
