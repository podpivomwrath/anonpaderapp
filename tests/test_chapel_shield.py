"""После возрождения у часовни гильдии - щит от PvP 2 минуты (2026-10-21)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bot.handlers import respawn
from services import pvp_shield


async def test_chapel_respawn_gives_shield_bound_to_the_cell(monkeypatch, db_session, make_character) -> None:
    c = await make_character(level=30, region="ridge")
    c.guild_id, c.respawn_at_chapel = 1, True
    c.respawn_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.flush()

    class Context:
        async def __aenter__(self): return db_session
        async def __aexit__(self, *args): pass

    async def chapel_cell(db, guild_id): return SimpleNamespace(x=7, y=8)
    async def field_keyboard(peer): return None
    sent = []

    class Api:
        class messages:
            @staticmethod
            async def send(**kw): sent.append(kw)

    monkeypatch.setattr(respawn, "get_session_factory", lambda: Context)
    monkeypatch.setattr(respawn.guild_territory_service, "chapel_cell", chapel_cell)
    monkeypatch.setattr(respawn, "_field_keyboard", field_keyboard)
    monkeypatch.setattr(respawn, "_bot_api", Api)
    pvp_shield.drop(c.id)

    await respawn.scan()

    assert (c.pos_x, c.pos_y) == (7, 8)
    left, why = pvp_shield.left(c.id)
    assert 110 < left <= 121 and why == pvp_shield.CHAPEL
    assert "не нападут" in sent[0]["message"]
    c.pos_x = 9
    pvp_shield.on_moved(c)  # ушел с клетки часовни - щит пропал
    assert pvp_shield.left(c.id) == (0, "")
