"""Кто имеет доступ к админ-панели мини-аппа.

Администратор - один, settings.admin_vk_id (ему же бот шлёт баг-репорты).
Модераторы (2026-10-13) получают в панели тот же доступ, что и админ: обзор,
игроки и действия над ними, журнал, руда, промокоды, баги. Их действия
пишутся в журнал под их собственным vk_id - видно, кто что сделал.

Добавить модератора - дописать vk_id сюда и выкатить.
"""

from config import Settings

MODERATOR_VK_IDS: frozenset[int] = frozenset({
    450240819,  # Гостус
})


def is_moderator(vk_id: int) -> bool:
    return vk_id in MODERATOR_VK_IDS


def has_panel_access(settings: Settings, vk_id: int) -> bool:
    """Админ или модератор."""
    return (bool(settings.admin_vk_id) and vk_id == settings.admin_vk_id) or is_moderator(vk_id)
