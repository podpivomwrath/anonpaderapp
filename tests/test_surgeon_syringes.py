"""Шприцы Хирурга (2026-10-29): набранный шприц колется следующим ходом,
попытка контроля по Хирургу в этот ход его выбивает."""

import random
from types import SimpleNamespace

from bot.handlers import raid_results
from game.combat.session import EffectKind
from game.economy import raid_config as rc
from tests.conftest import combatant


def _battle(surgeon, drawn: str):
    return SimpleNamespace(surgeon_id=surgeon.id, syringe_drawn=drawn, syringe_active=None,
                           syringe_left=0, rng=random.Random(1))


def test_red_syringe_gives_damage_buff() -> None:
    surgeon = combatant(9, side=1, kind="mob")
    battle = _battle(surgeon, "red")
    lines: list[str] = []
    raid_results._syringe_tick(battle, surgeon, SimpleNamespace(control_attempts_on={}), lines)
    assert surgeon.effect_total(EffectKind.DAMAGE_BUFF) == rc.SURGEON_SYRINGE_DAMAGE
    assert battle.syringe_left == rc.SURGEON_SYRINGE_TURNS and lines


def test_control_attempt_knocks_the_syringe_out() -> None:
    surgeon = combatant(9, side=1, kind="mob")
    battle = _battle(surgeon, "black")
    lines: list[str] = []
    raid_results._syringe_tick(battle, surgeon, SimpleNamespace(control_attempts_on={9: {1}}), lines)
    assert battle.syringe_active is None and surgeon.buff_modifiers.get("incoming_damage_reduction", 0) == 0
    assert lines == [raid_results.rt.SURGEON_SYRINGE_KNOCKED]


def test_green_syringe_heals_and_black_wears_off() -> None:
    surgeon = combatant(9, side=1, kind="mob")
    surgeon.current_hp = surgeon.max_hp // 2
    battle = _battle(surgeon, "green")
    calm = SimpleNamespace(control_attempts_on={})
    raid_results._syringe_tick(battle, surgeon, calm, [])
    before = surgeon.current_hp
    raid_results._syringe_tick(battle, surgeon, calm, [])
    assert surgeon.current_hp > before

    battle = _battle(surgeon, "black")
    raid_results._syringe_tick(battle, surgeon, calm, [])
    assert surgeon.buff_modifiers["incoming_damage_reduction"] == rc.SURGEON_SYRINGE_ARMOR
    for _ in range(rc.SURGEON_SYRINGE_TURNS):
        raid_results._syringe_tick(battle, surgeon, calm, [])
    assert surgeon.buff_modifiers["incoming_damage_reduction"] == 0.0
