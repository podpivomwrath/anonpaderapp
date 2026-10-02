"""Предел этапа рейда: на RAID_STAGE_TURN_LIMIT-м ходу босс бьёт ультимативно -
вайп с описанием удара, а не бесконечный бой на зельях."""

import random
from types import SimpleNamespace

from bot.handlers import raid_combat
from game.economy import raid_config as rc


class FakeEngine:
    def __init__(self) -> None:
        self.sessions = {}
        self.aborted = []

    def abort_session(self, session_id) -> None:
        self.aborted.append(session_id)


def _result():
    return SimpleNamespace(finished=False, deaths=[], winner_side=None, control_attempts_on={},
                           hit_renders=[], heal_renders=[])


async def test_stage_ends_with_ultimate_at_turn_limit(monkeypatch) -> None:
    engine = FakeEngine()
    wiped = []

    async def fake_wipe(session_id, battle, text=None):
        wiped.append(text)

    async def fake_board(*args, **kwargs):
        return None

    monkeypatch.setattr(raid_combat, "_engine", engine)
    monkeypatch.setattr(raid_combat, "_finish_wipe", fake_wipe)
    monkeypatch.setattr(raid_combat, "_broadcast_board", fake_board)
    battle = raid_combat.RaidBattle(group_id=None, participants={}, member_inputs=[], rng=random.Random(1))
    monkeypatch.setitem(raid_combat._battles, 77, battle)

    for tick in range(1, rc.RAID_STAGE_TURN_LIMIT):
        await raid_combat.on_raid_tick_resolved(77, tick, _result())
    assert wiped == [] and engine.aborted == []
    await raid_combat.on_raid_tick_resolved(77, rc.RAID_STAGE_TURN_LIMIT, _result())
    assert engine.aborted == [77]
    assert wiped == [rc.RAID_ULTIMATE_TEXT[rc.RAID_PUPPET_THEATRE_ID]]
