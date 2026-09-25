"""Венец топ-1 (патч 91): кто держит доску и что ему за это.

Венцы лежат КОЛОНКОЙ на персонаже — `{id доски: когда получен}`. Не отдельной
таблицей со связью: бонус читается там, где до базы уже не дотянуться
(experience_service.add_experience принимает готового персонажа и про сессию
не знает — и не должен, это единственная точка начисления опыта в игре).
Связь пришлось бы подгружать лениво, а ленивая подгрузка в асинхронном коде
падает с MissingGreenlet.

Пересчёт раз в сутки. Живой означал бы смену характеристик посреди боя —
движок берёт их на старте сессии — и мигание венца по нескольку раз за вечер
при восемнадцати игроках.

Сервис не отправляет сообщений: он возвращает список смещённых, а кому и как
писать, решает хендлер. Тот же порядок, что у остальных проактивных
уведомлений в проекте.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import crown_config as cc
from models import Character
from services import leaderboard_service


@dataclass
class Displaced:
    """Кого и с какой доски сместили — для уведомления."""

    character_id: int
    board: str
    #: Кто занял место. None — доска опустела вовсе.
    successor_name: str | None


def _crowns(character: Character) -> dict:
    """Венцы персонажа, безопасно.

    getattr, а не прямое обращение: множители зовут не только с настоящей
    моделью. Движок боя и несколько сервисов принимают облегчённые
    объекты-заглушки «как персонаж», и у них этого поля нет. Отсутствие поля
    честно означает «венца нет» - объект, у которого его не бывает, венца
    держать и не может.
    """
    return getattr(character, "crowns", None) or {}


def has_crown(character: Character, board: str) -> bool:
    return board in _crowns(character)


def crown_boards(character: Character) -> list[str]:
    """Доски, которые персонаж держит, в порядке BOARDS.

    Порядок именно фиксированный: рамка в шапке мини-аппа одна, и брать её
    «первой попавшейся» значило бы менять её от показа к показу вслед за
    порядком ключей в JSON.
    """
    held = _crowns(character)
    return [board for board in leaderboard_service.BOARDS if board in held]


def held_since(character: Character, board: str) -> datetime | None:
    raw = _crowns(character).get(board)
    return datetime.fromisoformat(raw) if raw else None


def xp_multiplier(character: Character) -> float:
    return 1.0 + cc.XP_BONUS if has_crown(character, leaderboard_service.BOARD_PVP) else 1.0


def mob_gold_multiplier(character: Character) -> float:
    return 1.0 + cc.MOB_GOLD_BONUS if has_crown(character, leaderboard_service.BOARD_KILLS) else 1.0


def fish_sale_multiplier(character: Character) -> float:
    board = leaderboard_service.BOARD_FISHING
    return 1.0 + cc.FISH_SALE_BONUS if has_crown(character, board) else 1.0


def travel_multiplier(character: Character) -> float:
    board = leaderboard_service.BOARD_FISH_WEIGHT
    return 1.0 - cc.TRAVEL_CUT if has_crown(character, board) else 1.0


def mining_multiplier(character: Character) -> float:
    board = leaderboard_service.BOARD_MINING
    return 1.0 - cc.MINING_CUT if has_crown(character, board) else 1.0


def _set(character: Character, crowns: dict[str, str]) -> None:
    """JSON-колонку надо ЗАМЕНЯТЬ целиком.

    Правка словаря на месте не помечает объект изменённым, и SQLAlchemy
    молча не сохранит её (mutable tracking для JSON по умолчанию выключен).
    """
    character.crowns = dict(crowns)


async def recompute(db: AsyncSession) -> list[Displaced]:
    """Сверяет венцы с досками. Возвращает тех, кого сместили.

    Тот, кто остался первым, венца не теряет и отсчёт удержания сохраняет:
    если переписывать дату каждые сутки, «держишь четыре дня» не вырастет
    никогда.
    """
    leaders: dict[str, int | None] = {}
    for board in leaderboard_service.BOARDS:
        leaders[board] = await leaderboard_service.leader_character_id(db, board)

    wanted: dict[int, set[str]] = {}
    for board, leader_id in leaders.items():
        if leader_id is not None:
            wanted.setdefault(leader_id, set()).add(board)

    # Берём и нынешних держателей, и новых лидеров: у первых венец может
    # исчезнуть, у вторых появиться.
    characters = (
        await db.scalars(
            select(Character).where(Character.creation_state.is_(None))
        )
    ).all()

    now = datetime.now(timezone.utc).isoformat()
    names = {c.id: c.name for c in characters}
    displaced: list[Displaced] = []

    for character in characters:
        held = set(_crowns(character))
        should = wanted.get(character.id, set())
        if held == should:
            continue
        for board in sorted(held - should):
            successor_id = leaders.get(board)
            displaced.append(
                Displaced(character.id, board, names.get(successor_id) if successor_id else None)
            )
        _set(
            character,
            {
                board: _crowns(character).get(board) or now
                for board in should
            },
        )

    await db.flush()
    return displaced


async def holders(db: AsyncSession) -> dict[str, int]:
    """Доска -> id держателя. Для показа венцов там, где персонажа под рукой
    нет (чужие профили, строки топа)."""
    rows = (
        await db.scalars(select(Character).where(Character.creation_state.is_(None)))
    ).all()
    found: dict[str, int] = {}
    for character in rows:
        for board in _crowns(character):
            found[board] = character.id
    return found
