"""Гильдейская ежедневка, закрытая событием, должна дойти до игрока строкой
(2026-11-07: Котёнок получил 135 золота за задание гильдии без сообщения)."""

from types import SimpleNamespace

import pytest

from bot.handlers import scene_events
from services import scene_event_service


def test_applied_keeps_streak_notice() -> None:
    applied = scene_event_service.Applied()
    applied.add_progress(SimpleNamespace(completed=[], streak_notice="🏰 Гильдейская ежедневка выполнена"))
    applied.add_progress(SimpleNamespace(completed=[], streak_notice=None))
    assert applied.daily_notices == ["🏰 Гильдейская ежедневка выполнена"]


def test_two_notices_in_one_fight_both_kept() -> None:
    from services import encounter_service

    assert encounter_service._join_notice("трофеи", "победа") == "трофеи\nпобеда"
    assert encounter_service._join_notice(None, None) is None


def test_ruins_exit_asks_first() -> None:
    """Выход из руин - только второй кнопкой с номером этажа (2026-11-07)."""
    import inspect

    from bot.handlers import ruins

    src = inspect.getsource(ruins.up)
    assert src.index('payload.get("sure") != run.floor') < src.index("exit_run")


@pytest.mark.asyncio
async def test_notify_sends_guild_line(monkeypatch) -> None:
    sent: list[str] = []

    async def fake_send(peer_id, text, *args, **kwargs):
        sent.append(text)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(scene_events, "_send", fake_send)
    monkeypatch.setattr(scene_events.stats_window, "notify_levelup", noop)
    monkeypatch.setattr(scene_events.group_texts, "notify_group_kick", noop)
    applied = scene_event_service.Applied(new_level=60)
    applied.add_progress(SimpleNamespace(completed=[], streak_notice="🏰 Гильдейская ежедневка выполнена"))
    await scene_events._notify(1, applied)
    assert any("Гильдейская ежедневка" in text for text in sent)
