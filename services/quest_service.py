"""Первый региональный квест: назначение, прогресс, выдача награды у наставника.

Возвращаются полностью материализованные dataclass'ы (не ORM-объекты), чтобы
не спотыкаться о detached instances / lazy-load вне сессии в async SQLAlchemy.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Character, CharacterQuest, CharacterStats, Quest, QuestStatus
from services import experience_service


@dataclass
class QuestProgress:
    code: str
    title: str
    progress_label: str
    target_count: int
    progress: int
    status: str
    is_new: bool = False


@dataclass
class TurnInResult:
    """Квест закрыт. Опыт начислен (крупный разовый); золото — хук на будущее,
    пока не капает (progression-patch-4)."""

    xp_reward: int = 0
    gold_reward: int = 0
    levels_gained: int = 0
    new_level: int = 1


async def _get_quest_def(db: AsyncSession, region: str) -> Quest | None:
    return await db.scalar(select(Quest).where(Quest.region == region))


async def _get_character_quest(
    db: AsyncSession, character_id: int, quest_id: int
) -> CharacterQuest | None:
    return await db.scalar(
        select(CharacterQuest).where(
            CharacterQuest.character_id == character_id,
            CharacterQuest.quest_id == quest_id,
        )
    )


async def get_or_assign(db: AsyncSession, character: Character) -> QuestProgress | None:
    """Назначает квест региона при первом обращении к своему наставнику."""
    quest = await _get_quest_def(db, character.region)
    if quest is None:
        return None
    cq = await _get_character_quest(db, character.id, quest.id)
    is_new = False
    if cq is None:
        cq = CharacterQuest(
            character_id=character.id, quest_id=quest.id, progress=0, status=QuestStatus.ACTIVE
        )
        db.add(cq)
        await db.flush()
        is_new = True
    return QuestProgress(
        quest.code, quest.title, quest.progress_label, quest.target_count,
        cq.progress, cq.status, is_new,
    )


async def record_kill(db: AsyncSession, character: Character) -> QuestProgress | None:
    """+1 к прогрессу активного квеста региона персонажа (если есть)."""
    quest = await _get_quest_def(db, character.region)
    if quest is None:
        return None
    cq = await db.scalar(
        select(CharacterQuest).where(
            CharacterQuest.character_id == character.id,
            CharacterQuest.quest_id == quest.id,
            CharacterQuest.status == QuestStatus.ACTIVE,
        )
    )
    if cq is None:
        return None
    cq.progress = min(cq.progress + 1, quest.target_count)
    if cq.progress >= quest.target_count:
        cq.status = QuestStatus.READY
    await db.flush()
    return QuestProgress(
        quest.code, quest.title, quest.progress_label, quest.target_count,
        cq.progress, cq.status,
    )


async def turn_in(db: AsyncSession, character: Character) -> TurnInResult | None:
    """Закрывает квест в статусе READY у наставника и начисляет опыт.

    Опыт — крупный разовый (из данных квеста). Золото — хук на будущее,
    пока НЕ начисляется (progression-patch-4).
    """
    quest = await _get_quest_def(db, character.region)
    if quest is None:
        return None
    cq = await db.scalar(
        select(CharacterQuest).where(
            CharacterQuest.character_id == character.id,
            CharacterQuest.quest_id == quest.id,
            CharacterQuest.status == QuestStatus.READY,
        )
    )
    if cq is None:
        return None
    stats = await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )
    levelup = experience_service.add_experience(character, stats, quest.xp_reward)
    # золото пока не капает — хук на будущее (quest.gold_reward НЕ начисляем)
    cq.status = QuestStatus.COMPLETED
    await db.flush()
    return TurnInResult(
        xp_reward=quest.xp_reward,
        gold_reward=0,
        levels_gained=levelup.levels_gained,
        new_level=levelup.new_level,
    )
