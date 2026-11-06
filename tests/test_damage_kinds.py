"""Три вида урона (2026-11-05, владелец): прямой (обычная атака и навыки),
периодический (яд, горение, кровотечение) и весь (оба). Бонус прямого урона
яд и горение не видят, периодического - удары не видят, весь - оба."""

from game.combat import shared_rules
from game.combat.session import BURN_TAG, Effect, EffectKind
from game.combat.skills import compute_hit
from tests.conftest import NoCritRng, combatant


def _tick(mods: dict) -> int:
    src, tgt = combatant(1, 0), combatant(2, 1)
    src.stats.will = 0  # прибавка Воли - отдельный тест
    src.buff_modifiers.update(mods)
    burn = Effect(kind=EffectKind.DOT, value=100, remaining_ticks=3, source_id=1, stacks=1, tag=BURN_TAG)
    return shared_rules.poison_tick_damage(burn, src, tgt)


def _hit(mods: dict) -> int:
    src, tgt = combatant(1, 0), combatant(2, 1)
    src.buff_modifiers.update(mods)
    return compute_hit(src, tgt, NoCritRng(), label="бьёт").amount


def test_direct_bonus_only_hits() -> None:
    assert _tick({"direct_damage_bonus": 0.5}) == _tick({})
    assert abs(_hit({"direct_damage_bonus": 0.5}) - _hit({}) * 1.5) <= 1


def test_dot_bonus_only_ticks() -> None:
    assert _tick({"dot_damage_bonus": 0.5}) == 150
    assert _hit({"dot_damage_bonus": 0.5}) == _hit({})


def test_all_damage_bonus_both() -> None:
    assert _tick({"damage_bonus": 0.5}) == 150
    assert abs(_hit({"damage_bonus": 0.5}) - _hit({}) * 1.5) <= 1


def test_gifts_and_passives_are_direct_food_is_all() -> None:
    from game.content_loader import load_content
    from game.economy import cooking_config
    from game.ruins_gifts import BY_ID

    buffs = load_content().buffs
    for bid in ("guardian_heavy_hand", "blood_knight_blood_rage", "warrior_path_heavy_swing", "mage_path_monolith"):
        assert "direct_damage_bonus" in buffs[bid].stat_modifiers and "damage_bonus" not in buffs[bid].stat_modifiers
    for gid in ("whetstone", "vow_silence"):
        assert "direct_damage_bonus" in BY_ID[gid].mods
    assert BY_ID["candle_wax"].mods == {"dot_damage_bonus": 0.25}
    assert any("damage_bonus" in d.buff for d in cooking_config.DISHES)


def test_will_boosts_every_dot() -> None:
    """2026-11-06, владелец: Воля качает периодический урон всем - и горение
    Элементалиста. Отравителю - нет: его Воля уже в силе яда, яд не трогаем."""
    from game.combat import balance_config as bc

    src, tgt = combatant(1, 0), combatant(2, 1)
    for will in (0, 100):
        src.stats.will = will
        for tag in (BURN_TAG, None):
            effect = Effect(kind=EffectKind.DOT, value=100, remaining_ticks=3, source_id=1, stacks=1, tag=tag)
            assert shared_rules.poison_tick_damage(effect, src, tgt) == round(100 * (1 + bc.DOT_POWER_PER_WIL * will))
    poisoner = combatant(3, 0, subclass_id="poisoner")
    poisoner.stats.will = 100
    effect = Effect(kind=EffectKind.DOT, value=100, remaining_ticks=3, source_id=3, stacks=1)
    assert shared_rules.poison_tick_damage(effect, poisoner, tgt) == 100, "у Отравителя без двойного учёта"


def test_every_event_modifier_has_a_label() -> None:
    """Репорт 324 (2026-11-06): в плашке события был виден сырой ключ
    «direct_damage_bonus». У каждого модификатора событий - подпись."""
    from game.world import scene_events
    from services.buffs_service import FOOD_SHORT

    keys = {k for e in scene_events.content().effects.values() for k in e.modifiers}
    assert keys <= set(FOOD_SHORT), sorted(keys - set(FOOD_SHORT))
    assert {"damage_bonus", "direct_damage_bonus", "dot_damage_bonus"} <= set(FOOD_SHORT)
