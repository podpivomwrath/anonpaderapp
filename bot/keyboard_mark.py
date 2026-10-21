"""Метка на каждой текстовой кнопке бота (2026-10-21).

Игрой управляют только кнопки и команды через «/» (bot/button_gate.py):
набранный текст без payload бот не читает. Чтобы не дописывать payload в
сотню клавиатур руками, метка ставится здесь, в Keyboard.get_json, на каждую
текстовую кнопку без своего payload. Подключается импортом пакета bot.
"""

from vkbottle import Keyboard

BUTTON_MARK = {"btn": 1}

_original_get_json = Keyboard.get_json


def _marked_get_json(self: Keyboard) -> str:
    for row in self.buttons:
        for button in row:
            action = button.action
            if getattr(action, "type", None) == "text" and not getattr(action, "payload", None):
                action.payload = BUTTON_MARK
    return _original_get_json(self)


if getattr(Keyboard.get_json, "__name__", "") != "_marked_get_json":
    Keyboard.get_json = _marked_get_json
