"""Короткий боевой лог (2026-10-22, владелец): полоски с изменением за ход и
значки эффектов; «📜 Сводка» в боевой клавиатуре правит последний лог в
полный и обратно."""

import json

from bot import short_log
from bot.keyboards.world import combat_keyboard
from game.combat import battle_log
from game.combat.resolver import resolve_tick
from game.combat.session import BURN_TAG, CombatMode, CombatSessionState, DeclaredAction, Effect, EffectKind
from tests.conftest import NoCritRng, combatant


class _Api:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self.messages = self

    async def send(self, **kw):
        self.sent.append(kw)
        return 555

    async def edit(self, **kw):
        self.edited.append(kw)
        return 1


def _session():
    hero = combatant(1, side=0)
    wolf = combatant(2, side=1, vitality=500)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    state.add(hero)
    state.add(wolf)
    return state, hero, wolf


def test_short_render_shows_hp_change_and_effect_icons() -> None:
    state, hero, wolf = _session()
    wolf.effects.append(Effect(kind=EffectKind.DOT, value=5, remaining_ticks=3, source_id=1, tag=BURN_TAG))
    wolf.effects.append(Effect(kind=EffectKind.FREEZE, value=1, remaining_ticks=1, source_id=1))
    result = resolve_tick(state, {1: DeclaredAction(type="attack", target_id=2)}, NoCritRng())
    text = battle_log.render_short(state, result)
    wolf_line = next(line for line in text.splitlines() if line.startswith(wolf.name))
    assert "(-" in wolf_line and "🔥" in wolf_line
    assert "→" not in text  # строк ударов нет
    full = battle_log.render_tick(state, result)
    assert len(text) < len(full)


def test_toggle_button_goes_into_the_combat_keyboard() -> None:
    kb = combat_keyboard("mage", {})
    rows = json.loads(short_log.with_toggle(kb))["buttons"]
    labels = [b["action"]["label"] for r in rows for b in r]
    assert short_log.BTN_OPEN in labels and len(rows) <= 5 and all(len(r) <= 3 for r in rows)
    hidden = json.loads(short_log.with_toggle(kb, expanded=True))["buttons"]
    assert short_log.BTN_HIDE in [b["action"]["label"] for r in hidden for b in r]
    # Инлайн и пустые клавиатуры не трогаем.
    empty = json.dumps({"one_time": False, "buttons": []})
    assert short_log.with_toggle(empty) == empty


async def test_send_short_then_expand_and_hide() -> None:
    api = _Api()
    short_log.set_short(42, True)
    try:
        await short_log.send(api, 42, "коротко", "полностью", combat_keyboard("mage", {}))
        assert api.sent[-1]["message"] == "коротко"
        assert await short_log.toggle(api, 42)
        assert api.edited[-1]["message"] == "полностью" and api.edited[-1]["message_id"] == 555
        assert short_log.BTN_HIDE in api.edited[-1]["keyboard"]
        assert await short_log.toggle(api, 42)
        assert api.edited[-1]["message"] == "коротко"
    finally:
        short_log.set_short(42, False)
    # Выключил - полный лог, кнопке править нечего.
    await short_log.send(api, 42, "коротко", "полностью", combat_keyboard("mage", {}))
    assert api.sent[-1]["message"] == "полностью" and short_log.BTN_OPEN not in api.sent[-1]["keyboard"]
    assert not await short_log.toggle(api, 42)
