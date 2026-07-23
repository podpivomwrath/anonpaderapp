"""Первый региональный квест: назначение, прогресс, выдача награды."""

from services import quest_service as svc
from services.wallet_service import get_wallet


async def test_get_or_assign_creates_on_first_visit(db_session, make_character, seed_quests) -> None:
    character = await make_character(region="ridge")
    progress = await svc.get_or_assign(db_session, character)
    assert progress.is_new
    assert progress.status == "active"
    assert progress.progress == 0
    assert progress.target_count == 10


async def test_get_or_assign_returns_existing_on_revisit(db_session, make_character, seed_quests) -> None:
    character = await make_character(region="ridge")
    first = await svc.get_or_assign(db_session, character)
    await db_session.commit()
    second = await svc.get_or_assign(db_session, character)
    assert first.is_new
    assert not second.is_new


async def test_record_kill_increments_progress(db_session, make_character, seed_quests) -> None:
    character = await make_character(region="woods")
    await svc.get_or_assign(db_session, character)
    progress = await svc.record_kill(db_session, character)
    assert progress.progress == 1
    assert progress.status == "active"


async def test_record_kill_transitions_to_ready_at_target(db_session, make_character, seed_quests) -> None:
    character = await make_character(region="docks")
    await svc.get_or_assign(db_session, character)
    progress = None
    for _ in range(10):
        progress = await svc.record_kill(db_session, character)
    assert progress.progress == 10
    assert progress.status == "ready"


async def test_record_kill_without_assigned_quest_is_noop(db_session, make_character, seed_quests) -> None:
    character = await make_character(region="scorched")
    # квест ещё не назначен (наставник не посещался)
    assert await svc.record_kill(db_session, character) is None


async def test_turn_in_requires_ready_status(db_session, make_character, seed_quests) -> None:
    character = await make_character(region="ridge")
    await svc.get_or_assign(db_session, character)
    await svc.record_kill(db_session, character)  # прогресс 1/10, ещё не ready
    assert await svc.turn_in(db_session, character) is None


async def test_turn_in_gives_xp_not_gold(db_session, make_character, seed_quests) -> None:
    """progression-patch-4: квест даёт крупный опыт (500), золото пока не капает."""
    character = await make_character(region="ridge")
    await svc.get_or_assign(db_session, character)
    for _ in range(10):
        await svc.record_kill(db_session, character)

    result = await svc.turn_in(db_session, character)
    assert result is not None
    assert result.xp_reward == 500       # из данных квеста
    assert result.gold_reward == 0       # золото — хук, пока не начисляется
    assert result.levels_gained >= 1     # 500 опыта поднимает уровень со старта
    assert character.level == result.new_level

    wallet = await get_wallet(db_session, character.id)
    assert wallet.farm_currency == 0     # золота действительно нет

    # повторная сдача уже невозможна — статус completed
    assert await svc.turn_in(db_session, character) is None


async def test_quests_are_region_specific(db_session, make_character, seed_quests) -> None:
    ridge_char = await make_character(region="ridge")
    woods_char = await make_character(region="woods")
    ridge_progress = await svc.get_or_assign(db_session, ridge_char)
    woods_progress = await svc.get_or_assign(db_session, woods_char)
    assert ridge_progress.code == "first_blood_ridge"
    assert woods_progress.code == "first_blood_woods"
