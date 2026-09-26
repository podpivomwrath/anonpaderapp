"""Что бот на самом деле отправил игроку - глазами самого бота (патч 102).

Запуск на сервере, внутри контейнера бота:

    python tools/vk_dialog.py [vk_id игрока] [сколько сообщений]

По умолчанию - диалог с pupsik (персонаж владельца), 5 последних сообщений.
Только чтение: бот ничего не отправляет.

Зачем. Отправка, которую ВК принял, ещё не значит, что игрок увидел то, что
задумано: битое вложение ВК иногда молча выбрасывает и доставляет один
текст. Здесь видно, что сообщение реально несёт - текст и фото с номерами.

Токен - БОТА (у сообщества есть право на сообщения). Личный токен владельца
для этого не нужен и не используется: он заведён только под загрузку фото.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import get_settings  # noqa: E402

PUPSIK = 106468413
#: Время - московское: по нему живут ежедневки и весь игровой календарь.
MSK = timezone(timedelta(hours=3))


async def history(peer_id: int, count: int) -> list[dict]:
    settings = get_settings()
    params = {
        "access_token": settings.vk_token, "v": "5.199", "peer_id": peer_id, "count": count,
    }
    async with (
        aiohttp.ClientSession() as session,
        session.post("https://api.vk.com/method/messages.getHistory", data=params) as response,
    ):
        body = await response.json(content_type=None)
    if "error" in body:
        raise RuntimeError(body["error"]["error_msg"])
    return list(reversed(body["response"]["items"]))


def describe(message: dict) -> str:
    who = "бот" if message["from_id"] < 0 else "игрок"
    when = datetime.fromtimestamp(message["date"], tz=MSK).strftime("%d.%m %H:%M:%S")
    text = (message.get("text") or "").replace("\n", " ")[:90]
    line = f"[{when} МСК] {who}: {text}"
    attachments = []
    for item in message.get("attachments", []):
        if item["type"] == "photo":
            photo = item["photo"]
            attachments.append(f"фото {photo['owner_id']}_{photo['id']}")
        else:
            attachments.append(item["type"])
    if attachments:
        line += f"\n          вложения: {', '.join(attachments)}"
    return line


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    peer = int(sys.argv[1]) if len(sys.argv) > 1 else PUPSIK
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    for message in asyncio.run(history(peer, count)):
        print(describe(message))
