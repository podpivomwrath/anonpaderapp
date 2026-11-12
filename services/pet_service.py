"""Питомцы (2026-11-12, владелец): владение, слот и Пепельный дракон.

Питомец не даёт статов, только свою механику (game/economy/pet_config.py).
Каждого вида у персонажа не больше одного; в слоте - один (character.pet_id),
остальные ждут в «Героя» и меняются в любой момент. Механики живут там,
где их событие: хорёк и плетельщик - bot/pet_finds.py, ворон - bot/raven.py,
гончая - bot/hound.py, руна и дракон - bot/handlers/pets.py.
"""

from __future__ import annotations

import json
import random
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import pet_config as pc
from models import AshDragon, Character, CharacterMount, CharacterPet, User

CONTENT = Path(__file__).resolve().parent.parent / "content" / "pets" / "pets.json"


@dataclass(frozen=True)
class PetDef:
    id: str
    name: str
    emoji: str
    effect: str
    flavor: str
    how: str


_defs: dict[str, PetDef] | None = None


def defs() -> dict[str, PetDef]:
    global _defs
    if _defs is None:
        raw = json.loads(CONTENT.read_text(encoding="utf-8"))
        loaded = {r["id"]: PetDef(**r) for r in raw}
        _defs = {pid: loaded[pid] for pid in pc.ORDER}
    return _defs


def pet_def(pet_id: str | None) -> PetDef | None:
    return defs().get(pet_id) if pet_id else None


def label(pet_id: str) -> str:
    d = defs()[pet_id]
    return f"{d.emoji} {d.name}"


def has_active(character: Character, pet_id: str) -> bool:
    return getattr(character, "pet_id", None) == pet_id


class PetError(Exception):
    pass


async def owned_ids(db: AsyncSession, character_id: int) -> list[str]:
    rows = (await db.scalars(select(CharacterPet.pet_id).where(CharacterPet.character_id == character_id))).all()
    return [pid for pid in pc.ORDER if pid in set(rows)]


async def owns(db: AsyncSession, character_id: int, pet_id: str) -> bool:
    return await db.scalar(select(CharacterPet.id).where(
        CharacterPet.character_id == character_id, CharacterPet.pet_id == pet_id,
    )) is not None


async def grant(db: AsyncSession, character: Character, pet_id: str) -> bool:
    """Выдать питомца. True - выдан сейчас; False - уже был (второй раз не
    выдаётся). Пустой слот занимает сразу: новый питомец должен быть виден."""
    if pet_id not in defs():
        raise PetError("Такого питомца нет.")
    if await owns(db, character.id, pet_id):
        return False
    try:
        async with db.begin_nested():
            db.add(CharacterPet(character_id=character.id, pet_id=pet_id))
            await db.flush()
    except IntegrityError:
        return False  # параллельный запрос выдал того же
    if character.pet_id is None:
        character.pet_id = pet_id
    from services import resource_log

    resource_log.add(db, character.id, "pet", pet_id, 1)
    await db.flush()
    return True


async def wear(db: AsyncSession, character: Character, pet_id: str) -> None:
    if pet_id not in defs():
        raise PetError("Такого питомца нет.")
    if character.pet_id == pet_id:
        raise PetError("Этот питомец уже с вами.")
    if not await owns(db, character.id, pet_id):
        raise PetError("Этого питомца у вас нет.")
    character.pet_id = pet_id
    await db.flush()


async def remove(db: AsyncSession, character: Character) -> None:
    if character.pet_id is None:
        raise PetError("Питомца в слоте нет.")
    character.pet_id = None
    await db.flush()


def info(pet_id: str) -> dict:
    d = defs()[pet_id]
    return {"id": d.id, "name": d.name, "emoji": d.emoji, "icon": f"pet:{d.id}",
            "effect": d.effect, "flavor": d.flavor}


async def payload(db: AsyncSession, character: Character) -> dict | None:
    """Слот питомца в силуэте «Героя»: кто с вами и кто ждёт. None -
    питомцев нет совсем, слот пустой."""
    owned = await owned_ids(db, character.id)
    current = character.pet_id if character.pet_id in owned else None
    if not owned:
        return None
    return {"worn": info(current) if current else None,
            "bag": [info(pid) for pid in owned if pid != current]}


async def holders(db: AsyncSession, pet_id: str) -> list[tuple[Character, int]]:
    """Все, у кого этот питомец в слоте, с vk_id."""
    rows = (await db.execute(
        select(Character, User.vk_id).join(User, User.id == Character.user_id).where(
            Character.pet_id == pet_id, Character.creation_state.is_(None),
        )
    )).all()
    return [(c, vk) for c, vk in rows if vk is not None]


# --- Пепельный дракон --------------------------------------------------------


def new_code(rng: random.Random | None = None) -> str:
    pick = rng.choice if rng is not None else secrets.choice
    return "".join(pick(pc.CODE_ALPHABET) for _ in range(pc.CODE_LENGTH))


def normalize(text: str | None) -> str:
    """Что игрок прислал, без пробелов и кавычек: код копируют из сообщения
    руны, и вместе с ним легко прихватить лишнее."""
    return "".join(ch for ch in (text or "") if not ch.isspace() and ch not in "«»\"'.,!?")


async def dragon_state(db: AsyncSession) -> AshDragon:
    """Строка дракона; при первом обращении - с новым кодом."""
    state = await db.get(AshDragon, 1)
    if state is None:
        try:
            async with db.begin_nested():
                db.add(AshDragon(id=1, code=new_code()))
                await db.flush()
        except IntegrityError:
            pass
        state = await db.get(AshDragon, 1)
    return state


async def claim_dragon(db: AsyncSession, character: Character, now: datetime | None = None) -> bool:
    """Разбудить дракона. True - этот персонаж первый; дальше - маунт и титул.
    Условный UPDATE: из двух одновременных верных ответов пройдёт один."""
    from services import mount_service, title_service

    now = now or datetime.now(timezone.utc)
    await dragon_state(db)
    won = await db.execute(
        update(AshDragon).where(AshDragon.id == 1, AshDragon.awakened_at.is_(None))
        .values(awakened_by=character.id, awakened_at=now)
        .execution_options(synchronize_session=False)
    )
    if not won.rowcount:
        return False
    await mount_service.grant(db, character, pc.DRAGON_MOUNT_ID)
    await title_service.unlock(db, character, pc.DRAGON_TITLE_ID)
    character.active_title_id = pc.DRAGON_TITLE_ID
    await db.flush()
    return True


async def dragon_owner(db: AsyncSession) -> Character | None:
    """У кого дракон сейчас (его передают из рук в руки)."""
    row = await db.scalar(select(CharacterMount.character_id).where(CharacterMount.mount_id == pc.DRAGON_MOUNT_ID))
    return await db.get(Character, row) if row is not None else None
