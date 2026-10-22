"""Алхимия (2026-10-21): рецепты, варка, отмена, доваривание по времени."""

import json
import random
from datetime import datetime, timedelta, timezone

import pytest

from bot.handlers import house as house_handlers
from game.economy import alchemy
from game.economy import alchemy_config as ac
from game.economy import elixir_config as ec
from game.economy import herbalism
from services import alchemy_service, elixir_service, herb_service, wallet_service

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


class _Always(random.Random):
    def random(self):
        return 0.0


def test_recipes_cover_shop_elixirs_and_use_known_herbs() -> None:
    shop = {d.id for d in elixir_service.elixir_defs_ordered() if d.category != "scroll"}
    assert {r.elixir_id for r in ac.RECIPES} == shop
    for r in ac.RECIPES:
        assert all(herbalism.herb_def(h) for h in r.herbs)
        assert r.out == (10 if r.elixir_id in ec.HEAL_IDS else 3)
        # Выгоднее лавки: золото на склянки меньше цены готовых зелий.
        assert r.gold < ec.ELIXIR_PRICES[r.elixir_id] * r.out / 3


def test_level_milestones() -> None:
    small = ac.RECIPES_BY_ID["heal_small"]
    assert alchemy.gold_cost(small, 9) == 40 and alchemy.gold_cost(small, 30) == 28
    assert alchemy.bonus_chance(50) == pytest.approx(0.5)
    assert [r.elixir_id for r in alchemy.unlocked_between(7, 12)] == ["ashen_fever", "heal_medium"]


async def _ready(db, make_character, gold=1000, herbs=None):
    c = await make_character(farm=gold)
    for h, n in (herbs or {"bitter_wormwood": 5}).items():
        await herb_service.add_herb(db, c.id, h, n)
    return c


async def test_brew_spends_and_finishes_into_inventory(db_session, make_character) -> None:
    c = await _ready(db_session, make_character)
    await alchemy_service.start(db_session, c, "heal_small", NOW)
    assert alchemy_service.brewing(c).elixir_id == "heal_small"
    assert (await wallet_service.get_wallet(db_session, c.id)).farm_currency == 960
    assert [(h.id, n) for h, n in await herb_service.get_bag(db_session, c.id)] == [("bitter_wormwood", 3)]
    with pytest.raises(alchemy_service.AlchemyError):
        await alchemy_service.start(db_session, c, "heal_small", NOW)
    assert await alchemy_service.due(db_session, NOW + timedelta(seconds=10)) == []
    assert [x.id for x in await alchemy_service.due(db_session, NOW + timedelta(seconds=31))] == [c.id]
    res = await alchemy_service.finish(db_session, c, random.Random(1))
    assert res.amount == 10 and res.xp == 22 and not alchemy_service.is_working(c)
    stock = {d.id: n for d, n in await elixir_service.get_stock(db_session, c.id)}
    assert stock["heal_small"] == 10
    assert "Малое исцеление ×10" in house_handlers.brewed_text(res)


async def test_refusals_keep_herbs_and_gold(db_session, make_character) -> None:
    c = await _ready(db_session, make_character, gold=10)
    with pytest.raises(alchemy_service.AlchemyError, match="золота"):
        await alchemy_service.start(db_session, c, "heal_small", NOW)
    assert [(h.id, n) for h, n in await herb_service.get_bag(db_session, c.id)] == [("bitter_wormwood", 5)]
    with pytest.raises(alchemy_service.AlchemyError, match="не знаком"):
        await alchemy_service.start(db_session, c, "heal_large", NOW)
    c2 = await _ready(db_session, make_character, herbs={"bitter_wormwood": 1})
    with pytest.raises(alchemy_service.AlchemyError, match="трав"):
        await alchemy_service.start(db_session, c2, "heal_small", NOW)
    assert (await wallet_service.get_wallet(db_session, c2.id)).farm_currency == 1000


async def test_cancel_loses_ingredients(db_session, make_character) -> None:
    c = await _ready(db_session, make_character)
    await alchemy_service.start(db_session, c, "heal_small", NOW)
    assert alchemy_service.cancel(c).elixir_id == "heal_small"
    assert not alchemy_service.is_working(c)
    assert [(h.id, n) for h, n in await herb_service.get_bag(db_session, c.id)] == [("bitter_wormwood", 3)]


async def test_bonus_portion_and_level_up(db_session, make_character) -> None:
    c = await _ready(db_session, make_character, herbs={"ash_plantain": 2, "bitter_wormwood": 1})
    c.alchemy_level, c.alchemy_xp = 10, alchemy.xp_to_next(10) - 1
    await alchemy_service.start(db_session, c, "ashen_fever", NOW)
    res = await alchemy_service.finish(db_session, c, _Always(1))
    assert res.amount == 4 and res.level_after == 11


def test_alchemy_keyboard_fits_vk_with_all_recipes() -> None:
    rows = json.loads(house_handlers.alchemy_keyboard(ac.MAX_LEVEL))["buttons"]
    # 2026-10-21: по 3 короткие кнопки в ряд - экран без прокрутки.
    assert len(rows) <= 5 and all(len(r) <= 3 for r in rows)
    assert rows[-1][-1]["action"]["label"] == house_handlers.BTN_HOUSE_BACK


class _Msg:
    def __init__(self, payload: dict):
        self.from_id = self.peer_id = 1
        self._payload = payload
        self.sent: list[str] = []

    def get_payload_json(self):
        return self._payload

    async def answer(self, text, **_kw):
        self.sent.append(text)


async def test_refusal_answers_after_rollback(db_session, make_character, monkeypatch) -> None:
    """Баг 2026-10-22: «Не хватает трав» откатывал сессию, потом читал уровень
    у просроченного персонажа - падало, и игрок видел «кнопка устарела»."""
    c = await _ready(db_session, make_character, herbs={"bitter_wormwood": 1})

    class _Db:
        def __getattr__(self, name):
            return getattr(db_session, name)

        async def rollback(self):
            db_session.expire(c)  # как настоящий откат: поля персонажа просрочены

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *a):
            return False

    async def _home(_db, _m):
        return c

    monkeypatch.setattr(house_handlers, "get_session_factory", lambda: _Factory())
    monkeypatch.setattr(house_handlers, "_home_character", _home)
    msg = _Msg({"type": "brew", "id": "heal_small"})
    await house_handlers.brew(msg)
    assert "трав" in msg.sent[-1]
    await db_session.refresh(c)
    msg = _Msg({"type": "cook_fish", "d": "wormwood_soup", "f": "gudgeon", "g": "common"})
    await house_handlers.cook(msg)
    assert len(msg.sent) == 1  # отказ дошёл, а не упал
