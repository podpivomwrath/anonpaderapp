"""Мини-апп, 2026-11-14 (владелец): «Сейчас идёт», отметка «▲» у «Инвентаря»,
мои забеги в руинах, окно чужого игрока - только надетое."""

from datetime import datetime, timedelta, timezone

from models import Inventory, Item, RuinMember, RuinRun
from services import item_service


async def _item(db, character, slot: str, stats: dict, equipped: bool, ilvl: int | None = None) -> Item:
    item = Item(name=f"Вещь {slot} {sum(stats.values())}", slot=slot, base_stats=stats, rarity="common", ilvl=ilvl)
    db.add(item)
    await db.flush()
    db.add(Inventory(character_id=character.id, item_id=item.id, equipped=equipped))
    await db.flush()
    return item


async def test_better_items_counts_slots_with_a_stronger_wearable_item(db_session, make_character) -> None:
    c = await make_character(level=10)
    await _item(db_session, c, "weapon", {"str": 5}, True)
    await _item(db_session, c, "weapon", {"str": 9}, False)          # сильнее - да
    await _item(db_session, c, "weapon", {"str": 12}, False)         # тот же слот - один раз
    await _item(db_session, c, "helmet", {"vit": 3}, True)
    await _item(db_session, c, "helmet", {"vit": 2}, False)          # слабее - нет
    await _item(db_session, c, "boots", {"agi": 30}, False, ilvl=40)  # не по уровню - нет
    await _item(db_session, c, "legs", {"vit": 1}, False)            # пустой слот - да
    items = await item_service.get_inventory(db_session, c.id)
    assert item_service.better_than_worn(items, c.level) == 2


async def test_now_running_lists_brewing_and_mount_with_end_times(db_session, make_character) -> None:
    from bot import now_running
    from models import MountTravel

    c = await make_character(level=30)
    now = datetime.now(timezone.utc)
    c.house_work = "alchemy:heal_small"
    c.house_work_until = now + timedelta(minutes=5)
    db_session.add(MountTravel(
        character_id=c.id, mount_id="turbo_ishak", from_x=0, from_y=0, to_x=3, to_y=0,
        started_at=now, arrives_at=now + timedelta(seconds=30), ambush_at=None, ambush_done=True,
        status="traveling", step_seconds=10, cell_index=0, next_cell_at=now + timedelta(seconds=10), path=None,
    ))
    await db_session.flush()
    rows = {r["id"]: r for r in await now_running.collect(db_session, c, 987654321, now)}
    assert rows["brew"]["title"].startswith("Варка") and abs(rows["brew"]["ends_at"] - (now.timestamp() + 300)) < 2
    assert rows["ride"]["title"] == "Верхом в (3; 0)" and rows["ride"]["ends_at"] > now.timestamp()
    assert "dead" not in rows and "battle" not in rows


async def test_now_running_is_empty_for_an_idle_hero(db_session, make_character) -> None:
    from bot import now_running

    c = await make_character(level=5)
    assert await now_running.collect(db_session, c, 987654322) == []


async def test_look_shows_only_worn_things(db_session, make_character) -> None:
    """Владелец: «никакой лишней информации по типу инвентаря игрока или его
    страницы»."""
    from bot.miniapp_look_api import look_payload

    c = await make_character(level=20)
    worn = await _item(db_session, c, "weapon", {"str": 7}, True)
    await _item(db_session, c, "helmet", {"vit": 99}, False)
    data = await look_payload(db_session, c)
    assert [i["name"] for i in data["items"]] == [worn.name]
    assert set(data) == {
        "name", "level", "base_class", "subclass", "gender", "class_title", "title", "title_tier",
        "items", "ring", "runes",
    }
    assert set(data["runes"]) == {"hero", "abilities", "gear"}
    text = repr(data)
    for leak in ("vk_id", "pos_x", "gold", "farm_currency", "bag", "user_id"):
        assert leak not in text


async def test_my_runs_newest_first_with_party_and_bag(db_session, make_character) -> None:
    from services import ruins_top_service

    me = await make_character(level=60)
    mate = await make_character(level=60)
    t0 = datetime(2026, 11, 13, 10, 0, tzinfo=timezone.utc)
    old = RuinRun(status="done", outcome="exited", leader_id=me.id, floor=5, deepest=5,
                  started_at=t0, finished_at=t0 + timedelta(minutes=30))
    new = RuinRun(status="done", outcome="wiped", leader_id=me.id, floor=9, deepest=9,
                  started_at=t0 + timedelta(hours=2), finished_at=t0 + timedelta(hours=3, minutes=5))
    live = RuinRun(status="active", leader_id=me.id, floor=1, started_at=t0 + timedelta(hours=5))
    db_session.add_all([old, new, live])
    await db_session.flush()
    db_session.add_all([
        RuinMember(run_id=old.id, character_id=me.id, floors=5, left_reason="exited",
                   bag={"runes": {}, "trophies": {}}),
        RuinMember(run_id=new.id, character_id=me.id, floors=8, left_reason="wiped", bag={}),
        RuinMember(run_id=new.id, character_id=mate.id, floors=8, left_reason="wiped", bag={}),
        RuinMember(run_id=live.id, character_id=me.id),
    ])
    await db_session.flush()
    runs = await ruins_top_service.my_runs(db_session, me.id)
    assert [r.run_id for r in runs] == [new.id, old.id]
    assert runs[0].party == [me.id, mate.id] and runs[0].floors == 8
    assert ruins_top_service.run_length(runs[0].started_at, runs[0].finished_at) == "1 ч 5 мин"
