"""Одна проверка «чем занят игрок» (bot/busy.py, 2026-10-21) и как каждое
занятие заканчивается. Раньше у каждого входа была своя копия, и они
расходились: Морфей застрял в забое, карта пускала маунта из рейда."""

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot import busy as busy_mod
from bot import explore_rest
from bot.handlers import mounts as mounts_handlers
from bot.handlers import world as world_handlers
from bot.miniapp_map_api import _MAP_REASONS
from models import Character

ROOT = Path(__file__).resolve().parent.parent


def test_every_state_says_how_it_ends() -> None:
    """Новое занятие без записи в ENDS_BY - это будущий игрок, который
    застрял навсегда: сначала реши, что его снимает."""
    assert set(busy_mod.STATES) == set(busy_mod.ENDS_BY)
    assert set(busy_mod.ENDS_BY.values()) <= {"unstick", "timer", "battle"}


def test_every_entry_knows_every_state() -> None:
    # Карта мини-аппа: на каждый код - свой отказ, и у фронтенда есть его текст.
    assert set(_MAP_REASONS) == set(busy_mod.STATES) - {"riding"}  # маунт в пути карта проверяет сама
    map_tab = (ROOT / "miniapp/src/components/MapTab.jsx").read_text(encoding="utf-8")
    for reason in _MAP_REASONS.values():
        assert re.search(rf"^\s*{reason}:\s*'", map_tab, re.M), f"нет текста отказа {reason} в MapTab.jsx"
    # Маунт в чате подставляет свои тексты - только для известных кодов.
    assert set(mounts_handlers._MOUNT_TEXTS) <= set(busy_mod.STATES)


def _char(**kw) -> Character:
    return Character(user_id=1, name="x", base_class="warrior", **kw)


async def test_states_detected_in_memory() -> None:
    now = datetime.now(timezone.utc)
    soon = now + timedelta(minutes=5)

    async def code(c):
        found = await busy_mod.busy(None, c, peer_id=777001, now=now, skip=("riding",))
        return found.code if found else None

    assert await code(_char()) is None
    assert await code(_char(respawn_at=soon)) == "dead"
    assert await code(_char(screen="mine", mining_ends_at=soon)) == "digging"
    # Вынесло наверх - добыча больше не держит.
    assert await code(_char(screen=None, mining_ends_at=soon)) is None
    assert await code(_char(house_work="alchemy:heal_small", house_work_until=soon)) == "house_work"
    assert await code(_char(pos_x=0, pos_y=0, travel_target_x=3, travel_target_y=3, travel_arrives_at=soon)) \
        == "traveling_on_foot"


async def test_unstick_clears_every_unstick_state(db_session, character_at, monkeypatch) -> None:
    """Всё, что помечено «unstick», /застрял действительно снимает - разом."""
    import bot.handlers.combat as combat_handlers
    from game.economy import mining

    class _FakeEngine:
        sessions: dict = {}

    monkeypatch.setattr(combat_handlers, "_engine", _FakeEngine())
    mine = mining.all_mines()[0]
    c = await character_at(mine.x, mine.y)
    peer = 777002
    now = datetime.now(timezone.utc)
    c.screen = "mine"
    c.mining_mine_id = mine.id
    c.mining_ends_at = now + timedelta(minutes=5)
    explore_rest.restore(explore_rest.EXPLORE, peer)
    await db_session.flush()
    assert (await busy_mod.busy(db_session, c, peer)) is not None

    await world_handlers.force_unstick(db_session, c, peer)
    assert await busy_mod.busy(db_session, c, peer) is None


async def test_cast_line_holds_on_the_cell() -> None:
    """2026-10-23, баг-репорт: со снастью в воде уходили с клетки."""
    now = datetime.now(timezone.utc)
    cast = _char(screen="lake", fishing_cast_at=now, fishing_bite_at=now + timedelta(seconds=20))
    found = await busy_mod.busy(None, cast, peer_id=777003, now=now, skip=("riding",), leaving=True)
    assert found is not None and found.code == "fishing"
    # Остальным занятиям (передача, исследование, вход к воде) снасть не мешает.
    assert await busy_mod.busy(None, cast, peer_id=777003, now=now, skip=("riding",)) is None
    # Окно подсечки давно прошло (рестарт) - не держит.
    stale = _char(screen="lake", fishing_cast_at=now - timedelta(hours=1), fishing_bite_at=now - timedelta(hours=1))
    assert await busy_mod.busy(None, stale, peer_id=777003, now=now, skip=("riding",)) is None


async def test_open_event_blocks_the_mount() -> None:
    """2026-10-23, владелец: с открытым событием исследования в седло нельзя."""
    peer = 777004
    assert await busy_mod.open_event(peer) is None
    world_handlers._pending_events[peer] = "wounded_traveler"
    try:
        found = await busy_mod.open_event(peer)
        assert found is not None and found.code == "event"
    finally:
        world_handlers._pending_events.pop(peer, None)


def test_open_event_guards_mine_and_lake_entry() -> None:
    """2026-10-24: /рудник с открытым событием закрывал его кнопки, и событие
    терялось. Вход в рудник и на озеро ждёт, пока событие закроют."""
    import inspect

    from bot.handlers import fishing, mining

    assert "open_event(" in inspect.getsource(mining._enter_mine)
    assert "open_event(" in inspect.getsource(fishing._enter_lake)


def test_leaving_mine_or_lake_restores_event_buttons() -> None:
    """2026-10-24: «Отойти от воды» с открытым событием давало карту без его
    кнопок, а маунт отвечал «сначала закончи событие». Выход берёт общую
    клавиатуру мира - там кнопки события важнее карты."""
    import inspect

    from bot.handlers import fishing, mining

    assert "_current_keyboard" in inspect.getsource(mining.leave_mine)
    assert "_root_keyboard" in inspect.getsource(fishing.leave_lake)


def test_rift_wait_drops_any_shield() -> None:
    """2026-10-24, владелец: встал к разлому - снимается любая защита."""
    from bot.handlers import rift
    from services import pvp_shield

    pvp_shield.grant(9901, pvp_shield.DRAW)
    pvp_shield.grant(9902, pvp_shield.MONOLITH)
    try:
        assert pvp_shield.drop(9901) and pvp_shield.drop(9902)
        assert pvp_shield.left(9901) == (0, "") and pvp_shield.left(9902) == (0, "")
        assert not pvp_shield.drop(9903)
    finally:
        pvp_shield.drop(9901)
        pvp_shield.drop(9902)
    import inspect

    assert "pvp_shield.drop(" in inspect.getsource(rift)
