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

from sqlalchemy import desc, select
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
    db: AsyncSession, order_column, value_fn, limit: int, min_value: int = 1
) -> list[BoardEntry]:
    """Топ по колонке самого персонажа (победы/убийства/уровень рыбалки).

    min_value отсекает тех, кто ещё не начинал: список из десяти нулей —
    не топ, а шум.
    """
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(
                Character.name, order_column, Character.active_title_id,
                Character.premium_until, Character.pvp_losses,
            )
            .where(Character.creation_state.is_(None), order_column >= min_value)
            .order_by(desc(order_column), Character.pvp_losses.asc())
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
    )


async def fish_weight_board(db: AsyncSession, limit: int = 10) -> list[BoardEntry]:
    """Самые тяжёлые пойманные экземпляры — по одному лучшему на игрока.

    Иначе один рыбак с крупным озером занял бы весь топ своими рекордами по
    пяти видам сразу, и таблица перестала бы показывать, кто чего добился.
    """
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(
                Character.name, CharacterFishRecord.fish_id,
                CharacterFishRecord.weight_grams, Character.active_title_id,
                Character.premium_until,
            )
            .join(Character, Character.id == CharacterFishRecord.character_id)
            .where(Character.creation_state.is_(None))
            .order_by(desc(CharacterFishRecord.weight_grams))
            .limit(limit * 8)
        )
    ).all()

    seen: set[str] = set()
    entries: list[BoardEntry] = []
    for name, fish_id, grams, title_id, premium_until in rows:
        if name in seen:
            continue
        seen.add(name)
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
