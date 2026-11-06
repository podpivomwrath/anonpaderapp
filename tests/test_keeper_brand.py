"""Клеймо Хранителя (2026-11-06): премиум для 60 уровня и перстень в руинах."""

import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from game.economy import brand_config as brc
from game.economy import premium_config as pc
from game.economy import raid_key_config as rkc
from game.economy import ruins_config as rc
from game.ruins_rooms import rules
from services import premium_service, ruins_service, shop_service

NOW = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def _char(**kw):
    base = dict(premium_until=None, brand_until=None, legacy_perks_until=None,
                premium_warn_sent=False, premium_expire_notified=False,
                brand_warn_sent=False, brand_expire_notified=False, level=60)
    return SimpleNamespace(**{**base, **kw})


def test_brand_check_extend_and_badge() -> None:
    c = _char()
    assert not premium_service.is_brand(c, NOW) and premium_service.badge(c, NOW) == ""
    premium_service.extend_brand(c, 3, NOW)
    premium_service.extend_brand(c, 2, NOW)
    assert c.brand_until == NOW + 5 * DAY, "срок складывается"
    c.premium_until = NOW + DAY
    assert premium_service.badge(c, NOW) == f"{brc.BRAND_BADGE} ", "Клеймо старше Метки"
    c.brand_until = NOW - DAY
    assert premium_service.badge(c, NOW) == f"{pc.PREMIUM_BADGE} "


def test_expiry_notices_for_both() -> None:
    c = _char(premium_until=NOW + timedelta(hours=5), brand_until=NOW + timedelta(hours=3))
    text = premium_service.check_expiry_notice(c, NOW)
    assert pc.EXPIRY_WARNING_TEXT in text and brc.EXPIRY_WARNING_TEXT in text
    assert premium_service.check_expiry_notice(c, NOW) is None, "разово"
    later = NOW + DAY
    assert brc.EXPIRED_TEXT in premium_service.check_expiry_notice(c, later)


def test_keys_and_preset_moved_to_brand_with_legacy() -> None:
    from services import preset_service, raid_key_service

    c = _char(premium_until=NOW + 10 * DAY, raid_keys=0, preset_slots=1)
    assert not premium_service.big_key_cap(c, NOW), "новая Метка ключей не даёт"
    c.legacy_perks_until = NOW + 10 * DAY
    assert premium_service.big_key_cap(c, NOW), "Метка, активная в день переноса, - до конца срока"
    assert not premium_service.big_key_cap(c, NOW + 11 * DAY)
    c = _char(brand_until=datetime.now(timezone.utc) + DAY, raid_keys=0, preset_slots=1)
    assert raid_key_service.current_cap(c) == rkc.RAID_KEY_CAP_PREMIUM
    assert preset_service.effective_preset_slots(c) == 1 + pc.PRESET_SLOT_BONUS


def test_shop_item_price_and_perks() -> None:
    item = shop_service.brand_item(_char())
    assert item["id"] == shop_service.BRAND_ID and item["kind"] == "days"
    assert item["prices"][1] == 75 and item["prices"][30] == 1200, "в полтора раза дороже Метки"
    perks = shop_service._premium_perks()
    assert not any("Ключей Монолита" in p or "слот пресета" in p for p in perks), "ушли на Клеймо"


async def test_buy_brand_needs_level_60(make_character, db_session) -> None:
    young = await make_character(level=59, donate=10_000)
    with pytest.raises(shop_service.ShopError):
        await shop_service.buy_brand(db_session, young, 7)
    old = await make_character(level=60, donate=10_000)
    until = await shop_service.buy_brand(db_session, old, 7)
    assert premium_service.is_brand(old) and until > datetime.now(timezone.utc) + 6 * DAY


async def test_rune_drop_chance_in_exploration(make_character, db_session, monkeypatch) -> None:
    from services import rune_service

    seen = []

    async def fake_drop(db, character, rng, chance=None):
        seen.append(chance)

    monkeypatch.setattr(rune_service, "maybe_drop", fake_drop)
    c = await make_character(level=60)
    await rune_service.drop_line(db_session, c, random.Random(1))
    c.brand_until = datetime.now(timezone.utc) + DAY
    await rune_service.drop_line(db_session, c, random.Random(1))
    from game.economy import runes_config

    assert seen == [runes_config.MOB_DROP_CHANCE, pytest.approx(runes_config.MOB_DROP_CHANCE * brc.RUNE_DROP_MULT)]


async def _run(db_session, make_character, kind: str):
    a = await make_character(level=60)
    a.pos_x, a.pos_y = rc.ENTRY_CELL
    run = await ruins_service.start(db_session, a, [a], random.Random(1))
    rooms = dict(run.layout["rooms"])
    target = next(iter(rules.exits(run.layout, run.pos).values()))
    rooms[str(target)] = kind
    run.layout = {**run.layout, "rooms": rooms, "events": {}}
    ruins_service.move(run, target)
    return run, a


async def test_wipe_salvage_only_with_brand(make_character, db_session) -> None:
    run, a = await _run(db_session, make_character, rules.FIGHT)
    (m,) = await ruins_service.members(db_session, run.id)
    m.bag = {"trophies": {"ash_dust": 8}, "runes": {"thin_sting": 1}}
    assert await ruins_service.brand_salvage(db_session, run, random.Random(1)) == {}
    a.brand_until = datetime.now(timezone.utc) + DAY
    kept = await ruins_service.brand_salvage(db_session, run, random.Random(1))
    assert kept == {a.id: {"ash_dust": 2}}, "четверть реликвий, руны сгорают"


async def test_ring_drops_in_ruins_straight_to_player(make_character, db_session, monkeypatch) -> None:
    from game.economy import resists

    run, a = await _run(db_session, make_character, rules.FIGHT)
    monkeypatch.setattr(resists, "RING_DROP_CHANCE", 1.0)
    found = await ruins_service.room_won(db_session, run, {a.id: 100}, {a.id: 0}, random.Random(1), kills=2)
    assert found[a.id].get("ring") in ("worn", "bag")
    from bot import ruins_texts

    assert "Перстень" in ruins_texts.found_line(found[a.id])
    monkeypatch.setattr(resists, "RING_DROP_CHANCE", 0.0)
    run2, b = await _run(db_session, make_character, rules.FIGHT)
    found = await ruins_service.room_won(db_session, run2, {b.id: 100}, {b.id: 0}, random.Random(1), kills=2)
    assert "ring" not in found[b.id]


def test_cart_extra_crate() -> None:
    from services import trade_service

    cart = SimpleNamespace(body=1)
    plain, branded = _char(), _char(brand_until=datetime.now(timezone.utc) + DAY)
    assert trade_service.capacity(cart, plain) == trade_service.capacity(cart) == 8
    assert trade_service.capacity(cart, branded) == 8 + brc.CART_EXTRA_CRATES


async def test_voyage_craft_chance_doubles(make_character, db_session, monkeypatch) -> None:
    from services import voyage_service

    class Passed(Exception):
        pass

    class Rng:
        """Бросок шанса - 0,6; дошло до выбора ремесла - шанс пройден."""

        def random(self) -> float:
            return 0.6

        def choice(self, seq):
            raise Passed

    monkeypatch.setattr(voyage_service.vc, "CRAFT_XP_CHANCE", 0.4)
    c = await make_character(level=60)
    c.fishing_level = 1
    assert await voyage_service.craft_xp(db_session, c, Rng()) is None, "0,4 < 0,6 - без ремесла"
    c.brand_until = datetime.now(timezone.utc) + DAY
    with pytest.raises(Passed):
        await voyage_service.craft_xp(db_session, c, Rng())  # 0,4 × 2 = 0,8 > 0,6


async def test_rift_notice_goes_to_brand_holders_of_its_band(make_character, db_session) -> None:
    from models import Rift
    from services import rift_service

    from models import User

    holder = await make_character(level=60)
    holder.brand_until = datetime.now(timezone.utc) + DAY
    vk_id = (await db_session.get(User, holder.user_id)).vk_id
    await make_character(level=60)  # без Клейма
    now = datetime.now(timezone.utc)
    high = Rift(kind=next(iter(rift_service.rc.RIFT_TYPES)), ring=4, x=1, y=1, status="active", state="free",
                members=[], spawned_at=now, expires_at=now + timedelta(minutes=30))
    low = Rift(kind=high.kind, ring=1, x=2, y=2, status="active", state="free",
               members=[], spawned_at=now, expires_at=now + timedelta(minutes=30))
    db_session.add_all([high, low])
    await db_session.flush()
    assert await rift_service.brand_watchers(db_session, high) == [vk_id]
    assert await rift_service.brand_watchers(db_session, low) == []
    from bot import rift_texts

    assert "(1; 1)" in rift_texts.brand_notice(high, 30)
