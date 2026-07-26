"""Клавиатура списка пресетов баффов в чате (патч 14, ч.3)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot.keyboards.world import BTN_PRESETS, add_miniapp_button
from models import CharacterBuffPreset


def no_keyboard() -> str:
    return Keyboard(inline=True).get_json()


def presets_list_keyboard(presets: list[CharacterBuffPreset]) -> str:
    kb = Keyboard(inline=True)
    for idx, preset in enumerate(presets, start=1):
        label = f"{'✅ ' if preset.is_active else ''}{idx}. {preset.name}"
        kb.add(
            Text(label, payload={"type": "preset_switch", "id": preset.id}),
            color=KeyboardButtonColor.POSITIVE if preset.is_active else KeyboardButtonColor.SECONDARY,
        )
        kb.row()
    add_miniapp_button(kb)
    return kb.get_json()
