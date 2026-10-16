"""Справочные команды посреди событий (2026-10-16): /разломы и прочие не
считаются ответом на загадку или ставкой и проходят сквозь долгий путь."""

import asyncio
from types import SimpleNamespace

from bot.dispatch_rules import is_info_command, is_slash_command
from bot.handlers import scene_events, voyage
from game.world.scene_events import Riddle


def _msg(text, peer_id=777, payload=None):
    return SimpleNamespace(peer_id=peer_id, text=text, payload=payload)


def test_info_command_detection():
    assert is_info_command(_msg("/разломы"))
    assert is_info_command(_msg("/Разлом"))
    assert is_info_command(_msg("/daily"))
    assert not is_info_command(_msg("/разломы", payload='{"a":1}'))
    assert not is_info_command(_msg("полотенце"))
    assert is_slash_command(_msg(" /что-угодно"))
    assert not is_slash_command(_msg("полотенце"))


def test_riddle_ignores_commands():
    p = scene_events.Pending(event_id="e", scene_id="s", token=1, riddle=Riddle(q="?", a=["полотенце"]))
    scene_events._pending[777] = p
    try:
        rule = scene_events.RiddleAnswer()
        assert asyncio.run(rule.check(_msg("полотенце")))
        assert not asyncio.run(rule.check(_msg("/разломы")))
    finally:
        scene_events._pending.pop(777, None)


def test_voyage_lets_info_commands_through():
    voyage._away.add(777)
    try:
        assert not asyncio.run(voyage.AWAY_BLOCK.check(_msg("/разломы")))
        assert asyncio.run(voyage.AWAY_BLOCK.check(_msg("Осмотреться")))
    finally:
        voyage._away.discard(777)
