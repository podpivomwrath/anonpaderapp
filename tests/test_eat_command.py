"""/съесть (2026-10-21): еда без мини-аппа."""


from bot.handlers import house as house_handlers
from services import cooking_service


class _Msg:
    def __init__(self, from_id: int):
        self.from_id = from_id
        self.peer_id = from_id
        self.sent: list[str] = []

    async def answer(self, text, **_kw):
        self.sent.append(text)


async def test_find_food_by_name_ignores_case_and_yo(db_session, make_character) -> None:
    c = await make_character()
    await cooking_service.add_food(db_session, c.id, "baked_gudgeon", "common", 1)
    await cooking_service.add_food(db_session, c.id, "baked_gudgeon", "trophy", 1)
    found = await cooking_service.find_food(db_session, c.id, "ПЕЧЁНЫЙ пескарь")
    assert [g for _, _, g, _ in found] == ["trophy", "common"]  # лучшая градация первой
    assert await cooking_service.find_food(db_session, c.id, "пескарь")
    assert await cooking_service.find_food(db_session, c.id, "уха") == []


async def test_eat_command_lists_and_eats_best(db_session, make_character, monkeypatch) -> None:
    c = await make_character()
    await cooking_service.add_food(db_session, c.id, "wormwood_soup", "big", 1)
    await cooking_service.add_food(db_session, c.id, "wormwood_soup", "legendary", 1)

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(house_handlers, "get_session_factory", lambda: _Factory())

    async def _char(_db, _vk):
        return c

    monkeypatch.setattr(house_handlers.onboarding_svc, "get_character", _char)
    monkeypatch.setattr("bot.battle_keyboard.in_any_battle", lambda _p: False)
    msg = _Msg(1)
    await house_handlers.eat_command(msg)
    assert "Уха с полынью" in msg.sent[-1] and "/съесть" in msg.sent[-1]
    await house_handlers.eat_command(msg, name="уха")
    assert "Съедено: Уха с полынью (рыба легендарная)" in msg.sent[-1]
    assert cooking_service.buff(c) == {"max_hp_bonus": 0.2}

    monkeypatch.setattr("bot.battle_keyboard.in_any_battle", lambda _p: True)
    await house_handlers.eat_command(msg, name="уха")
    assert "не до еды" in msg.sent[-1]
