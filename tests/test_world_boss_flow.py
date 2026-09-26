"""Заход к мировому боссу целиком: кнопка -> ходы на настоящем движке -> итог.

Отдельно от tests/test_world_boss.py: здесь проверяется связка обработчиков
(bot/handlers/world_boss.py + combat.py), которую сервисные тесты не видят -
что урон каждого хода доходит до БД, что заход кончается ровно на лимите и
что убийство раздаёт пул и закрывает бой.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers import combat
from bot.handlers import world_boss as handler
from game.combat.session import ActionType, DeclaredAction
from game.combat.tick_engine import InMemoryActionStore, TickEngine
from game.economy import world_boss_config as wbc
from game.world import world_boss
from models import (
    Base,
    Character,
    CharacterStats,
    User,
    Wallet,
    WorldBoss,
    WorldBossContribution,
)

PEER = 777


class _Message:
    def __init__(self) -> None:
        self.peer_id = PEER
        self.from_id = PEER
        self.text = ""
        self.answers: list[str] = []

    def get_payload_json(self):
        return {"type": "world_boss_attack"}

    async def answer(self, text, **kwargs):
        self.answers.append(text)


@pytest.fixture
async def wired(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sent: list[str] = []

    class _Messages:
        async def send(self, **kwargs):
            sent.append(kwargs.get("message", ""))

    class _Api:
        messages = _Messages()

    tick_engine = TickEngine(
        InMemoryActionStore(),
        on_tick_resolved=combat.on_tick_resolved,
        on_battle_finished=combat.on_battle_finished,
    )
    for module in (handler, combat):
        monkeypatch.setattr(module, "get_session_factory", lambda: factory)
        monkeypatch.setattr(module, "_bot_api", _Api())
    from bot.handlers import world as world_handlers

    monkeypatch.setattr(world_handlers, "get_session_factory", lambda: factory)
    monkeypatch.setattr(combat, "_engine", tick_engine)
    yield factory, sent
    await engine.dispose()


async def _setup(factory, hp: int, level: int = 60) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    async with factory() as db:
        x, y = world_boss.pick_cell(4, __import__("random").Random(4))
        boss = WorldBoss(
            boss_id="stitched_giant", ring=4, level=60, x=x, y=y, max_hp=wbc.BOSS_HP[4], hp=hp,
            status="active", spawned_at=now, expires_at=now + timedelta(hours=3),
        )
        user = User(vk_id=PEER)
        db.add_all([boss, user])
        await db.flush()
        character = Character(
            user_id=user.id, name="Боец", base_class="warrior", level=level, region="ridge",
            pos_x=x, pos_y=y, last_active_at=now,
        )
        db.add(character)
        await db.flush()
        db.add(CharacterStats(character_id=character.id, strength=200, vitality=60))
        db.add(Wallet(character_id=character.id, farm_currency=0, donate_currency=0))
        await db.commit()
        return boss.id, character.id


async def _hit() -> None:
    await combat._engine.declare_action(
        PEER, combat.PLAYER_ID, DeclaredAction(type=ActionType.ATTACK, target_id=combat.MOB_ID)
    )


async def test_attempt_lasts_exactly_the_turn_limit(wired) -> None:
    factory, sent = wired
    boss_pk, character_id = await _setup(factory, hp=wbc.BOSS_HP[4])

    await handler.attack(_Message())
    assert combat.world_boss_of(PEER) == boss_pk

    for _ in range(wbc.ATTEMPT_TURNS - 1):
        await _hit()
    assert combat.world_boss_of(PEER) == boss_pk, "заход кончился раньше лимита"
    await _hit()

    assert combat.world_boss_of(PEER) is None
    assert PEER not in combat._engine.sessions
    assert any("Заход окончен" in text for text in sent)
    async with factory() as db:
        boss = await db.get(WorldBoss, boss_pk)
        row = await db.scalar(select(WorldBossContribution))
    assert row.character_id == character_id and row.damage > 0
    assert boss.hp == boss.max_hp - row.damage, "урон захода не дошёл до общего здоровья"
    assert boss.status == "active"


async def test_second_attempt_within_the_hour_is_refused(wired) -> None:
    factory, _sent = wired
    await _setup(factory, hp=wbc.BOSS_HP[4])
    await handler.attack(_Message())
    await handler.leave(PEER)

    again = _Message()
    await handler.attack(again)

    assert combat.world_boss_of(PEER) is None
    assert again.answers and "Следующий заход" in again.answers[0]


async def test_killing_blow_ends_the_boss_and_pays_out(wired) -> None:
    factory, sent = wired
    boss_pk, _ = await _setup(factory, hp=50)

    await handler.attack(_Message())
    # Удар может промахнуться - бьём, пока заход не кончится.
    while combat.world_boss_of(PEER) is not None:
        await _hit()

    assert combat.world_boss_of(PEER) is None
    async with factory() as db:
        boss = await db.get(WorldBoss, boss_pk)
    assert boss.status == "killed" and boss.hp == 0
    assert any("пал" in text for text in sent), sent
    assert any("Опыт +" in text for text in sent)
    # итог босса раньше сводки локации: сводка несёт клавиатуру карты и
    # должна быть последним сообщением
    fell = next(i for i, text in enumerate(sent) if "пал" in text)
    over = next(i for i, text in enumerate(sent) if "Заход окончен" in text)
    assert fell < over


def test_missed_skill_is_named_in_the_log() -> None:
    """На заходе к боссу игрок нажал навык, а промах в логе назвался «атакой»."""
    from game.combat.battle_log import _hit_line
    from game.combat.resolver import RenderedHit

    hit = RenderedHit(
        source_id=1, target_id=2, source_side=0, target_side=1, label="Кровавый пакт",
        amount=0, crit=False, missed=True, is_dot=False, hp_before=10, hp_after=10, max_hp=10,
    )
    assert "Кровавый пакт по Босс - промах" in _hit_line(hit, "Игрок", "Босс", "pve")
