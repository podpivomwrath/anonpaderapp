"""Снимок мира для приложения (2026-11-15): действия - кнопки текущего экрана
бота, разобранные по смыслу (bot/app_state.py)."""

import asyncio
import json

from bot import app_state


def test_field_keyboard_becomes_scene_actions() -> None:
    from bot.keyboards import world as kw

    actions = app_state.actions_of(kw.movement_keyboard(5, 5, has_mount=True))
    intents = [(a["intent"], a.get("dir")) for a in actions]
    for expected in [("move", "up"), ("move", "left"), ("explore", None), ("move", "right"), ("move", "down"),
                     ("rest", None), ("look", None), ("mount", None)]:
        assert expected in intents, expected
    explore = next(a for a in actions if a["intent"] == "explore")
    assert explore["label"] == kw.BTN_EXPLORE  # клиент шлёт обратно ту же кнопку
    up = next(a for a in actions if a.get("dir") == "up")
    # «вверх» в мире - +y (bot/keyboards/world._DIRECTION_DELTAS), живая проверка 2026-11-15
    assert up["payload"]["type"] == "move" and (up["dx"], up["dy"]) == kw._DIRECTION_DELTAS[kw.BTN_UP] == (0, 1)
    first_row = app_state.actions_of(kw.movement_keyboard(5, 5))[0]
    assert first_row["dir"] == "up"  # первая кнопка клавиатуры - стрелка вверх


def test_payload_type_is_the_intent_and_unknown_is_other() -> None:
    assert app_state.classify({"label": "🔥 Поджог", "payload": {"type": "skill", "skill": "fire"}})["intent"] == "skill"
    assert app_state.classify({"label": "Что-то новое", "payload": None})["intent"] == "other"
    assert app_state.classify({"label": "🎭 Персонаж ↗", "type": "open_app"})["intent"] == "open_miniapp"
    choice = {"label": "Помочь", "payload": {"type": "event_choice", "event": "e1", "choice": 0}}
    assert app_state.classify(choice)["intent"] == "event_choice"


def test_battle_keyboard_actions() -> None:
    from bot.keyboards import combat_modes
    from bot.keyboards import world as kw

    raw = json.dumps({"buttons": [[
        {"action": {"type": "text", "label": kw.BTN_ATTACK}},
        {"action": {"type": "text", "label": combat_modes.DEFEND_LABEL,
                    "payload": json.dumps({"type": combat_modes.SOLO_PVE.defend_payload})}},
        {"action": {"type": "text", "label": kw.BTN_FLEE}},
    ]]})
    intents = [a["intent"] for a in app_state.actions_of(raw)]
    assert intents[0] == "attack" and intents[2] == "flee"
    assert intents[1] in ("defend", combat_modes.SOLO_PVE.defend_payload)


async def test_burst_of_messages_gives_one_snapshot(monkeypatch) -> None:
    sent = []

    async def fake_send(vk_id: int) -> None:
        sent.append(vk_id)

    monkeypatch.setattr(app_state, "send", fake_send)
    monkeypatch.setattr(app_state, "REFRESH_DELAY", 0.01)
    for _ in range(4):
        app_state.refresh_soon(6101)
    await asyncio.sleep(0.05)
    assert sent == [6101]
    app_state.refresh_soon(6101)
    await asyncio.sleep(0.05)
    assert sent == [6101, 6101]
