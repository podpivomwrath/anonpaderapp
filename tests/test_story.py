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


# --- Патч 36: named-враги — base_mob_id должен резолвиться в реальную картинку ---


def _all_named_enemies():
    for region in ("ridge", "woods", "docks", "scorched"):
        line = load_story_line(region)
        for act in line.acts:
            for quest in act.quests:
                if quest.named_enemy is not None:
                    yield region, quest.named_enemy


def test_named_enemy_base_mob_id_always_resolves_to_a_real_image() -> None:
    """Не защита от опечаток вслепую: если base_mob_id задан, он ОБЯЗАН
    указывать на существующего в бестиарии моба с картинкой — иначе это
    молчаливая опечатка в контенте, а не осознанное отсутствие картинки."""
    from game.world import encounters

    for region, enemy in _all_named_enemies():
        if enemy.base_mob_id is not None:
            image = encounters.base_mob_image(enemy.base_mob_id)
            assert image, f"{region}/{enemy.name}: base_mob_id={enemy.base_mob_id!r} без картинки"


def test_named_enemy_image_resolution_does_not_crash_without_either() -> None:
    """Патч 36: ни своей картинки, ни base_mob_id — не падать, просто без
    картинки (см. bot/handlers/world.py::_maybe_trigger_story)."""
    from game.world import encounters

    for _region, enemy in _all_named_enemies():
        image = enemy.image or encounters.base_mob_image(enemy.base_mob_id)
        assert image is None or isinstance(image, str)


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


async def test_travel_combat_active_shows_target_marker(db_session, character_at) -> None:
    character = await character_at(0, 0, region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert "(40;46)" in result.text
    assert "Осыпающиеся террасы" in result.text

    # патч 21: показанный (не резолвящий) визит помечает шаг увиденным
    row = await story_service.get_progress(db_session, character)
    assert row.quest_seen is True


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


async def test_no_level_gate_travel_combat_available_regardless_of_level(
    db_session, character_at
) -> None:
    """Патч 21, п.3: уровневые ворота убраны — акт 2 доступен с 1 уровня."""
    character = await character_at(0, 0, region="ridge", level=1)
    await _set_progress(db_session, character, "ridge_2_1", act=2, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    result = await story_service.visit_mentor(db_session, character, stats)
    assert "(30;35)" in result.text
    assert "Забытый редут" in result.text


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

    row = await story_service.get_progress(db_session, character)
    assert row.quest_seen is True


# --- /квест — quest_reminder_text ---


async def test_quest_reminder_before_any_progress(db_session, make_character) -> None:
    """Патч 21, п.5: первый квест ещё не взят — «нет активного, наставник ждёт»."""
    character = await make_character(region="ridge")
    text = await story_service.quest_reminder_text(db_session, character, "Сера Вейга")
    assert "нет активного задания" in text.lower()
    assert "Сера Вейга" in text


async def test_quest_reminder_on_first_quest(db_session, make_character, seed_quests) -> None:
    from services import quest_service

    character = await make_character(region="ridge")
    await quest_service.get_or_assign(db_session, character)  # квест реально взят
    text = await story_service.quest_reminder_text(db_session, character, "Сера Вейга")
    assert "пепельные твари" in text.lower()  # progress_label квеста ridge из content/quests.json


async def test_quest_reminder_ready_travel_combat(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="ready")
    text = await story_service.quest_reminder_text(db_session, character, "Сера Вейга")
    assert "цель достигнута" in text.lower()
    assert "Сера Вейга" in text


# --- compass_direction (патч 21, пп. 4-5) ---


@pytest.mark.parametrize(
    "px,py,tx,ty,expected",
    [
        (0, 0, 0, 5, "на север"),
        (0, 0, 0, -5, "на юг"),
        (0, 0, 5, 0, "на восток"),
        (0, 0, -5, 0, "на запад"),
        (0, 0, 5, 5, "на северо-восток"),
        (0, 0, -5, 5, "на северо-запад"),
        (0, 0, 5, -5, "на юго-восток"),
        (0, 0, -5, -5, "на юго-запад"),
        (3, 3, 3, 3, "ты уже на месте"),
    ],
)
def test_compass_direction(px, py, tx, ty, expected) -> None:
    assert story_service.compass_direction(px, py, tx, ty) == expected


# --- mentor_badge_active (патч 21, п.2) ---


async def test_mentor_badge_true_when_first_quest_not_taken(db_session, make_character, seed_quests) -> None:
    character = await make_character(region="ridge")
    assert await story_service.mentor_badge_active(db_session, character) is True


async def test_mentor_badge_first_quest_active_and_ready(db_session, make_character, seed_quests) -> None:
    from services import quest_service

    character = await make_character(region="ridge")
    await quest_service.get_or_assign(db_session, character)  # взят → активен
    assert await story_service.mentor_badge_active(db_session, character) is False

    progress = await quest_service.record_kill(db_session, character)
    for _ in range(9):
        progress = await quest_service.record_kill(db_session, character)
    assert progress.status == "ready"
    assert await story_service.mentor_badge_active(db_session, character) is True


async def test_mentor_badge_travel_combat_states(db_session, character_at) -> None:
    character = await character_at(0, 0, region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    assert await story_service.mentor_badge_active(db_session, character) is True  # свежий, не показан

    stats = await db_session.get(CharacterStats, character.id)
    await story_service.visit_mentor(db_session, character, stats)  # показали assign
    assert await story_service.mentor_badge_active(db_session, character) is False

    await story_service.mark_ready(db_session, character, "ridge_1_2")
    assert await story_service.mentor_badge_active(db_session, character) is True  # сдача


async def test_mentor_badge_false_after_region_completed(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=60)
    await _set_progress(db_session, character, "ridge_5_2", act=5, status="active")
    stats = await db_session.get(CharacterStats, character.id)
    await story_service.visit_mentor(db_session, character, stats)  # резолвит и завершает линию
    assert await story_service.mentor_badge_active(db_session, character) is False


# --- quest_summary_line (патч 21, п.4) ---


async def test_quest_summary_line_none_for_first_quest(db_session, make_character) -> None:
    character = await make_character(region="ridge")
    assert await story_service.quest_summary_line(db_session, character) is None


async def test_quest_summary_line_travel_combat_active(db_session, character_at) -> None:
    character = await character_at(0, 0, region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="active")
    line = await story_service.quest_summary_line(db_session, character)
    assert line == "📜 Пропавший патруль → (40; 46) · на северо-восток"


async def test_quest_summary_line_travel_combat_ready(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_2", act=1, status="ready")
    line = await story_service.quest_summary_line(db_session, character)
    assert line == "📜 Пропавший патруль → вернуться к наставнику"


async def test_quest_summary_line_city_scene(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=20)
    await _set_progress(db_session, character, "ridge_1_3", act=1, status="active")
    line = await story_service.quest_summary_line(db_session, character)
    assert line == "📜 Молчание казармы → вернуться в город"


async def test_quest_summary_line_none_after_region_completed(db_session, make_character) -> None:
    character = await make_character(region="ridge", level=60)
    row = await _set_progress(db_session, character, "ridge_5_2", act=5, status="active")
    row.completed = True
    await db_session.flush()
    assert await story_service.quest_summary_line(db_session, character) is None
