"""Клавиатуры мира: меню города, перемещение, бой.

Перемещение — маленькие стрелки в компас-раскладке (⬆️/⬅️➡️/⬇️),
БЕЗ подписей сторон света (С/Ю/З/В) — так попросил пользователь.

Боевые кнопки навыков несут payload {"type":"skill","id":...}: подпись меняется
со счётчиком КД, а матчинг идёт по payload и не ломается.
"""

from vkbottle import Keyboard, KeyboardButtonColor, OpenLink, Text

from bot import ash_handful_state
from bot.onboarding_texts import REGION_TITLES
from config import get_settings
from game.combat import balance_config as bc
from game.combat.base_skills import skills_for_character
from game.content_loader import ExplorationEventDef
from game.world import grid

BTN_MENTOR = "🧙 Наставник"
BTN_MENTOR_BADGE = f"{BTN_MENTOR} ❗"  # патч 21: есть что взять/сдать у наставника
BTN_MARKET = "🏬 Рынок"  # патч 39: 🏬 — отличать от 🏪 «Торговый квартал» (сам квартал)
BTN_APPRAISER = "💰 Скупщик"
BTN_GATE = "🚪 За ворота"
BTN_REST = "🛏️ Отдых"
BTN_CHARACTER = "🎭 Персонаж"
BTN_INVENTORY = "🎒 Инвентарь"
BTN_STATS = "📊 Характеристики"
BTN_KEEPER = "📖 Хранитель Списков"
BTN_PRESETS = "⚔️ Пресеты"
BTN_ELIXIR_SHOP = "⚗️ Лавка зелий"
BTN_DAILIES = "📜 Задания"
# Патч 39: кварталы города — см. city_square_keyboard/tavern_keyboard/
# market_quarter_keyboard ниже.
BTN_TAVERN = "🍺 Таверна"
BTN_MARKET_QUARTER = "🏪 Торговый квартал"
BTN_SQUARE_BACK = "← Главная площадь"


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
BTN_ASH_HANDFUL = "🌫 Горстка пепла"  # патч 25, п.4: одноразовая находка
BTN_MOUNT = "🐎 Маунт"  # патч 25, п.7

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


def city_square_keyboard(
    character=None, mentor_badge: bool = False, has_mount: bool = False, is_foreign: bool = False,
) -> str:
    """Патч 39: Главная площадь — корневой городской экран, куда игрок
    попадает при входе в город и при возрождении. Заменил монолитный
    city_menu_keyboard (10+ кнопок, часть не помещалась в лимит VK) —
    Таверна/Торговый квартал теперь СВОИ экраны (см. tavern_keyboard/
    market_quarter_keyboard), сюда попадает только то, что относится к
    самой площади: NPC-наставник, транспорт, выход, входы в кварталы.

    is_foreign (патч 26/39) — чужой город: Наставник и Таверна целиком
    недоступны (только Торговый квартал со скупщиком, с наценкой) — попытка
    зайти в Таверну извне отбивается отдельным отказом (bot/handlers/world.py)."""
    kb = Keyboard(one_time=False)
    if not is_foreign:
        kb.add(Text(BTN_MENTOR_BADGE if mentor_badge else BTN_MENTOR), color=KeyboardButtonColor.PRIMARY)
        kb.row()
    if has_mount:
        kb.add(Text(BTN_MOUNT), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    kb.add(Text(BTN_GATE), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    if not is_foreign:
        kb.add(Text(BTN_TAVERN), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_MARKET_QUARTER), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


def tavern_keyboard(character=None) -> str:
    """Патч 39: Таверна — личные меню (отдых/статы/задания) + условные
    (Хранитель Списков с 30 уровня, Пресеты после выбора подкласса — кнопки
    НЕ показываются вовсе, если недоступны, не серые). Только в родном
    городе — недоступна в чужом (см. city_square_keyboard)."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_REST), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_STATS), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_DAILIES), color=KeyboardButtonColor.SECONDARY)
    if character is not None and character.level >= bc.SUBCLASS_UNLOCK_MIN_LEVEL:
        kb.row()
        kb.add(Text(BTN_KEEPER), color=KeyboardButtonColor.SECONDARY)
    if character is not None and character.subclass is not None:
        kb.row()
        kb.add(Text(BTN_PRESETS), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_SQUARE_BACK), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def market_quarter_keyboard(is_foreign: bool = False) -> str:
    """Патч 39: Торговый квартал — Скупщик доступен ВСЕГДА (в чужом городе —
    с наценкой, см. bot/handlers/appraiser.py), Лавка зелий и Рынок — NPC,
    недоступны чужаку (та же логика, что была у city_menu_keyboard); Инвентарь
    — личное имущество, доступно всегда."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_APPRAISER), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    if not is_foreign:
        kb.add(Text(BTN_ELIXIR_SHOP), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    kb.add(Text(BTN_INVENTORY), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    if not is_foreign:
        kb.add(Text(BTN_MARKET), color=KeyboardButtonColor.SECONDARY)
        kb.row()
    add_miniapp_button(kb)
    kb.row()
    kb.add(Text(BTN_SQUARE_BACK), color=KeyboardButtonColor.SECONDARY)
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


def _direction_label(x: int, y: int, dx: int, dy: int, arrow: str) -> str:
    """Подпись кнопки направления от (x;y): название города — если соседняя
    клетка В ГРАНИЦАХ карты и ведёт в город, иначе обычная стрелка.

    Патч 31, п.7: кнопка направления, ведущего за границу сетки (-50..50),
    больше НЕ скрывается (раньше это дёргало раскладку — кнопки прыгали по
    позициям) — за границей просто остаётся обычная стрелка; сам запрет
    движения проверяется отдельно в bot/handlers/world.py::move по факту
    нажатия, лорным отказом, а не убранной кнопкой."""
    nx, ny = x + dx, y + dy
    if not grid.in_bounds(nx, ny):
        return arrow
    region = grid.city_region_at(nx, ny)
    return REGION_TITLES[region] if region is not None else arrow


def resolve_direction(x: int, y: int, text: str) -> tuple[int, int] | None:
    """Обратный маппинг: текст нажатой кнопки → (dx;dy) для позиции (x;y).
    None — кнопка больше не соответствует текущей позиции (устаревшая
    клавиатура, например была нажата подпись города, из которого игрок уже
    ушёл). Направление за границей карты теперь резолвится как обычно —
    легальность самого хода проверяет вызывающий (grid.in_bounds)."""
    for arrow, (dx, dy) in _DIRECTION_DELTAS.items():
        if _direction_label(x, y, dx, dy, arrow) == text:
            return dx, dy
    return None


def movement_keyboard(
    pos_x: int, pos_y: int, peer_id: int | None = None, has_mount: bool = False,
) -> str:
    """Карта (патч 25, п.1: компактная раскладка): крест перемещения с
    Исследовать в центре, часто используемые Отдых/Осмотреться сразу под
    ним, редкие/условные (Горстка пепла/Маунт) — отдельными рядами только
    когда актуальны, справочное (мини-апп) — внизу отдельно. Вход в город —
    автоматически при прибытии.

    Патч 17: направления за пределами сетки (-50..50) не показываются;
    направление, ведущее на клетку города, подписывается названием города
    вместо стрелки, компоновка перестраивается под доступные направления.

    peer_id (патч 25, п.4) — если задан и для игрока есть несобранная
    горстка пепла, добавляет её кнопку. has_mount (патч 25, п.7) — есть хотя
    бы один маунт, показывает кнопку выбора.

    Патч 31, п.7: все 4 направления теперь ВСЕГДА на месте (раньше кнопка,
    ведущая за границу карты, убиралась целиком — раскладка «прыгала», игрок
    промахивался мимо съехавших кнопок)."""
    up = _direction_label(pos_x, pos_y, *_DIRECTION_DELTAS[BTN_UP], BTN_UP)
    down = _direction_label(pos_x, pos_y, *_DIRECTION_DELTAS[BTN_DOWN], BTN_DOWN)
    left = _direction_label(pos_x, pos_y, *_DIRECTION_DELTAS[BTN_LEFT], BTN_LEFT)
    right = _direction_label(pos_x, pos_y, *_DIRECTION_DELTAS[BTN_RIGHT], BTN_RIGHT)

    kb = Keyboard(one_time=False)
    kb.add(Text(up), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(left), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_EXPLORE), color=KeyboardButtonColor.POSITIVE)
    kb.add(Text(right), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(down), color=KeyboardButtonColor.SECONDARY)
    kb.row()
    kb.add(Text(BTN_REST), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_LOOK_AROUND), color=KeyboardButtonColor.SECONDARY)
    if has_mount:
        kb.row()
        kb.add(Text(BTN_MOUNT), color=KeyboardButtonColor.SECONDARY)
    if peer_id is not None and ash_handful_state.is_pending(peer_id):
        kb.row()
        kb.add(Text(BTN_ASH_HANDFUL), color=KeyboardButtonColor.SECONDARY)
    add_miniapp_button(kb)
    return kb.get_json()


BTN_CONTINUE_TRAVEL = "🐎 Продолжить путь"  # патч 25, п.7


def continue_travel_keyboard(travel_id: int) -> str:
    """Кнопка продолжения пути после победы над нападением (патч 25, п.7)."""
    kb = Keyboard(inline=True)
    kb.add(
        Text(BTN_CONTINUE_TRAVEL, payload={"type": "continue_travel", "travel": travel_id}),
        color=KeyboardButtonColor.POSITIVE,
    )
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


BTN_READ_SONG = "📜 Прочесть Пепельную Песнь"  # патч 25, п.6


def event_choice_keyboard(event: ExplorationEventDef, song_extra: bool = False) -> str:
    """Кнопки события исследования (патч 9, блок 1): payload несёт id события +
    индекс выбора, чтобы устаревшие нажатия после уже разрешённого события
    отличались и игнорировались хендлером.

    song_extra (патч 25, п.6) — у Пепельного алтаря, если Песнь собрана
    полностью и ещё не прочитана, добавляет доп. кнопку с ОТДЕЛЬНЫМ типом
    payload (не event_choice) — прочтение не участвует в обычном ролле исходов."""
    kb = Keyboard(one_time=False)
    for idx, choice in enumerate(event.choices):
        kb.add(Text(choice.label, payload={"type": "event_choice", "event": event.id, "choice": idx}))
        kb.row()
    if song_extra:
        kb.add(Text(BTN_READ_SONG, payload={"type": "read_song"}))
        kb.row()
    add_miniapp_button(kb)
    return kb.get_json()


def combat_keyboard(base_class: str, cooldowns: dict[str, int], subclass_id: str | None = None) -> str:
    """Боевая клавиатура: Атака + навыки класса/подкласса (с КД-счётчиком) + Предмет + Побег.
    Навык на КД показывается с остатком, но остаётся нажимаемым — обработчик ответит
    «не готов» без траты хода. subclass_id (патч 39, ч.3) — после выбора подкласса
    навыки класса ЗАМЕНЯЮТСЯ навыками подкласса."""
    kb = Keyboard(one_time=False)
    kb.add(Text(BTN_ATTACK), color=KeyboardButtonColor.POSITIVE)
    kb.row()
    for skill in skills_for_character(base_class, subclass_id):
        cd = cooldowns.get(skill.id, 0)
        label = skill.name if cd <= 0 else f"{skill.name} (КД {cd})"
        color = KeyboardButtonColor.PRIMARY if cd <= 0 else KeyboardButtonColor.SECONDARY
        kb.add(Text(label, payload={"type": "skill", "id": skill.id}), color=color)
        kb.row()
    kb.add(Text(BTN_ITEM), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(BTN_FLEE), color=KeyboardButtonColor.NEGATIVE)
    return kb.get_json()
