"""«Убрать картинки в игре» (2026-10-22, просьба владельца).

Переключатель в мини-аппе (Персонаж -> Герой, внизу). Кто его включил, тому
бот шлёт сообщения без картинок: фото вырезаются из attachment прямо в общей
обёртке отправки (bot/silent_guard.install), так что ни один из ~90 вызовов
с картинкой править не нужно. Остальные вложения (документы, аудио) не
трогаем. Если в сообщении кроме картинки ничего нет, оно уходит как есть:
пустое сообщение VK не примет.

Настройка хранится в ui_flags персонажа (ключ no_images), здесь - копия в
памяти по vk_id для быстрой проверки на каждой отправке. Бот и API мини-аппа
живут в одном процессе, поэтому переключатель действует сразу.
"""

from loguru import logger
from sqlalchemy import select

_muted: set[int] = set()


async def load(session_factory) -> int:
    """Прочитать при старте, у кого картинки выключены."""
    from models import Character, User

    async with session_factory() as db:
        rows = (await db.execute(
            select(User.vk_id, Character.ui_flags).join(Character, Character.user_id == User.id)
        )).all()
    _muted.clear()
    _muted.update(int(vk_id) for vk_id, flags in rows if isinstance(flags, dict) and flags.get("no_images"))
    return len(_muted)


def set_muted(vk_id: int, on: bool) -> None:
    if on:
        _muted.add(int(vk_id))
    else:
        _muted.discard(int(vk_id))


def is_muted(vk_id: int) -> bool:
    return int(vk_id) in _muted


def peers_of(data: dict) -> list[int]:
    """Кому уходит сообщение. vkbottle шлёт по-разному: api.messages.send -
    peer_id числом, message.answer - peer_ids СПИСКОМ ([id]), рассылки -
    строкой «1,2,3». Раньше список не разбирался, и ответы через
    message.answer (статус клетки и почти всё остальное) уходили с картинкой
    (2026-10-22, жалоба: после отмены перехода картинка пришла)."""
    out: list[int] = []
    raw = [data.get("peer_id")]
    many = data.get("peer_ids")
    if isinstance(many, (list, tuple, set)):
        raw += list(many)
    elif many is not None:
        raw += str(many).split(",")
    for p in raw:
        if p is None:
            continue
        text = str(p).strip()
        if text.lstrip("-").isdigit():
            out.append(int(text))
    return out


def strip(method: str, data: dict) -> dict:
    """Убрать фото из messages.send / messages.edit тому, кто их выключил.
    Возвращает те же данные или копию без фото."""
    if not _muted or method not in ("messages.send", "messages.edit"):
        return data
    attachment = data.get("attachment")
    if not attachment:
        return data
    peers = peers_of(data)
    if not peers or not all(p in _muted for p in peers):
        return data
    if isinstance(attachment, (list, tuple)):
        parts = [str(a) for a in attachment if str(a).strip()]
    else:
        parts = [a for a in str(attachment).split(",") if a.strip()]
    kept = [a for a in parts if not a.strip().startswith("photo")]
    if len(kept) == len(parts):
        return data
    if not kept and not data.get("message"):
        return data  # без картинки сообщение пустое - VK его не примет
    out = dict(data)
    out["attachment"] = ",".join(kept)
    logger.debug("no_images: без картинки для {}", peers)
    return out
