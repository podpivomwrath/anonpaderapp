"""Передача по нику из мини-аппа (2026-10-22)."""

from sqlalchemy import select

from models import Character, CharacterConsumable, Inventory, Item, TransferLog
from tests.test_miniapp_api import (  # noqa: F401 - фикстуры
    _make_character,
    _signed_query,
    client,
    session_factory,
    settings,
)


async def _give_item(session_factory, character_id: int, name: str = "Ржавый клинок") -> int:
    async with session_factory() as db:
        item = Item(name=name, slot="weapon", base_stats={"str": 3}, rarity="common", ilvl=5)
        db.add(item)
        await db.flush()
        db.add(Inventory(character_id=character_id, item_id=item.id))
        await db.commit()
        return item.id


async def test_item_by_nick_preview_then_confirm(client, session_factory) -> None:
    a = await _make_character(session_factory, vk_id=801)
    b = await _make_character(session_factory, vk_id=802)
    item_id = await _give_item(session_factory, a.id)
    body = {"command": f"/передать Ржавый клинок {item_id}", "name": "Герой802"}

    preview = await client.post("/api/miniapp/transfer", params=_signed_query(801), json=body)
    data = await preview.json()
    assert data["preview"]["to"] == "Герой802" and not data["preview"]["courier"]
    async with session_factory() as db:  # проверка ничего не передала
        assert (await db.scalar(select(Inventory.character_id).where(Inventory.item_id == item_id))) == a.id

    done = await client.post("/api/miniapp/transfer", params=_signed_query(801), json={**body, "confirm": True})
    assert "Герой802" in (await done.json())["done"]
    async with session_factory() as db:
        assert (await db.scalar(select(Inventory.character_id).where(Inventory.item_id == item_id))) == b.id
        assert await db.scalar(select(TransferLog.id)) is not None


async def test_stack_by_nick_with_quantity(client, session_factory) -> None:
    a = await _make_character(session_factory, vk_id=803)
    b = await _make_character(session_factory, vk_id=804)
    async with session_factory() as db:
        db.add(CharacterConsumable(character_id=a.id, elixir_id="heal_small", count=5))
        await db.commit()
    body = {"command": "/передать Малое исцеление", "qty": 3, "name": "Герой804", "confirm": True}
    res = await client.post("/api/miniapp/transfer", params=_signed_query(803), json=body)
    assert res.status == 200, await res.text()
    async with session_factory() as db:
        mine = await db.scalar(select(CharacterConsumable.count).where(CharacterConsumable.character_id == a.id))
        theirs = await db.scalar(select(CharacterConsumable.count).where(CharacterConsumable.character_id == b.id))
    assert (mine, theirs) == (2, 3)


async def test_far_recipient_without_courier_is_refused(client, session_factory) -> None:
    a = await _make_character(session_factory, vk_id=805)
    b = await _make_character(session_factory, vk_id=806)
    async with session_factory() as db:
        far = await db.get(Character, b.id)
        far.pos_x, far.pos_y = 40, 40
        await db.commit()
    item_id = await _give_item(session_factory, a.id)
    res = await client.post("/api/miniapp/transfer", params=_signed_query(805),
                            json={"command": f"/передать Ржавый клинок {item_id}", "name": "Герой806"})
    assert res.status == 400
    assert "курьер" in (await res.json())["error"]


async def test_unknown_nick_and_self(client, session_factory) -> None:
    a = await _make_character(session_factory, vk_id=807)
    item_id = await _give_item(session_factory, a.id)
    cmd = f"/передать Ржавый клинок {item_id}"
    nobody = await client.post("/api/miniapp/transfer", params=_signed_query(807), json={"command": cmd, "name": "Никто"})
    assert nobody.status == 404
    me = await client.post("/api/miniapp/transfer", params=_signed_query(807), json={"command": cmd, "name": "Герой807"})
    assert me.status == 400
