"""Мировые боссы (патч 104): состояние мира в БД.

Все изменения здоровья и вкладов идут под блокировкой строки босса
(SELECT ... FOR UPDATE). События ВК обрабатываются параллельно, и два хода
разных игроков, прочитав одно и то же здоровье, иначе оба записали бы своё
- урон одного пропал бы, а босс мог бы «умереть» дважды и раздать пул
дважды. Блокировка выстраивает их в очередь.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import world_boss_config as wbc
from game.world import world_boss
from models import (
    Character,
    CharacterStats,
    Item,
    WorldBoss,
    WorldBossContribution,
    WorldBossMeter,
)
from services import (
    elixir_service,
    experience_service,
    group_service,
    item_service,
    trophy_service,
)

ACTIVE = "active"
KILLED = "killed"
ESCAPED = "escaped"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime | None) -> datetime | None:
    """SQLite в тестах отдаёт время без пояса - сравнение с «сейчас» падало бы."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def is_alive(boss: WorldBoss, now: datetime | None = None) -> bool:
    return boss.status == ACTIVE and boss.hp > 0 and _aware(boss.expires_at) > (now or _now())


async def active_boss(db: AsyncSession, now: datetime | None = None) -> WorldBoss | None:
    """Живой босс, если он есть. Истёкший, но ещё не закрытый задачей
    (expire_due) живым не считается."""
    boss = await db.scalar(
        select(WorldBoss).where(WorldBoss.status == ACTIVE).order_by(WorldBoss.id.desc()).limit(1)
    )
    if boss is None or not is_alive(boss, now):
        return None
    return boss


async def _lock(db: AsyncSession, boss_pk: int) -> WorldBoss | None:
    return await db.get(WorldBoss, boss_pk, with_for_update=True, populate_existing=True)


# --- Появление ------------------------------------------------------------------


async def _players_by_ring(db: AsyncSession, now: datetime) -> dict[int, int]:
    """Сколько игроков за сутки было в игре - по самому внешнему кольцу, куда
    их пускает уровень. Нужно, чтобы босс чаще вставал там, где играют."""
    levels = (
        await db.execute(
            select(Character.level).where(
                Character.creation_state.is_(None),
                Character.last_active_at >= now - timedelta(days=1),
            )
        )
    ).scalars().all()
    counts: dict[int, int] = {}
    for level in levels:
        ring = world_boss.ring_of_level(level)
        if ring is not None:
            counts[ring] = counts.get(ring, 0) + 1
    return counts


async def record_exploration(
    db: AsyncSession, rng: random.Random, now: datetime | None = None,
) -> WorldBoss | None:
    """Завершённое исследование любого игрока наполняет счётчик. Возвращает
    нового босса, если он только что появился (его надо объявить)."""
    now = now or _now()
    meter = await db.get(WorldBossMeter, 1, with_for_update=True)
    if meter is None:
        meter = WorldBossMeter(id=1, explorations=0)
        db.add(meter)
    meter.explorations = (meter.explorations or 0) + 1
    if meter.explorations < wbc.EXPLORATIONS_PER_SPAWN:
        await db.flush()
        return None
    # Счётчик полон, но босса нет - ждём конца живого или конца паузы.
    # Счётчик при этом не сбрасываем: следующее исследование после этого
    # выпустит босса сразу.
    if await active_boss(db, now) is not None:
        await db.flush()
        return None
    last = _aware(meter.last_spawn_at)
    if last is not None and now - last < timedelta(hours=wbc.MIN_SPAWN_GAP_HOURS):
        await db.flush()
        return None

    meter.explorations = 0
    meter.last_spawn_at = now
    boss = await spawn(db, rng, now)
    return boss


async def spawn(db: AsyncSession, rng: random.Random, now: datetime | None = None) -> WorldBoss:
    """Ставит нового босса на карту. Отдельно от счётчика - для админки и тестов."""
    now = now or _now()
    ring = world_boss.pick_ring(rng, await _players_by_ring(db, now))
    x, y = world_boss.pick_cell(ring, rng)
    hp = wbc.BOSS_HP[ring]
    boss = WorldBoss(
        boss_id=rng.choice(sorted(world_boss.boss_defs())),
        ring=ring, level=world_boss.boss_level(ring), x=x, y=y,
        max_hp=hp, hp=hp, status=ACTIVE, spawned_at=now,
        expires_at=now + timedelta(hours=wbc.LIFETIME_HOURS),
    )
    db.add(boss)
    await db.flush()
    return boss


async def announce_recipients(db: AsyncSession, boss: WorldBoss, now: datetime | None = None) -> list[int]:
    """vk_id тех, кому стоит сообщить о боссе: были в игре за сутки и
    допускаются к нему по уровню. Остальным сообщение было бы шумом."""
    from models import User

    now = now or _now()
    rows = await db.execute(
        select(User.vk_id).join(Character, Character.user_id == User.id).where(
            Character.creation_state.is_(None),
            Character.last_active_at >= now - timedelta(days=1),
            Character.level <= world_boss.max_attacker_level(boss.ring),
        )
    )
    return [vk_id for vk_id in rows.scalars().all() if vk_id is not None]


# --- Заход -----------------------------------------------------------------------


@dataclass
class AttemptCheck:
    ok: bool
    #: not_here | gone | level | cooldown - почему нельзя
    reason: str | None = None
    minutes_left: int = 0


async def cooldown_minutes(
    db: AsyncSession, boss: WorldBoss, character_id: int, now: datetime | None = None,
) -> int:
    """Сколько минут до следующего захода. 0 - можно сейчас."""
    now = now or _now()
    row = await _contribution(db, boss.id, character_id)
    if row is None or row.last_attempt_at is None:
        return 0
    ready_at = _aware(row.last_attempt_at) + timedelta(minutes=wbc.ATTEMPT_COOLDOWN_MINUTES)
    if ready_at <= now:
        return 0
    return max(1, -int(-(ready_at - now).total_seconds() // 60))


async def _contribution(db: AsyncSession, boss_pk: int, character_id: int) -> WorldBossContribution | None:
    return await db.scalar(
        select(WorldBossContribution).where(
            WorldBossContribution.world_boss_id == boss_pk,
            WorldBossContribution.character_id == character_id,
        )
    )


async def start_attempt(
    db: AsyncSession, character: Character, boss_pk: int, now: datetime | None = None,
) -> AttemptCheck:
    """Проверяет и засчитывает заход. Заход тратится в момент входа, а не
    выхода: иначе отступление в середине давало бы бесконечные заходы."""
    now = now or _now()
    boss = await _lock(db, boss_pk)
    if boss is None or not is_alive(boss, now):
        return AttemptCheck(False, "gone")
    if (character.pos_x, character.pos_y) != (boss.x, boss.y):
        return AttemptCheck(False, "not_here")
    if not world_boss.can_attack(character.level, boss.ring):
        return AttemptCheck(False, "level")
    minutes = await cooldown_minutes(db, boss, character.id, now)
    if minutes > 0:
        return AttemptCheck(False, "cooldown", minutes)
    row = await _contribution(db, boss.id, character.id)
    if row is None:
        row = WorldBossContribution(
            world_boss_id=boss.id, character_id=character.id, damage=0, attempts=0,
        )
        db.add(row)
    row.attempts = (row.attempts or 0) + 1
    row.last_attempt_at = now
    await db.flush()
    return AttemptCheck(True)


@dataclass
class DamageResult:
    hp: int
    max_hp: int
    #: урон, который реально лёг на босса (не больше остатка его здоровья)
    dealt: int
    #: этот удар добил босса - пул разыгрывать ЭТОМУ вызову
    killed_now: bool
    #: босса больше нет (убит кем-то, ушёл) - заход окончен
    over: bool


async def apply_damage(
    db: AsyncSession, boss_pk: int, character_id: int, damage: int, now: datetime | None = None,
) -> DamageResult:
    now = now or _now()
    boss = await _lock(db, boss_pk)
    if boss is None:
        return DamageResult(0, 1, 0, False, True)
    if not is_alive(boss, now):
        return DamageResult(boss.hp, boss.max_hp, 0, False, True)
    dealt = max(0, min(damage, boss.hp))
    if dealt:
        boss.hp -= dealt
        row = await _contribution(db, boss.id, character_id)
        if row is None:
            row = WorldBossContribution(
                world_boss_id=boss.id, character_id=character_id, damage=0, attempts=0,
            )
            db.add(row)
        row.damage = (row.damage or 0) + dealt
    killed = boss.hp <= 0
    if killed:
        boss.hp = 0
        boss.status = KILLED
        boss.ended_at = now
    await db.flush()
    return DamageResult(boss.hp, boss.max_hp, dealt, killed, killed)


async def damage_by_character(db: AsyncSession, boss_pk: int) -> dict[int, int]:
    rows = (
        await db.execute(
            select(WorldBossContribution).where(WorldBossContribution.world_boss_id == boss_pk)
        )
    ).scalars().all()
    return {row.character_id: row.damage or 0 for row in rows}


# --- Награда -----------------------------------------------------------------------


@dataclass
class Granted:
    """Что реально получил участник - для итогового сообщения."""

    character_id: int
    damage: int
    xp: int = 0
    levels_gained: int = 0
    new_level: int = 0
    items: list[Item] = field(default_factory=list)
    trophies: dict[str, int] = field(default_factory=dict)
    elixirs: dict[str, int] = field(default_factory=dict)
    group_kick: object | None = None


def pool_share(boss: WorldBoss) -> float:
    """Какая часть пула разыгрывается: весь за убийство, доля снятого
    здоровья - если босс ушёл живым. Недобитый босс всё равно платит за
    работу, но меньше."""
    if boss.status == KILLED:
        return 1.0
    return max(0.0, min(1.0, 1 - boss.hp / boss.max_hp)) if boss.max_hp else 0.0


async def distribute(db: AsyncSession, boss: WorldBoss, rng: random.Random) -> list[Granted]:
    """Разыгрывает пул и начисляет его. Зовётся ровно один раз на босса -
    тем, кто перевёл его из active (apply_damage с killed_now или
    expire_due), под той же блокировкой строки."""
    damage = await damage_by_character(db, boss.id)
    xp_pool = experience_service.xp_per_mob(boss.level) * wbc.XP_POOL_MOBS
    shares = world_boss.split_pool(boss.ring, damage, pool_share(boss), xp_pool, rng)
    granted: list[Granted] = []
    for character_id in sorted(shares, key=lambda cid: -damage[cid]):
        share = shares[character_id]
        character = await db.get(Character, character_id)
        if character is None:
            continue
        got = Granted(character_id=character_id, damage=damage[character_id], new_level=character.level)
        if share.xp:
            stats = await db.scalar(
                select(CharacterStats).where(CharacterStats.character_id == character_id)
            )
            levelup = experience_service.add_experience(character, stats, share.xp)
            got.xp = levelup.xp_awarded
            got.levels_gained = levelup.levels_gained
            got.new_level = levelup.new_level
            if levelup.levels_gained > 0:
                got.group_kick = await group_service.enforce_level_gap(db, character)
        for rarity_id in share.items:
            got.items.append(
                await item_service.grant_random_item(db, character, boss.level, rng, rarity_id=rarity_id)
            )
        for trophy_id, amount in share.trophies.items():
            await trophy_service.grant_specific(db, character_id, trophy_id, amount)
        for elixir_id, amount in share.elixirs.items():
            await elixir_service.grant(db, character_id, elixir_id, amount)
        got.trophies = dict(share.trophies)
        got.elixirs = dict(share.elixirs)
        granted.append(got)
    await db.flush()
    return granted


async def expire_due(db: AsyncSession, rng: random.Random, now: datetime | None = None) -> list[tuple[WorldBoss, list[Granted]]]:
    """Закрывает боссов, у которых вышло время: они уходят, пул раздаётся
    по доле снятого здоровья."""
    now = now or _now()
    ids = (
        await db.execute(select(WorldBoss.id).where(WorldBoss.status == ACTIVE))
    ).scalars().all()
    ended: list[tuple[WorldBoss, list[Granted]]] = []
    for boss_pk in ids:
        boss = await _lock(db, boss_pk)
        if boss is None or boss.status != ACTIVE or _aware(boss.expires_at) > now:
            continue
        boss.status = ESCAPED
        boss.ended_at = now
        await db.flush()
        ended.append((boss, await distribute(db, boss, rng)))
    return ended
