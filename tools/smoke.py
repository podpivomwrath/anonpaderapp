"""Проверка после выкатки (2026-10-21): основные экраны собираются на живых
данных тестового персонажа pupsik. Запускается из scripts/deploy-release.sh
внутри нового контейнера бота; упало - выкатка откатывается на прошлые образы.

Ничего игроку не шлёт и игровое состояние не меняет: только читает и
собирает ответы - карточку, сумку, карту, гильдию, магазин, клавиатуру
текущего экрана.

Запуск вручную: docker compose -f docker-compose.prod.yml exec -T bot python tools/smoke.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger  # noqa: E402

logger.remove()

#: Тестовый персонаж владельца (vk 106468413, «бубсик»).
SMOKE_VK_ID = 106468413


class FakeRequest(dict):
    """Ровно то, что читают GET-обработчики мини-аппа."""

    def __init__(self, app: dict, vk_id: int) -> None:
        super().__init__()
        from bot.miniapp_auth import VK_USER_ID_KEY

        self[VK_USER_ID_KEY] = vk_id
        self.app = app
        self.query: dict = {}
        self.match_info: dict = {}


async def main() -> int:
    from bot import miniapp_api, miniapp_guild_api, miniapp_map_api, miniapp_shop_api
    from bot.app_keys import SESSION_FACTORY_KEY, SETTINGS_KEY
    from config import get_settings
    from bot.handlers import world as world_handlers
    from services import admin_service, onboarding_service
    from services.db import get_session_factory

    factory = get_session_factory()
    app = {SESSION_FACTORY_KEY: factory, SETTINGS_KEY: get_settings()}
    checks = {
        "персонаж": miniapp_api.handle_get_character,
        "сумка": miniapp_api.handle_get_inventory,
        "карта": miniapp_map_api.handle_get_state,
        "гильдия": miniapp_guild_api.handle_get,
        "магазин": miniapp_shop_api.handle_get,
    }
    failed = []
    for name, handler in checks.items():
        try:
            response = await handler(FakeRequest(app, SMOKE_VK_ID))
            body = json.loads(response.body) if response.body else {}
            if response.status >= 500 or (response.status >= 400 and name == "персонаж"):
                failed.append(f"{name}: HTTP {response.status} {str(body)[:120]}")
        except Exception:  # noqa: BLE001
            failed.append(f"{name}: {traceback.format_exc(limit=3)}")

    async with factory() as db:
        try:
            character = await onboarding_service.get_character(db, SMOKE_VK_ID)
            if character is None:
                failed.append("pupsik не найден")
            else:
                await world_handlers._current_keyboard(db, character, SMOKE_VK_ID, datetime.now(timezone.utc))
                await admin_service.player_card(db, character.id)
        except Exception:  # noqa: BLE001
            failed.append(f"клавиатура/карточка: {traceback.format_exc(limit=3)}")
        finally:
            await db.rollback()

    for line in failed:
        print("ПРОВАЛ", line)
    print("smoke:", "OK" if not failed else f"{len(failed)} провал(ов)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
