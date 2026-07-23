"""Окно распределения статов в чате (патч 11, блок 1): рендер и финализация
с перепроверкой очков (гонка с мини-аппом)."""

from sqlalchemy import select

from models import CharacterStats
from services import stat_alloc_service as sas


async def _stats(db_session, character) -> CharacterStats:
    return await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character.id)
    )


def test_levelup_header() -> None:
    assert sas.levelup_header(5) == "✨ Метка окрепла. Уровень 5."


def test_snapshot_maps_all_five_stats() -> None:
    class FakeStats:
        strength = 16
        agility = 15
        intellect = 15
        vitality = 15
        will = 15

    snap = sas.snapshot(FakeStats())
    assert snap == {"str": 16, "agi": 15, "int": 15, "vit": 15, "wil": 15}


def test_render_window_shows_remaining_pool_after_pending() -> None:
    char_stats = {"str": 15, "agi": 15, "int": 15, "vit": 15, "wil": 15}
    text = sas.render_window("Заголовок", 5, char_stats, {"str": 2})
    assert "Свободных очков: 3" in text
    assert "Сила: 15 (+2)" in text
    assert "Ловкость: 15" in text
    assert "(+0)" not in text


def test_render_window_no_pending_shows_full_pool() -> None:
    char_stats = {"str": 15, "agi": 15, "int": 15, "vit": 15, "wil": 15}
    text = sas.render_window("Заголовок", 5, char_stats, {})
    assert "Свободных очков: 5" in text


def test_render_readonly_has_no_pool_line() -> None:
    char_stats = {"str": 15, "agi": 15, "int": 15, "vit": 15, "wil": 15}
    text = sas.render_readonly("Заголовок", char_stats)
    assert "Свободных очков" not in text
    assert "Сила: 15" in text


def test_render_final_without_shortfall() -> None:
    char_stats = {"str": 17, "agi": 15, "int": 15, "vit": 15, "wil": 15}
    text = sas.render_final(char_stats, None)
    assert text.startswith("✨ Характеристики закреплены.")
    assert "Сила 17" in text


def test_render_final_with_shortfall_note_prefixed() -> None:
    text = sas.render_final({"str": 15, "agi": 15, "int": 15, "vit": 15, "wil": 15}, "Часть очков уже была вложена в другом месте. Закреплено: 2.")
    assert text.startswith("Часть очков уже была вложена")
    assert "✨ Характеристики закреплены." in text


async def test_finalize_applies_full_request_when_budget_sufficient(db_session, make_character) -> None:
    character = await make_character()
    stats = await _stats(db_session, character)
    stats.unspent_points = 5

    result = await sas.finalize(db_session, stats, {"str": 2, "vit": 1})

    assert result.applied_total == 3
    assert result.requested_total == 3
    assert stats.strength == 17
    assert stats.vitality == 16
    assert stats.unspent_points == 2


async def test_finalize_partial_when_budget_spent_elsewhere(db_session, make_character) -> None:
    """Гонка: игрок нажимал (+stat) когда пул был 5, но к моменту "Готово"
    мини-апп уже потратил часть очков — применяем сколько можем, по STAT_ORDER."""
    character = await make_character()
    stats = await _stats(db_session, character)
    stats.unspent_points = 1  # уже потрачено 4 из исходных 5 где-то ещё

    result = await sas.finalize(db_session, stats, {"str": 2, "agi": 3})

    assert result.requested_total == 5
    assert result.applied_total == 1
    assert stats.strength == 16  # str идёт первым в STAT_ORDER
    assert stats.agility == 15  # на agi уже не хватило
    assert stats.unspent_points == 0


async def test_finalize_zero_budget_applies_nothing(db_session, make_character) -> None:
    character = await make_character()
    stats = await _stats(db_session, character)
    stats.unspent_points = 0

    result = await sas.finalize(db_session, stats, {"str": 2})

    assert result.applied_total == 0
    assert result.requested_total == 2
    assert stats.strength == 15
    assert stats.unspent_points == 0


async def test_finalize_char_stats_reflects_post_apply_values(db_session, make_character) -> None:
    character = await make_character()
    stats = await _stats(db_session, character)
    stats.unspent_points = 3

    result = await sas.finalize(db_session, stats, {"wil": 3})

    assert result.char_stats["wil"] == 18
    assert result.char_stats == sas.snapshot(stats)
