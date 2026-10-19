"""2026-10-19, жалоба: после смерти не было строки о потерянном опыте -
её стирала первая же правка отсчёта до возрождения."""

import asyncio
from datetime import datetime, timedelta, timezone

from bot.handlers import respawn


class _Messages:
    def __init__(self):
        self.edits = []

    async def send(self, peer_id, message, random_id=0, **kw):
        return 555

    async def edit(self, peer_id, message_id, message, **kw):
        self.edits.append(message)


def test_countdown_edit_keeps_xp_penalty(monkeypatch):
    api = type("Api", (), {})()
    api.messages = _Messages()
    monkeypatch.setattr(respawn, "_bot_api", api)
    respawn_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    asyncio.run(respawn.register_death(777, respawn_at, xp_lost=1234))
    assert respawn._death_xp[777] == 1234
    text = respawn._death_text(respawn_at, datetime.now(timezone.utc), respawn._death_xp.get(777, 0))
    assert "1234" in text.replace(" ", "").replace(" ", "")
    respawn._death_message.pop(777, None)
    respawn._death_xp.pop(777, None)
