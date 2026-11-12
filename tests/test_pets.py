"""Питомцы и Пепельный дракон (2026-11-12, владелец).

Слот питомца без статов; хорёк за самоцветы; ворон тройке сезона PvP один
раз; дракон в мире один - будит его первый, кто ввёл код руны у Монолита,
и передаётся как вещь; в полёте его не видно с земли."""

import random
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from bot import pet_texts, raven
from game.economy import pet_config as pc
from game.economy import pts_config as ptc
from models import CharacterMount, MountTravel, PvpBattle, PvpSeasonResult
from services import (
    mount_service,
    pet_service,
    pts_service,
    pvp_service,
    shop_service,
    wallet_service,
)
from services import transfer_service as ts

NOV = datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc)
OCT_DAY = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def test_catalog_has_every_pet_in_order() -> None:
    assert list(pet_service.defs()) == list(pc.ORDER)
    for d in pet_service.defs().values():
        assert d.name and d.emoji and d.effect and d.flavor and d.how


async def test_grant_once_and_takes_empty_slot(db_session, make_character) -> None:
    c = await make_character()
    assert await pet_service.grant(db_session, c, pc.SPIDER)
    assert c.pet_id == pc.SPIDER
    assert not await pet_service.grant(db_session, c, pc.SPIDER)
    # Второй питомец в занятый слот не лезет - ждёт в «Герое».
    assert await pet_service.grant(db_session, c, pc.HOUND)
    assert c.pet_id == pc.SPIDER
    slot = await pet_service.payload(db_session, c)
    assert slot["worn"]["id"] == pc.SPIDER and [p["id"] for p in slot["bag"]] == [pc.HOUND]


async def test_wear_and_remove(db_session, make_character) -> None:
    c = await make_character()
    assert await pet_service.payload(db_session, c) is None
    with pytest.raises(pet_service.PetError):
        await pet_service.wear(db_session, c, pc.RAVEN)  # нет такого
    await pet_service.grant(db_session, c, pc.FERRET)
    await pet_service.grant(db_session, c, pc.RAVEN)
    await pet_service.wear(db_session, c, pc.RAVEN)
    assert c.pet_id == pc.RAVEN
    await pet_service.remove(db_session, c)
    assert c.pet_id is None
    slot = await pet_service.payload(db_session, c)
    assert slot["worn"] is None and len(slot["bag"]) == 2


async def test_ferret_bought_once_for_gems(db_session, make_character) -> None:
    c = await make_character(donate=pc.FERRET_PRICE + 10)
    await pet_service.grant(db_session, c, pc.HOUND)
    await shop_service.buy_ferret(db_session, c)
    assert c.pet_id == pc.FERRET  # купленный - сразу в слот
    assert (await wallet_service.get_wallet(db_session, c.id)).donate_currency == 10
    with pytest.raises(shop_service.ShopError):
        await shop_service.buy_ferret(db_session, c)
    item = shop_service.ferret_item(True)
    assert item["available"] is False and item["price"] == pc.FERRET_PRICE


async def test_ferret_needs_gems(db_session, make_character) -> None:
    c = await make_character(donate=10)
    with pytest.raises(shop_service.ShopError):
        await shop_service.buy_ferret(db_session, c)
    assert not await pet_service.owns(db_session, c.id, pc.FERRET)


async def test_dragon_wakes_only_once(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    state = await pet_service.dragon_state(db_session)
    assert len(state.code) == pc.CODE_LENGTH and all(ch in pc.CODE_ALPHABET for ch in state.code)
    assert await pet_service.claim_dragon(db_session, a)
    assert not await pet_service.claim_dragon(db_session, b)
    assert (await pet_service.dragon_owner(db_session)).id == a.id
    assert a.active_title_id == pc.DRAGON_TITLE_ID
    # Код тот же навсегда: руна бормочет одно и то же.
    assert (await pet_service.dragon_state(db_session)).code == state.code


def test_code_survives_copy_noise() -> None:
    assert pet_service.normalize(" «ᚠᚢᚦ ᚨᚱ» \n") == "ᚠᚢᚦᚨᚱ"


def test_gate_lets_only_the_exact_code(monkeypatch) -> None:
    from bot.handlers import pets

    monkeypatch.setattr(pets, "_code", "ᚠᚢᚦᚨᚱᚲᚷᚹ")
    assert pets.is_code("ᚠᚢᚦᚨᚱᚲᚷᚹ")
    assert pets.is_code("  ᚠᚢᚦᚨ ᚱᚲᚷᚹ ")
    assert not pets.is_code("ᚠᚢᚦᚨᚱᚲᚷ")
    assert not pets.is_code("привет")
    monkeypatch.setattr(pets, "_code", None)
    assert not pets.is_code("")


async def test_dragon_moves_by_transfer(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    await pet_service.claim_dragon(db_session, a)
    lookup = await ts.find(db_session, a.id, "пепельный дракон")
    assert [o.kind for o in lookup.offers] == ["mount"]
    await ts.execute(db_session, a.id, b.id, lookup.offers[0], 1)
    assert (await pet_service.dragon_owner(db_session)).id == b.id
    assert (await ts.find(db_session, a.id, "дракон")).offers == []


async def test_dragon_not_given_mid_flight(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    await pet_service.claim_dragon(db_session, a)
    a.pos_x, a.pos_y = 0, 20
    await mount_service.start_travel(db_session, a, pc.DRAGON_MOUNT_ID, 0, 10, random.Random(1))
    lookup = await ts.find(db_session, a.id, "дракон")
    assert lookup.offers == [] and "приземлитесь" in lookup.refusal
    offer = ts.Offer("mount", pc.DRAGON_MOUNT_ID, "🐉", 1, stackable=False)
    with pytest.raises(ts.TransferFailed):
        await ts.execute(db_session, a.id, b.id, offer, 1)


async def test_dragon_flies_straight_and_is_not_seen(db_session, make_character) -> None:
    rider = await make_character()
    walker = await make_character()
    await pet_service.claim_dragon(db_session, rider)
    assert mount_service.flies(pc.DRAGON_MOUNT_ID)
    assert mount_service.ambush_chance(pc.DRAGON_MOUNT_ID) == 0
    for c in (rider, walker):
        c.pos_x, c.pos_y = 0, 20
    await db_session.flush()
    travel = await mount_service.start_travel(db_session, rider, pc.DRAGON_MOUNT_ID, 0, 5, random.Random(1),
                                              safe=True)
    assert travel.path is None  # безопасный обход дракону не нужен - прямая
    assert await pvp_service.others_at(db_session, walker) == []
    travel.status = "completed"
    await db_session.flush()
    assert [c.id for c in await pvp_service.others_at(db_session, walker)] == [rider.id]


async def test_admin_cannot_make_second_dragon(db_session, make_character) -> None:
    from services import admin_grant_service

    a = await make_character()
    b = await make_character()
    await pet_service.claim_dragon(db_session, a)
    with pytest.raises(admin_grant_service.GrantError):
        await admin_grant_service.grant(db_session, 1, b, f"mount:{pc.DRAGON_MOUNT_ID}", 1, None, random.Random(1))
    rows = (await db_session.scalars(select(CharacterMount).where(CharacterMount.mount_id == pc.DRAGON_MOUNT_ID))).all()
    assert len(rows) == 1


async def test_raven_goes_to_top_three_once(db_session, make_character) -> None:
    chars = []
    for pts in (1400, 1300, 1200, 1100):
        c = await make_character(level=40)
        c.pts, c.pts_season = pts, "2026-10"
        chars.append(c)
    await db_session.flush()
    for c in chars:
        for _ in range(ptc.SEASON_MIN_FIGHTS):
            db_session.add(PvpBattle(battle_type="duel", participant_ids=[c.id], winner_ids=[c.id],
                                     started_at=OCT_DAY))
    await pet_service.grant(db_session, chars[1], pc.RAVEN)  # уже был с прошлого сезона
    await db_session.flush()
    await pts_service.season_rollover(db_session, NOV)
    results = (await db_session.scalars(select(PvpSeasonResult).order_by(PvpSeasonResult.place))).all()
    assert [r.raven for r in results] == [True, False, True, False]
    assert await pet_service.owns(db_session, chars[0].id, pc.RAVEN)
    assert not await pet_service.owns(db_session, chars[3].id, pc.RAVEN)


def test_raven_does_not_repeat_itself() -> None:
    raven._seen.clear()
    now = time.time()
    assert raven.fresh(1, [10, 11], now) == [10, 11]
    assert raven.fresh(1, [10, 11, 12], now + 60) == [12]
    later = now + pc.RAVEN_REPEAT_MINUTES * 60 + 1
    raven._forget_old(later)
    assert raven.fresh(1, [10], later) == [10]
    raven._seen.clear()


def test_directions_and_lines() -> None:
    assert pet_texts.direction(0, 1) == "к северу"
    assert pet_texts.direction(-3, -2) == "к юго-западу"
    assert pet_texts.direction(0, 0) == "на вашей клетке"
    assert "1 клетка к востоку" in pet_texts.hound_line("Вор", 1, 0)
    assert "5 клеток" in pet_texts.hound_line("Вор", 5, -3)
    assert pet_texts.raven_message(["А (Воин, 3 ур.) - к северу"]).startswith("🐦‍⬛ Ворон: рядом А")


def test_hound_points_at_nearest_brand(monkeypatch) -> None:
    from types import SimpleNamespace

    from bot import hound

    monkeypatch.setattr(hound, "_branded", [(2, "Далёкий", 10, 10), (3, "Близкий", 2, 0), (1, "Я", 0, 0)])
    me = SimpleNamespace(id=1, pos_x=0, pos_y=0, pet_id=pc.HOUND)
    assert "Близкий" in hound.line_for(me) and "к востоку" in hound.line_for(me)
    assert hound.line_for(SimpleNamespace(id=1, pos_x=0, pos_y=0, pet_id=pc.RAVEN)) is None


async def test_holders_lists_only_active(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    await pet_service.grant(db_session, a, pc.RUNE)
    await pet_service.grant(db_session, b, pc.FERRET)
    await pet_service.grant(db_session, b, pc.RUNE)  # есть, но не в слоте
    holders = await pet_service.holders(db_session, pc.RUNE)
    assert [c.id for c, _ in holders] == [a.id]


async def test_flying_query_only_flyers(db_session, make_character) -> None:
    a = await make_character()
    db_session.add(MountTravel(character_id=a.id, mount_id="ashen_steed", from_x=0, from_y=0, to_x=1, to_y=1,
                               arrives_at=datetime.now(timezone.utc), status="traveling"))
    await db_session.flush()
    assert (await db_session.scalars(mount_service.flying_query())).all() == []
