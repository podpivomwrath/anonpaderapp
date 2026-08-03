"""Пепельная Песнь — сбор обрывков + прочтение у алтаря (патч 25, п.6)."""

from services import mount_service, song_service, title_service


async def test_record_seen_and_progress(db_session, make_character) -> None:
    character = await make_character(level=10)
    assert await song_service.is_complete(db_session, character.id) is False

    for i in range(9):
        await song_service.record_seen(db_session, character, i)
    assert await song_service.is_complete(db_session, character.id) is False

    await song_service.record_seen(db_session, character, 9)
    assert await song_service.is_complete(db_session, character.id) is True


async def test_record_seen_idempotent(db_session, make_character) -> None:
    character = await make_character(level=10)
    await song_service.record_seen(db_session, character, 3)
    await song_service.record_seen(db_session, character, 3)  # повторный показ того же обрывка
    seen = await song_service.seen_indices(db_session, character.id)
    assert seen == {3}


async def test_can_read_only_when_complete_and_not_read(db_session, make_character) -> None:
    character = await make_character(level=10)
    assert await song_service.can_read(db_session, character.id) is False

    for i in range(10):
        await song_service.record_seen(db_session, character, i)
    assert await song_service.can_read(db_session, character.id) is True

    await song_service.read_song(db_session, character)
    assert await song_service.can_read(db_session, character.id) is False
    assert await song_service.already_read(db_session, character.id) is True


async def test_read_song_grants_title_and_mount_once(db_session, make_character) -> None:
    character = await make_character(level=10)
    for i in range(10):
        await song_service.record_seen(db_session, character, i)

    granted = await song_service.read_song(db_session, character)
    assert granted is True
    assert character.active_title_id == "chronicler"
    assert title_service.name_of(character.active_title_id) == "Летописец"
    owned = await mount_service.owned_mounts(db_session, character.id)
    assert any(m.mount_id == "ashen_steed" for m in owned)

    granted_again = await song_service.read_song(db_session, character)
    assert granted_again is False  # идемпотентно — повторное прочтение недоступно


async def test_fragments_display_hides_unseen_text(db_session, make_character) -> None:
    character = await make_character(level=10)
    await song_service.record_seen(db_session, character, 0)

    display = await song_service.fragments_display(db_session, character.id)
    assert len(display) == 10
    assert display[0].seen is True and display[0].text is not None
    assert display[1].seen is False and display[1].text is None
