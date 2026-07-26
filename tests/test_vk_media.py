"""Вложения-иллюстрации (хабы городов, события исследования, победа/смерть)."""

import pytest

from bot import vk_media
from bot.world_texts import EVENT_PHOTO_IDS, HUB_PHOTO_IDS, event_attachment, hub_attachment
from config import Settings


@pytest.fixture(autouse=True)
def _fixed_group_id(monkeypatch):
    monkeypatch.setattr(vk_media, "get_settings", lambda: Settings(_env_file=None, vk_group_id=240167847))


def test_photo_attachment_format() -> None:
    assert vk_media.photo_attachment("457239033") == "photo-240167847_457239033"


def test_hub_attachment_covers_all_regions() -> None:
    for region in ("ridge", "woods", "docks", "scorched"):
        assert hub_attachment(region) == f"photo-240167847_{HUB_PHOTO_IDS[region]}"


def test_hub_attachment_unknown_region_returns_none() -> None:
    assert hub_attachment("nowhere") is None


def test_event_attachment_covers_all_exploration_events() -> None:
    for event_id in ("dead_box", "monolith_shard", "wounded_wanderer", "ash_altar"):
        assert event_attachment(event_id) == f"photo-240167847_{EVENT_PHOTO_IDS[event_id]}"


def test_event_attachment_unknown_id_returns_none() -> None:
    assert event_attachment("nope") is None


def test_event_photo_ids_match_real_exploration_content() -> None:
    from game.content_loader import load_exploration_events

    real_ids = {e.id for e in load_exploration_events()}
    assert set(EVENT_PHOTO_IDS) == real_ids
