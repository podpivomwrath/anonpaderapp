"""Ставки PvP (п.4 дизайна).

Победители забирают долю farm-валюты проигравших (PVP_STAKE_PERCENT).
При ничьей обмена ресурсами нет — сервис просто не вызывается.
"""

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from models import PvpStakeTransfer, Wallet
from services.wallet_service import charge, deposit


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
        # Кошелёк проигравшего под блокировкой (патч 96): ставка - доля от
        # ТЕКУЩЕГО баланса, и прочитать его надо так, чтобы до списания его
        # никто не поменял. Раньше баланс читался в питон и записывался
        # обратно целым числом - продажа, совпавшая с концом дуэли, молча
        # пропадала: её прибавку перезаписывало старое значение.
        loser_wallet = await db.scalar(
            select(Wallet).where(Wallet.character_id == loser_id)
            .with_for_update().execution_options(populate_existing=True)
        )
        if loser_wallet is None:
            continue
        stake = int(loser_wallet.farm_currency * bc.PVP_STAKE_PERCENT)
        if stake <= 0:
            continue
        await charge(db, loser_id, "farm", stake)

        share = stake // len(winner_character_ids)
        remainder = stake - share * len(winner_character_ids)
        for i, winner_id in enumerate(winner_character_ids):
            portion = share + (remainder if i == 0 else 0)
            if portion <= 0:
                continue
            await deposit(db, winner_id, "farm", portion)
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
