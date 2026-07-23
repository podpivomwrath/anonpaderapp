"""Трофеи (патч 9, блок 2/3): дроп, начисление, продажа скупщику."""

import random

from game.economy import loot
from game.economy import loot_config as lc
from models import CharacterTrophy
from services import trophy_service, wallet_service


async def _seed_trophy(db_session, character_id: int, trophy_id: str, count: int) -> None:
    db_session.add(CharacterTrophy(character_id=character_id, trophy_id=trophy_id, count=count))
    await db_session.flush()


# --- game/economy/loot.py: чистая логика ---


def test_rolls_for_dist_matches_bands() -> None:
    assert loot.rolls_for_dist(50) == 1
    assert loot.rolls_for_dist(40) == 1
    assert loot.rolls_for_dist(39) == 2
    assert loot.rolls_for_dist(25) == 2
    assert loot.rolls_for_dist(24) == 3
    assert loot.rolls_for_dist(12) == 3
    assert loot.rolls_for_dist(11) == 4
    assert loot.rolls_for_dist(3) == 4
    assert loot.rolls_for_dist(2) == 5
    assert loot.rolls_for_dist(0) == 5


def test_roll_once_respects_ordering_of_chances() -> None:
    class FixedRng(random.Random):
        def __init__(self, value: float) -> None:
            self._value = value

        def random(self) -> float:
            return self._value

    # 0.0 попадает в первый интервал — ash_dust (45%)
    assert loot.roll_once(FixedRng(0.0)) == "ash_dust"
    # чуть за пределами 45% — taint_clot
    assert loot.roll_once(FixedRng(0.45)) == "taint_clot"
    # за пределами суммы всех шансов (~68.85%) — ничего
    assert loot.roll_once(FixedRng(0.99)) is None


def test_roll_drop_counts_multiple_hits() -> None:
    class AlwaysAshRng(random.Random):
        def random(self) -> float:
            return 0.0  # всегда первый интервал (ash_dust)

    drop = loot.roll_drop(AlwaysAshRng(), rolls=5)
    assert drop == {"ash_dust": 5}


def test_roll_drop_no_hits_when_rng_high() -> None:
    class NeverDropRng(random.Random):
        def random(self) -> float:
            return 0.999

    assert loot.roll_drop(NeverDropRng(), rolls=10) == {}


def test_chance_sum_leaves_room_for_nothing() -> None:
    total = sum(lc.TROPHY_ROLL_CHANCES.values())
    assert 0 < total < 1  # обязателен шанс "ничего"


# --- services/trophy_service.py: работа с БД (character_at — см. conftest.py) ---


class AlwaysAshRng(random.Random):
    def random(self) -> float:
        return 0.0  # всегда ash_dust


class NeverDropRng(random.Random):
    def random(self) -> float:
        return 0.999


async def test_grant_from_kill_scales_rolls_by_zone(db_session, character_at) -> None:
    edge_character = await character_at(50, 0)  # dist=50 -> внешнее кольцо, 1 бросок
    drop = await trophy_service.grant_from_kill(db_session, edge_character, AlwaysAshRng())
    assert drop == {"ash_dust": 1}

    center_character = await character_at(0, 0)
    drop = await trophy_service.grant_from_kill(db_session, center_character, AlwaysAshRng())
    assert drop == {"ash_dust": 5}


async def test_grant_from_kill_persists_and_accumulates(db_session, character_at) -> None:
    character = await character_at(50, 50)  # dist=50 -> 1 бросок
    await trophy_service.grant_from_kill(db_session, character, AlwaysAshRng())
    await trophy_service.grant_from_kill(db_session, character, AlwaysAshRng())
    stock = await trophy_service.get_stock(db_session, character.id)
    assert len(stock) == 1
    trophy_def, count = stock[0]
    assert trophy_def.id == "ash_dust"
    assert count == 2


async def test_grant_from_event_always_one_roll(db_session, character_at) -> None:
    character = await character_at(0, 0)  # иначе было бы 5 бросков с боя
    drop = await trophy_service.grant_from_event(db_session, character, AlwaysAshRng())
    assert drop == {"ash_dust": 1}


async def test_grant_nothing_when_rng_never_hits(db_session, character_at) -> None:
    character = await character_at(0, 0)
    drop = await trophy_service.grant_from_kill(db_session, character, NeverDropRng())
    assert drop == {}
    stock = await trophy_service.get_stock(db_session, character.id)
    assert stock == []


async def test_get_stock_ordered_cheap_to_expensive(db_session, character_at) -> None:
    character = await character_at(50, 50)
    await _seed_trophy(db_session, character.id, "blood_shard", 1)
    await _seed_trophy(db_session, character.id, "ash_dust", 3)
    stock = await trophy_service.get_stock(db_session, character.id)
    assert [d.id for d, _ in stock] == ["ash_dust", "blood_shard"]


async def test_sell_all_credits_gold_and_clears_stock(db_session, character_at) -> None:
    character = await character_at(50, 50, farm=0)
    await _seed_trophy(db_session, character.id, "ash_dust", 3)    # 3*2=6
    await _seed_trophy(db_session, character.id, "taint_clot", 2)  # 2*15=30

    gold = await trophy_service.sell_all(db_session, character)
    assert gold == 36

    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency == 36
    assert await trophy_service.get_stock(db_session, character.id) == []


async def test_sell_all_empty_stock_returns_zero(db_session, character_at) -> None:
    character = await character_at(50, 50)
    assert await trophy_service.sell_all(db_session, character) == 0


async def test_sell_one_only_sells_that_grade(db_session, character_at) -> None:
    character = await character_at(50, 50, farm=0)
    await _seed_trophy(db_session, character.id, "ash_dust", 3)
    await _seed_trophy(db_session, character.id, "blood_shard", 1)

    gold = await trophy_service.sell_one(db_session, character, "ash_dust")
    assert gold == 6

    stock = await trophy_service.get_stock(db_session, character.id)
    assert [d.id for d, _ in stock] == ["blood_shard"]  # ash_dust продан, остальное цело


async def test_sell_one_nothing_to_sell_returns_zero(db_session, character_at) -> None:
    character = await character_at(50, 50)
    assert await trophy_service.sell_one(db_session, character, "monolith_tear") == 0


def test_format_drop_line_orders_rare_first() -> None:
    line = trophy_service.format_drop_line({"ash_dust": 2, "blood_shard": 1})
    assert line == "С твари осыпается: 🟣 Кровяной осколок, ⚪ Пепельная крошка ×2."


def test_format_drop_line_empty_is_none() -> None:
    assert trophy_service.format_drop_line({}) is None
