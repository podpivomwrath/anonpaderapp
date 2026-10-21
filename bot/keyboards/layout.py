"""Патч 41: общее правило раскладки для ВСЕХ клавиатур игры.

  - Кнопки по умолчанию идут ПО ДВЕ В РЯД (add_paired ниже), не по одной —
    иначе 5-6 кнопок растягивают экран на весь список ниже.
  - Исключения — отдельной строкой во всю ширину: главное действие экрана
    (напр. «Исследовать»), [← Назад], ссылка на мини-апп.
  - Главное (2026-10-21, владелец): экран не листается и подпись читается.
    На телефоне видно ~5 рядов, поэтому весь экран - не больше 5 рядов
    вместе с кнопкой мини-аппа и [← Назад]. Число кнопок само по себе не
    ограничено: короткие можно ставить по 3 в ряд.
  - Подписи: при 2 в ряд ≤ ~14 символов с эмодзи, при 3 в ряд ≤ ~11 - иначе
    VK обрезает многоточием. Следит tests/test_keyboard_fit.py.

Использовать add_paired при добавлении любого нового списка кнопок."""

from vkbottle import Keyboard, KeyboardButtonColor, Text


def add_paired(
    kb: Keyboard,
    items: list[tuple[str, KeyboardButtonColor, dict | None]],
) -> None:
    """Добавляет (label, color, payload|None) по 2 в ряд; нечётный хвост —
    последней кнопкой в своём ряду."""
    for i, (label, color, payload) in enumerate(items):
        if payload is not None:
            kb.add(Text(label, payload=payload), color=color)
        else:
            kb.add(Text(label), color=color)
        if i % 2 == 1:
            kb.row()
    if len(items) % 2 == 1:
        kb.row()
