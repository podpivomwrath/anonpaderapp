"""Страховка от «немых» кнопок (2026-10-13).

Игрок жмёт кнопку, а бот молчит: обработчик сработал и тихо вышел (инвентарь
вне города, старая клавиатура после рестарта, кнопка не по состоянию). Таких
выходов десятки, и каждый по отдельности не закрыть. Здесь - общая сеть:
если на сообщение в личке бот за GRACE_SECONDS ничего не отправил этому
игроку, он получает свежую клавиатуру под текущее состояние.

Как узнаём, что бот ответил: обёртка над api.request отмечает время каждого
messages.send/messages.edit по peer_id. Отложенные ответы (исследование,
планировщики) тоже идут через неё.

Бой не трогаем: там повторное нажатие в том же ходу молчит нарочно.
"""

import asyncio
import time

from loguru import logger
from vkbottle import BaseMiddleware
from vkbottle.bot import Message

GRACE_SECONDS = 2.5
STALE_TEXT = "Кнопки обновлены."

_last_out: dict[int, float] = {}
_api = None


def install(api) -> None:
    """Обернуть api.request один раз при старте (main.create_bot)."""
    global _api
    _api = api
    original = api.request

    async def request(method, data, version=None):
        if method in ("messages.send", "messages.edit"):
            now = time.monotonic()
            peer = data.get("peer_id")
            if peer is not None:
                _last_out[int(peer)] = now
            for p in str(data.get("peer_ids") or "").split(","):
                if p.strip().lstrip("-").isdigit():
                    _last_out[int(p)] = now
        return await original(method, data, version)

    api.request = request


def answered_since(peer_id: int, since: float) -> bool:
    return _last_out.get(peer_id, 0.0) >= since


async def _check_later(peer_id: int, from_id: int, started: float) -> None:
    await asyncio.sleep(GRACE_SECONDS)
    if answered_since(peer_id, started) or _api is None:
        return
    from bot.battle_keyboard import active_battle_keyboard
    from bot.handlers import world as world_handlers
    from datetime import datetime, timezone

    from services.db import get_session_factory
    from services.onboarding_service import get_character

    if active_battle_keyboard(peer_id) is not None:
        return
    logger.info(
        "Страховка кнопок: {} без ответа (начало {:.2f}, последний ответ {:.2f}, сейчас {:.2f})",
        peer_id, started, _last_out.get(peer_id, 0.0), time.monotonic(),
    )
    try:
        async with get_session_factory()() as db:
            character = await get_character(db, from_id)
            if character is None or character.creation_state is not None:
                return
            keyboard = await world_handlers._current_keyboard(db, character, peer_id, datetime.now(timezone.utc))
        await _api.messages.send(peer_id=peer_id, random_id=0, message=STALE_TEXT, keyboard=keyboard)
    except Exception:  # noqa: BLE001 - страховка не должна ронять ничего
        logger.exception("Страховка кнопок: не удалось ответить {}", peer_id)


class SilentGuardMiddleware(BaseMiddleware[Message]):
    async def pre(self) -> None:
        self._started = time.monotonic()

    async def post(self) -> None:
        event = self.event
        # Только личный диалог с игроком: в беседах бот молчит на чужие реплики.
        if event.from_id <= 0 or event.peer_id != event.from_id:
            return
        asyncio.get_running_loop().create_task(
            _check_later(event.peer_id, event.from_id, getattr(self, "_started", time.monotonic()))
        )


def setup_middleware(bot) -> None:
    bot.labeler.message_view.register_middleware(SilentGuardMiddleware)
