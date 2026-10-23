"""Строка в чат, когда из мини-аппа съели, выпили или рассыпали что-то с
баффом (2026-10-23, владелец): «использовал - получил бафф». Сообщение без
клавиатуры - экран чата не трогает.
"""

from loguru import logger

from bot import background
from services import buffs_service


def line(character, buff_id: str, verb: str) -> str | None:
    """«🍲 Уха - съедено: +10% здоровье, ещё 40 мин.»; None - баффа нет."""
    from datetime import datetime, timezone

    found = next((b for b in buffs_service.timed(character) if b["id"] == buff_id), None)
    if found is None:
        return None
    until = datetime.fromisoformat(found["until"])
    minutes = max(1, round((until - datetime.now(timezone.utc)).total_seconds() / 60))
    left = f"{minutes // 60} ч {minutes % 60} мин" if minutes >= 120 else f"{minutes} мин"
    return f"{found['emoji']} {found['name']} - {verb}: {found['value']}, ещё {left}."


async def _send(peer_id: int, text: str) -> None:
    from bot.handlers import house

    if house._bot_api is None:
        return
    try:
        await house._bot_api.messages.send(peer_id=peer_id, message=text, random_id=0)
    except Exception:  # noqa: BLE001 - бафф уже получен, строка в чат - только отчёт
        logger.warning("Бафф: не удалось написать в чат {}", peer_id)


def tell(peer_id: int, text: str | None) -> None:
    """Отправить после ответа мини-аппу, не задерживая его."""
    if text:
        background.spawn(_send(peer_id, text))
