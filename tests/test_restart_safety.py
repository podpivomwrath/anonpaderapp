"""Соло-бой переживает перезапуск бота (2026-10-12): при остановке уходит в
Redis целиком, при запуске возвращается движку тем же ходом, игрок получает
доску боя с кнопками. Групповые бои считаются для выкатки (она их ждёт)."""

import random

import pytest

from bot import restart_safety
from bot.handlers import combat
from game.combat import balance_config as bc
from game.combat.battle_report import BattleTracker
from game.combat.session import CombatMode, CombatSessionState, Stats, build_combatant
from game.combat.tick_engine import InMemoryActionStore, TickEngine
from game.world import encounters


class FakeRedis:
    def __init__(self):
        self.data = {}

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)

    async def scan_iter(self, match):
        prefix = match.rstrip("*")
        for key in list(self.data):
            if key.startswith(prefix):
                yield key


class FakeApi:
    def __init__(self):
        self.sent = []

        class Messages:
            async def send(inner, **kw):
                self.sent.append(kw)

        self.messages = Messages()


def _solo_fight(peer_id: int) -> CombatSessionState:
    player = build_combatant(
        id=combat.PLAYER_ID, side=0, kind="character", name="Герой", level=10,
        stats=Stats(strength=50, agility=20, intellect=10, vitality=40, will=20),
        primary_stat="str", base_class="warrior",
    )
    mob = encounters.spawn_mob(combat.MOB_ID, "ridge", 10, 27, random.Random(1)).combatant
    state = CombatSessionState(session_id=peer_id, mode=CombatMode.PVE)
    state.add(player)
    state.add(mob)
    return state


@pytest.fixture
def engine(monkeypatch):
    eng = TickEngine(store=InMemoryActionStore())
    api = FakeApi()
    monkeypatch.setattr(combat, "_engine", eng)
    monkeypatch.setattr(combat, "_bot_api", api)
    for name in combat._SNAPSHOT_MAPS:
        monkeypatch.setattr(combat, name, {})
    monkeypatch.setattr(combat, "_world_boss", {})
    return eng, api


async def test_solo_battle_survives_restart(engine) -> None:
    eng, api = engine
    state = _solo_fight(777)
    eng.start_session(state)
    state.combatants[combat.MOB_ID].current_hp -= 50
    combat._encounter_class[777] = "warrior"
    combat._encounter_mob_level[777] = 10
    combat._battle_trackers[777] = BattleTracker(combat.PLAYER_ID, combat.MOB_ID, 10, 500, 500)
    tick = state.tick_number
    mob_hp = state.combatants[combat.MOB_ID].current_hp

    redis = FakeRedis()
    assert await restart_safety.save_solo_battles(redis) == 1

    # Перезапуск: память процесса пуста
    eng.sessions.clear()
    for name in combat._SNAPSHOT_MAPS:
        getattr(combat, name).clear()

    assert await restart_safety.restore_solo_battles(redis) == 1
    restored = eng.sessions[777]
    assert restored.tick_number == tick
    assert restored.combatants[combat.MOB_ID].current_hp == mob_hp
    assert combat._encounter_class[777] == "warrior"
    assert combat.has_active_encounter(777)
    assert api.sent and "бой продолжается" in api.sent[0]["message"]
    assert redis.data == {}  # сохранённое использовано один раз


async def test_world_boss_run_is_not_saved(engine, monkeypatch) -> None:
    eng, _api = engine
    eng.start_session(_solo_fight(888))
    monkeypatch.setattr(combat, "_world_boss", {888: 1})
    assert await restart_safety.save_solo_battles(FakeRedis()) == 0


def test_busy_counter_counts_group_battles(monkeypatch) -> None:
    from bot.handlers import group_combat, group_events, pvp, raid_combat

    monkeypatch.setattr(group_combat, "_battles", {1: object()})
    monkeypatch.setattr(raid_combat, "_battles", {})
    monkeypatch.setattr(pvp, "_battles", {2: object(), 3: object()})
    monkeypatch.setattr(group_events, "_scenes", {})
    assert restart_safety.busy_battles() == 3
    assert bc.MAX_LEVEL  # модуль баланса доступен - импорты на месте


async def test_stuck_does_not_abort_solo_battle(engine, db_session, make_character, monkeypatch) -> None:
    """2026-10-13: /застрял в соло-бою не выводит из боя (лазейка - бросить
    проигрышный бой без штрафа), а только обновляет его. Админский сброс
    (admin_override) прерывает по-прежнему - он не менялся."""
    from bot import pending_activity
    from bot.handlers import world

    async def no_redis(*args, **kwargs):
        return None

    monkeypatch.setattr(pending_activity, "forget", no_redis)
    eng, _api = engine
    eng.start_session(_solo_fight(991))
    character = await make_character()

    assert await world.force_unstick(db_session, character, 991) is True
    assert combat.has_active_encounter(991)
    assert "БОЙ" in combat.board_text(991)
