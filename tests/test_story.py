"""Патчи 18-20: региональные сюжетные квесты — каркas + контент всех 4 линий."""

import pytest

from game.content_loader import load_story_line
from game.economy import story_config as sc
from models import CharacterStats, CharacterStoryProgress
from services import story_service


# --- Контент: все 4 линии грузятся и следуют общей схеме ---


@pytest.mark.parametrize("region", ["ridge", "woods", "docks", "scorched"])
def test_story_line_loads_five_acts(region: str) -> None:
    line = load_story_line(region)
    assert line.region == region
    assert len(line.acts) == 5
    assert line.acts[0].quests[0].kind == "first_quest"
    # уровневые ворота актов монотонно растут и покрывают 1..60 без дыр
    for act in line.acts:
        assert act.level_min <= act.level_max
    assert line.acts[0].level_min == 1
    assert line.acts[-1].level_max == 60


@pytest.mark.parametrize("region", ["ridge", "woods", "docks", "scorched"])
def test_exactly_one_subclass_gate_per_line(region: str) -> None:
    line = load_story_line(region)
    quests = [q for act in line.acts for q in act.quests]
    gates = [q for q in quests if q.kind == "subclass_gate"]
    assert len(gates) == 1


# --- format_text: подстановка {nickname} ---


async def test_format_text_substitutes_nickname(make_character) -> None:
    character = await make_character(region="ridge")
    character.name = "Огонёк"
    assert story_service.format_text("Привет, {nickname}.", character) == "Привет, Огонёк."


async def test_format_text_noop_without_placeholder(make_character) -> None:
    character = await make_character(region="ridge")
    assert story_service.format_text("Без плейсхолдера.", character) == "Без плейсхолдера."


# --- Квест 1.1 (first_quest) → advance_after_first_quest ---


async def test_first_quest_advances_to_next_step(db_session, make_character) -> None:
    character = await make_character(region="ridge")
    quest = await story_service.current_quest_def(db_session, character)
    assert quest.id == "ridge_1_1"
    assert quest.kind == "first_quest"

    transition = await story_service.advance_after_first_quest(db_session, character)
    assert transition  # непустой текст-переход
    assert "Сера" in transition

    quest = await story_service.current_quest_def(db_session, character)
    assert quest.id == "ridge_1_2"


async def test_advance_after_first_quest_idempotent(db_session, make_character) -> None:
    character = await make_character(region="ridge")
    await story_service.advance_after_first_quest(db_session, character)
    second = await story_service.advance_after_first_quest(db_session, character)
    assert second == ""


async def test_visit_mentor_returns_none_while_on_first_quest(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=1)
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert result is None


# --- Шаги travel_combat / city_scene / уровневый гейт ---


async def _set_progress(db_session, character, quest_step: str, act: int, status: str = "active"):
    row = CharacterStoryProgress(
        character_id=character.id, region=character.region, act=act,
        quest_step=quest_step, status=status,
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def test_travel_combat_active_shows_target_marker(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert "(40;46)" in result.text
    assert "Осыпающиеся террасы" in result.text


async def test_travel_combat_ready_grants_reward_and_advances(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20, farm=0)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="ready")
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert "мрачнеет" in result.text or "Значит, не слухи" in result.text
    assert "800" in result.text  # xp_reward ridge_1_2

    quest = await story_service.current_quest_def(db_session, character)
    assert quest.id == "ridge_1_3"


async def test_city_scene_resolves_in_one_visit(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_3", act=1, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert "400" in result.text  # xp_reward ridge_1_3
    assert result.region_completed is False

    quest = await story_service.current_quest_def(db_session, character)
    assert quest.id == "ridge_2_1"


async def test_level_gate_blocks_new_act_but_keeps_progress(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=1)
    await _set_progress(db_session, character, "ridge_2_1", act=2, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert result.text == story_service.LEVEL_GATE_TEXT

    # прогресс не откатился и не продвинулся
    row = await story_service.get_progress(db_session, character)
    assert row.quest_step == "ridge_2_1"
    assert row.status == "active"


async def test_region_completed_after_last_quest(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=60)
    await _set_progress(db_session, character, "ridge_5_2", act=5, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert result.region_completed is True

    # следующий визит — линия пройдена целиком, visit_mentor больше ничего не даёт
    second = await story_service.visit_mentor(db_session, character, stats)
    assert second is None


# --- Зона-триггер (check_zone_trigger) ---


async def test_zone_trigger_fires_within_radius(db_session, character_at) -> None:
    character = await character_at(41, 45, region="ridge", level=20)  # dist=1 до (40;46)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    quest = await story_service.check_zone_trigger(db_session, character)
    assert quest is not None
    assert quest.id == "ridge_1_2"


async def test_zone_trigger_respects_radius_boundary(db_session, character_at) -> None:
    character = await character_at(40 + sc.STORY_TRIGGER_RADIUS, 46, region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    assert await story_service.check_zone_trigger(db_session, character) is not None

    character.pos_x += 1  # на клетку дальше радиуса
    assert await story_service.check_zone_trigger(db_session, character) is None


async def test_zone_trigger_none_far_away(db_session, character_at) -> None:
    character = await character_at(0, 0, region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    assert await story_service.check_zone_trigger(db_session, character) is None


async def test_zone_trigger_ignores_ready_status(db_session, character_at) -> None:
    """Цель уже достигнута (ждём наставника) — повторный вход в зону не триггерит снова."""
    character = await character_at(40, 46, region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="ready")
    assert await story_service.check_zone_trigger(db_session, character) is None


# --- mark_ready ---


async def test_mark_ready_sets_status(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    await story_service.mark_ready(db_session, character, "ridge_1_2")
    row = await story_service.get_progress(db_session, character)
    assert row.status == "ready"


async def test_mark_ready_ignores_mismatched_quest_id(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    await story_service.mark_ready(db_session, character, "ridge_2_1")  # устаревшее/чужое
    row = await story_service.get_progress(db_session, character)
    assert row.status == "active"


# --- subclass_gate ---


async def test_advance_past_subclass_gate_grants_and_advances(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=30, subclass="guardian", farm=0)
    await _set_progress(db_session, character, "ridge_3_2", act=3, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    reward_text = await story_service.advance_past_subclass_gate(db_session, character, stats)
    assert "800" in reward_text  # xp_reward ridge_3_2

    quest = await story_service.current_quest_def(db_session, character)
    assert quest.id == "ridge_4_1"


async def test_advance_past_subclass_gate_noop_on_other_kind(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20, subclass="guardian")
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    reward_text = await story_service.advance_past_subclass_gate(db_session, character, stats)
    assert reward_text == ""
    quest = await story_service.current_quest_def(db_session, character)
    assert quest.id == "ridge_1_2"  # не продвинулось


async def test_visit_mentor_subclass_gate_waits_without_subclass(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=30, subclass=None)
    await _set_progress(db_session, character, "ridge_3_2", act=3, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert "Хранитель" in result.text or "созрела" in result.text
    quest = await story_service.current_quest_def(db_session, character)
    assert quest.id == "ridge_3_2"  # без подкласса не продвигается


# --- /квест — quest_reminder_text ---


async def test_quest_reminder_before_any_progress(db_session, make_character) -> None:
    """quest_reminder_text не создаёт прогресс сам (в отличие от current_quest_def) —
    до первого разговора с наставником просто отправляет туда же."""
    character = await make_character(region="ridge")
    text = await story_service.quest_reminder_text(db_session, character)
    assert "поговори с наставником" in text.lower()


async def test_quest_reminder_on_first_quest(db_session, make_character) -> None:
    character = await make_character(region="ridge")
    await story_service.current_quest_def(db_session, character)  # создаёт прогресс (ridge_1_1)
    text = await story_service.quest_reminder_text(db_session, character)
    assert "экзамен" in text.lower()


async def test_quest_reminder_ready_travel_combat(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="ready")
    text = await story_service.quest_reminder_text(db_session, character)
    assert "возвращайся к наставнику" in text.lower()
