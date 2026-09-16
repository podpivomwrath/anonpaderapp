"""Opt-in integration tests on a dedicated local database (see scripts/test_local.py)."""
import asyncio
import os
from uuid import uuid4
from urllib.parse import urlparse

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from models import Base, User, Character, CharacterStats, RaidRun
from services import stat_alloc_service as sas, raid_service as rs


@pytest.fixture
async def pg_factory():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated local pines_test PostgreSQL")
    parsed = urlparse(url)
    assert parsed.hostname in ("127.0.0.1", "localhost", "::1") and parsed.path == "/pines_test"
    schema = "audit_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            user = User(vk_id=12345)
            db.add(user)
            await db.flush()
            c = Character(user_id=user.id, name="Concurrency", base_class="warrior", level=60,
                          pos_x=0, pos_y=0, raid_keys=1)
            db.add(c)
            await db.flush()
            db.add(CharacterStats(character_id=c.id, unspent_points=3))
            await db.commit()
        yield factory
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_parallel_allocations_cannot_double_spend(pg_factory):
    ready = asyncio.Barrier(2)
    async def spend(stat):
        async with pg_factory() as db:
            stats = await db.get(CharacterStats, 1)
            await ready.wait()
            try:
                await sas.allocate(db, stats, {stat: 3})
                await db.commit()
                return True
            except sas.NotEnoughPoints:
                await db.rollback()
                return False
    assert sorted(await asyncio.gather(spend("str"), spend("agi"))) == [False, True]
    async with pg_factory() as db:
        stats = await db.get(CharacterStats, 1)
        assert stats.strength + stats.agility == 33
        assert stats.unspent_points == 0


async def test_chat_and_http_share_budget(pg_factory):
    ready = asyncio.Barrier(2)
    async def spend(chat):
        async with pg_factory() as db:
            stats = await db.get(CharacterStats, 1)
            await ready.wait()
            try:
                if chat:
                    await sas.finalize(db, stats, {"str": 3})
                else:
                    await sas.allocate(db, stats, {"agi": 3})
                await db.commit()
            except sas.NotEnoughPoints:
                await db.rollback()
    await asyncio.gather(spend(True), spend(False))
    async with pg_factory() as db:
        stats = await db.get(CharacterStats, 1)
        assert stats.strength + stats.agility == 33 and stats.unspent_points == 0


async def test_parallel_raid_starts_charge_one_key(pg_factory, monkeypatch):
    from bot.handlers import raid
    async with pg_factory() as db:
        c = await db.get(Character, 1)
        snap = await rs.touch_monolith(db, c, "puppet_theatre", None)
        await db.commit()
    started = []
    async def start(group, inputs, rng, *, run_id): started.append(run_id)
    async def allowed(*args): return None
    monkeypatch.setattr(raid, "get_session_factory", lambda: pg_factory)
    monkeypatch.setattr(raid, "blocked_reason", allowed)
    monkeypatch.setattr(raid.raid_combat_handlers, "start_raid", start)
    await asyncio.gather(raid._start_raid_from_lobby(snap.id), raid._start_raid_from_lobby(snap.id))
    assert len(started) == 1
    async with pg_factory() as db:
        assert (await db.get(Character, 1)).raid_keys == 0
        assert len(list(await db.scalars(select(RaidRun)))) == 1


async def test_parallel_recovery_refunds_once(pg_factory):
    async with pg_factory() as db:
        c = await db.get(Character, 1)
        snap = await rs.touch_monolith(db, c, "puppet_theatre", None)
        await rs.consume_key_and_start(db, c)
        await rs.record_run(db, snap)
        await db.commit()
    async def recover():
        async with pg_factory() as db:
            await rs.recover_interrupted(db)
            await db.commit()
    await asyncio.gather(recover(), recover())
    async with pg_factory() as db:
        assert (await db.get(Character, 1)).raid_keys == 1
