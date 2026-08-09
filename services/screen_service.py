"""Экран персонажа (патч 37): клавиатура — свойство ЭКРАНА, не сообщения.

Переход на экран заменяет клавиатуру ЦЕЛИКОМ (никакого накопления инлайн-кнопок
поверх городской/карточной клавиатуры — именно это ломало скупщика: экран
скупщика слал инлайн-кнопки, а городская reply-клавиатура так и оставалась
висеть внизу, съедая лимит и место).

character.screen хранит текущий ВЛОЖЕННЫЙ экран (None — корневой: город/карта/
бой, его клавиатуру как и раньше строит bot/handlers/world.py::_current_keyboard).
Персистентность в БД — переживает рестарт бота и /клавиатура без дополнительной
инфраструктуры (Redis и т.п. не нужен).

Общее правило (патч 37): при добавлении любого нового вложенного экрана
(магазин, гильдия, рейд, обмен) он обязан быть здесь зарегистрирован с
родителем, заменять клавиатуру целиком, иметь [← Назад] и укладываться в
лимиты VK (иначе — страницы, не попытка уместить всё)."""

from sqlalchemy.ext.asyncio import AsyncSession

from models import Character

# Родитель каждого вложенного экрана — куда ведёт [← Назад]. None (в т.ч.
# отсутствие в словаре) — родитель корневой (город/карта/бой).
PARENT: dict[str, str | None] = {
    "appraiser": None,
    "appraiser_trophies": "appraiser",
    "appraiser_gear": "appraiser",
    "appraiser_gear_detail": "appraiser_gear",
    "elixir_shop": None,
    "inventory": None,
}


def parent_of(screen: str | None) -> str | None:
    if screen is None:
        return None
    return PARENT.get(screen)


async def set_screen(db: AsyncSession, character: Character, screen: str | None) -> None:
    character.screen = screen
    await db.flush()
