"""Кнопка обычного боя без самого боя (патч 97).

После деплоя посреди боя реестр боёв пуст, а клавиатура у игрока осталась.
Раньше обработчики молча выходили, и «Атака» уходила в пустоту - снаружи это
неотличимо от мёртвого бота. PvP и рейд отвечают на такое давно, обычный бой -
нет.
"""

import pytest

from bot.handlers import combat


class _Message:
    def __init__(self, peer_id: int = 555) -> None:
        self.peer_id = peer_id
        self.from_id = peer_id
        self.text = ""

    def get_payload_json(self):
        return {"type": "skill", "id": "anything"}


@pytest.fixture
def wired(monkeypatch):
    answered: list[int] = []

    async def gone(message):
        answered.append(message.peer_id)

    class _Engine:
        sessions: dict = {}

    monkeypatch.setattr(combat, "_engine", _Engine())
    monkeypatch.setattr(combat, "answer_battle_gone", gone)
    return answered, monkeypatch


BUTTONS = ("attack", "use_skill", "use_item", "use_combat_item", "flee")


@pytest.mark.parametrize("handler", BUTTONS)
async def test_button_of_a_vanished_battle_is_answered(wired, handler) -> None:
    answered, monkeypatch = wired
    monkeypatch.setattr(combat, "in_any_battle", lambda peer_id: False)

    await getattr(combat, handler)(_Message())

    assert answered == [555], f"{handler}: игрок нажал кнопку боя и не получил ответа"


@pytest.mark.parametrize("handler", BUTTONS)
async def test_another_battle_is_not_hijacked(wired, handler) -> None:
    """Текст кнопок совпадает с групповыми боями - чужой бой перехватывать
    нельзя, там ответит свой обработчик."""
    answered, monkeypatch = wired
    monkeypatch.setattr(combat, "in_any_battle", lambda peer_id: True)

    await getattr(combat, handler)(_Message())

    assert answered == []
