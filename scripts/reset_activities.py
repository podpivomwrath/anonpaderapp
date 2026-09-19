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
  combat:session:*:actions (на случай мид-тик креша ДО этого редеплоя);
- заброшенная снасть (патч 58) — сообщение о поклёвке присылает планировщик
  в памяти процесса, и рестарт его теряет.

НЕ трогает: pos_x/pos_y, respawn_at, инвентарь, статы, квесты, экономику,
садок с рыбой — только "я сейчас куда-то иду / дерусь / удю" состояние.

Сама логика — в services/maintenance_service.py: её же дёргает кнопка
«Сбросить состояния» в админ-панели мини-аппа, и расходиться им нельзя.

Запуск: python scripts/reset_activities.py [--yes]
--yes (или -y) пропускает интерактивное подтверждение — для запуска в составе
деплой-скрипта по SSH, где стоит ввод недоступен.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from config import get_settings
from services import maintenance_service
from services.db import dispose_engine, get_session_factory


async def _run(skip_confirm: bool) -> None:
    """Тонкая обёртка над services/maintenance_service.py.

    Сама логика сброса живёт там, потому что её же дёргает кнопка в
    админ-панели мини-аппа — двум путям расходиться нельзя.
    """
    # Один event loop на весь скрипт: get_session_factory() кеширует движок
    # на процесс — повторный asyncio.run() с новым event loop ломает уже
    # открытое соединение (особенно заметно на Windows/ProactorEventLoop).
    sf = get_session_factory()
    async with sf() as db:
        counts = await maintenance_service.preview(db)
        print(
            f"Будет сброшено: {counts.travelers} пеших переходов, "
            f"{counts.mount_travelers} поездок на маунте, "
            f"{counts.casters} заброшенных снастей, "
            f"{counts.diggers} незаконченных добыч. Позиции и остальной "
            f"прогресс персонажей не меняются."
        )
        if not skip_confirm:
            answer = input('Продолжить? Введи "YES" для подтверждения: ')
            if answer.strip() != "YES":
                print("Отменено.")
                return

        report = await maintenance_service.reset_stuck_activities(db)

    redis_cleared = await maintenance_service.clear_redis_combat_keys(
        get_settings().redis_url
    )
    await dispose_engine()
    print(
        f"Готово: пеших переходов сброшено {report.travel_reset}, поездок на "
        f"маунте отменено {report.mount_reset}, снастей вынуто "
        f"{report.fishing_reset}, добыч прервано {report.mining_reset}, "
        f"зависших Redis-ключей боя очищено {redis_cleared}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", "-y", action="store_true", help="не спрашивать подтверждение")
    args = parser.parse_args()
    asyncio.run(_run(args.yes))


if __name__ == "__main__":
    main()
