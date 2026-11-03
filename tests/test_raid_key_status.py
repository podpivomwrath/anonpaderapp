"""/ключ (2026-11-03): сколько ключей из скольких можно накопить."""

from bot import raid_key_texts


def test_status_shows_count_of_cap_and_premium_hint() -> None:
    text = raid_key_texts.raid_key_status(1, 2, 4)
    assert "1 из 2" in text and "падает" in text and "до 4" in text


def test_status_at_cap_says_no_more_drops_and_no_hint_with_mark() -> None:
    text = raid_key_texts.raid_key_status(4, 4, None)
    assert "4 из 4" in text and "не выпадет" in text and "Метк" not in text
