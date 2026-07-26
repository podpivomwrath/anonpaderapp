"""Общий хелпер для VK-вложений (фото из альбома группы).

Используется онбордингом (bot/onboarding_texts.py) и игровыми моментами
(bot/world_texts.py, bot/handlers/combat.py, bot/handlers/respawn.py) —
вынесено сюда, чтобы не плодить копии одной и той же строки."""

from config import get_settings


def photo_attachment(photo_id: str) -> str:
    """photo{owner_id}_{photo_id} — owner_id отрицательный для сообщества."""
    return f"photo-{get_settings().vk_group_id}_{photo_id}"
