"""Журнал ресурсов (2026-10-21): что пришло и ушло и откуда - сам, при каждом
сохранении, и явно у массовых UPDATE (жалоба «выдали два эпика, где они»)."""

from sqlalchemy import select

from models import CharacterOre, ResourceLog
from services import herb_service, resource_log
from services import transfer_service as ts


async def _log(db, character_id):
    return [(r.kind, r.ref, r.delta, r.reason) for r in (await db.scalars(
        select(ResourceLog).where(ResourceLog.character_id == character_id).order_by(ResourceLog.id)
    )).all()]


async def test_orm_changes_are_logged_with_their_origin(db_session, make_character) -> None:
    c = await make_character()
    await herb_service.add_herb(db_session, c.id, "bitter_wormwood", 3)  # новая строка
    await herb_service.add_herb(db_session, c.id, "bitter_wormwood", 2)  # изменение количества
    db_session.add(CharacterOre(character_id=c.id, ore_id="salt_quartz", grade="epic", count=2))
    await db_session.flush()
    rows = await _log(db_session, c.id)
    assert rows[0] == ("herb", "bitter_wormwood", 3, "herb_service.add_herb")
    assert rows[1] == ("herb", "bitter_wormwood", 2, "herb_service.add_herb")
    assert rows[2][:3] == ("ore", "salt_quartz:epic", 2)


async def test_bulk_transfer_is_logged_for_both_sides(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    await herb_service.add_herb(db_session, a.id, "bitter_wormwood", 5)
    offer = (await ts.find(db_session, a.id, "горькая полынь")).offers[0]
    await ts.execute(db_session, a.id, b.id, offer, 2)
    assert ("herb", "bitter_wormwood", -2) in [r[:3] for r in await _log(db_session, a.id)]
    assert ("herb", "bitter_wormwood", 2) in [r[:3] for r in await _log(db_session, b.id)]


async def test_cleanup_keeps_fresh_rows(db_session, make_character) -> None:
    c = await make_character()
    resource_log.add(db_session, c.id, "ore", "salt_quartz:common", 1, reason="тест")
    await db_session.flush()
    assert await resource_log.cleanup(db_session) == 0
    assert len(await _log(db_session, c.id)) == 1


async def test_admin_card_shows_journal_in_russian(db_session, make_character) -> None:
    from services import admin_service

    c = await make_character()
    db_session.add(CharacterOre(character_id=c.id, ore_id="salt_quartz", grade="epic", count=2))
    await db_session.flush()
    rows = await admin_service.resource_journal(db_session, c.id)
    assert rows[0]["what"] == "⛏ Соляной кварц (эпическая)" and rows[0]["amount"] == "+2"
    card = await admin_service.player_card(db_session, c.id)
    assert card["resource_log"] and card["wallet_log"] is not None
