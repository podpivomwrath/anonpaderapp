"""scripts/delete_character.py: удаление одного персонажа целиком."""

import importlib.util
import sys
from pathlib import Path

import pytest
from sqlalchemy import func, select

from models import Character, CharacterFish, CharacterStats, User, Wallet

_SPEC = importlib.util.spec_from_file_location(
    "delete_character_script", Path(__file__).resolve().parent.parent / "scripts" / "delete_character.py"
)
dc = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = dc  # dataclass с отложенными аннотациями ищет модуль здесь
_SPEC.loader.exec_module(dc)


async def _count(db, model, **where) -> int:
    query = select(func.count()).select_from(model)
    for key, value in where.items():
        query = query.where(getattr(model, key) == value)
    return await db.scalar(query)


@pytest.mark.asyncio
async def test_summary_reports_wallet_and_related_rows(db_session, make_character) -> None:
    character = await make_character(farm=500, donate=77)
    db_session.add(CharacterFish(
        character_id=character.id, fish_id="monolith_catfish", grade="common", total_grams=1500,
    ))
    await db_session.flush()

    summary = await dc.summarize(db_session, character.id)

    assert summary.name == character.name
    assert summary.farm_currency == 500 and summary.donate_currency == 77
    assert any(key.startswith("character_fish.character_id") for key in summary.counts)
    # Донат пропадёт - об этом нужно предупредить до удаления.
    assert any("донат" in w.lower() for w in summary.warnings)


@pytest.mark.asyncio
async def test_purge_removes_only_that_character(db_session, make_character) -> None:
    victim = await make_character(farm=10)
    other = await make_character(farm=20)
    for c in (victim, other):
        db_session.add(CharacterFish(
            character_id=c.id, fish_id="monolith_catfish", grade="common", total_grams=1000,
        ))
    await db_session.flush()
    victim_id, other_id, victim_user_id = victim.id, other.id, victim.user_id

    removed = await dc.purge(db_session, victim_id)
    await db_session.commit()

    assert removed["characters"] == 1
    assert await db_session.get(Character, victim_id) is None
    assert await _count(db_session, Wallet, character_id=victim_id) == 0
    assert await _count(db_session, CharacterStats, character_id=victim_id) == 0
    assert await _count(db_session, CharacterFish, character_id=victim_id) == 0
    # Запись пользователя остаётся: vk_id сохраняется, онбординг пойдёт заново.
    assert await db_session.get(User, victim_user_id) is not None
    # Чужой персонаж и его данные не тронуты.
    assert await db_session.get(Character, other_id) is not None
    assert await _count(db_session, Wallet, character_id=other_id) == 1
    assert await _count(db_session, CharacterFish, character_id=other_id) == 1


@pytest.mark.asyncio
async def test_find_by_name_is_exact_and_case_insensitive(db_session, make_character) -> None:
    character = await make_character()
    character.name = "Кригер"
    await db_session.flush()

    assert [c.id for c in await dc.find_by_name(db_session, "кригер")] == [character.id]
    assert await dc.find_by_name(db_session, "Криг") == []
