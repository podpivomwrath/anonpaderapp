"""Отображение состава группы (патч 51, ч.2) — блок «👥 ГРУППА» в сводке
локации (bot/world_summary.py::location_summary) и уведомление об исключении
по разрыву уровней. Себя в списке тоже показываем (порядок — joined_at, как
и в services/group_service.py::GroupSnapshot)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import display
from models import Character, CharacterStats, User
from services import group_service, item_service, vitals_service
from services.db import get_session_factory


async def group_summary_block(db: AsyncSession, character_id: int) -> str | None:
    """None — персонаж не в группе (блок не выводится вовсе, см. патч)."""
    snapshot = await group_service.get_group_snapshot(db, character_id)
    if snapshot is None:
        return None
    lines = ["👥 ГРУППА"]
    for member in snapshot.members:
        stats = await db.scalar(
            select(CharacterStats).where(CharacterStats.character_id == member.id)
        )
        gear_bonus = await item_service.compute_gear_bonus(db, member.id)
        vit_bonus = gear_bonus.get("vit", 0)
        max_hp = vitals_service.max_hp(member, stats, vit_bonus)
        current_hp = vitals_service.current_hp(member, stats, vit_bonus)
        crown = "👑 " if member.id == snapshot.leader_character_id else ""
        lines.append(
            f"{crown}{member.name} · {member.level} ур. · "
            f"{display.health_bar(current_hp, max_hp)} · ({member.pos_x}; {member.pos_y})"
        )
    return "\n".join(lines)


def level_gap_kick_line(kick: "group_service.LevelGapKick") -> str:
    """Уведомление ОСТАЛЬНЫМ участникам группы (не самому исключённому —
    для него отдельный текст, см. level_gap_kick_self_line)."""
    return f"👥 {kick.kicked_name} вышел за пределы разрыва уровней группы и покинул отряд."


def level_gap_kick_self_line() -> str:
    return "👥 Разрыв уровней в группе превысил лимит — ты исключён из отряда."


async def notify_group_kick(bot_api, kick: "group_service.LevelGapKick | None") -> None:
    """Проактивно рассылает ОСТАЛЬНЫМ участникам группы сообщение об
    исключении (сам исключённый узнаёт из текста своего текущего действия —
    level_gap_kick_self_line добавляется вызывающим кодом отдельно). Открывает
    СОБСТВЕННУЮ короткую сессию БД — вызывается уже ПОСЛЕ commit основной
    транзакции хендлера (тот же паттерн, что и остальные проактивные
    рассылки группы, см. bot/handlers/group.py)."""
    if kick is None or not kick.remaining_member_character_ids:
        return
    async with get_session_factory()() as db:
        rows = (
            await db.execute(
                select(User.vk_id)
                .join(Character, Character.user_id == User.id)
                .where(Character.id.in_(kick.remaining_member_character_ids))
            )
        ).scalars().all()
    line = level_gap_kick_line(kick)
    for vk_id in rows:
        try:
            await bot_api.messages.send(peer_id=vk_id, message=line, random_id=0)
        except Exception:
            pass
