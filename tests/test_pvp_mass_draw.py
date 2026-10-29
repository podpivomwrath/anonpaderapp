"""2026-10-18, баг-репорт: при ничьей в массовом PvP павшие погибали, но им
приходило «Ничья. Списки остались нетронутыми»."""

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.handlers import pvp as pvp_handlers
from game.combat.tick_engine import InMemoryActionStore, TickEngine


class _Messages:
    def __init__(self):
        self.sent = []

    async def send(self, peer_id, message, random_id=0, keyboard=None, **kwargs):
        self.sent.append((peer_id, message))


@pytest.fixture
def api(db_session, monkeypatch):
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    monkeypatch.setattr(pvp_handlers, "get_session_factory", lambda: factory)
    api = SimpleNamespace(messages=_Messages())
    pvp_handlers.setup(TickEngine(InMemoryActionStore()), api)
    yield api
    pvp_handlers._battles.clear()
    pvp_handlers._peer_battle.clear()


async def test_fallen_in_a_mass_draw_are_told_they_died(db_session, make_character, api) -> None:
    alive_a = await make_character(level=30)
    alive_b = await make_character(level=30)
    fallen = await make_character(level=30)
    for c in (alive_a, alive_b, fallen):
        c.pos_x, c.pos_y = 3, 3
    await db_session.commit()
    battle = pvp_handlers.Battle(battle_type="mass", location=(3, 3))
    for side, c in ((0, alive_a), (1, alive_b), (1, fallen)):
        battle.participants[c.id] = pvp_handlers._participant(c, 9000 + c.id)
        battle.side_of[c.id] = side
    battle.last_combatants = {
        alive_a.id: SimpleNamespace(alive=True), alive_b.id: SimpleNamespace(alive=True),
        fallen.id: SimpleNamespace(alive=False),
    }
    pvp_handlers._battles[-901] = battle
    await pvp_handlers.on_mass_battle_finished(-901, SimpleNamespace(draw=True, draw_reason="turn_limit"))
    texts = dict(api.messages.sent)
    assert "Тебя одолели" in texts[9000 + fallen.id]
    assert "Расходитесь, пока целы" not in texts[9000 + fallen.id]
    assert "павшие" in texts[9000 + alive_a.id]
