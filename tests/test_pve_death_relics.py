"""2026-10-17: смерть в PvE сжигает все реликвии (в PvP их забирает победитель)."""

from models import CharacterTrophy
from services import encounter_service, trophy_service


async def test_pve_defeat_burns_all_relics(db_session, make_character) -> None:
    character = await make_character()
    db_session.add(CharacterTrophy(character_id=character.id, trophy_id="ash_dust", count=5))
    db_session.add(CharacterTrophy(character_id=character.id, trophy_id="blood_shard", count=2))
    await db_session.flush()

    defeat = await encounter_service.resolve_defeat(db_session, character)

    assert defeat.relics_lost == {"ash_dust": 5, "blood_shard": 2}
    assert await trophy_service.get_stock(db_session, character.id) == []
    assert "рассыпались в пепел" in trophy_service.lost_line(defeat.relics_lost)


async def test_pve_defeat_without_relics_loses_nothing(db_session, make_character) -> None:
    character = await make_character()
    defeat = await encounter_service.resolve_defeat(db_session, character)
    assert defeat.relics_lost == {}
    assert trophy_service.lost_line({}) == ""
