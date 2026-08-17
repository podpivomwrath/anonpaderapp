"""Ключ Монолита (патч 45, ч.4) — задел под будущий рейд. Падает независимым
броском 0.5% с ЛЮБОГО источника лута (моб/событие/горстка пепла/ларец),
капается на 2 в инвентаре — сверх капа не выпадает вовсе, без лога (не
дразнить игрока "чуть-чуть не хватило"). Функционала пока нет."""

import random

from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import raid_key_config as rc
from models import Character
from services import premium_service


async def maybe_grant(db: AsyncSession, character: Character, rng: random.Random) -> bool:
    """True — ключ выпал (и уже начислен). Вызывается независимо от прочих
    бросков лута на каждом источнике дропа.

    Патч 50: с Меткой Хранителя кап 4 вместо 2. Лимит ограничивает только
    НАКОПЛЕНИЕ новых ключей — при истечении премиума уже полученные ключи не
    отбираются нигде (character.raid_keys здесь только читается/растёт)."""
    cap = rc.RAID_KEY_CAP_PREMIUM if premium_service.is_premium(character) else rc.RAID_KEY_CAP
    if character.raid_keys >= cap:
        return False
    if rng.random() >= rc.RAID_KEY_DROP_CHANCE:
        return False
    character.raid_keys += 1
    await db.flush()
    return True
