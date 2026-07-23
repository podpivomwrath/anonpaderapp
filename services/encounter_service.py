"""Итог PvE-встречи: победа даёт опыт за моба + трофеи + двигает квест;
поражение — смерть (штраф опыта, таймер), респавн в городе автоматически."""

import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat.formulas import respawn_time_minutes
from models import Character, CharacterStats
from services import death_service, experience_service, quest_service, trophy_service


@dataclass
class VictoryOutcome:
    xp_gained: int
    levels_gained: int
    new_level: int
    quest_label: str | None
    quest_progress: int | None
    quest_target: int | None
    quest_ready: bool
    trophies_gained: dict[str, int] = field(default_factory=dict)


async def resolve_victory(
    db: AsyncSession, character: Character, mob_level: int, rng: random.Random
) -> VictoryOutcome:
    """Опыт за моба (xp_per_mob от уровня моба) + трофеи (патч 9) + прогресс квеста."""
    stats = await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )
    xp = experience_service.xp_per_mob(mob_level)
    levelup = experience_service.add_experience(character, stats, xp)
    trophies = await trophy_service.grant_from_kill(db, character, rng)

    progress = await quest_service.record_kill(db, character)
    if progress is None:
        return VictoryOutcome(
            xp, levelup.levels_gained, levelup.new_level, None, None, None, False, trophies
        )
    return VictoryOutcome(
        xp, levelup.levels_gained, levelup.new_level,
        progress.progress_label, progress.progress, progress.target_count,
        progress.status == "ready", trophies,
    )


@dataclass
class DefeatOutcome:
    respawn_minutes: float
    xp_lost: int


async def resolve_defeat(db: AsyncSession, character: Character) -> DefeatOutcome:
    """Смерть в PvE: штраф опыта текущего уровня, таймер респавна. Возрождение в
    родном городе — АВТОМАТИЧЕСКИ по таймеру (bot.handlers.respawn)."""
    minutes = respawn_time_minutes(character.level)
    xp_lost = death_service.apply_death(character)
    character.travel_target_x = None
    character.travel_target_y = None
    character.travel_arrives_at = None
    return DefeatOutcome(minutes, xp_lost)
