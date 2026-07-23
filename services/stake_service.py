"""Ставки PvP (п.4 дизайна).

Победители забирают долю farm-валюты проигравших (PVP_STAKE_PERCENT).
При ничьей обмена ресурсами нет — сервис просто не вызывается.
"""

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from models import PvpStakeTransfer
from services.wallet_service import get_wallet


async def settle_stakes(
    db: AsyncSession,
    session_id: int,
    winner_character_ids: list[int],
    loser_character_ids: list[int],
) -> list[PvpStakeTransfer]:
    """Каждый проигравший отдаёт долю farm-валюты; пул делится между
    победителями поровну (остаток — первому)."""
    if not winner_character_ids or not loser_character_ids:
        return []

    transfers: list[PvpStakeTransfer] = []
    for loser_id in loser_character_ids:
        loser_wallet = await get_wallet(db, loser_id)
        stake = int(loser_wallet.farm_currency * bc.PVP_STAKE_PERCENT)
        if stake <= 0:
            continue
        loser_wallet.farm_currency -= stake

        share = stake // len(winner_character_ids)
        remainder = stake - share * len(winner_character_ids)
        for i, winner_id in enumerate(winner_character_ids):
            portion = share + (remainder if i == 0 else 0)
            if portion <= 0:
                continue
            winner_wallet = await get_wallet(db, winner_id)
            winner_wallet.farm_currency += portion
            transfer = PvpStakeTransfer(
                session_id=session_id,
                loser_character_id=loser_id,
                winner_character_id=winner_id,
                amount=portion,
            )
            db.add(transfer)
            transfers.append(transfer)
        logger.info(
            "PvP-ставка: {} теряет {} золота (сессия {})", loser_id, stake, session_id
        )
    return transfers
