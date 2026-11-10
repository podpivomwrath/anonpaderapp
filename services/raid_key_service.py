"""Ключ Монолита (патч 45, ч.4) - вход в рейды. Падает независимым броском
0.5% с ЛЮБОГО источника лута (моб/событие/горстка пепла/ларец, дно озера).
Потолок накопления - current_cap: 2, с Клеймом Хранителя (и Метками,
активными в день переноса бонусов) - 4. Сверх потолка не выпадает вовсе,
без строки в логе (не дразнить игрока "чуть-чуть не хватило")."""

import random

from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import raid_key_config as rc
from models import Character
from services import premium_service


def current_cap(character: Character) -> int:
    """Потолок накопления ключей. Вынесено из maybe_grant: с патчем 58
    ключ может прийти и с рыбалки (со дна), и правило капа не должно
    существовать в двух местах."""
    # С 2026-11-06 - Клеймо Хранителя (и Метки, активные в день переноса).
    return rc.RAID_KEY_CAP_PREMIUM if premium_service.big_key_cap(character) else rc.RAID_KEY_CAP


async def maybe_grant(db: AsyncSession, character: Character, rng: random.Random) -> bool:
    """True — ключ выпал (и уже начислен). Вызывается независимо от прочих
    бросков лута на каждом источнике дропа.

    Патч 50: с Меткой Хранителя кап 4 вместо 2. Лимит ограничивает только
    НАКОПЛЕНИЕ новых ключей — при истечении премиума уже полученные ключи не
    отбираются нигде (character.raid_keys здесь только читается/растёт)."""
    cap = current_cap(character)
    if character.raid_keys >= cap:
        return False
    from services import guild_service

    chance = rc.RAID_KEY_DROP_CHANCE * (1 + guild_service.perk(character, "key_chance_pct") / 100)
    if rng.random() >= chance:
        return False
    character.raid_keys += 1
    await db.flush()
    return True
