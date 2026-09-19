"""Сброс «зависших» активностей всех игроков (патч 30, расширен патчем 58).

Боевые сессии, таймеры исследования/отдыха и таймер поклёвки живут В ПАМЯТИ
процесса — рестарт бота их теряет, а в БД остаётся состояние «я куда-то иду /
у меня заброшена снасть», под которое игроку выдана клавиатура, больше не
соответствующая реальности. Этот модуль возвращает всех «просто на локацию»,
ничего не отнимая.

Логика вынесена сюда из scripts/reset_activities.py, потому что у неё стало
два вызывающих: сам скрипт (руками по SSH) и кнопка в админ-панели мини-аппа.
Расходиться этим двум путям нельзя — иначе кнопка однажды начнёт сбрасывать
не то же самое, что скрипт.

НЕ трогает: pos_x/pos_y, respawn_at, инвентарь, статы, квесты, экономику,
садок с рыбой — только состояние «я сейчас куда-то иду / дерусь / удю».
"""

from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Character, MountTravel


@dataclass
class ResetPreview:
    travelers: int
    mount_travelers: int
    casters: int
    diggers: int = 0

    @property
    def total(self) -> int:
        return self.travelers + self.mount_travelers + self.casters + self.diggers


@dataclass
class ResetReport:
    travel_reset: int
    mount_reset: int
    fishing_reset: int
    mining_reset: int = 0
    redis_cleared: int = 0

    @property
    def total(self) -> int:
        return (self.travel_reset + self.mount_reset + self.fishing_reset
                + self.mining_reset)


async def preview(db: AsyncSession) -> ResetPreview:
    """Сколько строк реально затронет сброс — для подтверждения перед ним."""
    travelers = await db.scalar(
        select(func.count()).select_from(Character).where(
            Character.creation_state.is_(None),
            Character.travel_arrives_at.is_not(None),
        )
    )
    mount_travelers = await db.scalar(
        select(func.count()).select_from(MountTravel)
        .where(MountTravel.status.in_(("traveling", "ambushed")))
    )
    casters = await db.scalar(
        select(func.count()).select_from(Character).where(
            Character.creation_state.is_(None),
            Character.fishing_cast_at.is_not(None),
        )
    )
    diggers = await db.scalar(
        select(func.count()).select_from(Character).where(
            Character.creation_state.is_(None),
            Character.mining_ends_at.is_not(None)
            | Character.mining_left_seconds.is_not(None),
        )
    )
    return ResetPreview(
        travelers or 0, mount_travelers or 0, casters or 0, diggers or 0
    )


async def reset_stuck_activities(db: AsyncSession) -> ResetReport:
    """Отменяет пеший путь, поездки на маунте и заброшенные снасти.

    Позиции персонажей не меняются: пеший путь отменяется как «/застрял» —
    персонаж остаётся там, где уже был, а не телепортируется к цели.
    """
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
    # Патч 58: заброшенная снасть. Сообщение о поклёвке присылает планировщик
    # в памяти процесса, и рестарт его теряет — без сброса игрок остался бы со
    # снастью «в воде» и без кнопки подсечки.
    fishing_result = await db.execute(
        update(Character)
        .where(
            Character.creation_state.is_(None),
            Character.fishing_cast_at.is_not(None),
        )
        .values(
            fishing_cast_at=None, fishing_bite_at=None,
            fishing_pending_fish=None, fishing_pending_grams=None,
        )
    )
    # Патч 59: незаконченная добыча. Она блокирует игроку вообще всё, поэтому
    # зависшая добыча — самое неприятное из того, что может пережить рестарт.
    #
    # Начатые куски возвращаются в жилы: массовый сброс не должен уничтожать
    # общий ресурс мира. Иначе каждое нажатие кнопки в админке стирало бы по
    # руде с каждой занятой жилы.
    from services import mining_service

    occupied = (
        await db.execute(
            select(Character.mining_mine_id).where(
                Character.creation_state.is_(None),
                Character.mining_mine_id.is_not(None),
                Character.mining_ends_at.is_not(None)
                | Character.mining_left_seconds.is_not(None),
            )
        )
    ).scalars().all()
    for mine_id in occupied:
        await mining_service.release_ore(db, mine_id)

    mining_result = await db.execute(
        update(Character)
        .where(
            Character.creation_state.is_(None),
            # Приостановленная добыча тоже висит на игроке и тоже блокирует
            # его, когда он в забое, — сбрасывать надо оба состояния.
            Character.mining_ends_at.is_not(None)
            | Character.mining_left_seconds.is_not(None),
        )
        .values(mining_ends_at=None, mining_left_seconds=None, mining_mine_id=None)
    )
    await db.commit()
    return ResetReport(
        travel_reset=travel_result.rowcount,
        mount_reset=mount_result.rowcount,
        fishing_reset=fishing_result.rowcount,
        mining_reset=mining_result.rowcount,
    )


async def clear_redis_combat_keys(redis_url: str | None) -> int:
    """Зависшие ключи хода боя. Best-effort: если Redis недоступен, основная
    (БД) часть сброса уже применена и закоммичена — молча не падаем."""
    if not redis_url:
        return 0
    import redis.asyncio as aioredis
    from loguru import logger

    redis = aioredis.from_url(redis_url, decode_responses=True)
    cleared = 0
    try:
        async for key in redis.scan_iter(match="combat:session:*:actions"):
            await redis.delete(key)
            cleared += 1
    except Exception:  # noqa: BLE001 - Redis не критичен для сброса
        logger.warning("Не удалось очистить Redis-ключи боя при сбросе состояний")
    finally:
        await redis.aclose()
    return cleared
