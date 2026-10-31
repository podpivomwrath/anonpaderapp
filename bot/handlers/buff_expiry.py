"""Сообщение о конце баффов со сроком (репорт 262, 2026-10-31): еда,
прикормка, молитва, настойка пепла. Эффекты событий, которые считаются
боями, пишут «прошло» в итоге боя (scene_event_service.finish_fight_effects).
"""

from datetime import datetime, timezone

from loguru import logger

from services.db import get_session_factory
from services import buffs_service
from services import onboarding_service as onboarding_svc

TICK_SECONDS = 60

_bot_api = None
#: Граница прошлой проверки. После рестарта - с момента запуска: баффы,
#: кончившиеся, пока бот лежал, молча пропускаются.
_since: datetime | None = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def tick_job() -> None:
    global _since
    if _bot_api is None:
        return
    now = datetime.now(timezone.utc)
    if _since is None:
        _since = now
        return
    sends = []
    try:
        async with get_session_factory()() as db:
            for character_id, lines in await buffs_service.expired(db, _since, now):
                peer = await onboarding_svc.vk_id_for_character(db, character_id)
                if peer is not None:
                    sends.append((peer, "\n".join(lines)))
    except Exception:
        logger.exception("Баффы: проверка окончания не прошла")
        return
    _since = now
    for peer, text in sends:
        try:
            await _bot_api.messages.send(peer_id=peer, random_id=0, message=text)
        except Exception:
            logger.warning("Баффы: сообщение не доставлено {}", peer)
