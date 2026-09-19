"""Общие топы (патч 58): PvP, убийства, уровень рыбалки, вес рыбы.

Раньше топ был один (PvP) и жил прямо в pvp_service. С добавлением ещё трёх
таблиц нужна общая точка: у всех одинаковая форма строки (место, имя, титул,
премиум) и одинаковые правила отбора (только завершившие создание персонажа).
Разъезд этих правил между четырьмя вкладками был бы неизбежен.

pvp_service.leaderboard намеренно НЕ удалён и не продублирован: PvP-топ
продолжает жить там (его использует текстовая команда /топ), здесь он только
переиспользуется, чтобы правила сортировки не разошлись.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import fishing
from models import Character, CharacterFishRecord
from services import title_service

#: Идентификаторы вкладок. Мини-апп присылает именно эти строки.
BOARD_PVP = "pvp"
BOARD_KILLS = "kills"
BOARD_FISHING = "fishing"
BOARD_FISH_WEIGHT = "fish_weight"
BOARD_MINING = "mining"

BOARDS = (BOARD_PVP, BOARD_KILLS, BOARD_FISHING, BOARD_FISH_WEIGHT, BOARD_MINING)

BOARD_TITLES = {
    BOARD_PVP: "⚔️ PvP",
    BOARD_KILLS: "💀 Убийства",
    BOARD_FISHING: "🎣 Рыбалка",
    BOARD_FISH_WEIGHT: "🐟 Рекорды по рыбе",
    BOARD_MINING: "⛏ Горное дело",
}


@dataclass
class BoardEntry:
    rank: int
    name: str
    #: Готовая строка достижения — «14 побед», «1 240 мобов», «ур. 37»,
    #: «12,4 кг · Костяная щука». Формат принадлежит СЕРВЕРУ: клиент уже
    #: однажды пересказывал серверное правило своими словами и врал
    #: (правило пресетов, патч 57).
    value: str
    title: str | None = None
    premium: bool = False


def _premium(premium_until: datetime | None, now: datetime) -> bool:
    return premium_until is not None and premium_until > now


def _thousands(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return few
    return many


async def _character_board(
    db: AsyncSession, order_column, value_fn, limit: int, min_value: int = 1,
    tiebreak=None,
) -> list[BoardEntry]:
    """Топ по колонке самого персонажа (победы/убийства/уровень ремесла).

    min_value отсекает тех, кто ещё не начинал: список из десяти нулей —
    не топ, а шум.

    tiebreak — чем разрешать равенство. Раньше это ВСЕГДА было число
    PvP-поражений, из-за чего в топе рыбалки двух равных рыбаков разделял их
    боевой послужной список. Теперь каждая доска называет своё правило, а
    общий запасной вариант — id персонажа: кто раньше в игре, тот выше.
    """
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(
                Character.name, order_column, Character.active_title_id,
                Character.premium_until, Character.pvp_losses,
            )
            .where(Character.creation_state.is_(None), order_column >= min_value)
            .order_by(desc(order_column), *(tiebreak or (Character.id.asc(),)))
            .limit(limit)
        )
    ).all()
    return [
        BoardEntry(
            rank=i, name=name, value=value_fn(value, losses),
            title=title_service.name_of(title_id) if title_id else None,
            premium=_premium(premium_until, now),
        )
        for i, (name, value, title_id, premium_until, losses) in enumerate(rows, start=1)
    ]


async def pvp_board(db: AsyncSession, limit: int = 10) -> list[BoardEntry]:
    return await _character_board(
        db, Character.pvp_wins,
        lambda wins, losses: f"{wins} "
                             f"{_plural(wins, 'победа', 'победы', 'побед')} · {losses} "
                             f"{_plural(losses, 'поражение', 'поражения', 'поражений')}",
        limit,
        # У PvP меньшее число поражений — осмысленный признак, тут его и
        # оставляем: одинаковые победы при разных поражениях это не ничья.
        tiebreak=(Character.pvp_losses.asc(), Character.id.asc()),
    )


async def kills_board(db: AsyncSession, limit: int = 10) -> list[BoardEntry]:
    """Всего убито мобов за всё время. Счётчик заведён патчем 58 и стартует с
    нуля у всех: истории боёв с мобами в базе нет, пересчитать нечем."""
    return await _character_board(
        db, Character.mobs_killed,
        lambda kills, _losses: f"{_thousands(kills)} "
                               f"{_plural(kills, 'моб', 'моба', 'мобов')}",
        limit,
    )


async def fishing_board(db: AsyncSession, limit: int = 10) -> list[BoardEntry]:
    """Уровень рыбалки. Потолка у него нет, поэтому топ не упирается в
    «все на максимуме» — в отличие от боевого уровня."""
    return await _character_board(
        db, Character.fishing_level,
        lambda level, _losses: f"ур. {level}",
        limit, min_value=2,
        tiebreak=(Character.fishing_level_at.asc().nulls_last(), Character.id.asc()),
    )


async def fish_weight_board(db: AsyncSession, limit: int = 10) -> list[BoardEntry]:
    """Самые тяжёлые пойманные экземпляры — ровно ПО ОДНОМУ на игрока.

    Раньше бралось limit*8 строк и схлопывалось по имени уже в питоне: рыбак
    с десятком рекордов вытеснял остальных из выборки ещё до дедупликации, и
    они не попадали в топ вообще. Теперь лучший экземпляр каждого игрока
    выбирается в самом запросе, и limit значит ровно то, что написано.
    """
    now = datetime.now(timezone.utc)
    best = (
        select(
            CharacterFishRecord.character_id.label("character_id"),
            func.max(CharacterFishRecord.weight_grams).label("weight_grams"),
        )
        .group_by(CharacterFishRecord.character_id)
        .subquery()
    )
    rows = (
        await db.execute(
            select(
                Character.id, Character.name, CharacterFishRecord.fish_id,
                CharacterFishRecord.weight_grams, Character.active_title_id,
                Character.premium_until, CharacterFishRecord.caught_at,
            )
            .join(best, best.c.character_id == CharacterFishRecord.character_id)
            .join(Character, Character.id == CharacterFishRecord.character_id)
            .where(
                Character.creation_state.is_(None),
                CharacterFishRecord.weight_grams == best.c.weight_grams,
            )
            # Ничья по весу — у кого рекорд старше, тот и выше.
            .order_by(desc(CharacterFishRecord.weight_grams), CharacterFishRecord.caught_at.asc())
            .limit(limit * 2)
        )
    ).all()

    seen: set[int] = set()
    entries: list[BoardEntry] = []
    for character_id, name, fish_id, grams, title_id, premium_until, _caught_at in rows:
        # Страховка на случай, когда у игрока два вида весят одинаково и оба
        # прошли фильтр максимума: в топе он всё равно должен быть один раз.
        # Ключ - id, а не имя: имена сейчас уникальны (uq_characters_name_lower),
        # но правило топа не должно держаться на чужом индексе - иначе в день,
        # когда имена разрешат повторять, второй игрок молча исчезнет из топа.
        if character_id in seen:
            continue
        seen.add(character_id)
        definition = fishing.fish_def(fish_id)
        label = definition.name if definition else fish_id
        emoji = f"{definition.emoji} " if definition else ""
        entries.append(BoardEntry(
            rank=len(entries) + 1, name=name,
            value=f"{fishing.format_kg(grams)} · {emoji}{label}",
            title=title_service.name_of(title_id) if title_id else None,
            premium=_premium(premium_until, now),
        ))
        if len(entries) >= limit:
            break
    return entries


async def mining_board(db: AsyncSession, limit: int = 10) -> list[BoardEntry]:
    """Уровень горного дела. Как и у рыбалки, потолка нет — топ не упирается
    в «все на максимуме»."""
    return await _character_board(
        db, Character.mining_level,
        lambda level, _losses: f"ур. {level}",
        limit, min_value=2,
        tiebreak=(Character.mining_level_at.asc().nulls_last(), Character.id.asc()),
    )


_LOADERS = {
    BOARD_PVP: pvp_board,
    BOARD_KILLS: kills_board,
    BOARD_FISHING: fishing_board,
    BOARD_FISH_WEIGHT: fish_weight_board,
    BOARD_MINING: mining_board,
}


async def board(db: AsyncSession, board_id: str, limit: int = 10) -> list[BoardEntry]:
    loader = _LOADERS.get(board_id)
    if loader is None:
        raise ValueError(f"неизвестный топ: {board_id}")
    return await loader(db, limit)
