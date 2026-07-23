"""Клавиатуры мира: меню города, перемещение, бой.

Перемещение — маленькие стрелки в компас-раскладке (⬆️/⬅️➡️/⬇️),
БЕЗ подписей сторон света (С/Ю/З/В) — так попросил пользователь.

Боевые кнопки навыков несут payload {"type":"skill","id":...}: подпись меняется
со счётчиком КД, а матчинг идёт по payload и не ломается.
"""

from vkbottle import Keyboard, KeyboardButtonColor, OpenLink, Text

from config import get_settings
from game.combat import balance_config as bc
from game.combat.base_skills import skills_for_class
from game.content_loader import ExplorationEventDef

BTN_MENTOR = "🧙 Наставник"
BTN_MARKET = "🏪 Рынок"
BTN_APPRAISER = "💰 Скупщик"
BTN_GATE = "🚪 За ворота"
BTN_REST = "🛏️ Отдых"
BTN_CHARACTER = "🎭 Персонаж"
BTN_INVENTORY = "🎒 Инвентарь"
BTN_STATS = "📊 Характеристики"
BTN_KEEPER = "📖 Хранитель Списков"


def add_miniapp_button(kb: Keyboard) -> None:
    """Кнопка-ссылка на мини-апп хаба персонажа; если VK_MINIAPP_URL ещё не
    заполнен (приложение в VK не создано), кнопку не добавляем вовсе."""
    miniapp_url = get_settings().vk_miniapp_url
    if not miniapp_url:
        return
    kb.row()
    kb.add(OpenLink(miniapp_url, BTN_CHARACTER))

BTN_UP = "⬆️"
BTN_DOWN = "⬇️"
BTN_LEFT = "⬅️"
BTN_RIGHT = "➡️"
BTN_EXPLORE = "🔍 Исследовать"

BTN_ATTACK = "🗡️ Атака"
BTN_ITEM = "🎒 Предмет"
BTN_FLEE = "🏃 Побег"


def empty_keyboard() -> str:
    """Пустая клавиатура — убирает кнопки в моменты ожидания (чистка шума)."""
    return Keyboard().get_json()


def waiting_keyboard() -> str:
    """Клавиатура на время ожидания (переход/исследование/отдых/смерть):
    без игровых кнопок, но с кнопкой мини-аппа — она нужна везде, кроме боя
    (ux-patch-10)."""
    kb = Keyboard(one_time=False)
    add_miniapp_button(kb)
    return kb.get_json()


def city_menu_keyboard(character=None) -> str:
    """character (патч 12) — при level>=30 добавляет кнопку Хранителя Списков
    (выбор подкласса/испытания). None — легаси-вызовы без гейта (нет кнопки)."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_MENTOR), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text(BTN_MARKET), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_GATE), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_REST), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_APPRAISER), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_INVENTORY), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_STATS), color=KeyboardButtonColor.SECONDARY)
    if character is not None and character.level >= bc.SUBCLASS_UNLOCK_MIN_LEVEL:
        kb.row()
        kb.add(Text(BTN_KEEPER), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


def movement_keyboard() -> str:
    """Карта: D-pad из стрелок (циферблатная раскладка 12/3/6/9 часов) +
    исследование и отдых. Вход в город — автоматически при прибытии."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_UP), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_LEFT), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_RIGHT), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_DOWN), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_EXPLORE), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_REST), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


def event_choice_keyboard(event: ExplorationEventDef) -> str:
    """Кнопки события исследования (патч 9, блок 1): payload несёт id события +
    индекс выбора, чтобы устаревшие нажатия после уже разрешённого события
    отличались и игнорировались хендлером."""
    kb = Keyboard(one_time=False)
    for idx, choice in enumerate(event.choices):
        kb.add(Text(choice.label, payload={"type": "event_choice", "event": event.id, "choice": idx}))
        kb.row()
    add_miniapp_button(kb)
    return kb.get_json()


def combat_keyboard(base_class: str, cooldowns: dict[str, int]) -> str:
    """Боевая клавиатура: Атака + до 3 навыков класса (с КД-счётчиком) + Предмет + Побег.
    Навык на КД показывается с остатком, но остаётся нажимаемым — обработчик ответит
    «не готов» без траты хода."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_ATTACK), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    for skill in skills_for_class(base_class):
        cd = cooldowns.get(skill.id, 0)
        label = skill.name if cd <= 0 else f"{skill.name} (КД {cd})"
        color = KeyboardButtonColor.PRIMARY if cd <= 0 else KeyboardButtonColor.SECONDARY
        kb.add(Text(label, payload={"type": "skill", "id": skill.id}), color=color)
        kb.row()
    kb.add(Text(BTN_ITEM), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_FLEE), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()
