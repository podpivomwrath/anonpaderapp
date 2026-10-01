"""Страж цитадели - гильдейский босс.

Призывает глава или казначей в цитадели за золото и руду, не чаще раза в
неделю. Бьют только свои, заходами по BOSS_ATTEMPT_TURNS ходов, не чаще раза
в час - как мирового босса (и тем же боем: bot/handlers/world_boss.py ведёт
оба, страж отличается отрицательным id захода).

Страж - каменный: в ответ не бьёт, держит удар. Награда - слава гильдии,
золото и руда в казну и на склад, личное золото и вклад по урону. Если он
уйдёт недобитым, всё это - по доле снятого здоровья.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat import session as combat_session
from game.combat.session import CombatantState
from game.economy import guild_config as gc
from game.world import encounters, grid
from game.world import world_boss as world_boss_rules
from models import Character, Guild, GuildBoss, GuildBossContribution
from services import guild_service, guild_territory_service, wallet_service
from services.guild_service import GuildError, aware, now_utc

BOSS_NAME = "Страж цитадели"
BOSS_LEVEL = 60


async def active_boss(db: AsyncSession, guild_id: int, now: datetime | None = None) -> GuildBoss | None:
    boss = await db.scalar(
        select(GuildBoss).where(GuildBoss.guild_id == guild_id, GuildBoss.status == "active")
    )
    if boss is None:
        return None
    return boss


def is_alive(boss: GuildBoss, now: datetime | None = None) -> bool:
    return boss.status == "active" and aware(boss.expires_at) > (now or now_utc()) and boss.hp > 0


async def _lock(db: AsyncSession, boss_pk: int) -> GuildBoss | None:
    return await db.scalar(
        select(GuildBoss).where(GuildBoss.id == boss_pk).with_for_update()
        .execution_options(populate_existing=True)
    )


def cooldown_days_left(guild: Guild, now: datetime | None = None) -> float:
    last = aware(guild.last_boss_at)
    if last is None:
        return 0.0
    left = last + timedelta(days=gc.BOSS_COOLDOWN_DAYS) - (now or now_utc())
    return max(0.0, left.total_seconds() / 86400)


async def summon(db: AsyncSession, actor: Character) -> GuildBoss:
    guild, _member = await guild_service.require_treasurer(db, actor)
    cells = await guild_territory_service.cells_of(db, guild.id)
    citadel = next((c for c in cells if c.status == "held" and c.base_tier == gc.BASE_CITADEL), None)
    if citadel is None:
        raise GuildError("Стража призывают только в цитадели.")
    if await active_boss(db, guild.id) is not None:
        raise GuildError("Страж уже призван.")
    wait = cooldown_days_left(guild)
    if wait > 0:
        raise GuildError(f"Страж ещё не набрался сил: {max(1, round(wait * 24))} ч.")
    ore_id, ore_count = gc.BOSS_SUMMON_ORE
    await guild_service.spend_guild_ore(db, guild.id, ore_id, ore_count)
    await guild_service.treasury_spend(db, guild.id, gold=gc.BOSS_SUMMON_GOLD)
    now = now_utc()
    hp = max(gc.BOSS_MIN_HP, gc.BOSS_HP_PER_MEMBER * await guild_service.member_count(db, guild.id))
    boss = GuildBoss(
        guild_id=guild.id, x=citadel.x, y=citadel.y, max_hp=hp, hp=hp, status="active",
        spawned_at=now, expires_at=now + timedelta(hours=gc.BOSS_LIFETIME_HOURS),
    )
    db.add(boss)
    guild.last_boss_at = now
    await guild_service.log(db, guild.id, "boss", f"{actor.name} призывает Стража цитадели.", actor.id)
    await db.flush()
    return boss


async def _contribution(db: AsyncSession, boss_pk: int, character_id: int) -> GuildBossContribution | None:
    return await db.scalar(
        select(GuildBossContribution).where(
            GuildBossContribution.boss_id == boss_pk, GuildBossContribution.character_id == character_id,
        )
    )


async def cooldown_minutes(db: AsyncSession, boss: GuildBoss, character_id: int) -> int:
    row = await _contribution(db, boss.id, character_id)
    if row is None or row.last_attempt_at is None:
        return 0
    ready = aware(row.last_attempt_at) + timedelta(minutes=gc.BOSS_ATTEMPT_COOLDOWN_MINUTES)
    now = now_utc()
    if ready <= now:
        return 0
    return max(1, -int(-(ready - now).total_seconds() // 60))


@dataclass
class AttemptCheck:
    ok: bool
    reason: str | None = None
    minutes_left: int = 0


async def start_attempt(db: AsyncSession, character: Character, boss_pk: int) -> AttemptCheck:
    boss = await _lock(db, boss_pk)
    if boss is None or not is_alive(boss):
        return AttemptCheck(False, "Стража больше нет.")
    if character.guild_id != boss.guild_id:
        return AttemptCheck(False, "Это страж чужой гильдии.")
    if (character.pos_x, character.pos_y) != (boss.x, boss.y):
        return AttemptCheck(False, "Страж стоит в цитадели - иди туда.")
    minutes = await cooldown_minutes(db, boss, character.id)
    if minutes:
        return AttemptCheck(False, f"Следующий заход через {minutes} мин.", minutes)
    row = await _contribution(db, boss.id, character.id)
    if row is None:
        row = GuildBossContribution(boss_id=boss.id, character_id=character.id, damage=0, attempts=0)
        db.add(row)
    row.attempts += 1
    row.last_attempt_at = now_utc()
    await db.flush()
    return AttemptCheck(True)


@dataclass
class DamageResult:
    hp: int
    max_hp: int
    dealt: int
    killed_now: bool
    over: bool
    my_total: int = 0


async def apply_damage(db: AsyncSession, boss_pk: int, character_id: int, damage: int) -> DamageResult:
    boss = await _lock(db, boss_pk)
    if boss is None:
        return DamageResult(0, 1, 0, False, True)
    row = await _contribution(db, boss.id, character_id)
    if not is_alive(boss):
        return DamageResult(boss.hp, boss.max_hp, 0, False, True, row.damage if row else 0)
    dealt = max(0, min(damage, boss.hp))
    if dealt:
        boss.hp -= dealt
        if row is None:
            row = GuildBossContribution(boss_id=boss.id, character_id=character_id, damage=0, attempts=0)
            db.add(row)
        row.damage += dealt
    killed = boss.hp <= 0
    if killed:
        boss.hp = 0
        boss.status = "killed"
        boss.ended_at = now_utc()
    await db.flush()
    return DamageResult(boss.hp, boss.max_hp, dealt, killed, killed, row.damage if row else 0)


@dataclass
class BossGrant:
    character_id: int
    damage: int
    gold: int
    net_gold: int = 0


@dataclass
class BossResult:
    boss: GuildBoss
    share: float
    fame: int
    treasury_gold: int
    ore: int
    granted: list[BossGrant] = field(default_factory=list)


async def distribute(db: AsyncSession, boss: GuildBoss) -> BossResult:
    """Ровно один раз на стража - тем, кто перевёл его из active."""
    share = 1.0 if boss.status == "killed" else max(0.0, min(1.0, 1 - boss.hp / boss.max_hp))
    rows = (
        await db.scalars(select(GuildBossContribution).where(GuildBossContribution.boss_id == boss.id))
    ).all()
    damage = {r.character_id: r.damage for r in rows if r.damage > 0}
    total = sum(damage.values()) or 1
    fame = await guild_service.add_fame(db, boss.guild_id, round(gc.BOSS_FAME * share)) if share > 0 else None
    treasury = round(gc.BOSS_TREASURY_GOLD * share)
    if treasury:
        await guild_service.treasury_add(db, boss.guild_id, gold=treasury)
    ore_id, ore_count = gc.BOSS_ORE_REWARD
    ore = round(ore_count * share)
    if ore:
        await guild_service.add_guild_ore(db, boss.guild_id, ore_id, "rare", ore)
    pool = round(gc.BOSS_PERSONAL_GOLD * len(damage) * share)
    result = BossResult(boss, share, fame.gained if fame else 0, treasury, ore)
    for character_id, dealt in sorted(damage.items(), key=lambda t: -t[1]):
        gold = round(pool * dealt / total)
        if gold:
            await wallet_service.deposit(db, character_id, "farm", gold)
        await guild_service.add_contribution(db, character_id, max(1, round(50 * dealt / total)))
        member = await db.get(Character, character_id)
        result.granted.append(BossGrant(
            character_id, dealt, gold, guild_service.after_tax(member, gold) if member else gold,
        ))
    status = "повержен" if boss.status == "killed" else "уходит недобитым"
    await guild_service.log(
        db, boss.guild_id, "boss",
        f"Страж цитадели {status}: +{result.fame} славы, {treasury} золота в казну, {ore} руды на склад.",
    )
    await db.flush()
    return result


async def expire_due(db: AsyncSession, now: datetime | None = None) -> list[BossResult]:
    now = now or now_utc()
    ids = (await db.scalars(select(GuildBoss.id).where(GuildBoss.status == "active"))).all()
    ended = []
    for boss_pk in ids:
        boss = await _lock(db, boss_pk)
        if boss is None or boss.status != "active" or aware(boss.expires_at) > now:
            continue
        boss.status = "escaped"
        boss.ended_at = now
        await db.flush()
        ended.append(await distribute(db, boss))
    return ended


def build_combatant(participant_id: int, hp: int, max_hp: int) -> CombatantState:
    """Статы - как у моба 60 уровня у Монолита, здоровье - общее."""
    zone = grid.zone_level_range(3)
    hp_mult = bc.MOB_HP_MULTIPLIER * formulas.mob_ring_multiplier(*zone)
    dmg_mult = bc.MOB_DAMAGE_MULTIPLIER * formulas.mob_ring_damage_multiplier(*zone)
    stats = encounters._scale_stats_split(encounters.balanced_mob_stats(BOSS_LEVEL), hp_mult, dmg_mult)
    combatant = combat_session.build_combatant(
        id=participant_id, side=1, kind="mob", name=BOSS_NAME, level=BOSS_LEVEL,
        stats=stats, primary_stat="str",
    )
    combatant.max_hp = max_hp
    combatant.current_hp = hp
    combatant.scripted_hit = world_boss_rules._stands_still
    return combatant
