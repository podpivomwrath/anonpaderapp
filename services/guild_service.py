"""Гильдии: основание, состав и звания, казна, склад, слава и уровни, бонусы
древа на участниках.

Территория и постройки - guild_territory_service, задания -
guild_quest_service, осады - guild_siege_service, сезоны -
guild_season_service, древо - guild_tree_service, босс - guild_boss_service.

Сервис не шлёт сообщений: возвращает, кому что случилось, а писать решает
хендлер (тот же порядок, что у венцов и мировых боссов).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import guild_config as gc
from game.guild import tree as guild_tree
from models import (
    Character,
    CharacterOre,
    Guild,
    GuildBuilding,
    GuildCell,
    GuildInvite,
    GuildItem,
    GuildLog,
    GuildMember,
    GuildOre,
    Inventory,
    Item,
)
from services import onboarding_service, wallet_service

_TZ = ZoneInfo("Europe/Moscow")
NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 \-']*[A-Za-zА-Яа-яЁё0-9]$")
TAG_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9]+$")


class GuildError(Exception):
    """Отказ с готовым текстом для игрока."""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(moment: datetime | None) -> datetime | None:
    """SQLite в тестах отдаёт время без зоны - считаем его UTC."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=timezone.utc)


def today_msk(now: datetime | None = None) -> date:
    return (now or now_utc()).astimezone(_TZ).date()


def week_start_msk(now: datetime | None = None) -> date:
    today = today_msk(now)
    return today - timedelta(days=today.weekday())


# --- Чтение -------------------------------------------------------------------


async def membership(db: AsyncSession, character_id: int) -> GuildMember | None:
    return await db.scalar(select(GuildMember).where(GuildMember.character_id == character_id))


async def guild_of(db: AsyncSession, character: Character) -> Guild | None:
    if character.guild_id is None:
        return None
    return await db.get(Guild, character.guild_id)


async def members(db: AsyncSession, guild_id: int) -> list[tuple[GuildMember, Character]]:
    rows = (
        await db.execute(
            select(GuildMember, Character)
            .join(Character, Character.id == GuildMember.character_id)
            .where(GuildMember.guild_id == guild_id)
            .order_by(GuildMember.joined_at, GuildMember.id)
        )
    ).all()
    return [(m, c) for m, c in rows]


async def member_count(db: AsyncSession, guild_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(GuildMember).where(GuildMember.guild_id == guild_id)
    ) or 0


async def member_ids(db: AsyncSession, guild_id: int) -> list[int]:
    return list(
        (await db.scalars(select(GuildMember.character_id).where(GuildMember.guild_id == guild_id))).all()
    )


async def peers_of(db: AsyncSession, guild_id: int, min_rank: str | None = None) -> list[int]:
    """vk id участников (для рассылок). min_rank - не ниже этого звания."""
    result = []
    for member, _character in await members(db, guild_id):
        if min_rank is not None and gc.RANK_ORDER[member.rank] < gc.RANK_ORDER[min_rank]:
            continue
        peer = await onboarding_service.vk_id_for_character(db, member.character_id)
        if peer is not None:
            result.append(peer)
    return result


async def log(
    db: AsyncSession, guild_id: int, kind: str, text: str, character_id: int | None = None,
) -> None:
    db.add(GuildLog(guild_id=guild_id, kind=kind, text=text[:300], character_id=character_id))


async def recent_log(db: AsyncSession, guild_id: int, limit: int = 40) -> list[GuildLog]:
    return list(
        (
            await db.scalars(
                select(GuildLog).where(GuildLog.guild_id == guild_id)
                .order_by(GuildLog.created_at.desc(), GuildLog.id.desc()).limit(limit)
            )
        ).all()
    )


def rank_at_least(member: GuildMember | None, rank: str) -> bool:
    return member is not None and gc.RANK_ORDER[member.rank] >= gc.RANK_ORDER[rank]


def can_manage_treasury(member: GuildMember | None) -> bool:
    """Казна, траты, стройка, древо, знамёна, осады - глава и казначеи."""
    return rank_at_least(member, gc.RANK_TREASURER)


async def _require_member(db: AsyncSession, character: Character) -> tuple[Guild, GuildMember]:
    member = await membership(db, character.id)
    if member is None:
        raise GuildError("Ты не состоишь в гильдии.")
    guild = await db.get(Guild, member.guild_id)
    return guild, member


async def require_treasurer(db: AsyncSession, character: Character) -> tuple[Guild, GuildMember]:
    guild, member = await _require_member(db, character)
    if not can_manage_treasury(member):
        raise GuildError("Это могут только глава и казначеи.")
    return guild, member


async def require_member(db: AsyncSession, character: Character) -> tuple[Guild, GuildMember]:
    return await _require_member(db, character)


# --- Бонусы на участниках -----------------------------------------------------


async def building_levels(db: AsyncSession, guild_id: int) -> dict[str, int]:
    """Лучший готовый уровень каждой постройки по всем базам гильдии
    (склад - сумма по базам)."""
    rows = (
        await db.execute(
            select(GuildBuilding.building, GuildBuilding.level)
            .join(GuildCell, GuildCell.id == GuildBuilding.cell_id)
            .where(GuildCell.guild_id == guild_id, GuildCell.status == "held")
        )
    ).all()
    result: dict[str, int] = {}
    for building, level in rows:
        if building == gc.B_WAREHOUSE:
            result[building] = result.get(building, 0) + level
        else:
            result[building] = max(result.get(building, 0), level)
    return result


async def guild_effects(db: AsyncSession, guild: Guild) -> dict[str, float]:
    """Эффекты древа + гильдейские эффекты построек, которые читаются там,
    где базы нет (кузня - в мастерской, часовня - при смерти)."""
    effects = guild_tree.total_effects(set(guild.tree_nodes or []))
    levels = await building_levels(db, guild.id)
    effects["_forge_cut"] = round(levels.get(gc.B_FORGE, 0) * gc.FORGE_ORE_CUT_PER_LEVEL, 4)
    effects["_chapel"] = levels.get(gc.B_CHAPEL, 0)
    # Ставка налога - тоже копией на персонаже: тексты о золоте показывают
    # «сколько на руки» там, где до базы не дотянуться.
    effects["_tax"] = guild.gold_tax or 0
    return effects


async def refresh_perks(db: AsyncSession, guild: Guild) -> None:
    effects = await guild_effects(db, guild)
    for _member, character in await members(db, guild.id):
        character.guild_perks = dict(effects)


def after_tax(character, amount: int) -> int:
    """Сколько золота дойдёт до игрока после налога гильдии. Округление то
    же, что в wallet_service._guild_tax."""
    tax = int(perk(character, "_tax"))
    return amount - amount * tax // 100 if amount > 0 else amount


def gold_label(character, amount: int, word: str = "золота") -> str:
    """«500 золота» или «500 золота (после налога 450)»."""
    net = after_tax(character, amount)
    if net == amount:
        return f"{amount} {word}"
    return f"{amount} {word} (после налога {net})"


def perk(character, key: str) -> float:
    """Эффект гильдии у персонажа. getattr - движок и часть сервисов зовут
    это с облегчёнными объектами «как персонаж», у которых поля нет."""
    if getattr(character, "guild_id", None) is None:
        return 0.0
    return float((getattr(character, "guild_perks", None) or {}).get(key, 0.0))


# --- Основание и состав -------------------------------------------------------


def _validate_name(name: str, tag: str) -> None:
    if not (gc.NAME_MIN_LEN <= len(name) <= gc.NAME_MAX_LEN) or not NAME_RE.match(name):
        raise GuildError(
            f"Название - от {gc.NAME_MIN_LEN} до {gc.NAME_MAX_LEN} знаков: буквы, цифры, пробел, дефис."
        )
    if not (gc.TAG_MIN_LEN <= len(tag) <= gc.TAG_MAX_LEN) or not TAG_RE.match(tag):
        raise GuildError(f"Тег - от {gc.TAG_MIN_LEN} до {gc.TAG_MAX_LEN} букв или цифр.")
    if onboarding_service.contains_banned_word(name) or onboarding_service.contains_banned_word(tag):
        raise GuildError("Такое название не пройдёт.")


def rejoin_wait_hours(character: Character, now: datetime | None = None) -> float:
    left_at = aware(character.guild_left_at)
    if left_at is None:
        return 0.0
    ready = left_at + timedelta(hours=gc.REJOIN_COOLDOWN_HOURS)
    remaining = (ready - (now or now_utc())).total_seconds() / 3600
    return max(0.0, remaining)


def _check_free(character: Character) -> None:
    if character.guild_id is not None:
        raise GuildError("Ты уже в гильдии.")
    if character.level < gc.JOIN_MIN_LEVEL:
        raise GuildError(f"В гильдии вступают с {gc.JOIN_MIN_LEVEL} уровня.")
    wait = rejoin_wait_hours(character)
    if wait > 0:
        raise GuildError(f"После ухода из гильдии вступить можно через {max(1, round(wait))} ч.")


async def create(db: AsyncSession, character: Character, name: str, tag: str) -> Guild:
    name, tag = " ".join(name.split()), tag.strip().upper()
    if character.level < gc.FOUND_MIN_LEVEL:
        raise GuildError(f"Основать гильдию можно с {gc.FOUND_MIN_LEVEL} уровня.")
    _check_free(character)
    _validate_name(name, tag)
    # Сравнение в питоне, а не lower() в SQL: SQLite (тесты) не опускает
    # регистр кириллицы, и «Орден»/«орден» прошли бы как разные. Гильдий -
    # десятки, выборка копеечная.
    existing = (await db.execute(select(Guild.name, Guild.tag))).all()
    if any(n.lower() == name.lower() for n, _t in existing):
        raise GuildError("Гильдия с таким названием уже есть.")
    if any(t.lower() == tag.lower() for _n, t in existing):
        raise GuildError("Такой тег уже занят.")
    try:
        await wallet_service.charge(db, character.id, "donate", gc.FOUND_COST_GEMS)
    except wallet_service.NotEnoughCurrency:
        raise GuildError(f"Нужно 💎 {gc.FOUND_COST_GEMS} самоцветов.") from None
    guild = Guild(name=name, tag=tag, siege_hour=gc.DEFAULT_SIEGE_HOUR, tree_nodes=[])
    db.add(guild)
    await db.flush()
    db.add(GuildMember(guild_id=guild.id, character_id=character.id, rank=gc.RANK_LEADER))
    character.guild_id = guild.id
    await db.execute(delete(GuildInvite).where(GuildInvite.character_id == character.id))
    await log(db, guild.id, "found", f"{character.name} основывает гильдию «{name}».", character.id)
    await db.flush()
    await refresh_perks(db, guild)
    return guild


async def _join(db: AsyncSession, guild: Guild, character: Character) -> None:
    _check_free(character)
    if await member_count(db, guild.id) >= gc.member_cap(guild.level):
        raise GuildError("В гильдии нет мест.")
    db.add(GuildMember(guild_id=guild.id, character_id=character.id, rank=gc.RANK_RECRUIT))
    character.guild_id = guild.id
    character.guild_perks = await guild_effects(db, guild)
    await db.execute(delete(GuildInvite).where(GuildInvite.character_id == character.id))
    await log(db, guild.id, "join", f"{character.name} вступает в гильдию.", character.id)
    await db.flush()


async def _find_character(db: AsyncSession, name: str) -> Character | None:
    name = name.strip()
    exact = await db.scalar(select(Character).where(Character.name == name))
    if exact is not None:
        return exact
    return await db.scalar(select(Character).where(func.lower(Character.name) == name.lower()))


async def invite(db: AsyncSession, actor: Character, target_name: str) -> Character:
    guild, member = await _require_member(db, actor)
    if not rank_at_least(member, gc.RANK_VETERAN):
        raise GuildError("Звать в гильдию могут ветераны и выше.")
    target = await _find_character(db, target_name)
    if target is None or target.creation_state is not None:
        raise GuildError("Такого персонажа нет.")
    if target.guild_id is not None:
        raise GuildError("Он уже в гильдии.")
    if target.level < gc.JOIN_MIN_LEVEL:
        raise GuildError(f"В гильдии вступают с {gc.JOIN_MIN_LEVEL} уровня.")
    if await member_count(db, guild.id) >= gc.member_cap(guild.level):
        raise GuildError("В гильдии нет мест.")
    await _upsert_invite(db, guild.id, target.id, "invite", actor.id)
    return target


async def _upsert_invite(
    db: AsyncSession, guild_id: int, character_id: int, kind: str, from_id: int | None,
) -> None:
    existing = await db.scalar(
        select(GuildInvite).where(
            GuildInvite.guild_id == guild_id, GuildInvite.character_id == character_id,
            GuildInvite.kind == kind,
        )
    )
    expires = now_utc() + timedelta(hours=gc.INVITE_TTL_HOURS)
    if existing is not None:
        existing.expires_at = expires
        existing.from_character_id = from_id
    else:
        db.add(GuildInvite(
            guild_id=guild_id, character_id=character_id, kind=kind,
            from_character_id=from_id, expires_at=expires,
        ))
    await db.flush()


async def apply(db: AsyncSession, character: Character, guild_id: int) -> Guild:
    _check_free(character)
    guild = await db.get(Guild, guild_id)
    if guild is None:
        raise GuildError("Такой гильдии нет.")
    await _upsert_invite(db, guild.id, character.id, "apply", character.id)
    return guild


async def _live_invite(db: AsyncSession, guild_id: int, character_id: int, kind: str) -> GuildInvite | None:
    row = await db.scalar(
        select(GuildInvite).where(
            GuildInvite.guild_id == guild_id, GuildInvite.character_id == character_id,
            GuildInvite.kind == kind,
        )
    )
    if row is None:
        return None
    if aware(row.expires_at) < now_utc():
        await db.delete(row)
        return None
    return row


async def invites_for(db: AsyncSession, character_id: int) -> list[tuple[GuildInvite, Guild]]:
    rows = (
        await db.execute(
            select(GuildInvite, Guild).join(Guild, Guild.id == GuildInvite.guild_id)
            .where(GuildInvite.character_id == character_id)
        )
    ).all()
    now = now_utc()
    return [(i, g) for i, g in rows if aware(i.expires_at) >= now]


async def applications_of(db: AsyncSession, guild_id: int) -> list[tuple[GuildInvite, Character]]:
    rows = (
        await db.execute(
            select(GuildInvite, Character).join(Character, Character.id == GuildInvite.character_id)
            .where(GuildInvite.guild_id == guild_id, GuildInvite.kind == "apply")
        )
    ).all()
    now = now_utc()
    return [(i, c) for i, c in rows if aware(i.expires_at) >= now]


async def accept_invite(db: AsyncSession, character: Character, guild_id: int) -> Guild:
    row = await _live_invite(db, guild_id, character.id, "invite")
    if row is None:
        raise GuildError("Приглашение уже недействительно.")
    guild = await db.get(Guild, guild_id)
    await _join(db, guild, character)
    return guild


async def decline_invite(db: AsyncSession, character: Character, guild_id: int) -> None:
    await db.execute(delete(GuildInvite).where(
        GuildInvite.guild_id == guild_id, GuildInvite.character_id == character.id,
    ))


async def accept_application(db: AsyncSession, actor: Character, character_id: int) -> Character:
    guild, member = await _require_member(db, actor)
    if not rank_at_least(member, gc.RANK_OFFICER):
        raise GuildError("Заявки принимают офицеры и выше.")
    row = await _live_invite(db, guild.id, character_id, "apply")
    if row is None:
        raise GuildError("Заявка уже недействительна.")
    target = await db.get(Character, character_id)
    await _join(db, guild, target)
    return target


async def decline_application(db: AsyncSession, actor: Character, character_id: int) -> None:
    guild, member = await _require_member(db, actor)
    if not rank_at_least(member, gc.RANK_OFFICER):
        raise GuildError("Заявки разбирают офицеры и выше.")
    await db.execute(delete(GuildInvite).where(
        GuildInvite.guild_id == guild.id, GuildInvite.character_id == character_id,
        GuildInvite.kind == "apply",
    ))


async def _remove_member(db: AsyncSession, member: GuildMember, character: Character) -> None:
    await db.delete(member)
    character.guild_id = None
    character.guild_perks = {}
    character.guild_left_at = now_utc()
    character.prayer_stat = None
    character.prayer_until = None
    await db.flush()


async def leave(db: AsyncSession, character: Character) -> Guild | None:
    """None - гильдия распущена (уходил последний)."""
    guild, member = await _require_member(db, character)
    if member.rank == gc.RANK_LEADER:
        if await member_count(db, guild.id) > 1:
            raise GuildError("Глава не может просто уйти: сначала передай главенство.")
        await disband(db, character)
        return None
    await _remove_member(db, member, character)
    await log(db, guild.id, "leave", f"{character.name} покидает гильдию.", character.id)
    return guild


def _can_kick(actor: GuildMember, target: GuildMember) -> bool:
    if actor.character_id == target.character_id:
        return False
    if actor.rank == gc.RANK_LEADER:
        return True
    if actor.rank == gc.RANK_TREASURER:
        return target.rank not in (gc.RANK_LEADER, gc.RANK_TREASURER)
    if actor.rank == gc.RANK_OFFICER:
        return target.rank in (gc.RANK_VETERAN, gc.RANK_RECRUIT)
    return False


async def kick(db: AsyncSession, actor: Character, character_id: int) -> Character:
    guild, member = await _require_member(db, actor)
    target_member = await membership(db, character_id)
    if target_member is None or target_member.guild_id != guild.id:
        raise GuildError("Он не в твоей гильдии.")
    if not _can_kick(member, target_member):
        raise GuildError("Исключить его ты не можешь.")
    target = await db.get(Character, character_id)
    await _remove_member(db, target_member, target)
    await log(db, guild.id, "kick", f"{actor.name} исключает {target.name}.", actor.id)
    return target


def _can_set_rank(actor: GuildMember, target: GuildMember, rank: str) -> bool:
    if actor.character_id == target.character_id or rank == gc.RANK_LEADER:
        return False
    if actor.rank == gc.RANK_LEADER:
        return True
    if actor.rank == gc.RANK_TREASURER:
        # Казначей не трогает главу и других казначеев и не делает казначеев.
        return target.rank not in (gc.RANK_LEADER, gc.RANK_TREASURER) and rank != gc.RANK_TREASURER
    if actor.rank == gc.RANK_OFFICER:
        return target.rank in (gc.RANK_VETERAN, gc.RANK_RECRUIT) and rank in (
            gc.RANK_VETERAN, gc.RANK_RECRUIT,
        )
    return False


async def set_rank(db: AsyncSession, actor: Character, character_id: int, rank: str) -> Character:
    if rank not in gc.RANK_ORDER:
        raise GuildError("Нет такого звания.")
    guild, member = await _require_member(db, actor)
    target_member = await membership(db, character_id)
    if target_member is None or target_member.guild_id != guild.id:
        raise GuildError("Он не в твоей гильдии.")
    if not _can_set_rank(member, target_member, rank):
        raise GuildError("Такое звание ты дать не можешь.")
    target_member.rank = rank
    target = await db.get(Character, character_id)
    await log(db, guild.id, "rank", f"{target.name} теперь {gc.RANK_TITLES[rank].lower()}.", actor.id)
    return target


async def transfer_leadership(db: AsyncSession, actor: Character, character_id: int) -> Character:
    guild, member = await _require_member(db, actor)
    if member.rank != gc.RANK_LEADER:
        raise GuildError("Передать главенство может только глава.")
    target_member = await membership(db, character_id)
    if target_member is None or target_member.guild_id != guild.id or target_member.id == member.id:
        raise GuildError("Он не в твоей гильдии.")
    target_member.rank = gc.RANK_LEADER
    member.rank = gc.RANK_TREASURER
    target = await db.get(Character, character_id)
    await log(db, guild.id, "rank", f"{actor.name} передаёт главенство: глава теперь {target.name}.", actor.id)
    return target


async def disband(db: AsyncSession, actor: Character) -> list[int]:
    """Распустить гильдию. Казна и склад отходят главе - иначе они бы
    просто исчезли. Возвращает id бывших участников."""
    guild, member = await _require_member(db, actor)
    if member.rank != gc.RANK_LEADER:
        raise GuildError("Распустить гильдию может только глава.")
    if guild.treasury_gold:
        await wallet_service.deposit(db, actor.id, "farm", guild.treasury_gold, taxable=False)
    if guild.treasury_gems:
        await wallet_service.deposit(db, actor.id, "donate", guild.treasury_gems)
    for ore in (await db.scalars(select(GuildOre).where(GuildOre.guild_id == guild.id))).all():
        if ore.count > 0:
            await _add_character_ore(db, actor.id, ore.ore_id, ore.grade, ore.count)
    for stored in (await db.scalars(select(GuildItem).where(GuildItem.guild_id == guild.id))).all():
        db.add(Inventory(character_id=actor.id, item_id=stored.item_id, equipped=False))
        await db.delete(stored)
    former = []
    for m, character in await members(db, guild.id):
        former.append(character.id)
        await _remove_member(db, m, character)
    await db.flush()
    await db.delete(guild)
    await db.flush()
    return former


# --- Казна --------------------------------------------------------------------

CURRENCY_FIELDS = {"gold": ("farm", Guild.treasury_gold), "gems": ("donate", Guild.treasury_gems)}


async def treasury_add(db: AsyncSession, guild_id: int, gold: int = 0, gems: int = 0) -> None:
    await db.execute(
        update(Guild).where(Guild.id == guild_id).values(
            treasury_gold=Guild.treasury_gold + gold, treasury_gems=Guild.treasury_gems + gems,
        ).execution_options(synchronize_session="fetch")
    )


async def treasury_spend(db: AsyncSession, guild_id: int, gold: int = 0, gems: int = 0) -> None:
    """Списание одним UPDATE с условием - как у кошельков (wallet_service)."""
    result = await db.execute(
        update(Guild).where(
            Guild.id == guild_id, Guild.treasury_gold >= gold, Guild.treasury_gems >= gems,
        ).values(
            treasury_gold=Guild.treasury_gold - gold, treasury_gems=Guild.treasury_gems - gems,
        ).execution_options(synchronize_session="fetch")
    )
    if result.rowcount == 0:
        need = []
        if gold:
            need.append(f"{gold:,} золота".replace(",", " "))
        if gems:
            need.append(f"💎 {gems}")
        raise GuildError(f"В казне не хватает: нужно {' и '.join(need)}.")


async def deposit(db: AsyncSession, character: Character, currency: str, amount: int) -> None:
    guild, _member = await _require_member(db, character)
    if currency not in CURRENCY_FIELDS or amount <= 0:
        raise GuildError("Неверная сумма.")
    minimum = gc.DEPOSIT_MIN_GOLD if currency == "gold" else gc.DEPOSIT_MIN_GEMS
    if amount < minimum:
        what = "золота" if currency == "gold" else "самоцветов"
        raise GuildError(f"Вносить можно от {minimum} {what}.")
    wallet_currency, _ = CURRENCY_FIELDS[currency]
    try:
        await wallet_service.charge(db, character.id, wallet_currency, amount)
    except wallet_service.NotEnoughCurrency:
        raise GuildError("Столько у тебя нет.") from None
    if currency == "gold":
        await treasury_add(db, guild.id, gold=amount)
    else:
        await treasury_add(db, guild.id, gems=amount)
    what = f"{amount} золота" if currency == "gold" else f"💎 {amount}"
    await log(db, guild.id, "deposit", f"{character.name} вносит в казну {what}.", character.id)


async def withdraw(
    db: AsyncSession, actor: Character, currency: str, amount: int, to_character_id: int | None = None,
) -> Character:
    guild, _member = await require_treasurer(db, actor)
    if currency not in CURRENCY_FIELDS or amount <= 0:
        raise GuildError("Неверная сумма.")
    receiver = actor
    if to_character_id is not None and to_character_id != actor.id:
        target_member = await membership(db, to_character_id)
        if target_member is None or target_member.guild_id != guild.id:
            raise GuildError("Выдавать из казны можно только своим.")
        receiver = await db.get(Character, to_character_id)
    if currency == "gold":
        await treasury_spend(db, guild.id, gold=amount)
    else:
        await treasury_spend(db, guild.id, gems=amount)
    await wallet_service.deposit(db, receiver.id, CURRENCY_FIELDS[currency][0], amount, taxable=False)
    what = f"{amount} золота" if currency == "gold" else f"💎 {amount}"
    await log(db, guild.id, "withdraw", f"{actor.name} выдаёт из казны {what}: {receiver.name}.", actor.id)
    return receiver


async def set_tax(db: AsyncSession, actor: Character, percent: int) -> None:
    guild, _member = await require_treasurer(db, actor)
    if not 0 <= percent <= gc.TAX_MAX:
        raise GuildError(f"Налог - от 0 до {gc.TAX_MAX}%.")
    guild.gold_tax = percent
    await log(db, guild.id, "tax", f"{actor.name} назначает налог гильдии: {percent}%.", actor.id)
    await db.flush()
    await refresh_perks(db, guild)


# --- Склад --------------------------------------------------------------------


@dataclass
class WarehouseCapacity:
    ore: int
    items: int


async def capacity(db: AsyncSession, guild: Guild) -> WarehouseCapacity:
    levels = await building_levels(db, guild.id)
    effects = guild_tree.total_effects(set(guild.tree_nodes or []))
    mult = 1 + effects.get("warehouse_pct", 0) / 100
    wh = levels.get(gc.B_WAREHOUSE, 0)
    return WarehouseCapacity(
        ore=round((gc.WAREHOUSE_BASE_ORE + gc.WAREHOUSE_ORE_PER_LEVEL * wh) * mult),
        items=round((gc.WAREHOUSE_BASE_ITEMS + gc.WAREHOUSE_ITEMS_PER_LEVEL * wh) * mult),
    )


async def ore_stock(db: AsyncSession, guild_id: int) -> list[GuildOre]:
    return list(
        (await db.scalars(select(GuildOre).where(GuildOre.guild_id == guild_id, GuildOre.count > 0))).all()
    )


async def ore_total(db: AsyncSession, guild_id: int) -> int:
    return int(await db.scalar(
        select(func.coalesce(func.sum(GuildOre.count), 0)).where(GuildOre.guild_id == guild_id)
    ) or 0)


async def item_count(db: AsyncSession, guild_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(GuildItem).where(GuildItem.guild_id == guild_id)
    ) or 0


async def stored_items(db: AsyncSession, guild_id: int) -> list[Item]:
    return list(
        (
            await db.scalars(
                select(Item).join(GuildItem, GuildItem.item_id == Item.id).where(GuildItem.guild_id == guild_id)
            )
        ).all()
    )


async def _add_character_ore(db: AsyncSession, character_id: int, ore_id: str, grade: str, count: int) -> None:
    row = await db.scalar(
        select(CharacterOre).where(
            CharacterOre.character_id == character_id, CharacterOre.ore_id == ore_id,
            CharacterOre.grade == grade,
        )
    )
    if row is None:
        db.add(CharacterOre(character_id=character_id, ore_id=ore_id, grade=grade, count=count))
    else:
        row.count += count
    await db.flush()


async def add_guild_ore(
    db: AsyncSession, guild_id: int, ore_id: str, grade: str, count: int,
) -> None:
    row = await db.scalar(
        select(GuildOre).where(
            GuildOre.guild_id == guild_id, GuildOre.ore_id == ore_id, GuildOre.grade == grade,
        ).with_for_update()
    )
    if row is None:
        db.add(GuildOre(guild_id=guild_id, ore_id=ore_id, grade=grade, count=count))
    else:
        row.count += count
    await db.flush()


async def spend_guild_ore(db: AsyncSession, guild_id: int, ore_id: str, count: int) -> None:
    """Списать руду вида ore_id любой градации - с худших градаций."""
    from game.economy import mining_config as mc

    if count <= 0:
        return
    grades = [g[1] for g in mc.GRADES]
    rows = (
        await db.scalars(
            select(GuildOre).where(GuildOre.guild_id == guild_id, GuildOre.ore_id == ore_id)
            .with_for_update()
        )
    ).all()
    rows = sorted(rows, key=lambda r: grades.index(r.grade) if r.grade in grades else 99)
    if sum(r.count for r in rows) < count:
        from game.economy import mining

        ore = mining.ore_def(ore_id)
        raise GuildError(f"На складе не хватает руды: нужно {count} × {ore.name if ore else ore_id}.")
    left = count
    for row in rows:
        take = min(row.count, left)
        row.count -= take
        left -= take
        if left == 0:
            break
    await db.flush()


async def deposit_ore(
    db: AsyncSession, character: Character, ore_id: str, grade: str, count: int,
) -> None:
    guild, _member = await _require_member(db, character)
    if count <= 0:
        raise GuildError("Неверное количество.")
    cap = await capacity(db, guild)
    if await ore_total(db, guild.id) + count > cap.ore:
        raise GuildError(f"Склад полон: руды помещается {cap.ore}.")
    row = await db.scalar(
        select(CharacterOre).where(
            CharacterOre.character_id == character.id, CharacterOre.ore_id == ore_id,
            CharacterOre.grade == grade,
        ).with_for_update()
    )
    if row is None or row.count < count:
        raise GuildError("Столько руды у тебя нет.")
    row.count -= count
    await add_guild_ore(db, guild.id, ore_id, grade, count)
    from game.economy import mining

    ore = mining.ore_def(ore_id)
    await log(db, guild.id, "ore", f"{character.name} сдаёт на склад: {ore.name if ore else ore_id} ×{count}.", character.id)


async def withdraw_ore(
    db: AsyncSession, actor: Character, ore_id: str, grade: str, count: int,
    to_character_id: int | None = None,
) -> Character:
    guild, _member = await require_treasurer(db, actor)
    receiver = actor
    if to_character_id is not None and to_character_id != actor.id:
        target_member = await membership(db, to_character_id)
        if target_member is None or target_member.guild_id != guild.id:
            raise GuildError("Выдавать со склада можно только своим.")
        receiver = await db.get(Character, to_character_id)
    row = await db.scalar(
        select(GuildOre).where(
            GuildOre.guild_id == guild.id, GuildOre.ore_id == ore_id, GuildOre.grade == grade,
        ).with_for_update()
    )
    if count <= 0 or row is None or row.count < count:
        raise GuildError("Столько руды на складе нет.")
    row.count -= count
    await _add_character_ore(db, receiver.id, ore_id, grade, count)
    from game.economy import mining

    ore = mining.ore_def(ore_id)
    await log(db, guild.id, "ore", f"{actor.name} выдаёт со склада {ore.name if ore else ore_id} ×{count}: {receiver.name}.", actor.id)
    return receiver


async def deposit_item(db: AsyncSession, character: Character, item_id: int) -> Item:
    guild, _member = await _require_member(db, character)
    entry = await db.scalar(
        select(Inventory).where(Inventory.character_id == character.id, Inventory.item_id == item_id)
    )
    item = await db.get(Item, item_id)
    if entry is None or item is None:
        raise GuildError("Такой вещи у тебя нет.")
    if entry.equipped:
        raise GuildError("Сначала сними вещь.")
    if item.bound or item.admin_only:
        raise GuildError("Эта вещь привязана к тебе.")
    cap = await capacity(db, guild)
    if await item_count(db, guild.id) >= cap.items:
        raise GuildError(f"Склад полон: вещей помещается {cap.items}.")
    await db.delete(entry)
    db.add(GuildItem(item_id=item.id, guild_id=guild.id, deposited_by=character.id))
    await log(db, guild.id, "item", f"{character.name} сдаёт на склад: {item.name}.", character.id)
    await db.flush()
    return item


async def withdraw_item(
    db: AsyncSession, actor: Character, item_id: int, to_character_id: int | None = None,
) -> Character:
    guild, _member = await require_treasurer(db, actor)
    receiver = actor
    if to_character_id is not None and to_character_id != actor.id:
        target_member = await membership(db, to_character_id)
        if target_member is None or target_member.guild_id != guild.id:
            raise GuildError("Выдавать со склада можно только своим.")
        receiver = await db.get(Character, to_character_id)
    stored = await db.scalar(
        select(GuildItem).where(GuildItem.guild_id == guild.id, GuildItem.item_id == item_id)
    )
    if stored is None:
        raise GuildError("Такой вещи на складе нет.")
    item = await db.get(Item, item_id)
    await db.delete(stored)
    db.add(Inventory(character_id=receiver.id, item_id=item_id, equipped=False))
    await log(db, guild.id, "item", f"{actor.name} выдаёт со склада {item.name}: {receiver.name}.", actor.id)
    await db.flush()
    return receiver


# --- Слава и уровни -----------------------------------------------------------


@dataclass
class FameResult:
    gained: int
    levels_gained: int
    new_level: int


async def add_fame(db: AsyncSession, guild_id: int, amount: int) -> FameResult:
    guild = await db.scalar(
        select(Guild).where(Guild.id == guild_id).with_for_update().execution_options(populate_existing=True)
    )
    if guild is None or amount <= 0:
        return FameResult(0, 0, guild.level if guild else 0)
    effects = guild_tree.total_effects(set(guild.tree_nodes or []))
    gained = round(amount * (1 + effects.get("fame_pct", 0) / 100))
    guild.fame += gained
    guild.fame_total += gained
    guild.fame_month += gained
    levels = 0
    while guild.fame >= gc.fame_to_next(guild.level):
        guild.fame -= gc.fame_to_next(guild.level)
        guild.level += 1
        levels += 1
    if levels:
        await log(db, guild.id, "level", f"Гильдия достигает {guild.level} уровня!")
    await db.flush()
    return FameResult(gained, levels, guild.level)


async def add_contribution(db: AsyncSession, character_id: int, amount: int) -> None:
    member = await membership(db, character_id)
    if member is None or amount <= 0:
        return
    week = week_start_msk()
    if member.week_start != week:
        member.week_start = week
        member.contribution_week = 0
    member.contribution_week += amount
    member.contribution_total += amount


def tree_points_available(guild: Guild) -> int:
    spent = sum(
        guild_tree.POINTS[n.kind] for n in (guild_tree.node(i) for i in guild.tree_nodes or []) if n
    )
    return (guild.level - 1) * gc.TREE_POINTS_PER_LEVEL - spent


@dataclass
class DirectoryEntry:
    guild: Guild
    members: int
    #: Сумма убийств мобов всех участников (PvE-активность).
    pve: int
    #: Сумма побед в PvP всех участников.
    pvp: int


async def directory(db: AsyncSession) -> list[DirectoryEntry]:
    """Все гильдии с суммами по участникам - для топа. Сортирует клиент:
    гильдий десятки, а четыре сортировки одного списка незачем гонять
    четырьмя запросами."""
    totals = {
        guild_id: (count, pve, pvp)
        for guild_id, count, pve, pvp in (
            await db.execute(
                select(
                    Character.guild_id, func.count(Character.id),
                    func.coalesce(func.sum(Character.mobs_killed), 0),
                    func.coalesce(func.sum(Character.pvp_wins), 0),
                ).where(Character.guild_id.isnot(None)).group_by(Character.guild_id)
            )
        ).all()
    }
    result = []
    for guild in (await db.scalars(select(Guild))).all():
        count, pve, pvp = totals.get(guild.id, (0, 0, 0))
        result.append(DirectoryEntry(guild, int(count), int(pve), int(pvp)))
    result.sort(key=lambda e: (-e.guild.level, -e.guild.fame_total))
    return result
