"""Патч 30, баг 2: bot/battle_keyboard.py — единая точка получения актуальной
боевой клавиатуры (PvP приоритетнее PvE, None — бой не идёт)."""

import bot.handlers.combat as combat_handlers
import bot.handlers.pvp as pvp_handlers
from bot.battle_keyboard import active_battle_keyboard, in_any_battle


def test_none_when_not_in_any_battle(monkeypatch) -> None:
    monkeypatch.setattr(pvp_handlers, "rebuild_keyboard", lambda peer_id: None)
    monkeypatch.setattr(combat_handlers, "rebuild_keyboard", lambda peer_id: None)
    assert active_battle_keyboard(1) is None


def test_returns_pve_keyboard_when_only_pve_active(monkeypatch) -> None:
    monkeypatch.setattr(pvp_handlers, "rebuild_keyboard", lambda peer_id: None)
    monkeypatch.setattr(combat_handlers, "rebuild_keyboard", lambda peer_id: "PVE_KB")
    assert active_battle_keyboard(1) == "PVE_KB"


def test_prefers_pvp_keyboard_over_pve(monkeypatch) -> None:
    """PvP не прерывается сторонним действием — если игрок каким-то образом
    числится и там, и там, приоритет у боя без аварийного выхода."""
    monkeypatch.setattr(pvp_handlers, "rebuild_keyboard", lambda peer_id: "PVP_KB")
    monkeypatch.setattr(combat_handlers, "rebuild_keyboard", lambda peer_id: "PVE_KB")
    assert active_battle_keyboard(1) == "PVP_KB"


def test_in_any_battle_true_for_pve(monkeypatch) -> None:
    monkeypatch.setattr(pvp_handlers, "has_active_battle", lambda peer_id: False)
    monkeypatch.setattr(combat_handlers, "has_active_encounter", lambda peer_id: True)
    assert in_any_battle(1) is True


def test_in_any_battle_false_when_neither(monkeypatch) -> None:
    monkeypatch.setattr(pvp_handlers, "has_active_battle", lambda peer_id: False)
    monkeypatch.setattr(combat_handlers, "has_active_encounter", lambda peer_id: False)
    assert in_any_battle(1) is False
