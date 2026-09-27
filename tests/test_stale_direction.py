"""Устаревшая стрелка карты получает ответ, а не тишину.

Живой прогон на pupsik: с клетки (0;29) (тогда - (50;49)) нажатие «⬆️» (вверх там уже
подпись города) уходило в пустоту - обработчик молча выходил. Для игрока со
старой клавиатурой это неотличимо от мёртвого бота.
"""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.handlers import world
from models import Base, Character, CharacterStats, User, Wallet


class _Message:
    peer_id = from_id = 4242
    text = "⬆️"

    def __init__(self) -> None:
        self.answers: list[tuple[str, str | None]] = []

    async def answer(self, text, keyboard=None, **kwargs):
        self.answers.append((text, keyboard))


@pytest.fixture
async def factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    made = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(world, "get_session_factory", lambda: made)
    async with made() as db:
        user = User(vk_id=4242)
        db.add(user)
        await db.flush()
        character = Character(user_id=user.id, name="Путник", base_class="warrior", level=10,
                              region="ridge", pos_x=0, pos_y=29,
                              last_active_at=datetime.now(timezone.utc))
        db.add(character)
        await db.flush()
        db.add(CharacterStats(character_id=character.id))
        db.add(Wallet(character_id=character.id, farm_currency=0, donate_currency=0))
        await db.commit()
    yield made
    await engine.dispose()


async def test_stale_arrow_next_to_a_city_is_answered(factory) -> None:
    message = _Message()
    await world.move(message)

    assert message.answers, "устаревшая стрелка ушла в пустоту"
    text, keyboard = message.answers[0]
    assert "так не пройти" in text
    labels = [b["action"]["label"] for row in json.loads(keyboard)["buttons"] for b in row]
    assert any("Обетованный Кряж" in label for label in labels), "нужны кнопки этой клетки, с подписью города"
