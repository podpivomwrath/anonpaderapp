"""Гильдейские задания: личные ежедневки участника и общие недельные.

Единственный источник славы гильдии (кроме босса): ежедневки дают славу и
личный вклад, недельные - славу, а их вклад делится между теми, кто двигал
прогресс. По вкладу строятся топы внутри гильдии (неделя и всё время).

Прогресс приходит через record() из тех же точек, что двигают обычные
ежедневки (services/daily_service.py), плюс добыча руды и рыбы. У персонажа
без гильдии record() выходит сразу, без единого запроса: это горячий путь.

Набор заданий выбирается детерминированно от (персонажа, дня) и (гильдии,
недели): перезагрузка или гонка двух запросов не перетасуют задания.
"""

import random
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import guild_config as gc
from models import Character, GuildDaily, GuildWeekly
from services import guild_service, wallet_service


def _metrics() -> list[str]:
    return list(gc.QUEST_METRICS)


def daily_metrics(character_id: int, day) -> list[str]:
    rng = random.Random(f"gd:{character_id}:{day.isoformat()}")
    return rng.sample(_metrics(), gc.DAILIES_PER_MEMBER)


def weekly_metrics(guild_id: int, week) -> list[str]:
    rng = random.Random(f"gw:{guild_id}:{week.isoformat()}")
    return rng.sample(_metrics(), gc.WEEKLY_QUESTS)


def title_of(metric: str) -> str:
    return gc.QUEST_METRICS[metric][0]


def label_of(metric: str) -> str:
    return gc.QUEST_METRICS[metric][1]


async def ensure_dailies(db: AsyncSession, character: Character) -> list[GuildDaily]:
    day = guild_service.today_msk()
    rows = list(
        (
            await db.scalars(
                select(GuildDaily).where(GuildDaily.character_id == character.id, GuildDaily.date == day)
            )
        ).all()
    )
    if rows or character.guild_id is None:
        return rows
    for metric in daily_metrics(character.id, day):
        db.add(GuildDaily(
            character_id=character.id, guild_id=character.guild_id, date=day, metric=metric,
            target=gc.QUEST_METRICS[metric][2],
        ))
    await db.flush()
    return list(
        (
            await db.scalars(
                select(GuildDaily).where(GuildDaily.character_id == character.id, GuildDaily.date == day)
            )
        ).all()
    )


async def ensure_weekly(db: AsyncSession, guild_id: int) -> list[GuildWeekly]:
    week = guild_service.week_start_msk()
    rows = list(
        (
            await db.scalars(
                select(GuildWeekly).where(GuildWeekly.guild_id == guild_id, GuildWeekly.week_start == week)
            )
        ).all()
    )
    if rows:
        return rows
    size = max(await guild_service.member_count(db, guild_id), gc.WEEKLY_MIN_MEMBERS_FOR_TARGET)
    for metric in weekly_metrics(guild_id, week):
        db.add(GuildWeekly(
            guild_id=guild_id, week_start=week, metric=metric,
            target=gc.QUEST_METRICS[metric][3] * size, contributors={},
        ))
    await db.flush()
    return list(
        (
            await db.scalars(
                select(GuildWeekly).where(GuildWeekly.guild_id == guild_id, GuildWeekly.week_start == week)
            )
        ).all()
    )


async def record(db: AsyncSession, character: Character, metric: str, amount: int = 1) -> list[str]:
    """Двигает гильдейские задания. Возвращает строки для игрока."""
    if character.guild_id is None or amount <= 0 or metric not in gc.QUEST_METRICS:
        return []
    notices: list[str] = []
    guild_id = character.guild_id
    await ensure_dailies(db, character)
    day = guild_service.today_msk()
    daily = await db.scalar(
        select(GuildDaily).where(
            GuildDaily.character_id == character.id, GuildDaily.date == day,
            GuildDaily.metric == metric, GuildDaily.completed.is_(False),
        ).with_for_update().execution_options(populate_existing=True)
    )
    if daily is not None:
        daily.progress = min(daily.progress + amount, daily.target)
        if daily.progress >= daily.target:
            daily.completed = True
            fame = await guild_service.add_fame(db, guild_id, gc.DAILY_FAME)
            await guild_service.add_contribution(db, character.id, gc.DAILY_CONTRIBUTION)
            gold = round(gc.DAILY_PERSONAL_GOLD * (1 + guild_service.perk(character, "daily_gold_pct") / 100))
            await wallet_service.deposit(db, character.id, "farm", gold)
            line = (
                f"🏰 Гильдейская ежедневка «{title_of(metric)}» выполнена: "
                f"+{fame.gained} славы гильдии, +{gold} золота."
            )
            if fame.levels_gained:
                line += f"\n🏰 Гильдия достигает {fame.new_level} уровня!"
            notices.append(line)

    await ensure_weekly(db, guild_id)
    week = guild_service.week_start_msk()
    weekly = await db.scalar(
        select(GuildWeekly).where(
            GuildWeekly.guild_id == guild_id, GuildWeekly.week_start == week,
            GuildWeekly.metric == metric, GuildWeekly.completed.is_(False),
        ).with_for_update().execution_options(populate_existing=True)
    )
    if weekly is not None:
        useful = min(amount, weekly.target - weekly.progress)
        weekly.progress += useful
        contributors = dict(weekly.contributors or {})
        key = str(character.id)
        contributors[key] = contributors.get(key, 0) + useful
        weekly.contributors = contributors
        if weekly.progress >= weekly.target:
            weekly.completed = True
            fame = await guild_service.add_fame(db, guild_id, gc.WEEKLY_FAME)
            total = sum(contributors.values()) or 1
            for cid, part in contributors.items():
                share = max(1, round(gc.WEEKLY_FAME * part / total))
                await guild_service.add_contribution(db, int(cid), share)
            await guild_service.log(
                db, guild_id, "weekly",
                f"Недельное задание «{title_of(metric)}» выполнено: +{fame.gained} славы.",
            )
            notices.append(
                f"🏰 Недельное задание гильдии «{title_of(metric)}» выполнено! +{fame.gained} славы."
            )
    await db.flush()
    return notices


async def overview(db: AsyncSession, character: Character) -> dict:
    """Задания для мини-аппа."""
    dailies = await ensure_dailies(db, character)
    weekly = await ensure_weekly(db, character.guild_id) if character.guild_id else []
    gold = round(gc.DAILY_PERSONAL_GOLD * (1 + guild_service.perk(character, "daily_gold_pct") / 100))
    return {
        "dailies": [
            {
                "metric": d.metric, "title": title_of(d.metric), "label": label_of(d.metric),
                "progress": d.progress, "target": d.target, "completed": d.completed,
                "reward": f"+{gc.DAILY_FAME} славы, +{gold} золота",
            }
            for d in sorted(dailies, key=lambda d: d.metric)
        ],
        "weekly": [
            {
                "metric": w.metric, "title": title_of(w.metric), "label": label_of(w.metric),
                "progress": w.progress, "target": w.target, "completed": w.completed,
                "mine": int((w.contributors or {}).get(str(character.id), 0)),
                "reward": f"+{gc.WEEKLY_FAME} славы",
            }
            for w in sorted(weekly, key=lambda w: w.metric)
        ],
    }


async def contribution_tops(db: AsyncSession, guild_id: int) -> dict:
    week = guild_service.week_start_msk()
    rows = await guild_service.members(db, guild_id)
    weekly = sorted(
        (
            (m.contribution_week if m.week_start == week else 0, c.name, c.id)
            for m, c in rows
        ),
        key=lambda t: -t[0],
    )
    total = sorted(((m.contribution_total, c.name, c.id) for m, c in rows), key=lambda t: -t[0])
    return {
        "week": [{"name": n, "id": i, "value": v} for v, n, i in weekly if v > 0][:20],
        "total": [{"name": n, "id": i, "value": v} for v, n, i in total if v > 0][:20],
    }

