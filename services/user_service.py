"""Use-case'ы вокруг профиля персонажа.

Создание пользователя/персонажа — в services/onboarding_service.py (FSM).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.onboarding_texts import REGION_TITLES
from models import BaseClass, Character, User
from services import wallet_service

CLASS_TITLES = {
    BaseClass.WARRIOR: "Воин",
    BaseClass.ROGUE: "Разбойник",
    BaseClass.MAGE: "Маг",
}


async def get_profile_text(session: AsyncSession, vk_id: int) -> str | None:
    """Текст профиля для /profile. None — персонажа нет или создание не завершено."""
    character = await session.scalar(
        select(Character)
        .join(User, User.id == Character.user_id)
        .where(User.vk_id == vk_id, Character.creation_state.is_(None))
        .options(selectinload(Character.stats))
    )
    if character is None:
        return None
    s = character.stats
    wallet = await wallet_service.get_wallet(session, character.id)
    title = CLASS_TITLES.get(character.base_class, character.base_class)
    region = REGION_TITLES.get(character.region, "—") if character.region else "—"
    return (
        f"📜 {character.name}\n"
        f"Класс: {title}{f' ({character.subclass})' if character.subclass else ''}\n"
        f"Регион: {region}\n"
        f"Уровень: {character.level} (опыт: {character.experience})\n"
        f"\n"
        f"💪 STR: {s.strength}\n"
        f"🏃 AGI: {s.agility}\n"
        f"🧠 INT: {s.intellect}\n"
        f"❤️ VIT: {s.vitality}\n"
        f"✨ WIL: {s.will}\n"
        f"\n"
        f"Свободных очков: {s.unspent_points}\n"
        f"💰 Золото: {wallet.farm_currency}"
    )
