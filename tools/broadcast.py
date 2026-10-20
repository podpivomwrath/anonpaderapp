"""Рассылка игрокам (патчноуты, анонсы) - с обязательной проверкой текста.

Запуск на сервере, внутри контейнера бота:

    python tools/broadcast.py <файл.txt | -> [--hours 24 | --since 2026-10-20T12:17]
                              [--to VK_ID] [--photo НОМЕР] [--send] [--force]

Без --send ничего не отправляет: показывает текст, находки проверки и число
получателей. Получатели - все, у кого персонаж заходил за --hours часов (или
с момента --since, UTC); --to - один игрок (проверочная отправка, например
pupsik). --photo - номер фото из альбома группы (bot/vk_media.py).

Проверка - tools/text_slop.py, правила скилла game-text. Жёсткие находки
(длинное тире) не отправляются никогда. Мягкие тоже блокируют --send: текст
правится, а не отправляется как есть. --force пропускает только мягкие -
когда находка ложная (например, «эхо» как название механики).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import text_slop  # noqa: E402

#: Пауза между сообщениями: лимит VK на рассылку от сообщества.
PAUSE_SECONDS = 0.1


def check(text: str) -> tuple[list, list]:
    """(жёсткие, мягкие) находки."""
    hits = text_slop.check_text(text, where="рассылка")
    return [h for h in hits if h[0].hard], [h for h in hits if not h[0].hard]


def blocked(hard: list, soft: list, force: bool) -> bool:
    return bool(hard) or (bool(soft) and not force)


async def recipients(since: datetime) -> list[int]:
    from sqlalchemy import select

    from config import get_settings
    from models import Character, User
    from services.db import get_session_factory

    demo = get_settings().demo_vk_id
    async with get_session_factory()() as db:
        peers = (await db.scalars(
            select(User.vk_id).join(Character, Character.user_id == User.id)
            .where(Character.last_active_at >= since).distinct()
        )).all()
    return [p for p in peers if 0 < p < 2_000_000_000 and p != demo]


async def send_all(peers: list[int], text: str, attachment: str | None) -> int:
    from vkbottle import API

    from config import get_settings

    api = API(get_settings().vk_token)
    ok = 0
    for peer in peers:
        try:
            await api.messages.send(peer_id=peer, random_id=0, message=text, attachment=attachment)
            ok += 1
        except Exception as exc:  # закрытые сообщения и т.п.
            print("не доставлено", peer, type(exc).__name__)
        await asyncio.sleep(PAUSE_SECONDS)
    return ok


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", help="файл с текстом или - (stdin)")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--since", help="UTC, например 2026-10-20T12:17")
    parser.add_argument("--to", type=int, help="одному игроку (vk_id)")
    parser.add_argument("--photo", help="номер фото в альбоме группы")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--force", action="store_true", help="отправить с мягкими находками")
    args = parser.parse_args()

    text = (sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")).strip()
    print(text, "\n")
    hard, soft = check(text)
    for rule, _where, _line, frag in hard + soft:
        print(f"[{'ЖЁСТКОЕ' if rule.hard else 'мягкое'}] {rule.title}: …{frag}…")
    if not hard and not soft:
        print("Проверка текста: чисто.")

    if args.to:
        peers = [args.to]
    else:
        since = (
            datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since
            else datetime.now(timezone.utc) - timedelta(hours=args.hours)
        )
        peers = asyncio.run(recipients(since))
    print("получателей:", len(peers))

    if not args.send:
        return
    if blocked(hard, soft, args.force):
        print("НЕ ОТПРАВЛЕНО: сначала поправь текст" + ("" if hard else " (или --force, если находка ложная)") + ".")
        sys.exit(1)
    attachment = None
    if args.photo:
        from bot.vk_media import photo_attachment

        attachment = photo_attachment(args.photo)
    print("отправлено:", asyncio.run(send_all(peers, text, attachment)))


if __name__ == "__main__":
    main()
