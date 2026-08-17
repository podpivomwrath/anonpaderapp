"""Промокоды (патч 50): создание/удаление/список (админ), активация (игрок).

Приоритет ввода и защита от коллизий с координатами/никнеймом/PvP-текстом —
tests/test_promo_handler.py."""

from datetime import datetime, timedelta, timezone

import pytest

from game.combat import balance_config as bc
from game.economy import raid_key_config as rc
from services import premium_service, promo_service
from services.promo_service import PromoValidationError


async def test_create_code_normalizes_case_and_whitespace(db_session) -> None:
    promo = await promo_service.create_code(
        db_session, 1, "  MONOLITH2026  ", [{"type": "gold", "amount": 100}], None, True, None,
    )
    assert promo.code == "monolith2026"


async def test_create_code_rejects_duplicate(db_session) -> None:
    await promo_service.create_code(db_session, 1, "dup", [{"type": "gold", "amount": 1}], None, True, None)
    with pytest.raises(PromoValidationError):
        await promo_service.create_code(db_session, 1, "DUP", [{"type": "gold", "amount": 1}], None, True, None)


async def test_create_code_rejects_empty_code(db_session) -> None:
    with pytest.raises(PromoValidationError):
        await promo_service.create_code(db_session, 1, "   ", [{"type": "gold", "amount": 1}], None, True, None)


async def test_create_code_rejects_no_rewards(db_session) -> None:
    with pytest.raises(PromoValidationError):
        await promo_service.create_code(db_session, 1, "empty", [], None, True, None)


async def test_delete_code_removes_it(db_session) -> None:
    promo = await promo_service.create_code(db_session, 1, "gone", [{"type": "gold", "amount": 1}], None, True, None)
    deleted = await promo_service.delete_code(db_session, 1, promo.id)
    assert deleted is True
    codes = await promo_service.list_codes(db_session)
    assert all(c.id != promo.id for c in codes)


async def test_delete_code_missing_returns_false(db_session) -> None:
    assert await promo_service.delete_code(db_session, 1, 999999) is False


async def test_list_codes_includes_activation_count(db_session, make_character) -> None:
    promo = await promo_service.create_code(db_session, 1, "counted", [{"type": "gold", "amount": 1}], None, False, None)
    character = await make_character()
    await promo_service.activate_code(db_session, character, "counted")
    overview = await promo_service.list_codes(db_session)
    entry = next(c for c in overview if c.id == promo.id)
    assert entry.activation_count == 1


# --- Активация: успех и начисление наград ---


async def test_activate_unknown_code_returns_none(db_session, make_character) -> None:
    character = await make_character()
    outcome = await promo_service.activate_code(db_session, character, "NOPE123")
    assert outcome is None


async def test_activate_success_grants_gold(db_session, make_character) -> None:
    await promo_service.create_code(db_session, 1, "gold500", [{"type": "gold", "amount": 500}], None, True, None)
    character = await make_character(farm=0)
    outcome = await promo_service.activate_code(db_session, character, "gold500")
    assert outcome.status == "success"
    assert outcome.lines == ["500 золота"]


async def test_activate_case_and_whitespace_insensitive(db_session, make_character) -> None:
    await promo_service.create_code(db_session, 1, "MixedCase", [{"type": "gold", "amount": 10}], None, True, None)
    character = await make_character()
    outcome = await promo_service.activate_code(db_session, character, "  mixedcase  ")
    assert outcome.status == "success"


async def test_activate_grants_multiple_reward_items(db_session, make_character) -> None:
    await promo_service.create_code(
        db_session, 1, "bundle",
        [{"type": "gold", "amount": 100}, {"type": "gems", "amount": 5}, {"type": "premium", "days": 7}],
        None, True, None,
    )
    character = await make_character()
    outcome = await promo_service.activate_code(db_session, character, "bundle")
    assert outcome.status == "success"
    assert len(outcome.lines) == 3
    assert premium_service.is_premium(character) is True


async def test_activate_premium_on_premium_sums_duration(db_session, make_character) -> None:
    await promo_service.create_code(db_session, 1, "extra7", [{"type": "premium", "days": 7}], None, True, None)
    character = await make_character()
    now = datetime.now(timezone.utc)
    character.premium_until = now + timedelta(days=30)
    await promo_service.activate_code(db_session, character, "extra7")
    assert character.premium_until > now + timedelta(days=36)
    assert character.premium_until <= now + timedelta(days=37, hours=1)


# --- Активация: edge cases с явными текстами ---


async def test_activate_already_used_when_one_per_player(db_session, make_character) -> None:
    await promo_service.create_code(db_session, 1, "once", [{"type": "gold", "amount": 1}], None, True, None)
    character = await make_character()
    await promo_service.activate_code(db_session, character, "once")
    outcome = await promo_service.activate_code(db_session, character, "once")
    assert outcome.status == "already_used"


async def test_activate_allows_repeat_when_not_one_per_player(db_session, make_character) -> None:
    await promo_service.create_code(db_session, 1, "repeatable", [{"type": "gold", "amount": 1}], None, False, None)
    character = await make_character()
    first = await promo_service.activate_code(db_session, character, "repeatable")
    second = await promo_service.activate_code(db_session, character, "repeatable")
    assert first.status == "success"
    assert second.status == "success"


async def test_activate_limit_reached(db_session, make_character) -> None:
    await promo_service.create_code(db_session, 1, "limited", [{"type": "gold", "amount": 1}], 1, False, None)
    character_a = await make_character()
    character_b = await make_character()
    first = await promo_service.activate_code(db_session, character_a, "limited")
    second = await promo_service.activate_code(db_session, character_b, "limited")
    assert first.status == "success"
    assert second.status == "limit_reached"


async def test_activate_expired_code(db_session, make_character) -> None:
    past = datetime.now(timezone.utc) - timedelta(days=1)
    # Ссылка на promo удерживается явно: без внешней ссылки SQLAlchemy может
    # собрать объект по слабой ссылке из identity map и перечитать строку из
    # SQLite, которая (в отличие от Postgres TIMESTAMPTZ в проде) не хранит
    # смещение и возвращается наивной датой — тестовый артефакт SQLite, не
    # баг прод-кода (asyncpg/psycopg всегда возвращают aware для timestamptz).
    promo = await promo_service.create_code(db_session, 1, "stale", [{"type": "gold", "amount": 1}], None, True, past)
    character = await make_character()
    outcome = await promo_service.activate_code(db_session, character, "stale")
    assert outcome.status == "expired"
    assert promo.code == "stale"


async def test_activate_xp_at_max_level_not_granted(db_session, make_character) -> None:
    await promo_service.create_code(db_session, 1, "xpcode", [{"type": "xp", "amount": 1000}], None, True, None)
    character = await make_character(level=bc.MAX_LEVEL)
    outcome = await promo_service.activate_code(db_session, character, "xpcode")
    assert outcome.status == "success"
    assert outcome.lines == ["Опыт не начислен — достигнут максимальный уровень."]


async def test_activate_raid_keys_over_cap_partial_grant(db_session, make_character) -> None:
    await promo_service.create_code(db_session, 1, "keys", [{"type": "raid_keys", "amount": 2}], None, True, None)
    character = await make_character()
    character.raid_keys = rc.RAID_KEY_CAP - 1
    outcome = await promo_service.activate_code(db_session, character, "keys")
    assert outcome.status == "success"
    assert character.raid_keys == rc.RAID_KEY_CAP
    assert outcome.lines == [f"Ключей Монолита выдано: 1 из 2 (достигнут лимит {rc.RAID_KEY_CAP})."]


async def test_activate_mount_already_owned(db_session, make_character) -> None:
    await promo_service.create_code(
        db_session, 1, "steed", [{"type": "mount", "mount_id": "ashen_steed"}], None, False, None,
    )
    character = await make_character()
    first = await promo_service.activate_code(db_session, character, "steed")
    assert first.status == "success"
    assert first.lines[0].startswith("🐎") and "уже был" not in first.lines[0]

    second = await promo_service.activate_code(db_session, character, "steed")
    assert second.status == "success"
    assert "уже был" in second.lines[0]
