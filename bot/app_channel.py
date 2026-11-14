"""Канал приложения «Монолит» (2026-11-15, владелец: «бот должен молчать,
работать только в одном месте»).

Пока у игрока открыто приложение (живой WebSocket /api/app/ws), всё, что бот
отправил бы ему в ВК, уходит в приложение, а в ВК - ничего. Перехват - в
общей обёртке отправки (bot/silent_guard.py): messages.send/edit/delete к
такому игроку не идут в VK, а превращаются в события канала. Номер сообщения
- свой (fake_id: в нём же зашит игрок, messages.delete приходит без адресата),
поэтому код, который потом правит или удаляет окно (editable_message,
отсчёты), работает как с ВК. В приложение номер уходит строкой: JSON в Godot
читает большие числа с потерей точности.

Нажатия в приложении - те же кнопки бота: POST /api/miniapp/app/act
собирает событие message_new и пускает его в общий роутер (bot/app_api.py),
так что логика одна для чата и приложения.

Одно место: игрок написал боту в ВК при открытом приложении - канал
закрывается (событие moved), и бот дальше отвечает в ВК. Своё нажатие
приложения отличается номером сообщения 0 (у настоящих из ВК он больше 0).
"""

import itertools
import json
import time

from loguru import logger

#: vk_id -> открытые сокеты приложения (обычно один).
_sockets: dict[int, set] = {}
#: Номера «сообщений» приложения: FAKE_FLAG + (счётчик << 34) + vk_id. Выше
#: любых номеров ВК, игрок читается из номера (owner_of).
FAKE_FLAG = 1 << 62
_VK_MASK = (1 << 34) - 1
_ids = itertools.count(1)
#: id персонажа -> vk_id, пока его приложение открыто: бой узнаёт игрока по
#: бойцу (bot/app_battle.py).
_characters: dict[int, int] = {}


def active(vk_id) -> bool:
    try:
        return bool(_sockets.get(int(vk_id)))
    except (TypeError, ValueError):
        return False


def anyone() -> bool:
    return bool(_sockets)


def vk_of_character(character_id) -> int | None:
    return _characters.get(character_id)


def attach(vk_id: int, ws, character_id: int | None = None) -> None:
    _sockets.setdefault(int(vk_id), set()).add(ws)
    if character_id is not None:
        _characters[int(character_id)] = int(vk_id)
    logger.info("Приложение: канал открыт для {} (сокетов {})", vk_id, len(_sockets[int(vk_id)]))


def detach(vk_id: int, ws) -> None:
    group = _sockets.get(int(vk_id))
    if group is None:
        return
    group.discard(ws)
    if not group:
        _sockets.pop(int(vk_id), None)
        for cid in [c for c, v in _characters.items() if v == int(vk_id)]:
            _characters.pop(cid, None)
        logger.info("Приложение: канал закрыт для {} - бот снова пишет в ВК", vk_id)


def fake_id(vk_id: int) -> int:
    return FAKE_FLAG + (next(_ids) << 34) + (int(vk_id) & _VK_MASK)


def is_fake(message_id) -> bool:
    try:
        return int(message_id) >= FAKE_FLAG
    except (TypeError, ValueError):
        return False


def owner_of(message_id) -> int:
    return int(message_id) & _VK_MASK


async def publish(vk_id: int, event: dict) -> None:
    """Отправить событие во все сокеты игрока; мёртвый сокет снимается."""
    event = {**event, "at": time.time()}
    for ws in list(_sockets.get(int(vk_id), ())):
        try:
            await ws.send_json(event)
        except Exception:  # noqa: BLE001 - сокет закрылся между проверкой и отправкой
            detach(vk_id, ws)


async def moved_to_vk(vk_id: int) -> None:
    """Игрок пишет в ВК - приложение отпускает его (одно место игры)."""
    group = list(_sockets.get(int(vk_id), ()))
    if not group:
        return
    await publish(vk_id, {"type": "moved", "to": "vk"})
    for ws in group:
        detach(vk_id, ws)
        try:
            await ws.close()
        except Exception:  # noqa: BLE001, S110 - уже закрыт
            pass


# --- Разбор того, что бот отправил бы в ВК ---------------------------------------


def parse_keyboard(raw) -> dict | None:
    """JSON клавиатуры ВК -> {inline, rows: [[{label, payload, color, type, link}]]}."""
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return None
    rows = []
    for row in data.get("buttons") or []:
        out = []
        for button in row:
            action = button.get("action") or {}
            payload = action.get("payload")
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except ValueError:
                    pass
            out.append({
                "label": action.get("label") or "", "type": action.get("type") or "text",
                "payload": payload, "color": button.get("color"), "link": action.get("link"),
            })
        if out:
            rows.append(out)
    return {"inline": bool(data.get("inline")), "rows": rows}


def attachments(raw) -> list[str]:
    if not raw:
        return []
    return [a.strip() for a in str(raw).split(",") if a.strip()]


def message_event(data: dict, message_id: int) -> dict:
    return {
        "type": "message", "id": str(message_id), "text": data.get("message") or "",
        "keyboard": parse_keyboard(data.get("keyboard")), "attachments": attachments(data.get("attachment")),
    }


def edit_event(data: dict) -> dict:
    return {
        "type": "edit", "id": str(data.get("message_id") or ""), "text": data.get("message") or "",
        "keyboard": parse_keyboard(data.get("keyboard")), "attachments": attachments(data.get("attachment")),
    }


def delete_event(data: dict) -> dict:
    raw = data.get("message_ids")
    ids = raw if isinstance(raw, (list, tuple)) else str(raw or "").split(",")
    return {"type": "delete", "ids": [str(i).strip() for i in ids if str(i).strip().isdecimal()]}
