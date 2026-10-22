"""Мини-апп, вкладка «Герой» (2026-10-22): пол, кольцо опыта, полка трофеев."""

from models import Character, CharacterFishRecord, Inventory, Item, RaidRun
from services import item_service, raid_service
from tests.test_miniapp_api import (  # noqa: F401 - фикстуры
    _make_character,
    _signed_query,
    client,
    session_factory,
    settings,
)


async def test_character_has_xp_ring_and_gender(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=701)
    data = await (await client.get("/api/miniapp/character", params=_signed_query(701))).json()
    assert data["gender"] == "m"
    assert data["xp"] == 0 and data["xp_to_next"] > 0


async def test_gender_is_saved_and_validated(client, session_factory) -> None:
    await _make_character(session_factory, vk_id=702)
    bad = await client.post("/api/miniapp/gender", params=_signed_query(702), json={"gender": "x"})
    assert bad.status == 400
    ok = await client.post("/api/miniapp/gender", params=_signed_query(702), json={"gender": "f"})
    assert (await ok.json()) == {"gender": "f"}
    data = await (await client.get("/api/miniapp/character", params=_signed_query(702))).json()
    assert data["gender"] == "f"


async def test_trophies_shelf(client, session_factory) -> None:
    c = await _make_character(session_factory, vk_id=703)
    async with session_factory() as db:
        db.add(RaidRun(leader_character_id=c.id, raid_id="graveless_field", members=[c.id], status="active"))
        await db.flush()
        run = (await db.execute(RaidRun.__table__.select())).first()
        await raid_service.finish_run(db, run.id, won=True)
        # Чужая победа и проигранный заход - не в счёт.
        db.add(RaidRun(leader_character_id=c.id, raid_id="faceless_archive", members=[c.id], status="finished"))
        db.add(RaidRun(leader_character_id=c.id, raid_id="pilgrim_mill", members=[c.id + 1], status="won"))
        # Вещь с босса Тропы - старая победа, когда статуса won ещё не было.
        stride = item_service.unique_items()["nameless_stride"]
        item = Item(name=stride.name, slot="boots", base_stats={"agi": 3}, rarity="unique")
        db.add(item)
        await db.flush()
        db.add(Inventory(character_id=c.id, item_id=item.id))
        db.add(CharacterFishRecord(character_id=c.id, fish_id="gudgeon", weight_grams=120))
        ch = await db.get(Character, c.id)
        ch.mobs_killed, ch.pvp_wins = 42, 3
        await db.commit()
    data = await (await client.get("/api/miniapp/trophies", params=_signed_query(703))).json()
    won = {r["raid"]: r["won"] for r in data["raids"]}
    assert won == {"puppet_theatre": False, "graveless_field": True, "faceless_archive": False,
                   "pilgrim_mill": False, "nameless_trail": True}
    assert data["mobs_killed"] == 42 and data["pvp_wins"] == 3
    assert data["best_fish"]["weight"] and data["titles_total"] > 0
