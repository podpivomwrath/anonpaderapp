"""Сервис создания персонажа (онбординг-FSM).

Прогресс хранится в characters.creation_state (NULL = создание завершено):
бросивший на середине игрок продолжает с того же шага, не с начала.
Пока имя не выбрано, персонаж существует с плейсхолдер-именем "~<vk_id>" —
тильда не проходит валидацию никнеймов, поэтому коллизии исключены.
"""

import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.world import world_config as wc
from models import Character, CharacterStats, User, Wallet

BANNED_WORDS_PATH = Path(__file__).resolve().parent.parent / "content" / "banned_words.txt"

# Шаги FSM (значения characters.creation_state)
STATE_LORE = "lore_intro"
STATE_NICKNAME = "nickname_input"
STATE_CLASS_SELECT = "class_select"
STATE_CLASS_CONFIRM = "class_confirm"
STATE_REGION_SELECT = "region_select"
STATE_REGION_CONFIRM = "region_confirm"

NICKNAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_]{3,16}$")


def _placeholder_name(vk_id: int) -> str:
    return f"~{vk_id}"


@lru_cache(maxsize=1)
def _banned_words() -> tuple[str, ...]:
    if not BANNED_WORDS_PATH.exists():
        return ()
    words = []
    for line in BANNED_WORDS_PATH.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if word and not word.startswith("#"):
            words.append(word)
    return tuple(words)


def reload_banned_words() -> None:
    """Сбросить кэш (файл пополняется без правки кода)."""
    _banned_words.cache_clear()


async def get_or_create_user(db: AsyncSession, vk_id: int) -> User:
    user = await db.scalar(select(User).where(User.vk_id == vk_id))
    if user is None:
        user = User(vk_id=vk_id, last_login=datetime.now(timezone.utc))
        db.add(user)
        await db.flush()
    else:
        user.last_login = datetime.now(timezone.utc)
    return user


async def get_character(db: AsyncSession, vk_id: int) -> Character | None:
    """Персонаж игрока, включая незавершённого (в процессе создания)."""
    return await db.scalar(
        select(Character)
        .join(User, User.id == Character.user_id)
        .where(User.vk_id == vk_id)
    )


async def begin_creation(db: AsyncSession, user: User) -> Character:
    """Создаёт заготовку персонажа.

    Сюжетный онбординг: сцена пробуждения показывается без кнопки и сразу
    ждёт никнейм, поэтому стартовое состояние — NICKNAME (STATE_LORE оставлен
    для восстановления старых записей).
    """
    character = Character(
        user_id=user.id,
        name=_placeholder_name(user.vk_id),
        base_class="warrior",  # плейсхолдер, перезаписывается на шаге класса
        level=1,
        experience=0,
        creation_state=STATE_NICKNAME,
    )
    db.add(character)
    await db.flush()
    db.add(CharacterStats(character_id=character.id))
    db.add(Wallet(character_id=character.id))
    return character


async def set_state(db: AsyncSession, character: Character, state: str | None) -> None:
    character.creation_state = state
    await db.flush()


def validate_nickname_format(nickname: str) -> str | None:
    """Код ошибки "invalid" (длина/символы) или None."""
    if not (3 <= len(nickname) <= 16):
        return "invalid"
    if not NICKNAME_RE.match(nickname):
        return "invalid"
    return None


def contains_banned_word(nickname: str) -> bool:
    lowered = nickname.lower()
    return any(word in lowered for word in _banned_words())


async def is_nickname_taken(
    db: AsyncSession, nickname: str, exclude_character_id: int | None = None
) -> bool:
    query = select(Character.id).where(func.lower(Character.name) == nickname.lower())
    if exclude_character_id is not None:
        query = query.where(Character.id != exclude_character_id)
    return (await db.scalar(query)) is not None


async def try_set_nickname(
    db: AsyncSession, character: Character, nickname: str
) -> str | None:
    """Полная валидация + установка.

    Возвращает код ошибки ("invalid" | "banned" | "taken") или None (успех).
    Текст игроку подбирает хендлер (реплики Хранителя Списков в content/npc/).
    """
    nickname = nickname.strip()
    error = validate_nickname_format(nickname)
    if error:
        return error
    if contains_banned_word(nickname):
        return "banned"
    if await is_nickname_taken(db, nickname, exclude_character_id=character.id):
        return "taken"
    character.name = nickname
    await set_state(db, character, STATE_CLASS_SELECT)
    return None


async def apply_class(db: AsyncSession, character: Character, base_class: str) -> None:
    """Устанавливает класс и стартовое распределение статов (85 очков)."""
    start = bc.STARTING_STATS[base_class]
    character.base_class = base_class
    stats = await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )
    stats.strength = start["STR"]
    stats.agility = start["AGI"]
    stats.intellect = start["INT"]
    stats.vitality = start["VIT"]
    stats.will = start["WIL"]
    await set_state(db, character, STATE_REGION_SELECT)


async def complete_creation(
    db: AsyncSession, character: Character, region: str
) -> CharacterStats:
    """Финал: регион (постоянный выбор), позиция в родном городе, сброс FSM."""
    character.region = region
    character.pos_x, character.pos_y = wc.CITY_COORDS[region]
    await set_state(db, character, None)
    return await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )
