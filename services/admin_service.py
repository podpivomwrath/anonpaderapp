"""Админка (патч 27): статистика, поиск/карточка игрока, действия админа
(каждое логируется в admin_actions), репорты багов, лог смертей.

Слой намеренно не знает о bot/handlers (сервисы не импортируют bot/*, кроме
единственного текстового исключения в user_service) — часть «Сбросить
активности», завязанная на in-memory состояние хендлеров (боевая сессия,
исследование/отдых по peer_id), доделывается на уровне bot/miniapp_api.py,
который уже стоит рядом с хендлерами. Здесь — только то, что решается в БД.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.classes.base import REGISTRY
from game.combat import balance_config as bc
from game.content_loader import load_admin_weapons
from game.economy import mount_config as mc
from game.world import grid
from game.world import world_config as wc
from models import (
    AdminAction,
    BugReport,
    Character,
    CharacterDeath,
    CharacterMount,
    CharacterStats,
    CharacterStoryProgress,
    CharacterTitle,
    CharacterTrophy,
    CharacterUnlockedBuff,
    Inventory,
    Item,
    PvpBattle,
    User,
    Wallet,
)
from services import (
    daily_service,
    death_service,
    derived_stats_service,
    elixir_service,
    experience_service,
    item_service,
    movement_service,
    mount_service,
    premium_service,
    preset_service,
    song_service,
    story_service,
    title_service,
    trial_service,
    trophy_service,
    vitals_service,
    wallet_service,
)

BASE_CLASS_TITLES = {"warrior": "Воин", "rogue": "Разбойник", "mage": "Маг"}


def class_title(character: Character) -> str:
    if character.subclass is not None:
        subclass = REGISTRY.get(character.subclass)
        if subclass is not None:
            return subclass.title
    return BASE_CLASS_TITLES.get(character.base_class, character.base_class)


async def log_action(
    db: AsyncSession,
    admin_vk_id: int,
    action_type: str,
    target_character_id: int | None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    note: str | None = None,
) -> AdminAction:
    action = AdminAction(
        admin_vk_id=admin_vk_id,
        action_type=action_type,
        target_character_id=target_character_id,
        old_value=old_value,
        new_value=new_value,
        note=note,
    )
    db.add(action)
    await db.flush()
    return action


async def log_death(
    db: AsyncSession, character: Character, cause: str
) -> None:
    """Хук для encounter_service.resolve_defeat (PvE) и bot/handlers/pvp.py
    (оба apply_pvp_death call site) — статистика «смертей за сутки, топ зон»."""
    db.add(
        CharacterDeath(
            character_id=character.id, pos_x=character.pos_x, pos_y=character.pos_y, cause=cause
        )
    )
    await db.flush()


# --- Обзор (2.1) ---


@dataclass
class OverviewStats:
    players: dict = field(default_factory=dict)
    progression: dict = field(default_factory=dict)
    retention: dict = field(default_factory=dict)
    economy: dict = field(default_factory=dict)
    combat: dict = field(default_factory=dict)


async def overview_stats(db: AsyncSession) -> OverviewStats:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)

    finished = Character.creation_state.is_(None)

    total_characters = await db.scalar(select(func.count()).select_from(Character).where(finished))
    stuck_onboarding = await db.scalar(
        select(func.count()).select_from(Character).where(Character.creation_state.is_not(None))
    )
    active_24h = await db.scalar(
        select(func.count()).select_from(Character).where(finished, Character.last_active_at >= day_ago)
    )
    active_7d = await db.scalar(
        select(func.count()).select_from(Character).where(finished, Character.last_active_at >= week_ago)
    )
    active_30d = await db.scalar(
        select(func.count()).select_from(Character).where(finished, Character.last_active_at >= month_ago)
    )
    new_today = await db.scalar(
        select(func.count())
        .select_from(Character)
        .join(User, User.id == Character.user_id)
        .where(finished, User.created_at >= today_start)
    )
    new_week = await db.scalar(
        select(func.count())
        .select_from(Character)
        .join(User, User.id == Character.user_id)
        .where(finished, User.created_at >= week_ago)
    )

    players = {
        "total_characters": total_characters or 0,
        "stuck_onboarding": stuck_onboarding or 0,
        "active_24h": active_24h or 0,
        "active_7d": active_7d or 0,
        "active_30d": active_30d or 0,
        "new_today": new_today or 0,
        "new_week": new_week or 0,
    }

    # Гистограмма уровней по декадам (1-9, 10-19, ...)
    level_rows = (
        await db.execute(select(Character.level).where(finished))
    ).scalars().all()
    buckets: dict[str, int] = {}
    for lvl in level_rows:
        bucket = f"{(lvl // 10) * 10}-{(lvl // 10) * 10 + 9}"
        buckets[bucket] = buckets.get(bucket, 0) + 1
    reached_30 = sum(1 for lvl in level_rows if lvl >= bc.SUBCLASS_UNLOCK_MIN_LEVEL)
    avg_level_active = await db.scalar(
        select(func.avg(Character.level)).where(finished, Character.last_active_at >= week_ago)
    )

    class_rows = (await db.execute(select(Character.base_class, func.count()).where(finished).group_by(Character.base_class))).all()
    subclass_rows = (
        await db.execute(
            select(Character.subclass, func.count())
            .where(finished, Character.subclass.is_not(None))
            .group_by(Character.subclass)
        )
    ).all()
    region_rows = (
        await db.execute(
            select(Character.region, func.count())
            .where(finished, Character.region.is_not(None))
            .group_by(Character.region)
        )
    ).all()

    progression = {
        "level_buckets": dict(sorted(buckets.items(), key=lambda kv: int(kv[0].split("-")[0]))),
        "reached_subclass_level": reached_30,
        "by_class": {c: n for c, n in class_rows},
        "by_subclass": {s: n for s, n in subclass_rows},
        "by_region": {r: n for r, n in region_rows},
        "avg_level_active_7d": round(float(avg_level_active), 1) if avg_level_active else 0.0,
    }

    # Удержание: уровень последней активности у тех, кто не заходил > 7 дней
    dropoff_rows = (
        await db.execute(
            select(Character.level)
            .where(finished, Character.last_active_at.is_not(None), Character.last_active_at < week_ago)
        )
    ).scalars().all()
    dropoff_buckets: dict[str, int] = {}
    for lvl in dropoff_rows:
        bucket = f"{(lvl // 10) * 10}-{(lvl // 10) * 10 + 9}"
        dropoff_buckets[bucket] = dropoff_buckets.get(bucket, 0) + 1
    # Одна сессия и не вернулся: приблизительно — стрик входа так и не поднялся
    # выше 1 (нет выделенного лога сессий, это ближайшая доступная метрика)
    one_session_gone = await db.scalar(
        select(func.count())
        .select_from(Character)
        .where(
            finished,
            Character.login_streak <= 1,
            Character.last_login_date.is_not(None),
            Character.last_active_at.is_not(None),
            Character.last_active_at < week_ago,
        )
    )

    retention = {
        "dropoff_level_buckets": dict(sorted(dropoff_buckets.items(), key=lambda kv: int(kv[0].split("-")[0]))),
        "one_session_gone": one_session_gone or 0,
    }

    total_gold = await db.scalar(select(func.coalesce(func.sum(Wallet.farm_currency), 0)))
    total_gems = await db.scalar(select(func.coalesce(func.sum(Wallet.donate_currency), 0)))
    trophy_rows = (
        await db.execute(select(CharacterTrophy.trophy_id, func.sum(CharacterTrophy.count)).group_by(CharacterTrophy.trophy_id))
    ).all()

    economy = {
        "total_gold": int(total_gold or 0),
        "total_gems": int(total_gems or 0),
        "trophies_in_circulation": {tid: int(cnt) for tid, cnt in trophy_rows},
    }

    deaths_24h = await db.scalar(
        select(func.count()).select_from(CharacterDeath).where(CharacterDeath.died_at >= day_ago)
    )
    death_zone_rows = (
        await db.execute(
            select(CharacterDeath.pos_x, CharacterDeath.pos_y)
            .where(CharacterDeath.died_at >= day_ago)
        )
    ).all()
    zone_counts: dict[str, int] = {}
    for x, y in death_zone_rows:
        if x is None or y is None:
            continue
        dist = grid.chebyshev_distance(x, y)
        lo, hi = grid.zone_level_range(dist)
        key = f"{lo}-{hi}"
        zone_counts[key] = zone_counts.get(key, 0) + 1
    pvp_battles_24h = await db.scalar(
        select(func.count()).select_from(PvpBattle).where(PvpBattle.finished_at >= day_ago)
    )

    combat = {
        "deaths_24h": deaths_24h or 0,
        "deaths_by_zone_24h": dict(sorted(zone_counts.items(), key=lambda kv: -kv[1])),
        "pvp_battles_24h": pvp_battles_24h or 0,
    }

    return OverviewStats(players=players, progression=progression, retention=retention, economy=economy, combat=combat)


# --- Поиск и карточка игрока (2.2) ---


async def search_characters(db: AsyncSession, query: str, limit: int = 20) -> list[Character]:
    query = query.strip()
    if not query:
        return []
    conditions = [Character.name.ilike(f"%{query}%")]
    if query.isdigit():
        conditions.append(User.vk_id == int(query))
    rows = (
        await db.execute(
            select(Character)
            .join(User, User.id == Character.user_id)
            .where(Character.creation_state.is_(None))
            .where(conditions[0] if len(conditions) == 1 else (conditions[0] | conditions[1]))
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def player_card(db: AsyncSession, character_id: int) -> dict | None:
    """Патч 31, п.5: полная диагностическая карточка — всё, что нужно
    администратору для разбора конкретного игрока в одном ответе (детали
    группирует фронтенд, bot/miniapp_admin_api.py добавляет сверху только
    живые in-memory флаги «в бою/PvP/занят», которых нет в БД)."""
    character = await db.get(Character, character_id)
    if character is None:
        return None
    user = await db.get(User, character.user_id)
    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character_id))
    wallet = await wallet_service.get_wallet(db, character_id)
    trophy_stock = {t.id: count for t, count in await trophy_service.get_stock(db, character_id)}
    inventory = await item_service.get_inventory(db, character_id)
    story_rows = (
        await db.execute(select(CharacterStoryProgress).where(CharacterStoryProgress.character_id == character_id))
    ).scalars().all()
    unlocked_buffs = (
        await db.execute(select(CharacterUnlockedBuff.buff_id).where(CharacterUnlockedBuff.character_id == character_id))
    ).scalars().all()
    titles = (
        await db.execute(select(CharacterTitle.title_id).where(CharacterTitle.character_id == character_id))
    ).scalars().all()

    gear_bonus = await item_service.compute_gear_bonus(db, character_id)
    derived = derived_stats_service.compute(character, stats, gear_bonus) if stats is not None else None
    elixirs = await elixir_service.get_stock(db, character_id)
    owned_mounts = await mount_service.owned_mounts(db, character_id)
    mount_travel = await mount_service.active_travel(db, character_id)
    active_preset = await preset_service.get_active_preset(db, character_id)
    song_progress = await song_service.get_progress(db, character_id)
    trial_states = await trial_service.get_trial_states(db, character) if character.subclass else []
    dailies = await daily_service.get_dailies_overview(db, character)
    quest_line = await story_service.quest_summary_line(db, character) if character.region else None
    recent_actions = await action_journal(db, limit=10, target_character_id=character_id)

    return {
        "id": character.id,
        "vk_id": user.vk_id if user is not None else None,
        "name": character.name,
        "title": title_service.active_title_name(character),
        "level": character.level,
        "experience": character.experience,
        # Патч 34, ч.0: на потолке уровня xp_to_next(MAX_LEVEL) не имеет
        # смысла (левелапа больше не будет) — явный None вместо большого
        # бессмысленного числа, фронтенд показывает "МАКС".
        "xp_to_next": (
            experience_service.xp_to_next(character.level) if character.level < bc.MAX_LEVEL else None
        ),
        "base_class": character.base_class,
        "subclass": character.subclass,
        "class_title": class_title(character),
        "region": character.region,
        "pos_x": character.pos_x,
        "pos_y": character.pos_y,
        "is_dead": death_service.is_dead(character),
        "respawn_at": character.respawn_at.isoformat() if character.respawn_at else None,
        "foot_travel": {
            "to_x": character.travel_target_x, "to_y": character.travel_target_y,
            "remaining_seconds": movement_service.remaining_seconds(character),
        } if movement_service.is_traveling(character) else None,
        "mount_travel": {
            "mount_id": mount_travel.mount_id, "to_x": mount_travel.to_x, "to_y": mount_travel.to_y,
            "status": mount_travel.status, "remaining_seconds": mount_service.remaining_seconds(mount_travel),
        } if mount_travel is not None else None,
        "stats": {
            "str": stats.strength, "agi": stats.agility, "int": stats.intellect,
            "vit": stats.vitality, "wil": stats.will, "unspent_points": stats.unspent_points,
        } if stats is not None else None,
        "derived": {
            "max_hp": derived.max_hp,
            "current_hp": vitals_service.current_hp(character, stats, gear_bonus.get("vit", 0)),
            "damage": derived.damage,
            "crit_chance": derived.crit_chance,
            "mitigation": derived.mitigation,
            "control_resist": derived.control_resist,
            "support_power": derived.support_power,
            "dodge_chance": derived.dodge_chance,
            "ability_dodge_chance": derived.ability_dodge_chance,
        } if derived is not None else None,
        "gold": wallet.farm_currency,
        "gems": wallet.donate_currency,
        "trophies": {
            d.id: trophy_stock.get(d.id, 0) for d in trophy_service.trophy_defs_ordered()
        },
        "inventory": [
            {
                "id": item.id, "name": item.name, "slot": item.slot, "rarity": item.rarity,
                "ilvl": item.ilvl, "equipped": equipped, "stats": item.base_stats,
            }
            for item, equipped in inventory
        ],
        "elixirs": [
            {"id": d.id, "name": d.name, "emoji": d.emoji, "count": count} for d, count in elixirs
        ],
        "mounts": [
            {"mount_id": m.mount_id, "name": m.name, "rarity": m.rarity, "emoji": m.emoji}
            for m in owned_mounts
        ],
        "story_progress": [
            {"region": row.region, "act": row.act, "quest_step": row.quest_step, "status": row.status, "completed": row.completed}
            for row in story_rows
        ],
        "current_quest": quest_line,
        "unlocked_buffs": list(unlocked_buffs),
        "titles": list(titles),
        "active_preset": {"name": active_preset.name, "buff_ids": active_preset.buff_ids} if active_preset is not None else None,
        "song_progress": {
            "seen": len(song_progress.seen), "total": song_progress.total, "complete": song_progress.complete,
        },
        "trial_progress": {
            "unlocked": sum(1 for s in trial_states if s.unlocked), "total": len(trial_states),
        },
        "dailies_today": [
            {
                "title": q.title, "progress": q.progress, "target": q.target, "completed": q.completed,
            }
            for q in dailies.quests
        ],
        "pvp_wins": character.pvp_wins,
        "pvp_losses": character.pvp_losses,
        "login_streak": character.login_streak,
        "daily_streak": character.daily_streak,
        "is_banned": character.is_banned,
        "ban_reason": character.ban_reason,
        "banned_until": character.banned_until.isoformat() if character.banned_until else None,
        "premium_until": character.premium_until.isoformat() if character.premium_until else None,
        "is_premium": premium_service.is_premium(character),
        "created_at": user.created_at.isoformat() if user is not None else None,
        "last_active_at": character.last_active_at.isoformat() if character.last_active_at else None,
        "recent_admin_actions": [
            {
                "action_type": a.action_type, "note": a.note, "created_at": a.created_at.isoformat(),
            }
            for a in recent_actions
        ],
    }


# --- Действия над игроком (2.3), каждое логируется ---


async def grant_currency(
    db: AsyncSession, admin_vk_id: int, character: Character, currency: str, amount: int
) -> Wallet:
    """amount может быть отрицательным (забрать); списание не уходит в минус."""
    wallet = await wallet_service.get_wallet(db, character.id)
    field_name = "farm_currency" if currency == "farm" else "donate_currency"
    before = getattr(wallet, field_name)
    setattr(wallet, field_name, max(0, before + amount))
    after = getattr(wallet, field_name)
    await log_action(
        db, admin_vk_id, "grant_currency", character.id,
        old_value={currency: before}, new_value={currency: after}, note=f"delta={amount}",
    )
    return wallet


async def grant_trophy(db: AsyncSession, admin_vk_id: int, character: Character, trophy_id: str, amount: int) -> None:
    stock = await trophy_service.get_stock(db, character.id)
    before_count = next((c for t, c in stock if t.id == trophy_id), 0)
    await trophy_service.grant_specific(db, character.id, trophy_id, amount)
    await log_action(
        db, admin_vk_id, "grant_trophy", character.id,
        old_value={"trophy_id": trophy_id, "count": before_count},
        new_value={"trophy_id": trophy_id, "count": before_count + amount},
    )


async def grant_xp(db: AsyncSession, admin_vk_id: int, character: Character, amount: int) -> experience_service.LevelUp:
    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    before = {"level": character.level, "experience": character.experience}
    # apply_premium=False (патч 50): админ явно задаёт число — премиум-
    # множитель здесь неуместен, в отличие от игровых источников опыта.
    result = experience_service.add_experience(character, stats, amount, apply_premium=False)
    after = {"level": character.level, "experience": character.experience}
    await log_action(
        db, admin_vk_id, "grant_xp", character.id, old_value=before, new_value=after, note=f"amount={amount}"
    )
    return result


async def set_level(db: AsyncSession, admin_vk_id: int, character: Character, new_level: int) -> None:
    new_level = max(1, min(new_level, bc.MAX_LEVEL))
    before = character.level
    character.level = new_level
    character.experience = 0
    character.current_hp = None  # пересчёт max HP от нового уровня — лечит до полного
    await log_action(
        db, admin_vk_id, "set_level", character.id,
        old_value={"level": before}, new_value={"level": new_level},
    )


async def grant_item(
    db: AsyncSession, admin_vk_id: int, character: Character, ilvl: int, rng
) -> Item:
    item = await item_service.grant_random_item(db, character, ilvl, rng)
    await log_action(
        db, admin_vk_id, "grant_item", character.id,
        new_value={"item_id": item.id, "name": item.name, "slot": item.slot, "rarity": item.rarity},
    )
    return item


class NotSelfTarget(Exception):
    """Патч 34, ч.3: тестовые предметы админки — только себе. Случайная
    выдача другому игроку сломала бы ему баланс/экономику."""


async def _require_self(db: AsyncSession, admin_vk_id: int, character: Character) -> None:
    target_vk_id = await db.scalar(select(User.vk_id).where(User.id == character.user_id))
    if target_vk_id != admin_vk_id:
        raise NotSelfTarget


async def grant_admin_mount(db: AsyncSession, admin_vk_id: int, character: Character) -> None:
    """«Пепельный вестник» (патч 34, ч.3) — служебный маунт, 3 сек. на весь
    путь, 0% нападение. Только себе — см. _require_self."""
    await _require_self(db, admin_vk_id, character)
    await mount_service.grant(db, character, mc.ADMIN_MOUNT_ID)
    await log_action(db, admin_vk_id, "grant_admin_mount", character.id, note=mc.ADMIN_MOUNT_ID)


async def grant_admin_weapon(db: AsyncSession, admin_vk_id: int, character: Character) -> Item:
    """«Перо Хранителя» (патч 34, ч.3) — +1000 к каждому стату, служебная
    редкость (не продаётся — Item.admin_only). Только себе."""
    await _require_self(db, admin_vk_id, character)
    weapon_def = load_admin_weapons()[0]
    item = Item(
        name=weapon_def.name, slot=weapon_def.slot, base_stats=dict(weapon_def.stats),
        rarity=weapon_def.rarity, ilvl=None, admin_only=True,
    )
    db.add(item)
    await db.flush()
    db.add(Inventory(character_id=character.id, item_id=item.id, equipped=False))
    await db.flush()
    await log_action(
        db, admin_vk_id, "grant_admin_weapon", character.id,
        new_value={"item_id": item.id, "name": item.name},
    )
    return item


async def teleport(db: AsyncSession, admin_vk_id: int, character: Character, x: int, y: int) -> None:
    if not grid.in_bounds(x, y):
        raise ValueError("Координаты вне сетки")
    before = {"x": character.pos_x, "y": character.pos_y}
    movement_service.cancel_travel(character)
    character.pos_x = x
    character.pos_y = y
    await log_action(
        db, admin_vk_id, "teleport", character.id,
        old_value=before, new_value={"x": x, "y": y},
    )


async def restore_hp(db: AsyncSession, admin_vk_id: int, character: Character) -> None:
    before = {"current_hp": character.current_hp, "respawn_at": character.respawn_at.isoformat() if character.respawn_at else None}
    vitals_service.restore_full(character)
    character.respawn_at = None
    await log_action(db, admin_vk_id, "restore_hp", character.id, old_value=before, new_value={"current_hp": None, "respawn_at": None})


async def reset_activity_db(db: AsyncSession, character: Character) -> None:
    """DB-часть админского сброса активности — отмена перемещения/поездки на
    маунте (ЛЮБОЙ активный статус — "traveling" И "ambushed", см. баг ниже) +
    телепорт в родной город. Боевую/исследовательскую in-memory часть
    доделывает bot/miniapp_api.py (см. модульный докстринг) через
    bot.handlers.world.force_unstick(..., admin_override=True).

    Живой баг (2026-08-09, игрок 24815750/char 15): нападение в пути на
    маунте (MountTravel.status="ambushed") никогда не разрешилось (бой
    потерян/прерван), а старая проверка cancel_travel'ила только
    status=="traveling" — active_travel() же считает "ambushed" активным
    статусом наравне с "traveling" (см. mount_service.py), так что кнопка
    маунта продолжала утверждать "ты уже в пути" НАВСЕГДА, и ни /застрял,
    ни этот сброс её не снимали. Теперь отменяем В ЛЮБОМ случае, когда
    active_travel() вообще что-то вернул — тот уже сам знает, что считать
    активным."""
    if movement_service.is_traveling(character):
        movement_service.cancel_travel(character)
    active_mount_travel = await mount_service.active_travel(db, character.id)
    if active_mount_travel is not None:
        await mount_service.cancel_travel(db, active_mount_travel)
    if character.region is not None:
        home = wc.CITY_COORDS.get(character.region)
        if home is not None:
            character.pos_x, character.pos_y = home


async def log_reset_activity(db: AsyncSession, admin_vk_id: int, character: Character) -> None:
    await log_action(db, admin_vk_id, "reset_activity", character.id)


async def reset_stats(db: AsyncSession, admin_vk_id: int, character: Character) -> None:
    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    if stats is None:
        return
    before = {"str": stats.strength, "agi": stats.agility, "int": stats.intellect, "vit": stats.vitality, "wil": stats.will}
    total = stats.strength + stats.agility + stats.intellect + stats.vitality + stats.will
    start = bc.STARTING_STATS[character.base_class]
    start_total = start["STR"] + start["AGI"] + start["INT"] + start["VIT"] + start["WIL"]
    stats.strength = start["STR"]
    stats.agility = start["AGI"]
    stats.intellect = start["INT"]
    stats.vitality = start["VIT"]
    stats.will = start["WIL"]
    stats.unspent_points += max(0, total - start_total)
    await log_action(
        db, admin_vk_id, "reset_stats", character.id,
        old_value=before, new_value={"str": stats.strength, "agi": stats.agility, "int": stats.intellect, "vit": stats.vitality, "wil": stats.will},
    )


async def ban(
    db: AsyncSession, admin_vk_id: int, character: Character, reason: str, until: datetime | None = None
) -> None:
    before = {"is_banned": character.is_banned}
    character.is_banned = True
    character.ban_reason = reason
    character.banned_until = until
    await log_action(
        db, admin_vk_id, "ban", character.id, old_value=before,
        new_value={"is_banned": True, "ban_reason": reason, "banned_until": until.isoformat() if until else None},
    )


async def unban(db: AsyncSession, admin_vk_id: int, character: Character) -> None:
    before = {"is_banned": character.is_banned, "ban_reason": character.ban_reason}
    character.is_banned = False
    character.ban_reason = None
    character.banned_until = None
    await log_action(db, admin_vk_id, "unban", character.id, old_value=before, new_value={"is_banned": False})


def is_ban_active(character: Character, now: datetime | None = None) -> bool:
    if not character.is_banned:
        return False
    if character.banned_until is None:
        return True
    now = now or datetime.now(timezone.utc)
    return now < character.banned_until


# --- Журнал действий (2.4) ---


async def action_journal(
    db: AsyncSession, limit: int = 50, offset: int = 0, target_character_id: int | None = None,
) -> list[AdminAction]:
    query = select(AdminAction).order_by(AdminAction.created_at.desc(), AdminAction.id.desc())
    if target_character_id is not None:
        query = query.where(AdminAction.target_character_id == target_character_id)
    rows = (await db.execute(query.limit(limit).offset(offset))).scalars().all()
    return list(rows)


# --- Репорты багов (часть 3) ---


async def create_bug_report(db: AsyncSession, character_id: int | None, text: str, snapshot: dict) -> BugReport:
    report = BugReport(character_id=character_id, text=text, snapshot=snapshot)
    db.add(report)
    await db.flush()
    return report


async def bug_reports_since(db: AsyncSession, character_id: int, since: datetime) -> int:
    return await db.scalar(
        select(func.count())
        .select_from(BugReport)
        .where(BugReport.character_id == character_id, BugReport.created_at >= since)
    ) or 0


async def duplicate_bug_report(
    db: AsyncSession, character_id: int, text: str, since: datetime
) -> BugReport | None:
    """Патч 30, баг 1, исправление 3: репорт с ИДЕНТИЧНЫМ текстом от того же
    игрока за последние `since` — защита от дублей при ретрае VK Callback API
    (дедупликация по event_id уже есть на уровне webhook, это доп. рубеж на
    случай, если игрок ДЕЙСТВИТЕЛЬНО отправил одно и то же сообщение дважды
    вручную за короткое время)."""
    return await db.scalar(
        select(BugReport)
        .where(
            BugReport.character_id == character_id,
            BugReport.text == text,
            BugReport.created_at >= since,
        )
        .order_by(BugReport.created_at.desc())
        .limit(1)
    )


async def list_bug_reports(db: AsyncSession, status: str | None = None, limit: int = 50) -> list[BugReport]:
    stmt = select(BugReport).order_by(BugReport.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(BugReport.status == status)
    return list((await db.execute(stmt)).scalars().all())


async def set_bug_report_status(db: AsyncSession, report_id: int, status: str) -> BugReport | None:
    report = await db.get(BugReport, report_id)
    if report is None:
        return None
    report.status = status
    await db.flush()
    return report
