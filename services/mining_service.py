"""Горное дело (патч 59): начало добычи, её завершение, жилы, руда, спавн.

Чистая логика (время, вид, градация, уровень) — game/economy/mining.py.
Здесь состояние: инвентарь руды персонажа и ОБЩЕЕ состояние рудников.

Три правила, которые задают всю остальную конструкцию:

1. Добыча БЛОКИРУЕТ действия игрока до конца. Ограничителя больше нет
   никакого: носить можно сколько угодно, провалов нет, продать некому.

2. Руда в статичном руднике резервируется В НАЧАЛЕ добычи, а не в конце.
   Иначе два игрока, начавшие одновременно, оба забрали бы последний кусок.
   Списание атомарное (UPDATE ... WHERE ore_count > 0), без чтения в питон.

3. Возврат к прерванной добыче разный у рудника и у мелкой жилы:
   - статичный рудник: пока игрок НЕ УШЁЛ С КЛЕТКИ, он может вернуться и
     доработать остаток (срок хранится в БД и переживает рестарт бота);
   - мелкая жила из исследования: исчезает при любом выходе.
   Уход с клетки обнуляет и то и другое (см. abandon_dig).
"""

import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from game.content_loader import MineDef, OreDef
from game.economy import mining
from game.economy import mining_config as mc
from models import Character, CharacterOre, MineVein, MiningEvent

# --- Клетка -------------------------------------------------------------------

def mine_at(character: Character) -> MineDef | None:
    if character.pos_x is None or character.pos_y is None:
        return None
    return mining.mine_at(character.pos_x, character.pos_y)


def is_safe_mine(x: int, y: int) -> bool:
    return mining.is_safe_mine(x, y)


# --- Состояние жил мира -------------------------------------------------------

async def ore_in_mine(db: AsyncSession, mine_id: str) -> int:
    row = await db.get(MineVein, mine_id)
    return row.ore_count if row is not None else 0


async def ore_counts(db: AsyncSession) -> dict[str, int]:
    """{mine_id: сколько руды} — для карты мини-аппа и панели локации.

    Игрок видит количество ДО похода сознательно: идти 40 клеток к пустому
    руднику — то, после чего перестают ходить. Обратная сторона в том, что
    полный рудник на глубоком кольце становится местом встречи, а там открытое
    PvP; это и задумано.
    """
    rows = (await db.execute(select(MineVein))).scalars().all()
    return {row.mine_id: row.ore_count for row in rows if row.ore_count > 0}


async def spawn_ore(db: AsyncSession, rng: random.Random) -> str | None:
    """Бросок на появление 1 руды в случайном НЕполном руднике.

    Вызывается на каждое завершённое исследование ЛЮБОГО игрока: руда в
    рудниках — общий ресурс, который наполняет активность всего сервера.
    Возвращает id рудника, куда легла руда, либо None.

    Выбор только среди неполных: иначе часть бросков уходила бы в уже полные
    жилы, и реальная скорость наполнения была бы ниже расчётной.
    """
    if rng.random() >= mc.ORE_SPAWN_CHANCE_PER_EXPLORATION:
        return None

    rows = (await db.execute(select(MineVein))).scalars().all()
    counts = {row.mine_id: row.ore_count for row in rows}
    candidates = [
        mine.id for mine in mining.all_mines()
        if counts.get(mine.id, 0) < mc.MINE_ORE_CAP
    ]
    if not candidates:
        return None

    mine_id = rng.choice(candidates)
    vein = await db.get(MineVein, mine_id)
    if vein is None:
        vein = MineVein(mine_id=mine_id, ore_count=0)
        db.add(vein)
    vein.ore_count += 1
    db.add(MiningEvent(kind="spawn", mine_id=mine_id))
    await db.flush()
    return mine_id


async def _take_one_ore(db: AsyncSession, mine_id: str) -> bool:
    """Атомарно снимает 1 руду с жилы. False — жила пуста.

    Именно здесь живёт защита от гонки: двое, начавшие добычу одновременно,
    не могут забрать один и тот же последний кусок.
    """
    vein = await db.get(MineVein, mine_id)
    if vein is None:
        db.add(MineVein(mine_id=mine_id, ore_count=0))
        await db.flush()
        return False
    result = await db.execute(
        update(MineVein)
        .where(MineVein.mine_id == mine_id, MineVein.ore_count > 0)
        .values(ore_count=MineVein.ore_count - 1)
    )
    if result.rowcount:
        await db.refresh(vein)
        return True
    return False


# --- Состояние добычи ---------------------------------------------------------

def is_digging(character: Character) -> bool:
    return character.mining_ends_at is not None


def dig_finished(character: Character, now: datetime | None = None) -> bool:
    if character.mining_ends_at is None:
        return False
    return (now or datetime.now(timezone.utc)) >= character.mining_ends_at


def remaining_seconds(character: Character, now: datetime | None = None) -> float:
    if character.mining_ends_at is None:
        return 0.0
    now = now or datetime.now(timezone.utc)
    return max((character.mining_ends_at - now).total_seconds(), 0.0)



def is_event_vein(character: Character) -> bool:
    """Добыча из мелкой жилы (её id нет — она не принадлежит карте)."""
    return is_digging(character) and character.mining_mine_id is None


def abandon_dig(character: Character) -> None:
    """Снимает состояние добычи с персонажа, НЕ трогая жилу.

    Почти всегда нужен не этот вызов, а cancel_dig ниже: он ещё и возвращает
    начатый кусок в жилу. Голый abandon_dig оставлен для мелкой жилы из
    исследования (возвращать некуда, её нет на карте) и для мест, где руда
    уже возвращена отдельно.
    """
    character.mining_ends_at = None
    character.mining_mine_id = None


async def release_ore(db: AsyncSession, mine_id: str) -> None:
    """Возвращает начатый кусок обратно в жилу.

    Руда резервируется в начале добычи, и сперва она при отмене пропадала.
    Это открывало griefing: начать и сразу бросить восемь раз — рудник пуст,
    повторить по всей карте — руды в мире нет вообще. Порчи чужого ресурса
    быть не должно, поэтому отмена только сбрасывает таймер.

    Клампим потолком на случай, если за время добычи в жилу успел упасть
    спавн: превышать кромку возврат не должен.
    """
    vein = await db.get(MineVein, mine_id)
    if vein is None:
        db.add(MineVein(mine_id=mine_id, ore_count=1))
    else:
        vein.ore_count = min(vein.ore_count + 1, mc.MINE_ORE_CAP)
    await db.flush()


async def cancel_dig(db: AsyncSession, character: Character) -> bool:
    """Отмена добычи с возвратом куска в жилу. True — добыча была.

    Единственная правильная точка отмены: «Бросить кирку», поражение в PvP,
    уход с клетки, массовый сброс. Кусок возвращается всегда — отменяющий не
    должен иметь возможности уничтожить общий ресурс.
    """
    if not is_digging(character):
        return False
    mine_id = character.mining_mine_id
    abandon_dig(character)
    if mine_id is not None:
        await release_ore(db, mine_id)
    await db.flush()
    return True


async def abandon_if_elsewhere(db: AsyncSession, character: Character) -> bool:
    """Обнуляет добычу, если игрок оказался не на той клетке. True — обнулили.

    Правило из дизайна: к статичному руднику можно вернуться и доработать
    остаток, ПОКА не ушёл с клетки; мелкая жила из исследования исчезает при
    любом выходе. Вызывается на каждом прибытии — пешком, на маунте и через
    ворота города.

    Уйти во время самой добычи нельзя (она блокирует действия), так что
    сработает это ровно в одном сценарии: бот перезапустился, игрока подняло
    наверх, и он ушёл вместо того, чтобы вернуться в забой.
    """
    if not is_digging(character):
        return False
    if character.mining_mine_id is None:
        abandon_dig(character)  # мелкая жила: её больше нет нигде
        return True
    mine = mining.mine_by_id(character.mining_mine_id)
    if mine is None or (mine.x, mine.y) != (character.pos_x, character.pos_y):
        await cancel_dig(db, character)
        return True
    return False


@dataclass
class DigStart:
    seconds: float
    ends_at: datetime


@dataclass
class DigResult:
    ore: OreDef
    grade_id: str
    grade_label: str
    xp: int
    levels_gained: int
    new_level: int


async def start_dig(
    db: AsyncSession, character: Character, mine: MineDef | None,
    rng: random.Random, now: datetime | None = None,
) -> DigStart | None:
    """Начинает добычу. None — в статичном руднике не осталось руды.

    mine=None — мелкая жила из исследования: она не берёт руду из общего пула
    рудников и всегда «есть», потому что её только что нашли.
    """
    now = now or datetime.now(timezone.utc)

    # Возврата к прерванной добыче нет вовсе: ушёл из забоя — начинаешь
    # заново. Правило выбрано осознанно ради простоты; цена ухода — только
    # потраченное время, кусок руды возвращается в жилу.
    if is_digging(character):
        await cancel_dig(db, character)

    if mine is not None:
        if not await _take_one_ore(db, mine.id):
            return None
        tier, event_vein = mine.tier, False
    else:
        tier, event_vein = mining.ring_tier(character.pos_x, character.pos_y), True

    seconds = mining.roll_dig_seconds(rng, tier, character.mining_level, event_vein)
    character.mining_ends_at = now + timedelta(seconds=seconds)
    character.mining_mine_id = mine.id if mine is not None else None
    await db.flush()
    return DigStart(seconds=seconds, ends_at=character.mining_ends_at)


async def finish_dig(
    db: AsyncSession, character: Character, rng: random.Random,
    dig_seconds: float | None = None,
) -> DigResult | None:
    """Завершает добычу и кладёт руду в инвентарь. None — добыча не идёт.

    dig_seconds — сколько добыча длилась по плану; идёт в журнал, чтобы на
    проде было видно, как на деле работает штраф за глубину. Момент старта не
    хранится (возврата к добыче нет, он не нужен), поэтому длительность
    передаёт вызывающий.
    """
    if not is_digging(character):
        return None

    event_vein = is_event_vein(character)
    if event_vein:
        tier = mining.ring_tier(character.pos_x, character.pos_y)
    else:
        mine = mining.mine_by_id(character.mining_mine_id)
        tier = mine.tier if mine is not None else 1

    ore_id = mining.roll_ore_id(rng, tier, event_vein)
    grade_id, grade_label = mining.roll_grade(rng, tier, character.mining_level, event_vein)
    await add_ore(db, character.id, ore_id, grade_id, 1)
    db.add(MiningEvent(
        kind="dig", mine_id=character.mining_mine_id, character_id=character.id,
        ore_id=ore_id, grade=grade_id,
        seconds=round(dig_seconds) if dig_seconds is not None else None,
    ))

    xp = mining.dig_xp(ore_id, grade_id)
    level, remainder, levels = mining.add_mining_xp(
        character.mining_level, character.mining_xp, xp
    )
    if levels:
        character.mining_level_at = datetime.now(timezone.utc)
    character.mining_level, character.mining_xp = level, remainder
    abandon_dig(character)
    await db.flush()

    return DigResult(
        ore=mining.ore_def(ore_id), grade_id=grade_id, grade_label=grade_label,
        xp=xp, levels_gained=levels, new_level=level,
    )


# --- Инвентарь руды -----------------------------------------------------------

async def add_ore(
    db: AsyncSession, character_id: int, ore_id: str, grade_id: str, amount: int
) -> None:
    row = await db.scalar(
        select(CharacterOre).where(
            CharacterOre.character_id == character_id,
            CharacterOre.ore_id == ore_id,
            CharacterOre.grade == grade_id,
        )
    )
    if row is None:
        row = CharacterOre(
            character_id=character_id, ore_id=ore_id, grade=grade_id, count=0
        )
        db.add(row)
    row.count += amount
    await db.flush()


async def get_ore(db: AsyncSession, character_id: int) -> list[tuple[OreDef, str, int]]:
    """(вид, градация, количество) — только непустые стаки, в порядке каталога
    видов, внутри вида от лучшей градации к худшей."""
    rows = (
        await db.execute(
            select(CharacterOre).where(
                CharacterOre.character_id == character_id, CharacterOre.count > 0
            )
        )
    ).scalars().all()
    by_key = {(r.ore_id, r.grade): r.count for r in rows}
    grades = [g[1] for g in reversed(mc.GRADES)]
    result: list[tuple[OreDef, str, int]] = []
    for definition in mining.ore_defs_ordered():
        for grade_id in grades:
            count = by_key.get((definition.id, grade_id))
            if count:
                result.append((definition, grade_id, count))
    return result


async def total_ore(db: AsyncSession, character_id: int) -> int:
    return sum(count for _d, _g, count in await get_ore(db, character_id))


# --- Обслуживание -------------------------------------------------------------

async def release_after_restart(db: AsyncSession) -> int:
    """После рестарта бота выбрасывает копающих наверх и ОТМЕНЯЕТ их добычу.

    Возврата к прерванной добыче в игре нет: ушёл из забоя — начинаешь
    заново. Рестарт выносит игрока наверх, значит он из забоя ушёл, и правило
    применяется без исключений. Цена — только потраченное время: начатые куски
    возвращаются в жилы, уничтожать общий ресурс рестарт не должен.

    Экран сбрасывается только тем, кто стоял в руднике: чужой сохранённый
    экран (скупщик, лавка) трогать незачем.
    """
    diggers = (
        await db.execute(
            select(Character).where(Character.mining_ends_at.is_not(None))
        )
    ).scalars().all()
    for character in diggers:
        await cancel_dig(db, character)

    await db.execute(
        update(Character).where(Character.screen == "mine").values(screen=None)
    )
    await db.commit()
    return len(diggers)


# --- Статистика для админки ---------------------------------------------------

async def stats(db: AsyncSession, hours: int = 24) -> dict:
    """Как горное дело ведёт себя на самом деле.

    Три вопроса, на которые текущий остаток в жилах не отвечает:
      - сколько руды и какой реально собрали (всего и за окно);
      - успевает ли спавн за добычей (это и есть «работает или нет»);
      - сколько на деле длится добыча.

    hours — окно для «свежих» чисел. Итоги за всё время считаются отдельно:
    по ним видно оборот, а по окну — текущий темп.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    async def _count(kind: str, window: bool) -> int:
        query = select(func.count()).select_from(MiningEvent).where(MiningEvent.kind == kind)
        if window:
            query = query.where(MiningEvent.created_at >= since)
        return int(await db.scalar(query) or 0)

    by_ore = (
        await db.execute(
            select(MiningEvent.ore_id, MiningEvent.grade, func.count())
            .where(MiningEvent.kind == "dig")
            .group_by(MiningEvent.ore_id, MiningEvent.grade)
        )
    ).all()

    seconds_rows = (
        await db.execute(
            select(func.avg(MiningEvent.seconds), func.max(MiningEvent.seconds))
            .where(MiningEvent.kind == "dig", MiningEvent.seconds.is_not(None))
        )
    ).first()

    from_veins = int(await db.scalar(
        select(func.count()).select_from(MiningEvent)
        .where(MiningEvent.kind == "dig", MiningEvent.mine_id.is_not(None))
    ) or 0)

    counts = await ore_counts(db)
    dug_total = await _count("dig", False)
    spawned_total = await _count("spawn", False)
    dug_window = await _count("dig", True)
    spawned_window = await _count("spawn", True)

    ores: dict[str, dict] = {}
    for ore_id, grade, count in by_ore:
        if ore_id is None:
            continue
        definition = mining.ore_def(ore_id)
        row = ores.setdefault(ore_id, {
            "name": definition.name if definition else ore_id,
            "emoji": definition.emoji if definition else "",
            "tier": definition.tier if definition else 0,
            "total": 0, "by_grade": {},
        })
        row["total"] += count
        row["by_grade"][grade or "?"] = count

    return {
        "hours": hours,
        "in_veins": sum(counts.values()),
        "veins_with_ore": len(counts),
        "veins_total": len(mining.all_mines()),
        "vein_cap": mc.MINE_ORE_CAP,
        "dug_total": dug_total,
        "spawned_total": spawned_total,
        # Из рудников против мелких жил: жилы не трогают общий пул, и если
        # добыча идёт в основном из них, конечность рудников ни на что не
        # влияет — это ровно тот перекос, который мы хотели увидеть.
        "dug_from_veins": from_veins,
        "dug_from_event_veins": dug_total - from_veins,
        "dug_window": dug_window,
        "spawned_window": spawned_window,
        "spawn_per_hour": round(spawned_window / hours, 2) if hours else 0,
        "dig_per_hour": round(dug_window / hours, 2) if hours else 0,
        "avg_dig_seconds": round(seconds_rows[0]) if seconds_rows and seconds_rows[0] else None,
        "max_dig_seconds": int(seconds_rows[1]) if seconds_rows and seconds_rows[1] else None,
        "ores": sorted(ores.values(), key=lambda r: (r["tier"], r["name"])),
        "by_mine": [
            {"id": m.id, "name": m.name, "tier": m.tier, "ore": counts.get(m.id, 0)}
            for m in mining.all_mines()
        ],
    }


async def refill_all_veins(db: AsyncSession, amount: int | None = None) -> int:
    """Наполняет ВСЕ жилы до указанного количества (по умолчанию до кромки).

    Тестовый инструмент админки: если карту выкопали досуха, ждать спавна
    ради проверки чего-то другого — пустая трата времени. В журнал события
    НЕ пишутся: это не игровой спавн, и он не должен искажать статистику,
    по которой мы судим, работает ли настоящий.
    """
    target = mc.MINE_ORE_CAP if amount is None else max(0, min(amount, mc.MINE_ORE_CAP))
    existing = {
        row.mine_id: row
        for row in (await db.execute(select(MineVein))).scalars().all()
    }
    added = 0
    for mine in mining.all_mines():
        vein = existing.get(mine.id)
        if vein is None:
            db.add(MineVein(mine_id=mine.id, ore_count=target))
            added += target
        elif vein.ore_count < target:
            added += target - vein.ore_count
            vein.ore_count = target
    await db.commit()
    return added
