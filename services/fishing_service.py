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


def has_catch(character: Character) -> bool:
    """Рыба вытащена и ждёт решения: в садок или отпустить (2026-10-21).
    Хранится в тех же полях, что и рыба на крючке, но снасть уже не в воде."""
    return character.fishing_cast_at is None and character.fishing_pending_fish is not None


def drop_catch(character: Character) -> None:
    """Вытащенная рыба пропадает: игрок ушёл от воды, не решив (2026-10-21)."""
    if has_catch(character):
        clear_cast(character)


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
    character: Character, lake: LakeDef, rng: random.Random, now: datetime | None = None,
    rod_tier: int = 0,
) -> CastResult:
    """rod_tier - удочка (2026-10-23): рыба тяжелее, изредка тиром выше."""
    from game.economy import craft_gear

    now = now or datetime.now(timezone.utc)
    character.fishing_cast_at = now

    wait, f_bonus = fishing.roll_bite(rng)
    fish_id = fishing.roll_fish_id(
        rng, lake.tier, character.fishing_level, craft_gear.rod_tier_up_chance(rod_tier),
    )
    grams, _fraction = fishing.roll_weight(
        rng, fish_id, character.fishing_level, f_bonus + craft_gear.rod_weight_bonus(rod_tier),
    )
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
        return await _apply_break(db, character, lake, fish_id, grams, missed=True)

    fraction = fishing.fraction_of(fish_id, grams)
    # Леска (2026-10-23): рвётся реже.
    from game.economy import craft_gear
    from services import craft_gear_service

    line = craft_gear.line_break_mult(await craft_gear_service.tier(db, character.id, "line"))
    if rng.random() < fishing.line_break_chance(lake.tier, character.fishing_level, fraction) * line:
        return await _apply_break(db, character, lake, fish_id, grams)

    return await _apply_catch(db, character, fish_id, grams, fraction)


async def _apply_break(
    db: AsyncSession, character: Character, lake: LakeDef, fish_id: str, grams: int,
    missed: bool = False,
) -> StrikeResult:
    fraction = fishing.fraction_of(fish_id, grams)
    xp = fishing.break_xp(lake.tier, character.fishing_level)
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

    # 2026-10-21: в садок рыба идёт не сразу - игрок решает, оставить её или
    # отпустить (keep_catch / release_catch). Опыт и рекорд - за саму поимку.
    is_record = await _update_record(db, character.id, fish_id, grams)

    xp = fishing.catch_xp(fish_id, fraction)
    level, remainder, levels = fishing.add_fishing_xp(
        character.fishing_level, character.fishing_xp, xp
    )
    if levels:
        character.fishing_level_at = datetime.now(timezone.utc)
    character.fishing_level, character.fishing_xp = level, remainder
    character.fishing_cast_at = None
    character.fishing_bite_at = None
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
        # Первый улов вида - запоминаем вес, но рекордом не называем: у
        # мелочи это «рекорд» на каждом новом виде (2026-10-13).
        db.add(CharacterFishRecord(
            character_id=character_id, fish_id=fish_id, weight_grams=grams
        ))
        return False
    if grams > record.weight_grams:
        # Рекорд - только если вырос ВИДИМЫЙ вес: вес в тексте округлён до
        # 0,1 кг, и «0,1 кг - Личный рекорд!» при прежних 0,1 кг смешил.
        # Точный вес всё равно запоминаем.
        visible = fishing.format_kg(grams) != fishing.format_kg(record.weight_grams)
        record.weight_grams = grams
        record.caught_at = datetime.now(timezone.utc)
        return visible
    return False


# --- Садок --------------------------------------------------------------------

@dataclass
class Decision:
    """Чем кончилось решение по улову. kept=False и bag_full=False - отпустил."""

    fish: FishDef
    grams: int
    kept: bool = False
    bag_full: bool = False


async def keep_catch(db: AsyncSession, character: Character) -> Decision | None:
    """Положить вытащенную рыбу в садок. None - решать нечего.

    Лимит проверяется ДО добавления: пока в садке есть место хоть на грамм,
    рыба влезает целиком, даже если вес перевалит за лимит (11/10 кг)."""
    if not has_catch(character):
        return None
    fish_id, grams = character.fishing_pending_fish, character.fishing_pending_grams
    fish = fishing.fish_def(fish_id)
    capacity = fishing.bag_capacity_grams(character.fishing_level)
    if await bag_total_grams(db, character.id) >= capacity:
        return Decision(fish=fish, grams=grams, bag_full=True)
    grade_id, _label, _mult = fishing.grade_for(fishing.fraction_of(fish_id, grams))
    row = await db.scalar(
        select(CharacterFish).where(
            CharacterFish.character_id == character.id,
            CharacterFish.fish_id == fish_id,
            CharacterFish.grade == grade_id,
        )
    )
    if row is None:
        row = CharacterFish(character_id=character.id, fish_id=fish_id, grade=grade_id, total_grams=0)
        db.add(row)
    row.total_grams += grams
    clear_cast(character)
    await db.flush()
    return Decision(fish=fish, grams=grams, kept=True)


def auto_keep(character: Character) -> bool:
    """Игрок включил в Ремеслах «класть всю рыбу в садок» (2026-10-21)."""
    return bool((character.ui_flags or {}).get("fish_auto_keep"))


def release_catch(character: Character) -> Decision | None:
    """Отпустить вытащенную рыбу. None - решать нечего."""
    if not has_catch(character):
        return None
    decision = Decision(fish=fishing.fish_def(character.fishing_pending_fish), grams=character.fishing_pending_grams)
    clear_cast(character)
    return decision


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


def _stack_multiplier(definition, multiplier: float, buyer_tier: int | None) -> float:
    """buyer_tier - кольцо клетки рыбака: наценка с поправкой на тир рыбы."""
    if buyer_tier is None:
        return multiplier
    return fishing.buyer_fish_multiplier(multiplier, buyer_tier, definition.tier)


async def bag_value(
    db: AsyncSession, character_id: int, multiplier: float = 1.0, buyer_tier: int | None = None,
) -> int:
    """Сколько дадут за весь садок при этом множителе. Цена считается ОТ
    СТАКА: она линейна по весу, поэтому это ровно сумма цен всех рыб, но без
    поштучного округления, которое у мелочи упиралось в минимум 1 золотой."""
    return sum(
        round(fishing.price_of(definition.id, grams, grade_id) * _stack_multiplier(definition, multiplier, buyer_tier))
        for definition, grade_id, grams in await get_bag(db, character_id)
    )


async def sell_bag(
    db: AsyncSession, character: Character, multiplier: float = 1.0, buyer_tier: int | None = None,
) -> tuple[int, int]:
    """Продаёт садок целиком. Возвращает (золото, суммарный вес в граммах).
    Рекорды не трогаются — проданная рыба остаётся в рекордах навсегда.

    Строки садка берутся под блокировкой (патч 94). Продажа устроена как
    «прочитать садок -> удалить -> заплатить», а вебхук обрабатывает
    события параллельно: без блокировки два нажатия «Продать» читали один и
    тот же садок и платили оба - так же, как это подтвердилось на трофеях.
    Второе нажатие теперь ждёт первого и находит садок уже пустым.
    """
    locked = (
        await db.execute(
            select(CharacterFish)
            .where(CharacterFish.character_id == character.id, CharacterFish.total_grams > 0)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalars().all()
    if not locked:
        return 0, 0
    bag = await get_bag(db, character.id)
    if not bag:
        return 0, 0
    crown = crown_service.fish_sale_multiplier(character)
    gold = sum(
        round(fishing.price_of(definition.id, grams, grade_id) * _stack_multiplier(definition, multiplier, buyer_tier) * crown)
        for definition, grade_id, grams in bag
    )
    grams_total = sum(grams for _d, _g, grams in bag)
    await db.execute(
        delete(CharacterFish).where(CharacterFish.character_id == character.id)
    )
    from services import resource_log

    for definition, grade_id, grams in bag:
        resource_log.add(db, character.id, "fish", f"{definition.id}:{grade_id}", -grams)
    await wallet_service.deposit(db, character.id, "farm", gold)
    await db.flush()
    return gold, grams_total


async def drop_bag(db: AsyncSession, character_id: int) -> int:
    """Весь садок пропадает (поражение в открытом PvP, а с 2026-10-20 - и
    смерть от моба). Возвращает потерянный вес для сообщения.

    Рыба именно ПРОПАДАЕТ, а не переходит победителю — в отличие от трофеев
    (trophy_service.transfer_all). Решение продуктовое: победитель не должен
    получать чужой садок целиком, иначе выгоднее охотиться на рыбаков, чем
    рыбачить. Риск для проигравшего при этом сохраняется полностью.
    """
    grams = await bag_total_grams(db, character_id)
    if grams:
        from services import resource_log

        for definition, grade_id, stack in await get_bag(db, character_id):
            resource_log.add(db, character_id, "fish", f"{definition.id}:{grade_id}", -stack)
        await db.execute(
            delete(CharacterFish).where(CharacterFish.character_id == character_id)
        )
        await db.flush()
    return grams

