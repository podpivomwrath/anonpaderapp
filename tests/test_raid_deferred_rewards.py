"""2026-10-18: награды этапов рейда и разлома - только в конце захода, при
победе. Раньше брали ключ, проходили лёгкий этап, получали опыт и погибали."""

import asyncio
import random
from types import SimpleNamespace

from bot.handlers import raid_combat


def _battle():
    return raid_combat.RaidBattle(
        group_id=None, member_inputs=[], rng=random.Random(1),
        participants={1: SimpleNamespace(peer_id=101), 2: SimpleNamespace(peer_id=102)},
    )


def test_stage_reward_is_only_remembered(monkeypatch):
    battle = _battle()
    granted = []

    async def fake_grant(b, reward):
        granted.append(reward)
        return {}

    monkeypatch.setattr(raid_combat, "_grant_stage_reward", fake_grant)
    notices = asyncio.run(raid_combat._stage_rewards(battle, [1, 2]))
    assert granted == [] and len(battle.pending_rewards) == 1
    assert notices == {1: raid_combat.PENDING_REWARD_LINE, 2: raid_combat.PENDING_REWARD_LINE}
    assert battle.pending_rewards[0].stage == 1 and battle.pending_rewards[0].alive_ids == [1, 2]


def test_victory_pays_every_stage_with_its_own_snapshot(monkeypatch):
    battle = _battle()
    sent = []

    async def fake_grant(b, reward):
        return {cid: f"этап {reward.stage}" for cid in reward.alive_ids}

    class Api:
        class messages:
            @staticmethod
            async def send(peer_id, message, random_id=0, **kw):
                sent.append((peer_id, message))

    monkeypatch.setattr(raid_combat, "_grant_stage_reward", fake_grant)
    monkeypatch.setattr(raid_combat, "_bot_api", Api)
    asyncio.run(raid_combat._stage_rewards(battle, [1, 2]))
    battle.stage = 2
    asyncio.run(raid_combat._stage_rewards(battle, [1]))  # второй пал на этапе 2
    asyncio.run(raid_combat._grant_pending_rewards(battle))
    texts = dict(sent)
    assert "этап 1" in texts[101] and "этап 2" in texts[101]
    assert "этап 1" in texts[102] and "этап 2" not in texts[102]
    assert battle.pending_rewards == []
