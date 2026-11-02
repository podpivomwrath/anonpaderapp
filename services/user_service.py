"""Use-case'ы вокруг профиля персонажа.

Создание пользователя/персонажа — в services/onboarding_service.py (FSM).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.onboarding_texts import REGION_TITLES
from game.combat import balance_config as bc
from models import BaseClass, Character, User
from services import naming, premium_service, wallet_service

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
    # На потолке опыт не копится: «опыт: 0» выглядело как сброс.
    level_note = "максимум" if character.level >= bc.MAX_LEVEL else f"опыт: {character.experience}"
    title = CLASS_TITLES.get(character.base_class, character.base_class)
    # Подкласс - по-русски («Страж»), а не id из базы («guardian»).
    subclass = naming.subclass_title(character.subclass)
    region = REGION_TITLES.get(character.region, "-") if character.region else "-"
    return (
        f"📜 {premium_service.badge(character)}{character.name}\n"
        f"Класс: {title}{f' ({subclass})' if subclass else ''}\n"
        f"Регион: {region}\n"
        f"Уровень: {character.level} ({level_note})\n"
        f"\n"
        f"💪 Сила: {s.strength}\n"
        f"🏃 Ловкость: {s.agility}\n"
        f"🧠 Интеллект: {s.intellect}\n"
        f"❤️ Выносливость: {s.vitality}\n"
        f"✨ Воля: {s.will}\n"
        f"\n"
        f"Свободных очков: {s.unspent_points}\n"
        f"💰 Золото: {wallet.farm_currency}"
    )
