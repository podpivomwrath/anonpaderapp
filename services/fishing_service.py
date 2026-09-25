"""Рыбалка (патч 58): заброс, подсечка, садок, продажа, рекорды.

Чистая логика (розыгрыш вида/веса, градации, обрыв, цены, уровень) живёт в
game/economy/fishing.py и ничего не знает про БД — здесь только состояние.

Жизненный цикл заброса намеренно разложен на две БД-колонки по образцу
travel_* (services/movement_service.py), а не держится в памяти процесса:
рыбалка идёт минутами, бот перезапускается, и терять чужой заброс из-за
деплоя нельзя.

    [Забросить] -> fishing_cast_at = now, fishing_bite_at = now + ожидание,
                   вид и вес РАЗЫГРАНЫ СРАЗУ и лежат в fishing_pending_*
    [Подсекать] -> успевает в окно после bite_at -> рыба в садок
                   не успевает / рано -> сорвалась

Почему вид и вес разыгрываются в момент ЗАБРОСА, а не подсечки: иначе исход
зависел бы от того, когда игрок нажал кнопку, и быстрая реакция давала бы
лучшую рыбу. Подсечка должна проверять внимание, а не удачу тайминга.
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import FishDef, LakeDef
from game.economy import fishing
from game.economy import fishing_config as fc
from models import Character, CharacterFish, CharacterFishRecord
from services import crown_service, wallet_service

# --- Клетка ------------------------------------------------------------------

def lake_at(character: Character) -> LakeDef | None:
    if character.pos_x is None or character.pos_y is None:
        return None
    return fishing.lake_at(character.pos_x, character.pos_y)


def is_safe_lake(x: int, y: int) -> bool:
    """Озеро с запретом PvP (кольца I-II). Вынесено сюда, чтобы
    bot/handlers/pvp.py импортировал сервис, а не лез в game.economy."""
    return fishing.is_safe_lake(x, y)


# --- Состояние заброса --------------------------------------------------------

def is_casting(character: Character) -> bool:
    return character.fishing_cast_at is not None


def cast_is_stale(character: Character, now: datetime | None = None) -> bool:
    """Заброс, который уже некому разрешить: окно подсечки прошло.

    Нужен потому, что сообщение о поклёвке присылает планировщик в памяти
    процесса, а рестарт бота его теряет. Без этой проверки снасть осталась бы
    «в воде» навсегда, и игрок не смог бы забросить заново.
    """
    if character.fishing_cast_at is None:
        return False
    deadline = strike_deadline(character)
    if deadline is None:
        return True
    return (now or datetime.now(timezone.utc)) > deadline


def bite_ready(character: Character, now: datetime | None = None) -> bool:
    """Поклёвка уже случилась (можно подсекать)."""
    if character.fishing_bite_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now >= character.fishing_bite_at


def strike_deadline(character: Character) -> datetime | None:
    if character.fishing_bite_at is None:
        return None
    return character.fishing_bite_at + timedelta(seconds=fc.STRIKE_WINDOW_SECONDS)


def strike_expired(character: Character, now: datetime | None = None) -> bool:
    deadline = strike_deadline(character)
    if deadline is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now > deadline


def clear_cast(character: Character) -> None:
    character.fishing_cast_at = None
    character.fishing_bite_at = None
    character.fishing_pending_fish = None
    character.fishing_pending_grams = None


@dataclass
class CastResult:
    """Заброс сделан.

    seconds — через сколько будет поклёвка. Она случается всегда: пустых
    забросов в игре нет.
    """

    seconds: float


def start_cast(
    character: Character, lake: LakeDef, rng: random.Random, now: datetime | None = None
) -> CastResult:
    now = now or datetime.now(timezone.utc)
    character.fishing_cast_at = now

    wait, f_bonus = fishing.roll_bite(rng)
    fish_id = fishing.roll_fish_id(rng, lake.tier, character.fishing_level)
    grams, _fraction = fishing.roll_weight(rng, fish_id, character.fishing_level, f_bonus)
    character.fishing_bite_at = now + timedelta(seconds=wait)
    character.fishing_pending_fish = fish_id
    character.fishing_pending_grams = grams
    return CastResult(seconds=wait)


# --- Подсечка -----------------------------------------------------------------

@dataclass
class StrikeResult:
    """Исход подсечки. Ровно один из landed/broke/too_early/nothing истинен."""

    landed: bool = False
    broke: bool = False
    too_early: bool = False
    nothing: bool = False
    #: Обрыв случился потому, что игрок ПРОЗЕВАЛ окно подсечки, а не потому,
    #: что снасть не выдержала. Для игрока это разные истории, и текст обязан
    #: их различать - иначе опоздание выглядит как невезение.
    missed: bool = False

    fish: FishDef | None = None
    grams: int = 0
    grade_id: str = ""
    grade_label: str = ""
    fraction: float = 0.0

    xp: int = 0
    levels_gained: int = 0
    new_level: int = 0
    is_record: bool = False
    bag_full: bool = False


async def strike(
    db: AsyncSession, character: Character, lake: LakeDef,
    rng: random.Random, now: datetime | None = None,
) -> StrikeResult:
    now = now or datetime.now(timezone.utc)
    fish_id = character.fishing_pending_fish
    grams = character.fishing_pending_grams

    # Пустой заброс либо подсечка раньше поклёвки.
    if fish_id is None or grams is None:
        clear_cast(character)
        return StrikeResult(nothing=True)
    if not bite_ready(character, now):
        clear_cast(character)
        return StrikeResult(too_early=True)
    if strike_expired(character, now):
        # Прозевал окно — рыба ушла сама. Опыт как за обрыв, текст другой.
        return await _apply_break(db, character, fish_id, grams, missed=True)

    fraction = fishing.fraction_of(fish_id, grams)
    if rng.random() < fishing.line_break_chance(lake.tier, character.fishing_level, fraction):
        return await _apply_break(db, character, fish_id, grams)

    return await _apply_catch(db, character, fish_id, grams, fraction)


async def _apply_break(
    db: AsyncSession, character: Character, fish_id: str, grams: int,
    missed: bool = False,
) -> StrikeResult:
    fraction = fishing.fraction_of(fish_id, grams)
    xp = fishing.catch_xp(fish_id, fraction, landed=False)
    level, remainder, levels = fishing.add_fishing_xp(
        character.fishing_level, character.fishing_xp, xp
    )
    if levels:
        character.fishing_level_at = datetime.now(timezone.utc)
    character.fishing_level, character.fishing_xp = level, remainder
    clear_cast(character)
    await db.flush()
    # Вид сорвавшейся рыбы игроку НЕ показывается — только класс веса (см.
    # bot/fishing_texts.py). Потерять то, что почти держал, интереснее, когда
    # не знаешь наверняка, что именно ушло.
    return StrikeResult(
        broke=True, missed=missed, grams=grams, fraction=fraction, xp=xp,
        levels_gained=levels, new_level=level,
    )


async def _apply_catch(
    db: AsyncSession, character: Character, fish_id: str, grams: int, fraction: float
) -> StrikeResult:
    grade_id, grade_label, _mult = fishing.grade_for(fraction)

    capacity = fishing.bag_capacity_grams(character.fishing_level)
    current = await bag_total_grams(db, character.id)
    if current + grams > capacity:
        # Садок полон: рыба НЕ пропадает молча, заброс просто не завершается —
        # снасть остаётся заброшенной, игрок идёт продавать. Молча выбрасывать
        # трофей игрока недопустимо.
        return StrikeResult(bag_full=True, grams=grams, fraction=fraction)

    row = await db.scalar(
        select(CharacterFish).where(
            CharacterFish.character_id == character.id,
            CharacterFish.fish_id == fish_id,
            CharacterFish.grade == grade_id,
        )
    )
    if row is None:
        row = CharacterFish(
            character_id=character.id, fish_id=fish_id, grade=grade_id, total_grams=0
        )
        db.add(row)
    row.total_grams += grams

    is_record = await _update_record(db, character.id, fish_id, grams)

    xp = fishing.catch_xp(fish_id, fraction)
    level, remainder, levels = fishing.add_fishing_xp(
        character.fishing_level, character.fishing_xp, xp
    )
    if levels:
        character.fishing_level_at = datetime.now(timezone.utc)
    character.fishing_level, character.fishing_xp = level, remainder
    clear_cast(character)
    await db.flush()

    return StrikeResult(
        landed=True, fish=fishing.fish_def(fish_id), grams=grams, grade_id=grade_id,
        grade_label=grade_label, fraction=fraction, xp=xp, levels_gained=levels,
        new_level=level, is_record=is_record,
    )


async def _update_record(
    db: AsyncSession, character_id: int, fish_id: str, grams: int
) -> bool:
    record = await db.scalar(
        select(CharacterFishRecord).where(
            CharacterFishRecord.character_id == character_id,
            CharacterFishRecord.fish_id == fish_id,
        )
    )
    if record is None:
        db.add(CharacterFishRecord(
            character_id=character_id, fish_id=fish_id, weight_grams=grams
        ))
        return True
    if grams > record.weight_grams:
        record.weight_grams = grams
        record.caught_at = datetime.now(timezone.utc)
        return True
    return False


# --- Садок --------------------------------------------------------------------

async def bag_total_grams(db: AsyncSession, character_id: int) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(CharacterFish.total_grams), 0)).where(
            CharacterFish.character_id == character_id
        )
    )
    return int(total or 0)


async def get_bag(db: AsyncSession, character_id: int) -> list[tuple[FishDef, str, int]]:
    """(вид, градация, суммарный вес) — только непустые стаки, в порядке
    каталога видов, внутри вида от крупной градации к мелкой."""
    rows = (
        await db.execute(
            select(CharacterFish).where(
                CharacterFish.character_id == character_id,
                CharacterFish.total_grams > 0,
            )
        )
    ).scalars().all()
    by_key = {(r.fish_id, r.grade): r.total_grams for r in rows}
    grade_order = [g[1] for g in reversed(fc.GRADES)]
    result: list[tuple[FishDef, str, int]] = []
    for definition in fishing.fish_defs_ordered():
        for grade_id in grade_order:
            grams = by_key.get((definition.id, grade_id))
            if grams:
                result.append((definition, grade_id, grams))
    return result


async def bag_value(db: AsyncSession, character_id: int, multiplier: float = 1.0) -> int:
    """Сколько дадут за весь садок при этом множителе. Цена считается ОТ
    СТАКА: она линейна по весу, поэтому это ровно сумма цен всех рыб, но без
    поштучного округления, которое у мелочи упиралось в минимум 1 золотой."""
    return sum(
        round(fishing.price_of(definition.id, grams, grade_id) * multiplier)
        for definition, grade_id, grams in await get_bag(db, character_id)
    )


async def sell_bag(
    db: AsyncSession, character: Character, multiplier: float = 1.0
) -> tuple[int, int]:
    """Продаёт садок целиком. Возвращает (золото, суммарный вес в граммах).
    Рекорды не трогаются — проданная рыба остаётся в рекордах навсегда."""
    bag = await get_bag(db, character.id)
    if not bag:
        return 0, 0
    multiplier *= crown_service.fish_sale_multiplier(character)
    gold = sum(
        round(fishing.price_of(definition.id, grams, grade_id) * multiplier)
        for definition, grade_id, grams in bag
    )
    grams_total = sum(grams for _d, _g, grams in bag)
    await db.execute(
        delete(CharacterFish).where(CharacterFish.character_id == character.id)
    )
    await wallet_service.deposit(db, character.id, "farm", gold)
    await db.flush()
    return gold, grams_total


async def drop_bag(db: AsyncSession, character_id: int) -> int:
    """Весь садок пропадает (поражение в открытом PvP). Возвращает потерянный
    вес для сообщения.

    Рыба именно ПРОПАДАЕТ, а не переходит победителю — в отличие от трофеев
    (trophy_service.transfer_all). Решение продуктовое: победитель не должен
    получать чужой садок целиком, иначе выгоднее охотиться на рыбаков, чем
    рыбачить. Риск для проигравшего при этом сохраняется полностью.
    """
    grams = await bag_total_grams(db, character_id)
    if grams:
        await db.execute(
            delete(CharacterFish).where(CharacterFish.character_id == character_id)
        )
        await db.flush()
    return grams

