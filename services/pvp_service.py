"""Открытое PvP на карте (патч 22): кто на клетке, награды/штрафы, статистика,
лог боёв, топ. Живое состояние самих боёв (дуэли/массовые) — в памяти
bot/handlers/pvp.py + game/combat/duel_engine.py + game/combat/tick_engine.py;
здесь — только то, что трогает БД (персонажи, лог, рейтинг).
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.classes.base import REGISTRY
from game.economy import dailies_config as dc
from game.economy import pvp_config as pc
from models import Character, PvpBattle
from services import death_service

BASE_CLASS_TITLES = {"warrior": "Воин", "rogue": "Разбойник", "mage": "Маг"}


def class_title(character: Character) -> str:
    """Подкласс, если уже выбран, иначе базовый класс — для отображения в
    «Осмотреться»/боевых сообщениях (патч 22, п.2)."""
    if character.subclass is not None:
        subclass = REGISTRY.get(character.subclass)
        if subclass is not None:
            return subclass.title
    return BASE_CLASS_TITLES.get(character.base_class, character.base_class)


async def others_at(db: AsyncSession, character: Character) -> list[Character]:
    """Другие живые персонажи на той же клетке карты, что и character —
    основа «Осмотреться»/`/напасть` (патч 22, п.2-3). Себя и мёртвых не
    включает; персонажей, уже занятых в PvP-бою, отфильтровывает вызывающий
    (bot/handlers/pvp.py — знает про живой реестр боёв, этот слой не знает)."""
    rows = (
        await db.execute(
            select(Character).where(
                Character.pos_x == character.pos_x,
                Character.pos_y == character.pos_y,
                Character.id != character.id,
                Character.creation_state.is_(None),
            )
        )
    ).scalars().all()
    return [c for c in rows if not death_service.is_dead(c)]


def no_reward_for_kill(winner_level: int, victim_level: int) -> bool:
    """Патч 22, п.5: жертва значительно слабее победителя — трофеи не переходят."""
    return (winner_level - victim_level) > pc.PVP_LEVEL_DIFF_NO_REWARD


def record_win(character: Character) -> None:
    character.pvp_wins += 1


def record_loss(character: Character) -> None:
    character.pvp_losses += 1


async def log_battle(
    db: AsyncSession, battle_type: str, participant_ids: list[int], winner_ids: list[int],
) -> None:
    """battle_type: "duel" | "mass". winner_ids пуст при ничьей (только дуэль
    — в массовом бою ничьей не бывает, resolve_tick всегда даёт победителя,
    кроме одновременной гибели последних двух сторон)."""
    battle = PvpBattle(
        battle_type=battle_type,
        participant_ids=list(participant_ids),
        winner_ids=list(winner_ids),
        finished_at=datetime.now(timezone.utc),
    )
    db.add(battle)
    await db.flush()


@dataclass
class LeaderboardEntry:
    rank: int
    name: str
    wins: int
    losses: int
    title: str | None = None


async def leaderboard(db: AsyncSession, limit: int = 10) -> list[LeaderboardEntry]:
    """Топ-10 (или limit) по победам, при равенстве — по меньшему числу
    поражений (патч 22, п.7). title (патч 23) — активный титул, если задан."""
    rows = (
        await db.execute(
            select(
                Character.name, Character.pvp_wins, Character.pvp_losses, Character.active_title_id,
            )
            .where(Character.creation_state.is_(None))
            .order_by(Character.pvp_wins.desc(), Character.pvp_losses.asc())
            .limit(limit)
        )
    ).all()
    return [
        LeaderboardEntry(
            rank=i, name=name, wins=wins, losses=losses,
            title=dc.TITLE_NAMES.get(title_id) if title_id else None,
        )
        for i, (name, wins, losses, title_id) in enumerate(rows, start=1)
    ]


async def rank_of(db: AsyncSession, character: Character) -> int:
    """1-based место character в общем рейтинге (та же сортировка, что и
    leaderboard) — для строки «Ты: N место» вне топ-10."""
    better = await db.scalar(
        select(func.count()).select_from(Character).where(
            Character.creation_state.is_(None),
            (Character.pvp_wins > character.pvp_wins)
            | (
                (Character.pvp_wins == character.pvp_wins)
                & (Character.pvp_losses < character.pvp_losses)
            ),
        )
    )
    return (better or 0) + 1
