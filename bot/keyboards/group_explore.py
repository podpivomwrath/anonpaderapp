"""Клавиатура очереди готовности группового исследования (патч 51, ч.3)."""

from vkbottle import Keyboard, KeyboardButtonColor, OpenLink, Text

from bot.keyboards.world import BTN_CHARACTER
from config import get_settings


def group_ready_keyboard() -> str:
    """Кнопки нажавшего [🔍 Исследовать] на общей клетке, пока очередь ещё
    не собралась целиком — [Отменить] [🎭 Персонаж]. "Персонаж" — та же
    deep-link-кнопка в мини-апп, что и в обычных клавиатурах локации
    (bot/keyboards/world.py::add_miniapp_button), не отдельный payload."""
    kb = Keyboard(inline=True)
    kb.add(Text("Отменить", payload={"type": "group_explore_cancel"}), color=KeyboardButtonColor.NEGATIVE)
    miniapp_url = get_settings().vk_miniapp_url
    if miniapp_url:
        kb.add(OpenLink(miniapp_url, BTN_CHARACTER))
    return kb.get_json()
