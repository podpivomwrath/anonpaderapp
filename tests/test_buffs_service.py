"""Сводка действующих баффов для вкладки «Герой» и строки в чат (2026-10-23)."""

from datetime import datetime, timedelta, timezone

from bot import buff_notice
from services import buffs_service


async def test_timed_lists_food_bait_prayer_tincture(make_character) -> None:
    c = await make_character()
    now = datetime.now(timezone.utc)
    assert buffs_service.timed(c, now) == []
    c.food_dish, c.food_grade, c.food_until = "wormwood_soup", "common", now + timedelta(minutes=40)
    c.food_boost = 0.0
    c.bait_until = now + timedelta(minutes=30)
    c.prayer_stat, c.prayer_until = "str", now + timedelta(minutes=60)
    c.ash_tincture_until = now + timedelta(hours=2)
    got = {b["id"]: b for b in buffs_service.timed(c, now)}
    assert set(got) == {"food", "bait", "prayer", "tincture"}
    assert got["food"]["value"] == "+10% здоровье"
    assert got["prayer"]["value"] == "+10% сила"


async def test_expired_buffs_are_hidden(make_character) -> None:
    c = await make_character()
    now = datetime.now(timezone.utc)
    c.food_dish, c.food_grade, c.food_until = "wormwood_soup", "common", now - timedelta(minutes=1)
    c.bait_until = now - timedelta(minutes=1)
    assert buffs_service.timed(c, now) == []


async def test_chat_line(make_character) -> None:
    c = await make_character()
    c.bait_until = datetime.now(timezone.utc) + timedelta(minutes=30)
    text = buff_notice.line(c, "bait", "рассыпана")
    assert text.startswith("🪱 Прикормка - рассыпана: клёв на 30% быстрее, ещё")
    assert buff_notice.line(c, "food", "съедено") is None
