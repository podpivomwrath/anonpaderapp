"""Общие фикстуры: in-memory SQLite для сервисов, детерминированный RNG,
фабрики участников боя."""

import random
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from game.combat.session import CombatantState, Stats, build_combatant
from models import Base, Character, CharacterStats, User, Wallet


@pytest.fixture(autouse=True)
def _terms_accepted(request, monkeypatch):
    """Пользовательское соглашение (2026-10-15) в тестах считается принятым -
    иначе мини-апп отвечал бы terms_required на всё. Сам гейт проверяют тесты
    с маркером real_terms (tests/test_terms.py)."""
    if request.node.get_closest_marker("real_terms"):
        return
    from services import terms_service

    monkeypatch.setattr(terms_service, "accepted", lambda user: True)


@pytest.fixture(autouse=True)
def _fresh_map_snapshot():
    """Общий снимок карты (bot/miniapp_map_api._shared) живёт 5 секунд - между
    тестами с разными базами он переносил бы чужих боссов и разломы."""
    from bot import miniapp_map_api

    miniapp_map_api._shared.clear()


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def make_character(db_session):
    """Фабрика: персонаж + статы + кошелёк в тестовой БД."""

    counter = {"n": 0}

    async def _make(
        level: int = 1,
        farm: int = 0,
        donate: int = 0,
        subclass: str | None = None,
        experience: int = 0,
        region: str | None = None,
        base_class: str = "warrior",
    ) -> Character:
        counter["n"] += 1
        n = counter["n"]
        user = User(vk_id=1000 + n)
        db_session.add(user)
        await db_session.flush()
        character = Character(
            user_id=user.id,
            name=f"Тестовый#{n}",
            base_class=base_class,
            subclass=subclass,
            level=level,
            experience=experience,
            region=region,
            # Патч 33, ч.3: last_active_at питает pvp_service.is_afk — тестовый
            # персонаж по умолчанию "только что действовал", иначе он AFK и
            # незаметен для PvP-тестов, которые этого не ожидают. Тесты самого
            # AFK-поведения выставляют это поле явно (см. test_pvp.py).
            last_active_at=datetime.now(timezone.utc),
        )
        db_session.add(character)
        await db_session.flush()
        db_session.add(CharacterStats(character_id=character.id))
        db_session.add(
            Wallet(character_id=character.id, farm_currency=farm, donate_currency=donate)
        )
        await db_session.flush()
        return character

    return _make


@pytest.fixture
def character_at(make_character):
    """Фабрика персонажа с заданной позицией (для dist-зависимого дропа трофеев)."""

    async def _make(pos_x: int, pos_y: int, **kwargs):
        character = await make_character(**kwargs)
        character.pos_x = pos_x
        character.pos_y = pos_y
        return character

    return _make


class NoCritRng(random.Random):
    """Детерминированный RNG: никаких критов/заморозок, choice — первый."""

    def random(self) -> float:
        return 0.999

    def choice(self, seq):
        return seq[0]

    def shuffle(self, seq) -> None:
        pass  # порядок сохраняется


@pytest.fixture
def no_crit_rng() -> NoCritRng:
    return NoCritRng()


@pytest.fixture
async def seed_quests(db_session):
    """Квесты из content/quests.json — тот же источник, что и миграция 0004."""
    from game.content_loader import load_quest_defs
    from models import Quest

    for quest_def in load_quest_defs():
        db_session.add(Quest(**quest_def.model_dump()))
    await db_session.flush()


def combatant(
    id: int,
    side: int,
    kind: str = "character",
    name: str | None = None,
    level: int = 10,
    subclass_id: str | None = None,
    **stat_overrides: int,
) -> CombatantState:
    stats = Stats()
    for key, value in stat_overrides.items():
        setattr(stats, key, value)
    return build_combatant(
        id=id,
        side=side,
        kind=kind,
        name=name or f"Боец{id}",
        level=level,
        stats=stats,
        primary_stat="str",
        subclass_id=subclass_id,
    )


@pytest.fixture(autouse=True)
def _any_skill_allowed(request, monkeypatch):
    """Руны-навыки (2026-11-10): в игре персонаж применяет только навыки
    вставленных рун (resolver._own_skill_or_attack). Тесты механик навыков
    не раскладывают руны - им разрешён любой навык. Тест самой проверки
    помечается @pytest.mark.real_abilities."""
    if request.node.get_closest_marker("real_abilities"):
        return
    from game.combat import skill_catalog

    monkeypatch.setattr(skill_catalog, "has_skill", lambda mods, skill_id: bool(skill_id))


def kb_fighter(*skill_ids: str, cooldowns: dict | None = None):
    """Боец для тестов клавиатур боя (руны-навыки, 2026-11-10): навыки -
    вставленные руны. По умолчанию - три стартовые руны воина."""
    from types import SimpleNamespace

    from game.combat import skill_catalog

    ids = skill_ids or skill_catalog.STARTER_SKILLS["warrior"]
    return SimpleNamespace(cooldowns=dict(cooldowns or {}),
                           buff_modifiers={skill_catalog.ability_key(s): i + 1 for i, s in enumerate(ids)})
