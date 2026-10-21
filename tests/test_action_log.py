"""Последние действия игрока в чате (2026-10-21): дошло ли до бота и прочитал ли он."""

from types import SimpleNamespace

from bot import action_log


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    async def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    async def ltrim(self, key, start, stop):
        self.lists[key] = self.lists.get(key, [])[start:stop + 1]

    async def expire(self, key, seconds):
        pass

    async def lrange(self, key, start, stop):
        return self.lists.get(key, [])[start:stop + 1]


def _msg(text, payload=None, peer=7):
    return SimpleNamespace(text=text, payload=payload, peer_id=peer, from_id=peer)


async def test_keeps_last_twenty_newest_first(monkeypatch) -> None:
    monkeypatch.setattr(action_log, "_redis", FakeRedis())
    for i in range(25):
        await action_log.record(_msg(f"т{i}"), accepted=True)
    await action_log.record(_msg("🐎 Маунт"), accepted=False)
    await action_log.record(_msg("🔍 Исследовать", payload='{"btn":1}'), accepted=True)
    rows = await action_log.recent(7)
    assert len(rows) == action_log.KEEP
    assert (rows[0]["kind"], rows[0]["accepted"]) == ("кнопка", True)
    assert (rows[1]["text"], rows[1]["kind"], rows[1]["accepted"]) == ("🐎 Маунт", "текст", False)


async def test_group_chats_and_no_redis_are_skipped(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(action_log, "_redis", fake)
    await action_log.record(SimpleNamespace(text="/клава", payload=None, peer_id=2000000001, from_id=5), True)
    assert fake.lists == {}
    monkeypatch.setattr(action_log, "_redis", None)
    await action_log.record(_msg("/клава"), True)
    assert await action_log.recent(7) == []
