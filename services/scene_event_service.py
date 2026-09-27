"""Исходы событий со сценами (патч 110): награды, цены, следы, эффекты.

Все награды считаются в «мобах»: 1.0 = опыт и броски трофеев обычного моба
клетки, золото - ожидаемая цена трофеев такого моба. Контент не держит
абсолютных чисел, и событие само растёт с кольцом и уровнем.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot import raid_key_texts
from game.combat import display
from game.economy import loot, mining
from game.economy import loot_config as lc
from game.world import grid, scene_events
from game.world.scene_events import Requirement, SceneResult
from models import Character, CharacterEventEffect, CharacterStats, CharacterTrophy, EventTrail
from services import (
    daily_service,
    elixir_service,
    experience_service,
    group_service,
    item_service,
    mining_service,
    raid_key_service,
    story_service,
    trial_service,
    trophy_service,
    vitals_service,
    wallet_service,
)

#: «Разорение» (максимальное наказание в «ещё чуть-чуть»): здоровье падает до
#: этой доли и сгорает такая доля всех трофеев. Смерти от события нет -
#: так решено, чтобы не переписывать механику смерти.
RUIN_HP_PCT = 0.01
RUIN_TROPHY_SHARE = 0.3

HEAL_BY_RING = {1: "heal_small", 2: "heal_small", 3: "heal_medium", 4: "heal_medium", 5: "heal_large"}
HEAL_IDS = ("heal_small", "heal_medium", "heal_large")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


# --- Единицы награды --------------------------------------------------------------


def gold_unit(character: Character) -> int:
    """Ожидаемая цена трофеев с одного моба этой клетки."""
    per_roll = sum(
        chance * (trophy_service.trophy_def(tid).sell_price if trophy_service.trophy_def(tid) else 0)
        for tid, chance in lc.TROPHY_ROLL_CHANCES.items()
    )
    return max(1, round(per_roll * scene_events.ring_rolls(character.pos_x, character.pos_y)))


def gold_amount(character: Character, units: float) -> int:
    return max(1, round(units * gold_unit(character)))


async def total_stats(db: AsyncSession, character: Character, stats: CharacterStats) -> dict[str, int]:
    bonus = await item_service.compute_gear_bonus(db, character.id)
    return {
        "str": stats.strength + bonus.get("str", 0),
        "agi": stats.agility + bonus.get("agi", 0),
        "int": stats.intellect + bonus.get("int", 0),
        "vit": stats.vitality + bonus.get("vit", 0),
        "wil": stats.will + bonus.get("wil", 0),
    }


# --- Требования и цена ------------------------------------------------------------


async def _heal_in_stock(db: AsyncSession, character_id: int) -> str | None:
    stock = {d.id: n for d, n in await elixir_service.get_stock(db, character_id)}
    return next((eid for eid in HEAL_IDS if stock.get(eid)), None)


async def _cheapest_trophy(db: AsyncSession, character_id: int) -> str | None:
    stock = await trophy_service.get_stock(db, character_id)
    return stock[0][0].id if stock else None


async def can_afford(db: AsyncSession, character: Character, req: Requirement | None) -> bool:
    if req is None:
        return True
    wallet = await wallet_service.get_wallet(db, character.id)
    if req.gold and wallet.farm_currency < gold_amount(character, req.gold):
        return False
    if req.gems and wallet.donate_currency < req.gems:
        return False
    if req.elixir == "heal" and await _heal_in_stock(db, character.id) is None:
        return False
    if req.elixir and req.elixir != "heal":
        stock = {d.id: n for d, n in await elixir_service.get_stock(db, character.id)}
        if not stock.get(req.elixir):
            return False
    return not (req.trophy and await _cheapest_trophy(db, character.id) is None)


async def pay(db: AsyncSession, character: Character, req: Requirement | None) -> bool:
    """Списывает цену выбора. False - нечем заплатить (успели потратить)."""
    if req is None:
        return True
    try:
        if req.gold:
            await wallet_service.charge(db, character.id, "farm", gold_amount(character, req.gold))
        if req.gems:
            await wallet_service.charge(db, character.id, "donate", req.gems)
    except wallet_service.NotEnoughCurrency:
        return False
    if req.elixir:
        elixir_id = await _heal_in_stock(db, character.id) if req.elixir == "heal" else req.elixir
        if elixir_id is None or not await elixir_service.consume(db, character.id, elixir_id):
            return False
    if req.trophy:
        trophy_id = await _cheapest_trophy(db, character.id)
        if trophy_id is None:
            return False
        result = await db.execute(
            update(CharacterTrophy)
            .where(CharacterTrophy.character_id == character.id, CharacterTrophy.trophy_id == trophy_id,
                   CharacterTrophy.count > 0)
            .values(count=CharacterTrophy.count - 1)
        )
        if not result.rowcount:
            return False
    return True


def cost_label(character: Character, req: Requirement | None) -> str:
    """Подпись цены на кнопке: « · 120 зол.»."""
    if req is None:
        return ""
    parts = []
    if req.gold:
        parts.append(f"{gold_amount(character, req.gold)} зол.")
    if req.gems:
        parts.append(f"{req.gems} 💎")
    if req.elixir:
        parts.append("зелье")
    if req.trophy:
        parts.append("трофей")
    return f" · {', '.join(parts)}" if parts else ""


# --- Исход ------------------------------------------------------------------------


@dataclass
class Applied:
    lines: list[str] = field(default_factory=list)
    levels_gained: int = 0
    new_level: int = 1
    group_kick: "group_service.LevelGapKick | None" = None
    daily_completed: list = field(default_factory=list)


async def _add_xp(db, character, stats, units: float, applied: Applied) -> None:
    zone_level = grid.mob_level_at(character.pos_x, character.pos_y, character.level)
    xp = experience_service.event_xp(zone_level, character.level, units)
    levelup = experience_service.add_experience(character, stats, xp)
    applied.levels_gained += levelup.levels_gained
    applied.new_level = levelup.new_level
    if levelup.levels_gained > 0:
        applied.group_kick = await group_service.enforce_level_gap(db, character)
    line = display.xp_delta_line(levelup.xp_awarded, premium=levelup.premium_applied)
    if line:
        applied.lines.append(line)


async def grant_trophies(db, character, units: float, rng: random.Random, applied: Applied,
                         source: str = "event") -> None:
    exact = units * scene_events.ring_rolls(character.pos_x, character.pos_y)
    rolls = int(exact) + (1 if rng.random() < exact - int(exact) else 0)
    drop = loot.roll_drop(rng, rolls)
    if not drop and units >= 1:
        drop = loot.roll_guaranteed_drop(rng, 1)
    if not drop:
        return
    await trophy_service._grant(db, character.id, drop)
    line = trophy_service.format_drop_line(drop, source=source)
    if line:
        applied.lines.append(line)
    if character.subclass is not None:
        await trial_service.record_trophies(db, character, drop)
    progress = await daily_service.record_trophies(db, character, drop)
    applied.daily_completed += progress.completed


async def grant_gold(db, character, units: float, applied: Applied) -> int:
    amount = gold_amount(character, units)
    await wallet_service.deposit(db, character.id, "farm", amount)
    applied.lines.append(f"💰 +{amount} золота")
    return amount


async def grant_ore(db, character, count: int, rng: random.Random, applied: Applied) -> None:
    tier = grid.ring_tier(character.pos_x, character.pos_y)
    got: dict[str, int] = {}
    for _ in range(count):
        ore_id = mining.roll_ore_id(rng, tier)
        got[ore_id] = got.get(ore_id, 0) + 1
    for ore_id, n in got.items():
        await mining_service.add_ore(db, character.id, ore_id, "common", n)
    names = []
    for ore_id, n in got.items():
        ore = mining.ore_def(ore_id)
        names.append(f"{ore.emoji} {ore.name}" + (f" ×{n}" if n > 1 else ""))
    applied.lines.append("⛏ " + ", ".join(names))


async def _damage(db, character, stats, pct_range: list[float], rng, applied: Applied) -> None:
    vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
    max_hp = vitals_service.max_hp(character, stats, vit_bonus)
    current = vitals_service.current_hp(character, stats, vit_bonus)
    pct = rng.uniform(pct_range[0], pct_range[-1]) / 100
    new_hp = max(1, current - round(max_hp * pct))  # событие не убивает
    vitals_service.set_hp(character, stats, new_hp, vit_bonus)
    applied.lines.append(display.hp_delta_line(current, new_hp, max_hp))


async def ruin(db, character, stats, rng: random.Random, applied: Applied) -> None:
    """Здоровье до 1% и сгорает часть трофеев (случайных)."""
    vit_bonus = (await item_service.compute_gear_bonus(db, character.id)).get("vit", 0)
    max_hp = vitals_service.max_hp(character, stats, vit_bonus)
    current = vitals_service.current_hp(character, stats, vit_bonus)
    new_hp = max(1, round(max_hp * RUIN_HP_PCT))
    vitals_service.set_hp(character, stats, min(current, new_hp), vit_bonus)
    applied.lines.append(display.hp_delta_line(current, min(current, new_hp), max_hp))
    rows = list((await db.scalars(
        select(CharacterTrophy).where(CharacterTrophy.character_id == character.id, CharacterTrophy.count > 0)
        .with_for_update()
    )).all())
    units = [row.trophy_id for row in rows for _ in range(row.count)]
    if not units:
        return
    lost_n = max(1, round(len(units) * RUIN_TROPHY_SHARE))
    lost: dict[str, int] = {}
    for trophy_id in rng.sample(units, lost_n):
        lost[trophy_id] = lost.get(trophy_id, 0) + 1
    for row in rows:
        if row.trophy_id in lost:
            row.count -= lost[row.trophy_id]
    await db.flush()
    applied.lines.append(trophy_service.format_drop_line(lost, source="ruin") or "")


async def apply_result(
    db: AsyncSession, character: Character, stats: CharacterStats, result: SceneResult,
    rng: random.Random, applied: Applied | None = None,
) -> Applied:
    """Всё, кроме перехода по сцене и боя (их ведёт обработчик)."""
    applied = applied or Applied(new_level=character.level)
    if result.text:
        applied.lines.append(result.text)
    rewarded = False
    if result.reward:
        await _add_xp(db, character, stats, result.reward, applied)
        await grant_trophies(db, character, result.reward, rng, applied)
        rewarded = True
    if result.xp:
        await _add_xp(db, character, stats, result.xp, applied)
        rewarded = True
    if result.gold:
        await grant_gold(db, character, result.gold, applied)
        rewarded = True
    if result.elixir:
        elixir_id = (
            HEAL_BY_RING[grid.ring_tier(character.pos_x, character.pos_y)]
            if result.elixir == "heal" else result.elixir
        )
        await elixir_service.grant(db, character.id, elixir_id, 1)
        elixir = elixir_service.elixir_def(elixir_id)
        applied.lines.append(f"{elixir.emoji} {elixir.name} - в сумку")
        rewarded = True
    if result.item:
        zone_level = grid.mob_level_at(character.pos_x, character.pos_y, character.level)
        item = await item_service.grant_random_item(db, character, zone_level, rng)
        applied.lines.append(item_service.format_drop_announcement(item))
        rewarded = True
    if result.ore:
        await grant_ore(db, character, result.ore, rng, applied)
        rewarded = True
    if result.damage:
        await _damage(db, character, stats, result.damage, rng, applied)
    if result.ruin:
        await ruin(db, character, stats, rng, applied)
    if result.effect:
        applied.lines.append(await apply_effect(db, character.id, result.effect))
    if result.trail:
        line = await create_trail(db, character, result.trail, rng)
        if line:
            applied.lines.append(line)
    if rewarded and await raid_key_service.maybe_grant(db, character, rng):
        applied.lines.append(raid_key_texts.raid_key_drop_line())
    applied.lines = [line for line in applied.lines if line]
    return applied


async def finish_event(db: AsyncSession, character: Character, applied: Applied) -> None:
    """Событие пройдено до конца - засчитать ежедневку «Любопытный»."""
    progress = await daily_service.record_event_choice(db, character)
    applied.daily_completed += progress.completed


# --- Эффекты на N боёв -----------------------------------------------------------


async def apply_effect(db: AsyncSession, character_id: int, effect_id: str) -> str:
    effect = scene_events.content().effects[effect_id]
    row = await db.scalar(select(CharacterEventEffect).where(
        CharacterEventEffect.character_id == character_id, CharacterEventEffect.effect_id == effect_id,
    ))
    if row is None:
        db.add(CharacterEventEffect(character_id=character_id, effect_id=effect_id, fights_left=effect.fights))
    else:
        row.fights_left = effect.fights
    await db.flush()
    return f"{effect.emoji} {effect.name} - на {effect.fights} {_fights_word(effect.fights)}. {effect.text}".strip()


def _fights_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "бой"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "боя"
    return "боёв"


async def active_effects(db: AsyncSession, character_id: int) -> list[tuple[str, int]]:
    rows = (await db.scalars(select(CharacterEventEffect).where(
        CharacterEventEffect.character_id == character_id, CharacterEventEffect.fights_left > 0,
    ))).all()
    known = scene_events.content().effects
    return [(r.effect_id, r.fights_left) for r in rows if r.effect_id in known]


async def solo_modifiers(db: AsyncSession, character: Character, base: dict[str, float]) -> dict[str, float]:
    """Модификаторы пресета + эффекты событий - для одиночных боёв с мобами."""
    merged = dict(base)
    effects = scene_events.content().effects
    for effect_id, _left in await active_effects(db, character.id):
        for key, value in effects[effect_id].modifiers.items():
            merged[key] = merged.get(key, 0.0) + value
    return merged


async def trophy_bonus(db: AsyncSession, character_id: int) -> float:
    effects = scene_events.content().effects
    return sum(effects[eid].trophy_bonus for eid, _ in await active_effects(db, character_id))


async def extra_kill_trophies(db: AsyncSession, character: Character, rng: random.Random) -> dict[str, int]:
    """Лишний бросок трофеев с моба (эффект «больше трофеев»)."""
    drop = loot.roll_guaranteed_drop(rng, 1)
    await trophy_service._grant(db, character.id, drop)
    return drop


async def tick_effects(db: AsyncSession, character_id: int) -> list[str]:
    """Один одиночный бой с мобом прошёл. Возвращает строки о закончившихся."""
    rows = (await db.scalars(select(CharacterEventEffect).where(
        CharacterEventEffect.character_id == character_id,
    ))).all()
    ended = []
    effects = scene_events.content().effects
    for row in rows:
        row.fights_left -= 1
        if row.fights_left <= 0:
            if row.effect_id in effects:
                ended.append(f"{effects[row.effect_id].emoji} {effects[row.effect_id].name} - прошло.")
            await db.delete(row)
    await db.flush()
    return ended


# --- Следы ------------------------------------------------------------------------


async def create_trail(db: AsyncSession, character: Character, kind: str, rng: random.Random,
                       stage: int = 1) -> str | None:
    trail_def = scene_events.content().trails[kind]
    cell = scene_events.pick_trail_cell(rng, character.pos_x, character.pos_y)
    if cell is None:
        return None
    await db.execute(delete(EventTrail).where(EventTrail.character_id == character.id))
    db.add(EventTrail(
        character_id=character.id, kind=kind, x=cell[0], y=cell[1], stage=stage,
        expires_at=_now() + timedelta(minutes=trail_def.minutes),
    ))
    await db.flush()
    direction = story_service.compass_direction(character.pos_x, character.pos_y, *cell)
    return (
        f"{trail_def.emoji} {trail_def.hint} {direction}, клетка ({cell[0]}; {cell[1]}). "
        f"Остынет через {trail_def.minutes} мин."
    )


async def get_trail(db: AsyncSession, character_id: int) -> EventTrail | None:
    return await db.get(EventTrail, character_id)


def trail_alive(trail: EventTrail) -> bool:
    return _aware(trail.expires_at) > _now()


async def take_trail_here(db: AsyncSession, character: Character) -> EventTrail | None:
    """След, который обрывается на этой клетке и ещё не остыл, - снимается
    (одно исследование = один финал). Остывший удаляется молча."""
    trail = await db.scalar(
        select(EventTrail).where(EventTrail.character_id == character.id).with_for_update()
    )
    if trail is None:
        return None
    if _aware(trail.expires_at) <= _now():
        await db.delete(trail)
        await db.flush()
        return None
    if (trail.x, trail.y) != (character.pos_x, character.pos_y):
        return None
    await db.delete(trail)
    await db.flush()
    return trail


async def summary_lines(db: AsyncSession, character: Character) -> list[str]:
    """Строки для сводки локации: след и эффекты."""
    lines = []
    trail = await get_trail(db, character.id)
    if trail is not None:
        trail_def = scene_events.content().trails.get(trail.kind)
        if trail_def is None or _aware(trail.expires_at) <= _now():
            await db.delete(trail)
            await db.flush()
            if trail_def is not None:
                lines.append(f"{trail_def.emoji} {trail_def.cold_text}")
        elif (trail.x, trail.y) == (character.pos_x, character.pos_y):
            lines.append(f"{trail_def.emoji} {trail_def.title}: след обрывается здесь - исследуй.")
        else:
            left = max(1, round((_aware(trail.expires_at) - _now()).total_seconds() / 60))
            direction = story_service.compass_direction(character.pos_x, character.pos_y, trail.x, trail.y)
            lines.append(
                f"{trail_def.emoji} {trail_def.title} → ({trail.x}; {trail.y}) · {direction} · ещё {left} мин."
            )
    effects = scene_events.content().effects
    for effect_id, left in await active_effects(db, character.id):
        effect = effects[effect_id]
        lines.append(f"{effect.emoji} {effect.name}: ещё {left} {_fights_word(left)}")
    return lines
