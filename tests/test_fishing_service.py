

async def test_record_only_when_visible_weight_grows(db_session, make_character) -> None:
    """2026-10-13: «Личный рекорд» - только если вырос вес в тексте (0,1 кг),
    и не на первом улове вида."""
    from services.fishing_service import _update_record

    c = await make_character(level=5)
    assert await _update_record(db_session, c.id, "blind_gudgeon", 120) is False  # первый улов
    await db_session.flush()
    assert await _update_record(db_session, c.id, "blind_gudgeon", 140) is False  # 0,1 -> 0,1
    assert await _update_record(db_session, c.id, "blind_gudgeon", 260) is True   # 0,1 -> 0,3
    assert await _update_record(db_session, c.id, "blind_gudgeon", 200) is False  # легче
