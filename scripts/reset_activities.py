"""Сброс "зависших" активностей всех игроков — патч 30, по просьбе на выкате
с живыми игроками: часть багов патча (в первую очередь баг 2 — застревание в
бою) могла оставить игроков посреди пешего пути / поездки на маунте с
клавиатурой, которая больше не соответствует реальному состоянию после
рестарта бота. Скрипт возвращает всех "просто на локацию", ничего не отнимая:

- пеший путь (Character.travel_target_x/y, travel_arrives_at) — отменяется,
  как /застрял (см. services/movement_service.py::cancel_travel); pos_x/y НЕ
  меняются — персонаж остаётся там, где уже был;
- поездки на маунте (MountTravel.status in "traveling"/"ambushed") —
  помечаются "cancelled" (services/mount_service.py::cancel_travel), позиция
  персонажа тоже не трогается;
- боевые сессии (PvE tick_engine, PvP дуэль/групповой) ЦЕЛИКОМ в памяти
  процесса (см. патч 30, research) — рестарт бота их и так обнуляет, здесь
  дополнительно вычищаются возможные "зависшие" ключи Redis
  combat:session:*:actions (на случай мид-тик креша ДО этого редеплоя).

НЕ трогает: pos_x/pos_y, respawn_at, инвентарь, статы, квесты, экономику —
только "я сейчас куда-то иду / дерусь" состояние.

Запуск: python scripts/reset_activities.py [--yes]
--yes (или -y) пропускает интерактивное подтверждение — для запуска в составе
деплой-скрипта по SSH, где стоит ввод недоступен.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import func, select, update  # noqa: E402

from config import get_settings  # noqa: E402
from models import Character, MountTravel  # noqa: E402
from services.db import dispose_engine, get_session_factory  # noqa: E402


async def _preview_counts(db) -> tuple[int, int]:
    """Сколько строк реально затронет сброс — для текста подтверждения."""
    travelers_count = await db.scalar(
        select(func.count()).select_from(Character).where(
            Character.creation_state.is_(None), Character.travel_arrives_at.is_not(None),
        )
    )
    mount_travelers_count = await db.scalar(
        select(func.count()).select_from(MountTravel)
        .where(MountTravel.status.in_(("traveling", "ambushed")))
    )
    return travelers_count or 0, mount_travelers_count or 0


async def _reset(db) -> tuple[int, int]:
    travel_result = await db.execute(
        update(Character)
        .where(
            Character.creation_state.is_(None),
            Character.travel_arrives_at.is_not(None),
        )
        .values(travel_target_x=None, travel_target_y=None, travel_arrives_at=None)
    )
    mount_result = await db.execute(
        update(MountTravel)
        .where(MountTravel.status.in_(("traveling", "ambushed")))
        .values(status="cancelled")
    )
    await db.commit()
    return travel_result.rowcount, mount_result.rowcount


async def _clear_redis_combat_keys() -> int:
    """Лучшее из возможного, не критично: если Redis недоступен, DB-часть
    сброса (главное) уже применена и закоммичена — просто предупреждаем."""
    settings = get_settings()
    if not settings.redis_url:
        return 0
    import redis.asyncio as aioredis

    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    cleared = 0
    try:
        async for key in redis.scan_iter(match="combat:session:*:actions"):
            await redis.delete(key)
            cleared += 1
    except Exception as exc:
        print(f"Предупреждение: не удалось очистить Redis-ключи боя ({exc}).")
    finally:
        await redis.aclose()
    return cleared


async def _run(skip_confirm: bool) -> None:
    # Один event loop на весь скрипт: get_session_factory() кеширует движок
    # на процесс — повторный asyncio.run() с новым event loop ломает уже
    # открытое соединение (особенно заметно на Windows/ProactorEventLoop).
    sf = get_session_factory()
    async with sf() as db:
        travelers_count, mount_travelers_count = await _preview_counts(db)
        print(
            f"Будет сброшено: {travelers_count} пеших переходов, "
            f"{mount_travelers_count} поездок на маунте. Позиции и остальной "
            f"прогресс персонажей не меняются."
        )
        if not skip_confirm:
            answer = input('Продолжить? Введи "YES" для подтверждения: ')
            if answer.strip() != "YES":
                print("Отменено.")
                return

        travel_reset, mount_reset = await _reset(db)

    redis_cleared = await _clear_redis_combat_keys()
    await dispose_engine()
    print(
        f"Готово: пеших переходов сброшено {travel_reset}, поездок на маунте "
        f"отменено {mount_reset}, зависших Redis-ключей боя очищено {redis_cleared}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", "-y", action="store_true", help="не спрашивать подтверждение")
    args = parser.parse_args()
    asyncio.run(_run(args.yes))


if __name__ == "__main__":
    main()
