"""Массовый сброс зависших состояний (патч 30, расширен патчем 58).

Главное, что здесь проверяется, — сброс НЕ отнимает у игрока ничего, кроме
состояния «я куда-то иду / удю». Ошибка в эту сторону тихая и дорогая:
заметят её не сразу, а восстанавливать будет нечего.
"""

from datetime import datetime, timedelta, timezone

import pytest

from models import CharacterFish, MountTravel
from services import maintenance_service


@pytest.mark.asyncio
async def test_reset_cancels_travel_without_moving_the_character(
    db_session, make_character
) -> None:
    character = await make_character()
    character.pos_x, character.pos_y = 12, -8
    character.travel_target_x, character.travel_target_y = 20, -20
    character.travel_arrives_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    await db_session.flush()

    report = await maintenance_service.reset_stuck_activities(db_session)

    assert report.travel_reset == 1
    assert character.travel_arrives_at is None
    assert character.travel_target_x is None
    # Позиция НЕ меняется: отмена пути, а не телепорт к цели.
    assert (character.pos_x, character.pos_y) == (12, -8)


@pytest.mark.asyncio
async def test_reset_pulls_the_rod_out_of_the_water(db_session, make_character) -> None:
    """Патч 58: сообщение о поклёвке присылает планировщик в памяти процесса,
    и рестарт его теряет — снасть надо вынимать, иначе игрок заперт."""
    character = await make_character()
    now = datetime.now(timezone.utc)
    character.fishing_cast_at = now
    character.fishing_bite_at = now + timedelta(seconds=10)
    character.fishing_pending_fish = "pale_perch"
    character.fishing_pending_grams = 900
    await db_session.flush()

    report = await maintenance_service.reset_stuck_activities(db_session)

    assert report.fishing_reset == 1
    assert character.fishing_cast_at is None
    assert character.fishing_pending_fish is None
    assert character.fishing_pending_grams is None


@pytest.mark.asyncio
async def test_reset_cancels_mount_travel(db_session, make_character) -> None:
    character = await make_character()
    db_session.add(MountTravel(
        character_id=character.id, mount_id="admin_ashen_herald",
        from_x=0, from_y=0, to_x=1, to_y=1, status="traveling",
        arrives_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    ))
    await db_session.flush()

    report = await maintenance_service.reset_stuck_activities(db_session)

    assert report.mount_reset == 1


@pytest.mark.asyncio
async def test_reset_does_not_touch_the_fish_bag(db_session, make_character) -> None:
    """Садок — это добыча игрока, а не состояние активности. Сброс, съедающий
    улов, был бы кражей."""
    character = await make_character()
    character.fishing_cast_at = datetime.now(timezone.utc)
    db_session.add(CharacterFish(
        character_id=character.id, fish_id="pale_perch", grade="big", total_grams=4200
    ))
    await db_session.flush()

    await maintenance_service.reset_stuck_activities(db_session)

    from services import fishing_service

    assert await fishing_service.bag_total_grams(db_session, character.id) == 4200


@pytest.mark.asyncio
async def test_reset_does_not_touch_progress(db_session, make_character) -> None:
    character = await make_character()
    character.level, character.experience = 42, 12345
    character.fishing_level, character.fishing_xp = 7, 99
    character.mobs_killed = 500
    character.travel_arrives_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    await db_session.flush()

    await maintenance_service.reset_stuck_activities(db_session)

    assert (character.level, character.experience) == (42, 12345)
    assert (character.fishing_level, character.fishing_xp) == (7, 99)
    assert character.mobs_killed == 500


@pytest.mark.asyncio
async def test_preview_counts_match_what_reset_does(db_session, make_character) -> None:
    """Превью показывается админу ДО подтверждения — оно обязано совпадать с
    тем, что реально произойдёт."""
    character = await make_character()
    now = datetime.now(timezone.utc)
    character.travel_arrives_at = now + timedelta(minutes=5)
    character.fishing_cast_at = now
    await db_session.flush()

    counts = await maintenance_service.preview(db_session)
    report = await maintenance_service.reset_stuck_activities(db_session)

    assert counts.travelers == report.travel_reset
    assert counts.casters == report.fishing_reset
    assert counts.mount_travelers == report.mount_reset


@pytest.mark.asyncio
async def test_reset_is_idempotent(db_session, make_character) -> None:
    """Кнопку будут жать после каждого рестарта — повторное нажатие подряд не
    должно ничего ломать."""
    character = await make_character()
    character.travel_arrives_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    await db_session.flush()

    first = await maintenance_service.reset_stuck_activities(db_session)
    second = await maintenance_service.reset_stuck_activities(db_session)

    assert first.total == 1
    assert second.total == 0
