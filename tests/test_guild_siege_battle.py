"""Осадный бой в чате: сбор на клетке, запуск массового боя, итог.

Хендлеры открывают свою сессию БД через get_session_factory - здесь она
подменяется фабрикой на тестовом движке (in-memory SQLite держит одно
соединение, так что обе сессии видят одни и те же данные).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.handlers import guild as guild_handlers
from bot.handlers import guild_siege
from bot.handlers import pvp as pvp_handlers
from game.combat.duel_engine import DuelEngine
from game.combat.tick_engine import InMemoryActionStore, TickEngine
from game.economy import guild_config as gc
from models import GuildBuilding, GuildCell, GuildSiege, User
from services import guild_service


class _Messages:
    def __init__(self):
        self.sent = []

    async def send(self, peer_id, message, random_id=0, keyboard=None, **kwargs):
        self.sent.append((peer_id, message))


class _Api:
    def __init__(self):
        self.messages = _Messages()


@pytest.fixture
def wired(db_session, monkeypatch):
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    for module in (pvp_handlers, guild_siege, guild_handlers):
        monkeypatch.setattr(module, "get_session_factory", lambda: factory)
    api = _Api()
    pvp_handlers._battles.clear()
    pvp_handlers._peer_battle.clear()
    pvp_handlers.setup(DuelEngine(), TickEngine(InMemoryActionStore()), api)
    guild_handlers.setup(api)

    async def _no_block(db, character, peer):
        return None

    monkeypatch.setattr(guild_siege, "blocked_reason", _no_block)
    yield api
    pvp_handlers._battles.clear()
    pvp_handlers._peer_battle.clear()


async def _setup(db, make_character, defenders=True, barracks=0):
    a_leader = await make_character(level=30, donate=gc.FOUND_COST_GEMS)
    d_leader = await make_character(level=30, donate=gc.FOUND_COST_GEMS)
    attacker = await guild_service.create(db, a_leader, "Набег", "НБ")
    defender = await guild_service.create(db, d_leader, "Стена", "СТ")
    cell = GuildCell(guild_id=defender.id, x=5, y=12, status="held", base_tier=gc.BASE_OUTPOST)
    db.add(cell)
    await db.flush()
    if barracks:
        db.add(GuildBuilding(cell_id=cell.id, building=gc.B_BARRACKS, level=barracks))
    a_leader.pos_x, a_leader.pos_y = 5, 12
    d_leader.pos_x, d_leader.pos_y = (5, 12) if defenders else (0, 30)
    for character in (a_leader, d_leader):
        user = await db.get(User, character.user_id)
        user.vk_id = 5000 + character.id
    now = datetime.now(timezone.utc)
    siege = GuildSiege(
        attacker_guild_id=attacker.id, defender_guild_id=defender.id, cell_id=cell.id, x=5, y=12,
        declared_at=now - timedelta(hours=13), starts_at=now, status="scheduled",
    )
    db.add(siege)
    await db.commit()
    return siege, cell, attacker, defender, a_leader, d_leader


async def test_siege_without_defenders_is_captured(db_session, make_character, wired) -> None:
    siege, cell, attacker, _d, _a, _dl = await _setup(db_session, make_character, defenders=False)
    await guild_siege.start(siege.id)
    await db_session.refresh(cell)
    await db_session.refresh(siege)
    assert siege.status == "captured" and cell.guild_id == attacker.id


async def test_siege_battle_starts_and_finishes(db_session, make_character, wired) -> None:
    siege, cell, attacker, defender, a_leader, d_leader = await _setup(db_session, make_character, barracks=3)
    await guild_siege.start(siege.id)
    battle_id = pvp_handlers.battle_at((5, 12))
    assert battle_id is not None
    battle = pvp_handlers._battles[battle_id]
    session = pvp_handlers._mass_engine.sessions[battle_id]
    assert battle.side_guilds == (attacker.id, defender.id)
    guards = [c for c in session.combatants.values() if c.kind == "mob"]
    assert len(guards) == gc.garrison_size(3) and all(g.side == 1 for g in guards)
    assert {p.character_id for p in battle.participants.values()} == {a_leader.id, d_leader.id}
    assert any("Осада" in text for _peer, text in wired.messages.sent)
    # Итог: нападавшие победили.
    for c in session.combatants.values():
        if c.side == 1:
            c.current_hp = 0
    battle.last_combatants = dict(session.combatants)
    pvp_handlers._mass_engine.abort_session(battle_id)
    result = SimpleNamespace(draw=False, winner_side=0)
    await pvp_handlers.on_mass_battle_finished(battle_id, result)
    await db_session.refresh(cell)
    await db_session.refresh(siege)
    assert siege.status == "captured" and cell.guild_id == attacker.id
    assert d_leader.id not in pvp_handlers._peer_battle
