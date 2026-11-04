"""Короткий боевой лог (2026-10-22, просьба владельца).

Переключатель в мини-аппе (Персонаж -> Герой, «Настройки»). Кто его включил,
тому лог хода приходит коротко: полоски здоровья с изменением за ход и значки
эффектов (game/combat/battle_log.render_short). В боевой клавиатуре тогда есть
кнопка «📜 Сводка»: бот правит последний лог в полный, кнопка становится
«📜 Скрыть» и сворачивает его обратно.

Кнопка - в нижней клавиатуре, а не под сообщением: у VK к сообщению крепится
одна клавиатура, а лог несёт боевую (КД навыков, арена), и она должна
обновляться каждый ход (решение владельца).

Настройка - в ui_flags персонажа (ключ short_log), здесь копия в памяти по
vk_id, как у bot/no_images.py. Последний лог каждого игрока - тоже в памяти:
после перезапуска кнопка просто ничего не найдёт и ответит об этом.
"""

import json
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select
from vkbottle import KeyboardButtonColor

BTN_OPEN = "📜 Сводка"
BTN_HIDE = "📜 Скрыть"
PAYLOAD_TYPE = "log_toggle"
NOTHING_TEXT = "Лога этого хода уже нет: сводка доступна для последнего хода боя."

_short: set[int] = set()


@dataclass
class LastLog:
    message_id: int
    short: str
    full: str
    keyboard: str | None
    expanded: bool = False


_last: dict[int, LastLog] = {}


async def load(session_factory) -> int:
    """Прочитать при старте, у кого включён короткий лог."""
    from models import Character, User

    async with session_factory() as db:
        rows = (await db.execute(
            select(User.vk_id, Character.ui_flags).join(Character, Character.user_id == User.id)
        )).all()
    _short.clear()
    _short.update(int(vk_id) for vk_id, flags in rows if isinstance(flags, dict) and flags.get("short_log"))
    return len(_short)


def set_short(vk_id: int, on: bool) -> None:
    if on:
        _short.add(int(vk_id))
    else:
        _short.discard(int(vk_id))
        _last.pop(int(vk_id), None)


def is_short(vk_id: int) -> bool:
    return int(vk_id) in _short


def with_toggle(keyboard: str | None, expanded: bool = False) -> str | None:
    """Боевая клавиатура с кнопкой «📜 Сводка» («📜 Скрыть») в последнем ряду.
    Инлайн и пустые клавиатуры (ожидание хода) не трогаем: там лог читать
    некогда, а кнопка без боя не нужна."""
    if not keyboard:
        return keyboard
    try:
        data = json.loads(keyboard)
    except ValueError:
        return keyboard
    rows = data.get("buttons") or []
    if data.get("inline") or not rows:
        return keyboard
    button = {
        "action": {"type": "text", "label": BTN_HIDE if expanded else BTN_OPEN,
                   "payload": json.dumps({"type": PAYLOAD_TYPE})},
        "color": KeyboardButtonColor.SECONDARY.value,
    }
    # В последний ряд, если там меньше трёх кнопок, иначе - своим рядом.
    if len(rows[-1]) < 3:
        rows[-1] = [*rows[-1], button]
    else:
        rows.append([button])
    data["buttons"] = rows
    return json.dumps(data, ensure_ascii=False)


async def send(api, peer_id: int, short: str, full: str, keyboard: str | None = None) -> None:
    """Лог хода: короткий или полный - по настройке игрока."""
    if not is_short(peer_id):
        _last.pop(int(peer_id), None)
        await api.messages.send(peer_id=peer_id, message=full, random_id=0, keyboard=keyboard)
        return
    kb = with_toggle(keyboard)
    message_id = await api.messages.send(peer_id=peer_id, message=short, random_id=0, keyboard=kb)
    if isinstance(message_id, int) and message_id > 0:
        _last[int(peer_id)] = LastLog(message_id, short, full, keyboard)
    else:
        _last.pop(int(peer_id), None)


async def toggle(api, peer_id: int) -> bool:
    """Нажатие «📜 Сводка» / «📜 Скрыть»: правит последний лог. False -
    править нечего (бот перезапускался или лог уже полный по настройке)."""
    last = _last.get(int(peer_id))
    if last is None:
        return False
    last.expanded = not last.expanded
    try:
        await api.messages.edit(
            peer_id=peer_id, message_id=last.message_id,
            message=last.full if last.expanded else last.short,
            keyboard=with_toggle(last.keyboard, expanded=last.expanded),
        )
    except Exception:  # noqa: BLE001 - сообщение старше суток или удалено
        logger.warning("Короткий лог: не удалось править сообщение {} у {}", last.message_id, peer_id)
        last.expanded = not last.expanded
        return False
    return True
