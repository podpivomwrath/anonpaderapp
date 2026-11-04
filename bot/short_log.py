"""Короткий боевой лог (2026-10-22, просьба владельца).

Переключатель в мини-аппе (Персонаж -> Герой, «Настройки»). Кто его включил,
тому лог хода приходит коротко: полоски здоровья с изменением за ход и значки
эффектов (game/combat/battle_log.render_short). В боевой клавиатуре тогда есть
кнопка «📜 Сводка»: бот правит последний лог в полный, кнопка становится
«📜 Скрыть» и сворачивает его обратно.

У VK к сообщению крепится одна клавиатура, а лог текущего хода несёт боевую
(КД навыков, арена) - поэтому его кнопка в нижней клавиатуре. Когда приходит
следующий ход, прошлый лог получает свою кнопку под сообщением (callback,
нажатие ничего не пишет в чат): так любой ход боя сворачивается и
разворачивается в любой момент (2026-11-05, владелец; проверено вживую - нижняя
клавиатура при этой правке не сбрасывается).

Настройка - в ui_flags персонажа (ключ short_log), здесь копия в памяти по
vk_id, как у bot/no_images.py. Логи боя - тоже в памяти и только на один бой:
начался новый бой или бой кончился - кнопки старых логов отвечают, что бой
уже окончен, и снимаются.
"""

import asyncio
import json
from dataclasses import dataclass

from loguru import logger
from sqlalchemy import select
from vkbottle import KeyboardButtonColor

BTN_OPEN = "📜 Сводка"
BTN_HIDE = "📜 Скрыть"
PAYLOAD_TYPE = "log_toggle"
#: Кнопка под прошлым логом: {"type": CALLBACK_TYPE, "m": id сообщения}.
CALLBACK_TYPE = "log_cb"
BTN_INLINE_OPEN = "📜 Подробнее"
BTN_INLINE_HIDE = "📜 Свернуть"
NOTHING_TEXT = "Лога этого хода уже нет: сводка доступна для последнего хода боя."
ENDED_TEXT = "Бой окончен - этот лог уже не разворачивается."
#: Через сколько секунд после нового лога вешать кнопку на прошлый (0 - сразу, в тестах).
ATTACH_DELAY = 1.2

_short: set[int] = set()


@dataclass
class LastLog:
    message_id: int
    short: str
    full: str
    keyboard: str | None
    expanded: bool = False


@dataclass
class BattleLogs:
    #: Чей бой: ключ объекта боя (battle_key) - новый бой начинает список заново.
    key: int | None
    logs: list[LastLog]


_battles: dict[int, BattleLogs] = {}
_next_key = 0


def battle_key(battle) -> int | None:
    """Свой номер у каждого объекта боя: id сессии соло-боя повторяется у
    одного игрока из боя в бой, а объект состояния - новый."""
    global _next_key
    if battle is None:
        return None
    key = getattr(battle, "_log_key", None)
    if key is None:
        _next_key += 1
        key = _next_key
        try:
            battle._log_key = key
        except AttributeError:
            return None
    return key


def _last_of(peer_id: int) -> LastLog | None:
    entry = _battles.get(int(peer_id))
    return entry.logs[-1] if entry and entry.logs else None


def inline_keyboard(message_id: int, expanded: bool) -> str:
    return json.dumps({"inline": True, "buttons": [[{
        "action": {"type": "callback", "label": BTN_INLINE_HIDE if expanded else BTN_INLINE_OPEN,
                   "payload": json.dumps({"type": CALLBACK_TYPE, "m": message_id})},
        "color": KeyboardButtonColor.SECONDARY.value,
    }]]}, ensure_ascii=False)


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
        _battles.pop(int(vk_id), None)


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


async def send(api, peer_id: int, short: str, full: str, keyboard: str | None = None, battle=None) -> None:
    """Лог хода: короткий или полный - по настройке игрока. battle - объект
    боя (состояние соло-боя, групповой бой, PvP, рейд): по нему логи одного
    боя отличаются от прошлого."""
    peer = int(peer_id)
    if not is_short(peer):
        _battles.pop(peer, None)
        await api.messages.send(peer_id=peer, message=full, random_id=0, keyboard=keyboard)
        return
    key = battle_key(battle)
    entry = _battles.get(peer)
    if entry is None or entry.key != key:
        entry = _battles[peer] = BattleLogs(key, [])
    kb = with_toggle(keyboard)
    message_id = await api.messages.send(peer_id=peer, message=short, random_id=0, keyboard=kb)
    previous = entry.logs[-1] if entry.logs else None
    if isinstance(message_id, int) and message_id > 0:
        entry.logs.append(LastLog(message_id, short, full, keyboard))
    # Прошлый лог - кнопкой под сообщением. Правим после отправки нового: его
    # боевая клавиатура уже внизу и правкой не сбрасывается.
    if previous is not None:
        if ATTACH_DELAY:
            from bot import background

            background.spawn(_attach(api, peer, previous), name="short_log_attach")
        else:
            await _attach(api, peer, previous)


async def _attach(api, peer: int, log: LastLog) -> None:
    """Повесить кнопку на прошлый лог. Не сразу: правка в ту же секунду, что и
    новый лог, упиралась в ограничение частоты VK (ошибка 9) - кнопки не
    появлялись (2026-11-05, репорт). При 9 - ещё одна попытка."""
    for attempt in range(2):
        await asyncio.sleep(ATTACH_DELAY * (attempt + 1))
        try:
            await api.messages.edit(
                peer_id=peer, message_id=log.message_id,
                message=log.full if log.expanded else log.short,
                keyboard=inline_keyboard(log.message_id, log.expanded),
            )
            return
        except Exception as exc:  # noqa: BLE001 - лог уже удалён игроком; бой идёт дальше
            if getattr(exc, "code", None) == 9 and attempt == 0:
                continue
            logger.warning("Короткий лог: не удалось повесить кнопку на {} у {}: {}", log.message_id, peer, exc)
            return


async def toggle_inline(api, peer_id: int, message_id: int, in_battle: bool) -> str | None:
    """Кнопка под прошлым логом. None - развернули или свернули; иначе текст
    для всплывающей подсказки (бой окончен, лога нет), а кнопка снимается."""
    peer = int(peer_id)
    entry = _battles.get(peer)
    log = next((x for x in entry.logs if x.message_id == message_id), None) if entry else None
    if log is None or not in_battle:
        if entry is not None and not in_battle:
            _battles.pop(peer, None)
        if log is not None:
            # Кнопку снимаем, текст оставляем каким был.
            try:
                await api.messages.edit(
                    peer_id=peer, message_id=message_id,
                    message=log.full if log.expanded else log.short,
                    keyboard=json.dumps({"inline": True, "buttons": []}),
                )
            except Exception:  # noqa: BLE001 - снять кнопку не вышло - не страшно
                logger.warning("Короткий лог: не удалось снять кнопку {} у {}", message_id, peer)
        return ENDED_TEXT if not in_battle else NOTHING_TEXT
    log.expanded = not log.expanded
    try:
        await api.messages.edit(
            peer_id=peer, message_id=message_id,
            message=log.full if log.expanded else log.short,
            keyboard=inline_keyboard(message_id, log.expanded),
        )
    except Exception:  # noqa: BLE001 - сообщение удалено
        log.expanded = not log.expanded
        return NOTHING_TEXT
    return None


async def toggle(api, peer_id: int) -> bool:
    """Нажатие «📜 Сводка» / «📜 Скрыть»: правит последний лог. False -
    править нечего (бот перезапускался или лог уже полный по настройке)."""
    last = _last_of(peer_id)
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
