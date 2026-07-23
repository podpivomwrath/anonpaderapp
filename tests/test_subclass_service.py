"""Выбор подкласса за золото на 30 уровне (патч 12, «Раскол пути»)."""

import pytest

from game.combat import balance_config as bc
from services import subclass_service
from services.wallet_service import NotEnoughCurrency, get_wallet


def test_can_offer_requires_level_and_no_subclass() -> None:
    class Fake:
        level = 30
        subclass = None

    assert subclass_service.can_offer(Fake())

    Fake.level = 29
    assert not subclass_service.can_offer(Fake())

    Fake.level = 30
    Fake.subclass = "guardian"
    assert not subclass_service.can_offer(Fake())


def test_paths_for_returns_two_matching_base_class() -> None:
    warrior_paths = subclass_service.paths_for("warrior")
    assert {s.id for s in warrior_paths} == {"guardian", "blood_knight"}

    rogue_paths = subclass_service.paths_for("rogue")
    assert {s.id for s in rogue_paths} == {"shadow_blade", "poisoner"}

    mage_paths = subclass_service.paths_for("mage")
    assert {s.id for s in mage_paths} == {"elementalist", "dark_mystic"}


async def test_pay_unlock_charges_gold(db_session, make_character) -> None:
    character = await make_character(level=30, farm=bc.SUBCLASS_UNLOCK_COST + 500)
    await subclass_service.pay_unlock(db_session, character)
    wallet = await get_wallet(db_session, character.id)
    assert wallet.farm_currency == 500


async def test_pay_unlock_insufficient_gold_raises(db_session, make_character) -> None:
    character = await make_character(level=30, farm=bc.SUBCLASS_UNLOCK_COST - 1)
    with pytest.raises(NotEnoughCurrency):
        await subclass_service.pay_unlock(db_session, character)
    wallet = await get_wallet(db_session, character.id)
    assert wallet.farm_currency == bc.SUBCLASS_UNLOCK_COST - 1  # не списано при отказе


def test_apply_subclass_sets_field() -> None:
    class Fake:
        subclass = None

    fake = Fake()
    subclass_service.apply_subclass(fake, "guardian")
    assert fake.subclass == "guardian"
