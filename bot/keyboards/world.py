"""Клавиатуры мира: меню города, перемещение, бой.

Перемещение — маленькие стрелки в компас-раскладке (⬆️/⬅️➡️/⬇️),
БЕЗ подписей сторон света (С/Ю/З/В) — так попросил пользователь.

Боевые кнопки навыков несут payload {"type":"skill","id":...}: подпись меняется
со счётчиком КД, а матчинг идёт по payload и не ломается.
"""

from vkbottle import Keyboard, KeyboardButtonColor, OpenLink, Text

from bot.onboarding_texts import REGION_TITLES
from config import get_settings
from game.combat import balance_config as bc
from game.combat.base_skills import skills_for_class
from game.content_loader import ExplorationEventDef
from game.world import grid

BTN_MENTOR = "🧙 Наставник"
BTN_MENTOR_BADGE = f"{BTN_MENTOR} ❗"  # патч 21: есть что взять/сдать у наставника
BTN_MARKET = "🏪 Рынок"
BTN_APPRAISER = "💰 Скупщик"
BTN_GATE = "🚪 За ворота"
BTN_REST = "🛏️ Отдых"
BTN_CHARACTER = "🎭 Персонаж"
BTN_INVENTORY = "🎒 Инвентарь"
BTN_STATS = "📊 Характеристики"
BTN_KEEPER = "📖 Хранитель Списков"
BTN_PRESETS = "⚔️ Пресеты"
BTN_ELIXIR_SHOP = "⚗️ Лавка зелий"


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
BTN_LOOK_AROUND = "👁 Осмотреться"  # патч 22: кто ещё на клетке

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


def city_menu_keyboard(character=None, mentor_badge: bool = False) -> str:
    """character (патч 12) — при level>=30 добавляет кнопку Хранителя Списков
    (выбор подкласса/испытания); при выбранном подклассе (патч 14, ч.3) —
    кнопку [⚔️ Пресеты]. None — легаси-вызовы без гейта (нет кнопок).
    mentor_badge (патч 21) — есть невзятый/несданный сюжетный квест: кнопка
    наставника показывается с ❗ (см. BTN_MENTOR_BADGE)."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_MENTOR_BADGE if mentor_badge else BTN_MENTOR), color=KeyboardButtonColor.PRIMARY)
    kb.add(Text(BTN_MARKET), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_GATE), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_REST), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_APPRAISER), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_INVENTORY), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_STATS), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_ELIXIR_SHOP), color=KeyboardButtonColor.SECONDARY)
    if character is not None and character.level >= bc.SUBCLASS_UNLOCK_MIN_LEVEL:
        kb.row()
        kb.add(Text(BTN_KEEPER), color=KeyboardButtonColor.SECONDARY)
    if character is not None and character.subclass is not None:
        kb.row()
        kb.add(Text(BTN_PRESETS), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


# dx,dy по сторонам компаса (патч 17: подписи и границы зависят от позиции)
_DIRECTION_DELTAS = {
    BTN_UP: (0, 1),
    BTN_DOWN: (0, -1),
    BTN_LEFT: (-1, 0),
    BTN_RIGHT: (1, 0),
}

# Все тексты, которые может нести кнопка движения (стрелка ИЛИ название
# города) — для регистрации хендлера, фактическое направление резолвится
# по текущей позиции через resolve_direction().
MOVEMENT_TEXTS = list(_DIRECTION_DELTAS) + list(REGION_TITLES.values())


def _direction_label(x: int, y: int, dx: int, dy: int, arrow: str) -> str | None:
    """Подпись кнопки направления от (x;y): None — за границей сетки (кнопку
    не показываем), название города — если соседняя клетка ведёт в город,
    иначе обычная стрелка."""
    nx, ny = x + dx, y + dy
    if not grid.in_bounds(nx, ny):
        return None
    region = grid.city_region_at(nx, ny)
    return REGION_TITLES[region] if region is not None else arrow


def resolve_direction(x: int, y: int, text: str) -> tuple[int, int] | None:
    """Обратный маппинг: текст нажатой кнопки → (dx;dy) для позиции (x;y).
    None — кнопка больше не соответствует текущей позиции (устаревшая
    клавиатура) либо ушла бы за границу."""
    for arrow, (dx, dy) in _DIRECTION_DELTAS.items():
        if _direction_label(x, y, dx, dy, arrow) == text:
            return dx, dy
    return None


def movement_keyboard(pos_x: int, pos_y: int) -> str:
    """Карта: D-pad из стрелок (циферблатная раскладка 12/3/6/9 часов) +
    исследование и отдых. Вход в город — автоматически при прибытии.

    Патч 17: направления за пределами сетки (-50..50) не показываются;
    направление, ведущее на клетку города, подписывается названием города
    вместо стрелки."""
    up = _direction_label(pos_x, pos_y, *_DIRECTION_DELTAS[BTN_UP], BTN_UP)
    down = _direction_label(pos_x, pos_y, *_DIRECTION_DELTAS[BTN_DOWN], BTN_DOWN)
    left = _direction_label(pos_x, pos_y, *_DIRECTION_DELTAS[BTN_LEFT], BTN_LEFT)
    right = _direction_label(pos_x, pos_y, *_DIRECTION_DELTAS[BTN_RIGHT], BTN_RIGHT)

    kb = Keyboard(one_time=False)
    if up is not None:
        kb.add(Text(up), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    if left is not None or right is not None:
        if left is not None:
            kb.add(Text(left), color=KeyboardButtonColor.SECONDARY)
        if right is not None:
            kb.add(Text(right), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    if down is not None:
        kb.add(Text(down), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    kb.add(Text(BTN_EXPLORE), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(BTN_REST), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_LOOK_AROUND), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


def gate_direction_keyboard(pos_x: int, pos_y: int) -> str:
    """Выбор направления при выходе из города (патч 17, п.2): только
    направления, остающиеся в пределах сетки (из угловых городов — ровно 2)."""
    kb = Keyboard(inline=True)
    for arrow, (dx, dy) in _DIRECTION_DELTAS.items():
        nx, ny = pos_x + dx, pos_y + dy
        if not grid.in_bounds(nx, ny):
            continue
        kb.add(Text(arrow, payload={"type": "gate_dir", "dx": dx, "dy": dy}), color=KeyboardButtonColor.SECONDARY)
        kb.row()
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
