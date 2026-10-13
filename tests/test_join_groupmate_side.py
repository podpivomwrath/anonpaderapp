"""Вступление в идущий бой: согруппник уже дерётся - сразу на его сторону."""

from types import SimpleNamespace

from bot.handlers import pvp


def _battle(side_of):
    return SimpleNamespace(participants={cid: None for cid in side_of}, side_of=side_of)


async def test_groupmate_side(monkeypatch) -> None:
    me = SimpleNamespace(id=1)
    group = SimpleNamespace(members=[SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)])

    async def snapshot(db, cid):
        return group

    from services import group_service

    monkeypatch.setattr(group_service, "get_group_snapshot", snapshot)
    assert await pvp._groupmate_side(None, me, _battle({2: 1, 9: 0})) == 2
    assert await pvp._groupmate_side(None, me, _battle({2: 0, 9: 1})) == 1
    assert await pvp._groupmate_side(None, me, _battle({8: 0, 9: 1})) is None  # согруппников нет
    assert await pvp._groupmate_side(None, me, _battle({2: 0, 3: 1})) is None  # на обеих сторонах

    async def alone(db, cid):
        return None

    monkeypatch.setattr(group_service, "get_group_snapshot", alone)
    assert await pvp._groupmate_side(None, me, _battle({2: 1})) is None
