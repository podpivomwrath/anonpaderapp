"""Opt-in integration tests on a dedicated local database (see scripts/test_local.py)."""
import asyncio
import os
from uuid import uuid4
from urllib.parse import urlparse

import pytest
from sqlalchemy import func, select, text
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


# --- Патч 94: продажи и расход под параллельными нажатиями -------------------
#
# Вебхук запускает каждое событие отдельной задачей, поэтому два быстрых
# нажатия «Продать» идут ОДНОВРЕМЕННО. На боевом Postgres до исправления:
# десять трофеев за 20 золота приносили 80-120, один предмет продавался
# десять раз из десяти, садок - тоже, а одну склянку выпивали дважды.
# SQLite гонку не воспроизводит (пишет по одному), поэтому проверка - здесь.

TAPS = 10


async def _race(pg_factory, op):
    ready = asyncio.Barrier(TAPS)

    async def one():
        async with pg_factory() as db:
            character = await db.get(Character, 1)
            await ready.wait()
            got = await op(db, character)
            await db.commit()
            return got

    return await asyncio.gather(*(one() for _ in range(TAPS)))


async def _gold(pg_factory) -> int:
    from models import Wallet
    async with pg_factory() as db:
        return await db.scalar(select(Wallet.farm_currency).where(Wallet.character_id == 1)) or 0


async def _with_wallet(pg_factory):
    from models import Wallet
    async with pg_factory() as db:
        if await db.scalar(select(Wallet).where(Wallet.character_id == 1)) is None:
            db.add(Wallet(character_id=1, farm_currency=0, donate_currency=0))
            await db.commit()


async def test_parallel_trophy_sales_pay_once(pg_factory):
    from models import CharacterTrophy
    from services import trophy_service
    await _with_wallet(pg_factory)
    async with pg_factory() as db:
        db.add(CharacterTrophy(character_id=1, trophy_id="ash_dust", count=10))
        await db.commit()
    price = next(d.sell_price for d in trophy_service.trophy_defs_ordered() if d.id == "ash_dust")

    paid = await _race(pg_factory, lambda db, c: trophy_service.sell_all(db, c))

    assert sum(1 for p in paid if p) == 1
    assert await _gold(pg_factory) == price * 10


async def test_parallel_item_sales_pay_once(pg_factory):
    import random
    from services import item_service
    await _with_wallet(pg_factory)

    class _Rng(random.Random):
        def random(self):
            return 0.0

    async with pg_factory() as db:
        c = await db.get(Character, 1)
        item = await item_service.grant_from_kill(db, c, 20, _Rng())
        price = item_service.sell_price(item)
        item_id = item.id
        await db.commit()

    paid = await _race(pg_factory, lambda db, c: item_service.sell_item(db, c, item_id))

    assert sum(1 for p in paid if p) == 1
    assert await _gold(pg_factory) == price


async def test_parallel_bag_sales_pay_once(pg_factory):
    from models import CharacterFish
    from services import fishing_service
    await _with_wallet(pg_factory)
    async with pg_factory() as db:
        db.add(CharacterFish(character_id=1, fish_id="ashen_roach", grade="common",
                             total_grams=5000))
        await db.commit()

    async def sell(db, c):
        gold, _grams = await fishing_service.sell_bag(db, c)
        return gold

    paid = await _race(pg_factory, sell)

    assert sum(1 for p in paid if p) == 1
    assert await _gold(pg_factory) == max(paid)


async def test_last_elixir_is_drunk_once(pg_factory):
    from services import elixir_service
    async with pg_factory() as db:
        await elixir_service.grant(db, 1, "heal_small", 1)
        await db.commit()

    drunk = await _race(pg_factory, lambda db, c: elixir_service.consume(db, c.id, "heal_small"))

    assert sum(1 for d in drunk if d) == 1


async def test_promo_limit_holds_under_parallel_taps(pg_factory):
    """До исправления код с лимитом 3 дал 10 активаций из 10."""
    from models import PromoActivation, PromoCode
    from services import promo_service
    await _with_wallet(pg_factory)
    async with pg_factory() as db:
        db.add(PromoCode(code="racelim", rewards=[{"type": "gold", "amount": 1}],
                         one_per_player=False, max_activations=3, created_by=1))
        await db.commit()

    async def tap(db, c):
        return (await promo_service.activate_code(db, c, "racelim")).status

    statuses = await _race(pg_factory, tap)

    assert statuses.count("success") == 3
    async with pg_factory() as db:
        assert await db.scalar(select(func.count()).select_from(PromoActivation)) == 3


async def test_promo_once_per_player_under_parallel_taps(pg_factory):
    from models import PromoCode
    from services import promo_service
    await _with_wallet(pg_factory)
    async with pg_factory() as db:
        db.add(PromoCode(code="raceone", rewards=[{"type": "gold", "amount": 1000}],
                         one_per_player=True, max_activations=None, created_by=1))
        await db.commit()

    async def tap(db, c):
        return (await promo_service.activate_code(db, c, "raceone")).status

    statuses = await _race(pg_factory, tap)

    assert statuses.count("success") == 1
    assert await _gold(pg_factory) == 1000
