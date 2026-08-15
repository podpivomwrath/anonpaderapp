"""Клавиатура списка пресетов баффов в чате (патч 14, ч.3)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.layout import add_paired
from bot.keyboards.world import BTN_PRESETS, add_miniapp_button
from models import CharacterBuffPreset


def no_keyboard() -> str:
    return Keyboard(inline=True).get_json()


def presets_list_keyboard(presets: list[CharacterBuffPreset]) -> str:
    """Патч 41: пресеты — по 2 в ряд (до 5 слотов — максимум 3 ряда вместо 5)."""
    kb = Keyboard(inline=True)
    add_paired(kb, [
        (
            f"{'✅ ' if preset.is_active else ''}{idx}. {preset.name}",
            KeyboardButtonColor.POSITIVE if preset.is_active else KeyboardButtonColor.SECONDARY,
            {"type": "preset_switch", "id": preset.id},
        )
        for idx, preset in enumerate(presets, start=1)
    ])
    add_miniapp_button(kb)
    return kb.get_json()
