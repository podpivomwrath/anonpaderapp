"""Летопись: каталог титулов - открытые, условия закрытых, тайный скрыт."""

from services import title_service


async def test_catalog_hides_secret_and_explains_locked(db_session, make_character) -> None:
    character = await make_character()
    await title_service.unlock(db_session, character, "chronicler")
    rows = {r["id"]: r for r in await title_service.catalog(db_session, character)}
    assert rows["chronicler"]["unlocked"] and rows["chronicler"]["name"] == "Летописец"
    assert rows["relentless"]["how"] and not rows["relentless"]["unlocked"]
    assert rows["attentive"]["name"] == "???" and rows["attentive"]["secret"]
    first = next(iter(rows.values()))
    assert first["unlocked"]  # открытые - первыми
