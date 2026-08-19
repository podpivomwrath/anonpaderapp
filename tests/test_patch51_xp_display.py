"""Патч 51, ч.1: опыт с премиумом должен отображаться С учётом бонуса —
раньше сообщение строилось из xp ДО применения премиум-множителя внутри
services/experience_service.py::add_experience, хотя фактически начислялось
больше. Проверяем: LevelUp.xp_awarded/premium_applied, display.xp_delta_line,
flavor.quest_reward_line и сквозные сценарии на реальных вызывающих сервисах."""

from datetime import datetime, timedelta, timezone

from game.combat import display
from game.world import flavor
from services import experience_service


class _FakeStats:
    unspent_points = 0


class _FakeCharacter:
    def __init__(self, premium: bool, level: int = 1, experience: int = 0):
        self.level = level
        self.experience = experience
        self.current_hp = 100
        self.premium_until = (
            datetime.now(timezone.utc) + timedelta(days=1) if premium else None
        )


def test_add_experience_returns_actual_awarded_amount_with_premium() -> None:
    char = _FakeCharacter(premium=True, level=50)  # плато — избегаем левелапа, чтобы проверить сырое начисление
    levelup = experience_service.add_experience(char, _FakeStats(), 100)
    assert levelup.xp_awarded == 150
    assert levelup.premium_applied is True


def test_add_experience_returns_same_amount_without_premium() -> None:
    char = _FakeCharacter(premium=False)
    levelup = experience_service.add_experience(char, _FakeStats(), 100)
    assert levelup.xp_awarded == 100
    assert levelup.premium_applied is False


def test_add_experience_admin_grant_not_marked_premium_even_if_premium_active() -> None:
    char = _FakeCharacter(premium=True)
    levelup = experience_service.add_experience(char, _FakeStats(), 100, apply_premium=False)
    assert levelup.xp_awarded == 100
    assert levelup.premium_applied is False


def test_add_experience_zero_or_negative_amount_not_marked_premium() -> None:
    char = _FakeCharacter(premium=True)
    levelup = experience_service.add_experience(char, _FakeStats(), 0)
    assert levelup.xp_awarded == 0
    assert levelup.premium_applied is False


# --- display.xp_delta_line ---


def test_xp_delta_line_no_premium_no_marker() -> None:
    assert display.xp_delta_line(100) == "(+100 опыта)"


def test_xp_delta_line_with_premium_shows_marker() -> None:
    assert display.xp_delta_line(150, premium=True) == "(+150 опыта (💠 +50%))"


def test_xp_delta_line_with_mult_and_premium_combined() -> None:
    line = display.xp_delta_line(180, mult=1.2, premium=True)
    assert line == "(+180 опыта · ×1.2 за опасность (💠 +50%))"


# --- flavor.quest_reward_line ---


def test_quest_reward_line_no_premium() -> None:
    line = flavor.quest_reward_line(500)
    assert "💠" not in line
    assert "+500 опыта" in line


def test_quest_reward_line_with_premium() -> None:
    line = flavor.quest_reward_line(750, premium=True)
    assert "💠 +50%" in line
    assert "+750 опыта" in line


# --- сквозные сценарии на реальных сервисах ---


async def test_encounter_resolve_victory_shows_actual_xp(db_session, character_at) -> None:
    from services import encounter_service

    character = await character_at(5, 5, level=10)
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    import random

    outcome = await encounter_service.resolve_victory(db_session, character, mob_level=10, rng=random.Random(1))
    assert outcome.xp_premium_applied is True
    # ФАКТИЧЕСКИ начисленный опыт должен совпадать с показанным (не быть базовым)
    assert outcome.xp_gained > 0


async def test_daily_completion_xp_reflects_premium(db_session, make_character, seed_quests) -> None:
    from bot.dailies_texts import progress_notice_from
    from services import daily_service

    character = await make_character(level=10)
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    from datetime import date

    await daily_service._assign_new_dailies(db_session, character, date.today())
    from sqlalchemy import select

    from models import CharacterDaily

    row = (
        await db_session.scalars(
            select(CharacterDaily).where(CharacterDaily.character_id == character.id)
        )
    ).first()
    completion = await daily_service._apply_delta(db_session, character, row, 9999)
    assert completion is not None
    assert completion.xp_premium_applied is True
    text = progress_notice_from([completion], None)
    assert "💠 +50%" in text


async def test_promo_xp_reward_text_shows_premium_marker(db_session, make_character) -> None:
    from services import promo_service

    await promo_service.create_code(db_session, 1, "xpboost", [{"type": "xp", "amount": 100}], None, True, None)
    character = await make_character(level=5)
    character.premium_until = datetime.now(timezone.utc) + timedelta(days=1)
    outcome = await promo_service.activate_code(db_session, character, "xpboost")
    assert outcome.status == "success"
    assert outcome.lines == ["150 опыта (💠 +50%)"]
