"""Заказы на игроков (2026-10-16): команда /заказ, сгорание заказов и вести.

Создают и берут заказы на «Доске» мини-аппа (bot/miniapp_board_api.py);
здесь - коротко, где цели взятых заказов, и уведомления.
"""

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message

from bot import info_reply
from models import Character, Contract, ContractTaker
from services import contract_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True

_bot_api = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def _left(expires_at: datetime) -> str:
    expires = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    minutes = max(int((expires - datetime.now(timezone.utc)).total_seconds() // 60), 0)
    return f"{minutes // 60} ч {minutes % 60} мин"


@labeler.message(text=["/заказ", "/заказы", "/contract"])
async def contracts_command(message: Message) -> None:
    """Взятые заказы: цель, уровень, где она, сколько убийств и времени осталось."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        now = datetime.now(timezone.utc)
        rows = (await db.execute(
            select(Contract, Character).join(ContractTaker, ContractTaker.contract_id == Contract.id)
            .join(Character, Character.id == Contract.target_id)
            .where(
                ContractTaker.character_id == character.id, Contract.status == "active",
                Contract.kills_left > 0, Contract.expires_at > now,
            ).order_by(Contract.expires_at)
        )).all()
        lines = [
            f"🎯 {target.name} · {target.level} ур. · {contract_service.location_text(target)}\n"
            f"   убийств осталось {contract.kills_left}, 💎{contract.price} за каждое, ещё {_left(contract.expires_at)}"
            for contract, target in rows
        ]
        if await contract_service.is_target(db, character.id, now):
            lines.append("📜 На тебя есть заказ: вне городов охотники видят тебя на карте.")
    if not lines:
        await info_reply.answer(message, "📜 Взятых заказов нет. Заказы - на «Доске» в мини-аппе, вкладка «Заказы».")
        return
    await info_reply.answer(message, "📜 Твои заказы:\n\n" + "\n".join(lines))


async def notify_target(target_id: int, kills: int) -> None:
    """Цели - что на неё заказ (без имени заказчика)."""
    if _bot_api is None:
        return
    async with get_session_factory()() as db:
        peer = await onboarding_svc.vk_id_for_character(db, target_id)
    if peer is None:
        return
    try:
        await _bot_api.messages.send(
            peer_id=peer, random_id=0,
            message=(
                f"📜 На тебя оформлен заказ: убийств - {kills}. Пока он действует (до 20 ч), охотники, "
                "взявшие его, видят тебя на карте, а озёра, рудники и АФК от них не спасают. "
                "Спасение - города, Монолит и клетка мирового босса."
            ),
        )
    except Exception:  # noqa: BLE001 - цель закрыла диалог с ботом
        logger.warning("Заказы: не удалось известить цель {}", target_id)


async def expire_job() -> None:
    """Истёкшие заказы сгорают; цели, на которой заказов больше нет, - весть."""
    try:
        async with get_session_factory()() as db:
            freed = await contract_service.expire(db)
            peers = {cid: await onboarding_svc.vk_id_for_character(db, cid) for cid in freed}
            await db.commit()
    except Exception:
        logger.exception("Заказы: сгорание не прошло")
        return
    if _bot_api is None:
        return
    for peer in peers.values():
        if peer is None:
            continue
        try:
            await _bot_api.messages.send(
                peer_id=peer, random_id=0,
                message="📜 Заказов на тебя больше нет - мирные клетки и АФК снова защищают.",
            )
        except Exception:  # noqa: BLE001
            pass
