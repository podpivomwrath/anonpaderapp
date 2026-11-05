"""Ворон с письмом наставника - тем, кто уже был на 60 уровне, когда руины
открылись (2026-11-05). Новые 60-е получают его сами при левелапе
(bot/handlers/stats_window._ruins_raven).

Запуск в контейнере бота:
    python tools/ruins_raven.py            сухой прогон: кому уйдёт
    python tools/ruins_raven.py --send     отправить

Повтор безопасен: письмо отмечается флагом ruins_raven, получивший второй раз
не получит.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from vkbottle import API  # noqa: E402

from bot import ruins_texts  # noqa: E402
from config import get_settings  # noqa: E402
from game.economy import ruins_config as rc  # noqa: E402
from models import Character, User  # noqa: E402
from services import story_service  # noqa: E402
from services.db import get_session_factory  # noqa: E402


async def main(send: bool) -> None:
    async with get_session_factory()() as db:
        rows = (await db.execute(
            select(Character.id, Character.name, User.vk_id)
            .join(User, User.id == Character.user_id)
            .where(Character.level >= rc.MIN_LEVEL, Character.creation_state.is_(None))
        )).all()
        todo = []
        for cid, name, vk_id in rows:
            character = await db.get(Character, cid)
            if story_service.ruins_raven_due(character):
                todo.append((cid, name, vk_id))
    print(f"60-х: {len(rows)}, письмо уйдёт: {len(todo)}")
    for _cid, name, vk_id in todo:
        print(f"  {name} ({vk_id})")
    if not send:
        return
    api = API(get_settings().vk_token)
    sent = 0
    for cid, name, vk_id in todo:
        async with get_session_factory()() as db:
            character = await db.get(Character, cid, with_for_update=True)
            if character is None or not story_service.ruins_raven_due(character):
                continue
            story_service.mark_ruins_raven(character)
            await db.commit()
        try:
            await api.messages.send(peer_id=vk_id, message=ruins_texts.RAVEN_LETTER, random_id=0)
            sent += 1
        except Exception as exc:  # закрытые сообщения и т.п. - флаг остаётся
            print(f"  не ушло {name}: {exc}")
        await asyncio.sleep(0.2)
    print(f"отправлено: {sent}")


if __name__ == "__main__":
    asyncio.run(main("--send" in sys.argv[1:]))
