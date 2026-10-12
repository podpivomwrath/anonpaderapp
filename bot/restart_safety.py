"""Перезапуск бота без потерь (2026-10-12).

Деплой случается по нескольку раз в день, а бои живут в памяти процесса.
Раньше перезапуск обрывал всё: игрок жал «Атака» и получал «боя больше нет».

Что здесь:
  * соло-бой с тварью - самый частый. У него нет таймера хода, состояние -
    обычные объекты. При остановке (SIGTERM) он целиком уходит в Redis, при
    запуске возвращается движку тем же ходом, и игроку приходит доска боя с
    кнопками. Бой с мировым боссом не сохраняется: это общий заход, его итог
    и так считается по нанесённому урону;
  * групповые бои, рейды, разломы, PvP и групповые события сохранить так
    просто нельзя (общие окна хода, таймеры, несколько игроков). Их счётчик
    бот раз в несколько секунд кладёт в Redis (BUSY_KEY), и выкатка ждёт,
    пока он не станет нулём, вместо того чтобы обрывать бой.

Рыбалка, добыча, переходы, исследование и отдых восстанавливаются своими
модулями (resume_after_restart) - их состояние лежит в базе и Redis.
"""

import asyncio
import base64
import pickle

from loguru import logger

SOLO_PREFIX = "solo_battle:"
SOLO_TTL_SECONDS = 3600
BUSY_KEY = "busy:battles"
BUSY_PUBLISH_SECONDS = 5


async def save_solo_battles(redis) -> int:
    from bot.handlers import combat

    saved = 0
    for peer_id, snapshot in combat.solo_snapshots().items():
        try:
            blob = base64.b64encode(pickle.dumps(snapshot)).decode()
        except Exception:
            logger.exception("Бой {} не сохраняется - пропускаю", peer_id)
            continue
        await redis.set(f"{SOLO_PREFIX}{peer_id}", blob, ex=SOLO_TTL_SECONDS)
        saved += 1
    return saved


async def restore_solo_battles(redis) -> int:
    from bot.handlers import combat

    restored = 0
    async for key in redis.scan_iter(match=f"{SOLO_PREFIX}*"):
        blob = await redis.get(key)
        await redis.delete(key)
        if blob is None:
            continue
        peer_id = int(key[len(SOLO_PREFIX):])
        try:
            snapshot = pickle.loads(base64.b64decode(blob))
            if await combat.restore_solo(peer_id, snapshot):
                restored += 1
        except Exception:
            logger.exception("Бой {} не восстановился", peer_id)
    return restored


def busy_battles() -> int:
    """Идущие бои, которые перезапуск оборвал бы: всё, кроме соло с тварью."""
    from bot.handlers import group_combat, group_events, pvp, raid_combat

    return (len(group_combat._battles) + len(raid_combat._battles)
            + len(pvp._battles) + len(group_events._scenes))


async def publish_busy_loop(redis) -> None:
    while True:
        try:
            await redis.set(BUSY_KEY, busy_battles(), ex=BUSY_PUBLISH_SECONDS * 3)
        except Exception:
            logger.exception("Счётчик занятых боёв не записан")
        await asyncio.sleep(BUSY_PUBLISH_SECONDS)
