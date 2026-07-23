"""Онбординг: FSM создания персонажа, валидация ника, статы классов, регион."""

import pytest
from sqlalchemy import select

from game.combat import balance_config as bc
from models import CharacterStats
from services import onboarding_service as svc
from services.user_service import get_profile_text


async def start_creation(db, vk_id: int = 1):
    user = await svc.get_or_create_user(db, vk_id)
    character = await svc.begin_creation(db, user)
    return user, character


# --- Флоу целиком ---


async def test_full_creation_flow(db_session) -> None:
    _, char = await start_creation(db_session)
    # сюжетный онбординг: сцена пробуждения сразу ждёт никнейм
    assert char.creation_state == svc.STATE_NICKNAME
    assert char.name.startswith("~")  # плейсхолдер до выбора ника

    assert await svc.try_set_nickname(db_session, char, "Багровый_Витя") is None
    assert char.creation_state == svc.STATE_CLASS_SELECT

    await svc.apply_class(db_session, char, "mage")
    assert char.creation_state == svc.STATE_REGION_SELECT

    stats = await svc.complete_creation(db_session, char, "scorched")
    assert char.creation_state is None
    assert char.region == "scorched"
    assert char.base_class == "mage"
    # стартовые статы мага: 10/10/25/15/25 (85 суммарно)
    assert (stats.strength, stats.agility, stats.intellect, stats.vitality, stats.will) == (
        10, 10, 25, 15, 25,
    )
    # позиция — родной город региона (🔥 Выжженный Предел)
    assert (char.pos_x, char.pos_y) == (-50, -50)


async def test_resume_keeps_state(db_session) -> None:
    """Бросил на середине — продолжает с того же шага."""
    _, char = await start_creation(db_session)
    await svc.set_state(db_session, char, svc.STATE_CLASS_CONFIRM)
    await db_session.commit()

    reloaded = await svc.get_character(db_session, 1)
    assert reloaded.creation_state == svc.STATE_CLASS_CONFIRM


async def test_profile_hidden_until_done(db_session) -> None:
    _, char = await start_creation(db_session)
    assert await get_profile_text(db_session, 1) is None  # создание не завершено

    await svc.try_set_nickname(db_session, char, "Готовый")
    await svc.apply_class(db_session, char, "warrior")
    await svc.complete_creation(db_session, char, "ridge")
    profile = await get_profile_text(db_session, 1)
    assert profile is not None
    assert "Готовый" in profile
    assert "Обетованный Кряж" in profile


async def test_start_twice_no_duplicate(db_session) -> None:
    user, char = await start_creation(db_session)
    again = await svc.get_character(db_session, 1)
    assert again.id == char.id  # /start повторно не плодит персонажей


# --- Стартовые статы классов ---


@pytest.mark.parametrize("base_class", ["warrior", "rogue", "mage"])
async def test_class_stats_sum_85(db_session, base_class: str) -> None:
    assert sum(bc.STARTING_STATS[base_class].values()) == 85
    _, char = await start_creation(db_session)
    await svc.apply_class(db_session, char, base_class)
    stats = await db_session.scalar(
        select(CharacterStats).where(CharacterStats.character_id == char.id)
    )
    expected = bc.STARTING_STATS[base_class]
    assert stats.strength == expected["STR"]
    assert stats.agility == expected["AGI"]
    assert stats.intellect == expected["INT"]
    assert stats.vitality == expected["VIT"]
    assert stats.will == expected["WIL"]


# --- Валидация никнейма ---


def test_nickname_format() -> None:
    assert svc.validate_nickname_format("аб") is not None          # короткий
    assert svc.validate_nickname_format("а" * 17) is not None      # длинный
    assert svc.validate_nickname_format("Вася Пупкин") is not None  # пробел
    assert svc.validate_nickname_format("Вася!") is not None       # спецсимвол
    assert svc.validate_nickname_format("~123") is not None        # тильда (плейсхолдер)
    assert svc.validate_nickname_format("Vasya_2000") is None
    assert svc.validate_nickname_format("Ёжик") is None


def test_banned_words_filter() -> None:
    assert svc.contains_banned_word("СуперХуйер")   # подстрока, регистронезависимо
    assert svc.contains_banned_word("fUcKer123")
    assert not svc.contains_banned_word("Странник")


async def test_nickname_unique_case_insensitive(db_session) -> None:
    _, first = await start_creation(db_session, vk_id=1)
    await svc.try_set_nickname(db_session, first, "Vasya")

    _, second = await start_creation(db_session, vk_id=2)
    error = await svc.try_set_nickname(db_session, second, "vasya")
    assert error == "taken"
    # а свободное имя проходит
    assert await svc.try_set_nickname(db_session, second, "Petya") is None


async def test_nickname_errors_keep_state(db_session) -> None:
    """Отказ валидации не двигает FSM — повторный запрос на том же шаге."""
    _, char = await start_creation(db_session)
    assert await svc.try_set_nickname(db_session, char, "х") == "invalid"
    assert char.creation_state == svc.STATE_NICKNAME
    assert char.name.startswith("~")


# --- Реплики Хранителя Списков (контент, не хардкод) ---


def test_keeper_texts_loaded_from_content() -> None:
    from bot import onboarding_texts as texts

    assert "Хранитель Списков" in texts.KEEPER["scene_awakening"]
    assert set(texts.NICKNAME_ERRORS) == {"invalid", "banned", "taken"}
    assert set(texts.KEEPER["class_paths"]) == {"warrior", "rogue", "mage"}
    assert set(texts.KEEPER["regions"]) == {"ridge", "woods", "docks", "scorched"}


def test_final_message_renders() -> None:
    from types import SimpleNamespace

    from bot.onboarding_texts import final_message

    stats = SimpleNamespace(strength=25, agility=15, intellect=10, vitality=20, will=15)
    text = final_message("Багровый_Витя", "warrior", "scorched", stats)
    assert "Багровый_Витя" in text
    assert "Путь Стали" in text
    assert "🔥 Выжженный Предел" in text        # в сводке — с эмодзи
    assert "— Значит, Выжженный Предел." in text  # в реплике — без
    assert "💪 25" in text and "✨ 15" in text
    assert "{" not in text  # все плейсхолдеры подставлены
