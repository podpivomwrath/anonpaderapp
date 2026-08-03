"""Дев-утилита: полный вайп персонажей (users НЕ трогаем — vk_id остаются).

Запуск: python scripts/wipe.py
Требует ALLOW_WIPE=true в окружении (защита прода — на боевом сервере эта
переменная намеренно не задаётся, см. DEPLOY.md) И подтверждения — ввести
"YES" в консоли.

Порядок удаления учитывает FK без ON DELETE CASCADE:
  - pvp_stake_transfers, combat_participants, exchange_orders ссылаются на
    characters БЕЗ каскада — удаляем явно первыми;
  - items удаляем целиком: ondelete CASCADE на inventory.item_id чистит
    инвентарь автоматически;
  - characters удаляем последним: ondelete CASCADE чистит character_stats,
    character_buff_presets, wallets, character_quests.
item_upgrade_history не трогаем — item_id уходит в NULL (ondelete SET NULL),
история апгрейдов осознанно переживает вайп (аудит).
После вайпа: следующее сообщение любого игрока автоматически заново
запускает онбординг (bot/handlers/fallback.py).
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import delete  # noqa: E402

from models import (  # noqa: E402
    Character,
    CharacterQuest,
    CombatParticipant,
    CombatSession,
    ExchangeOrder,
    Item,
    PvpStakeTransfer,
)
from services.db import dispose_engine, get_session_factory  # noqa: E402


async def wipe() -> None:
    sf = get_session_factory()
    async with sf() as db:
        await db.execute(delete(PvpStakeTransfer))
        await db.execute(delete(CombatParticipant))
        await db.execute(delete(CombatSession))
        await db.execute(delete(ExchangeOrder))
        await db.execute(delete(CharacterQuest))
        await db.execute(delete(Item))  # каскадом чистит inventory
        result = await db.execute(delete(Character))  # каскадом чистит остальное
        await db.commit()
        print(f"Удалено персонажей: {result.rowcount}")
    await dispose_engine()


def main() -> None:
    if os.environ.get("ALLOW_WIPE") != "true":
        print(
            "Вайп заблокирован: нет ALLOW_WIPE=true в окружении. "
            "Это защита прод-базы — см. DEPLOY.md."
        )
        return
    answer = input('Полный вайп персонажей (users останутся). Введи "YES" для подтверждения: ')
    if answer.strip() != "YES":
        print("Отменено.")
        return
    asyncio.run(wipe())
    print("Готово.")


if __name__ == "__main__":
    main()
