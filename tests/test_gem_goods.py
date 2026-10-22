"""Товары за самоцветы (2026-10-19): настойка пепла, секретный карман,
смена фракции."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from game.economy import gem_goods_config as ggc
from game.world import world_config as wc
from models import CharacterQuest, CharacterStoryProgress, CharacterTrophy, CharacterVoyage
from services import death_service, shop_service, story_service, trophy_service, wallet_service

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)


# --- Секретный карман ---------------------------------------------------------

def test_pocket_keeps_half_rounding_up() -> None:
    assert [ggc.pocket_keeps(n) for n in (1, 2, 3, 10)] == [1, 1, 2, 5]


async def _stock(db, cid) -> dict[str, int]:
    return {d.id: n for d, n in await trophy_service.get_stock(db, cid)}


async def test_pve_death_keeps_half_with_pocket(db_session, make_character) -> None:
    c = await make_character()
    c.secret_pocket = True
    db_session.add(CharacterTrophy(character_id=c.id, trophy_id="ash_dust", count=5))
    db_session.add(CharacterTrophy(character_id=c.id, trophy_id="blood_shard", count=1))
    await db_session.flush()
    lost = await trophy_service.lose_all(db_session, c.id)
    assert lost == {"ash_dust": 2}
    assert await _stock(db_session, c.id) == {"ash_dust": 3, "blood_shard": 1}


async def test_pve_death_without_pocket_loses_all(db_session, make_character) -> None:
    c = await make_character()
    db_session.add(CharacterTrophy(character_id=c.id, trophy_id="ash_dust", count=5))
    await db_session.flush()
    assert await trophy_service.lose_all(db_session, c.id) == {"ash_dust": 5}
    assert await _stock(db_session, c.id) == {}


async def test_duel_winner_takes_only_the_unpocketed_half(db_session, make_character) -> None:
    loser, winner = await make_character(), await make_character()
    loser.secret_pocket = True
    db_session.add(CharacterTrophy(character_id=loser.id, trophy_id="ash_dust", count=10))
    await db_session.flush()
    assert await trophy_service.transfer_all(db_session, loser.id, winner.id) == {"ash_dust": 5}
    assert await _stock(db_session, loser.id) == {"ash_dust": 5}
    assert await _stock(db_session, winner.id) == {"ash_dust": 5}


async def test_mass_pvp_splits_only_the_unpocketed_half(db_session, make_character) -> None:
    victim, a, b = await make_character(), await make_character(), await make_character()
    victim.secret_pocket = True
    db_session.add(CharacterTrophy(character_id=victim.id, trophy_id="ash_dust", count=10))
    await db_session.flush()
    result = await trophy_service.split_among(db_session, victim.id, {a.id: 1.0, b.id: 1.0})
    assert sum(d.get("ash_dust", 0) for d in result.values()) == 5
    assert await _stock(db_session, victim.id) == {"ash_dust": 5}


async def test_pocket_is_bought_once(db_session, make_character) -> None:
    c = await make_character(donate=2000)
    await shop_service.buy_pocket(db_session, c)
    assert c.secret_pocket is True
    with pytest.raises(shop_service.ShopError):
        await shop_service.buy_pocket(db_session, c)
    assert (await wallet_service.get_wallet(db_session, c.id)).donate_currency == 2000 - ggc.POCKET_PRICE


# --- Настойка пепла -----------------------------------------------------------

async def test_tincture_saves_xp_on_pve_death(make_character) -> None:
    c = await make_character(level=30, experience=1000)
    c.ash_tincture_until = NOW + timedelta(hours=1)
    assert death_service.apply_death(c, NOW) == 0
    assert c.experience == 1000
    assert c.respawn_at is not None


async def test_expired_tincture_does_nothing(make_character) -> None:
    c = await make_character(level=30, experience=1000)
    c.ash_tincture_until = NOW - timedelta(seconds=1)
    assert death_service.apply_death(c, NOW) > 0


async def test_tincture_saves_branded_player_in_pvp(make_character) -> None:
    from game.economy import pk_config as pc

    now = datetime.now(timezone.utc)  # метки клейма сходят по настоящему времени
    c = await make_character(level=30, experience=1000)
    c.pk_marks, c.pk_marks_at = pc.COSTLY_DEATH_FROM, now
    c.ash_tincture_until = now + timedelta(hours=1)
    death_service.apply_pvp_death(c, now)
    assert c.experience == 1000
    c.ash_tincture_until = None
    death_service.apply_pvp_death(c, now)
    assert c.experience < 1000


async def test_second_tincture_adds_two_hours(db_session, make_character) -> None:
    c = await make_character(donate=1000)
    first = await shop_service.buy_tincture(db_session, c, NOW)
    assert first == NOW + timedelta(hours=ggc.TINCTURE_HOURS)
    second = await shop_service.buy_tincture(db_session, c, NOW + timedelta(minutes=30))
    assert second == NOW + timedelta(hours=2 * ggc.TINCTURE_HOURS)


# --- Смена фракции ------------------------------------------------------------

async def _story_row(db, cid, region):
    return await db.scalar(select(CharacterStoryProgress).where(
        CharacterStoryProgress.character_id == cid, CharacterStoryProgress.region == region))


async def test_faction_change_moves_and_carries_story_act(db_session, make_character, seed_quests) -> None:
    c = await make_character(level=40, donate=1000, region="ridge")
    db_session.add(CharacterStoryProgress(
        character_id=c.id, region="ridge", act=3, quest_step="ridge_3_2", status="active"))
    await db_session.flush()

    await shop_service.change_faction(db_session, c, "docks", NOW)

    assert c.region == "docks"
    assert (c.pos_x, c.pos_y) == wc.CITY_COORDS["docks"]
    row = await _story_row(db_session, c.id, "docks")
    assert (row.act, row.quest_step, row.status, row.completed) == (3, "docks_3_1", "active", False)
    # Стартовый квест нового города закрыт: наставник ведёт сразу по сюжету.
    starter = await db_session.scalar(select(CharacterQuest).where(CharacterQuest.character_id == c.id))
    assert starter.status == "completed"
    assert (await wallet_service.get_wallet(db_session, c.id)).donate_currency == 1000 - ggc.FACTION_PRICE


async def test_act_one_skips_the_starter_quest(db_session, make_character, seed_quests) -> None:
    c = await make_character(level=10, donate=1000, region="ridge")
    db_session.add(CharacterStoryProgress(
        character_id=c.id, region="ridge", act=1, quest_step="ridge_1_3", status="active"))
    await db_session.flush()
    await shop_service.change_faction(db_session, c, "woods", NOW)
    assert (await _story_row(db_session, c.id, "woods")).quest_step == "woods_1_2"


async def test_starter_not_done_means_fresh_story(db_session, make_character, seed_quests) -> None:
    c = await make_character(level=3, donate=1000, region="ridge")
    db_session.add(CharacterStoryProgress(
        character_id=c.id, region="ridge", act=1, quest_step="ridge_1_1", status="active"))
    await db_session.flush()
    await shop_service.change_faction(db_session, c, "woods", NOW)
    assert await _story_row(db_session, c.id, "woods") is None


async def test_completed_line_stays_completed(db_session, make_character, seed_quests) -> None:
    c = await make_character(level=60, donate=1000, region="ridge")
    db_session.add(CharacterStoryProgress(
        character_id=c.id, region="ridge", act=5, quest_step="ridge_5_2", status="active", completed=True))
    await db_session.flush()
    await shop_service.change_faction(db_session, c, "scorched", NOW)
    assert (await _story_row(db_session, c.id, "scorched")).completed is True


async def test_further_progress_in_new_city_is_kept(db_session, make_character, seed_quests) -> None:
    c = await make_character(level=40, donate=1000, region="ridge")
    db_session.add(CharacterStoryProgress(
        character_id=c.id, region="ridge", act=2, quest_step="ridge_2_1", status="active"))
    db_session.add(CharacterStoryProgress(
        character_id=c.id, region="docks", act=4, quest_step="docks_4_2", status="ready"))
    await db_session.flush()
    await shop_service.change_faction(db_session, c, "docks", NOW)
    row = await _story_row(db_session, c.id, "docks")
    assert (row.quest_step, row.status) == ("docks_4_2", "ready")


async def test_faction_change_ends_voyage_and_moves_gear(db_session, make_character, seed_quests) -> None:
    c = await make_character(level=40, donate=1000, region="ridge")
    db_session.add(CharacterVoyage(
        character_id=c.id, region="ridge", endurance=3, haul=2, guide=1, status="away",
        hours_done=2, trip_xp=0, trip_gold=0, trip_items={}, voyages_total=0,
    ))
    await db_session.flush()
    text = await shop_service.change_faction(db_session, c, "docks", NOW)
    voyage = await db_session.get(CharacterVoyage, c.id)
    assert text and voyage.status == "home" and voyage.region == "docks" and voyage.endurance == 3


async def test_faction_cooldown_and_bad_input(db_session, make_character, seed_quests) -> None:
    c = await make_character(level=40, donate=5000, region="ridge")
    with pytest.raises(shop_service.ShopError):
        await shop_service.change_faction(db_session, c, "ridge", NOW)
    with pytest.raises(shop_service.ShopError):
        await shop_service.change_faction(db_session, c, "atlantis", NOW)
    await shop_service.change_faction(db_session, c, "docks", datetime.now(timezone.utc))
    with pytest.raises(shop_service.ShopError):
        await shop_service.change_faction(db_session, c, "woods")
    # Отказ ничего не списывает.
    assert (await wallet_service.get_wallet(db_session, c.id)).donate_currency == 5000 - ggc.FACTION_PRICE
    assert shop_service.faction_item(c)["available"] is False


async def test_catalog_lists_new_goods(make_character) -> None:
    c = await make_character(region="ridge")
    ids = [i["id"] for i in shop_service.catalog(c, 0)["items"]]
    assert {ggc.TINCTURE_ID, ggc.POCKET_ID, ggc.FACTION_ID} <= set(ids)
    faction = next(i for i in shop_service.catalog(c, 0)["items"] if i["id"] == ggc.FACTION_ID)
    assert {o["id"] for o in faction["options"]} == {"docks", "woods", "scorched"}


def test_story_lines_share_act_layout() -> None:
    """Перенос «на тот же акт» опирается на одинаковое число актов во всех
    городах - если линию одного города перестроят, тест подскажет."""
    acts = {r: [a.act for a in story_service.get_line(r).acts] for r in ("ridge", "docks", "woods", "scorched")}
    assert len({tuple(v) for v in acts.values()}) == 1


async def test_bought_in_battle_moves_after(db_session, make_character, seed_quests) -> None:
    """Куплено в бою (2026-10-19): самоцветы списаны сразу, город прежний,
    переезд - move_pending, когда бой кончился."""
    c = await make_character(level=40, donate=1000, region="ridge")
    c.pos_x, c.pos_y = 5, 5
    await shop_service.change_faction(db_session, c, "docks", NOW, defer=True)
    assert (c.region, c.pending_faction, (c.pos_x, c.pos_y)) == ("ridge", "docks", (5, 5))
    assert (await wallet_service.get_wallet(db_session, c.id)).donate_currency == 1000 - ggc.FACTION_PRICE
    item = shop_service.faction_item(c)
    assert item["available"] is False and item["pending"]
    with pytest.raises(shop_service.ShopError):
        await shop_service.change_faction(db_session, c, "woods", NOW)

    await shop_service.move_pending(db_session, c, NOW)
    assert (c.region, c.pending_faction, (c.pos_x, c.pos_y)) == ("docks", None, wc.CITY_COORDS["docks"])


async def test_bought_while_dead_waits_for_respawn(db_session, make_character, seed_quests) -> None:
    c = await make_character(level=40, donate=1000, region="ridge")
    c.respawn_at = NOW + timedelta(minutes=5)
    await shop_service.change_faction(db_session, c, "docks", NOW)
    assert (c.region, c.pending_faction) == ("ridge", "docks")


async def test_tinctures_by_quantity_stack_time(db_session, make_character) -> None:
    c = await make_character(donate=ggc.TINCTURE_PRICE * 5)
    until = await shop_service.buy_tincture(db_session, c, NOW, qty=5)
    assert until == NOW + timedelta(hours=5 * ggc.TINCTURE_HOURS)
