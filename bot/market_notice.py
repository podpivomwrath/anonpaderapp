"""Строки о рынке в чат (2026-10-23): продано, куплено, снято по сроку.

Сервис возвращает список Notice (кому и что), а сюда их отдают после
коммита - отправка не держит транзакцию и не задерживает ответ мини-аппу.
"""

from loguru import logger

from bot import background


async def _send(notices) -> None:
    from bot.handlers import house
    from services import onboarding_service
    from services.db import get_session_factory

    if house._bot_api is None or not notices:
        return
    async with get_session_factory()() as db:
        peers = {n.character_id: await onboarding_service.vk_id_for_character(db, n.character_id) for n in notices}
    for n in notices:
        peer = peers.get(n.character_id)
        if peer is None:
            continue
        try:
            await house._bot_api.messages.send(peer_id=peer, message=n.text, random_id=0)
        except Exception:  # noqa: BLE001 - сделка уже прошла, строка в чат - только отчёт
            logger.warning("Рынок: не удалось написать {}", peer)


def tell(notices) -> None:
    if notices:
        background.spawn(_send(list(notices)))


async def expire_job() -> None:
    """Раз в минуту: заявки, чей срок вышел, снимаются, товар и золото - назад."""
    from services import market_service
    from services.db import get_session_factory

    async with get_session_factory()() as db:
        notices = await market_service.expire_due(db)
        await db.commit()
    tell(notices)
