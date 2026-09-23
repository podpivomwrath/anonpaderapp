"""Патч 72: чистая логика крафта — розыгрыш статов, эффективность, цены.

Система стоит на том, что выбор специализации НЕ задаёт раскладку, а только
предрасположенность. Значит проверять надо не конкретные числа (они
случайны), а свойства распределения: куда оно смещено, что сумма сходится,
что удачный ролл не теряется при улучшении.
"""

import random
import statistics

import pytest

from game.economy import craft_config as cc
from game.economy import crafting


class Rng(random.Random):
    """Обычный seeded RNG. Крафт разыгрывает распределения, поэтому тесты
    смотрят на статистику по многим броскам, а не на один подкрученный."""


def _profile(spec: str, grade: str = "common", tier: int = 3, runs: int = 3000,
             primary: str = "str", power: int = 45) -> dict[str, float]:
    """Средняя доля каждого стата в сумме очков за runs ковок."""
    rng = Rng(12345)
    totals: dict[str, float] = {}
    for _ in range(runs):
        base, _eff = crafting.roll_crafted_stats(rng, spec, power, primary, tier, grade)
        total = sum(base.values())
        for stat, amount in base.items():
            totals[stat] = totals.get(stat, 0.0) + amount / total
    return {stat: value / runs for stat, value in totals.items()}


# --- Предрасположенность --------------------------------------------------------


def test_each_spec_leans_on_its_own_stats() -> None:
    tank = _profile(cc.SPEC_TANK)
    dps = _profile(cc.SPEC_DPS)
    support = _profile(cc.SPEC_SUPPORT)

    assert max(tank, key=tank.get) == "vit"
    assert max(dps, key=dps.get) == "str"       # primary резолвится в str
    assert max(support, key=support.get) == "wil"

    # Каждая специализация сильнее прочих именно в своём: иначе выбор при
    # ковке ничего не решал бы.
    assert tank["vit"] > dps.get("vit", 0)
    assert support["wil"] > dps.get("wil", 0)
    assert dps["str"] > tank.get("str", 0)


def test_spec_is_a_tendency_not_a_guarantee() -> None:
    """Ради этого всё и затевалось: два одинаково скованных предмета разные."""
    rng = Rng(1)
    rolls = {
        tuple(sorted(crafting.roll_crafted_stats(rng, cc.SPEC_TANK, 45, "str", 3, "common")[0].items()))
        for _ in range(50)
    }
    assert len(rolls) > 40, "роллы почти не отличаются - разброса нет"


def test_primary_resolves_to_the_owner_class_stat() -> None:
    """У мага «primary» обязан стать интеллектом, а не силой."""
    mage = _profile(cc.SPEC_DPS, primary="int")
    assert max(mage, key=mage.get) == "int"
    assert "str" not in mage


def test_primary_merges_with_an_explicit_weight_of_the_same_stat() -> None:
    """У ловкача в ДД-весах и primary, и agi — это должен быть ОДИН стат с
    суммарным весом, а не потерянная половина."""
    weights = crafting.resolve_weights(cc.SPEC_WEIGHTS[cc.SPEC_DPS], "agi")
    assert weights["agi"] == pytest.approx(0.50 + 0.30)


# --- Градация руды: кучность ----------------------------------------------------


def test_better_grade_focuses_the_roll() -> None:
    """Вторая ось руды. Тир решает СКОЛЬКО очков, градация — насколько кучно
    они лягут; иначе копить имело бы смысл только одну ось."""
    shares = []
    for grade in ("common", "rare", "epic", "legendary"):
        profile = _profile(cc.SPEC_TANK, grade=grade)
        shares.append(profile["vit"] + profile.get("wil", 0))
    assert shares == sorted(shares), f"кучность не растёт с градацией: {shares}"
    assert shares[-1] > shares[0] + 0.10, "легендарная руда почти не отличается от обычной"


# --- Бюджет очков ---------------------------------------------------------------


def test_worst_craft_is_never_worse_than_the_source() -> None:
    """Иначе игроку выгоднее НЕ ковать, и вся система мёртвая."""
    source_power = 45
    worst = crafting.apply_efficiency(
        crafting.craft_power(source_power), cc.EFFICIENCY_MIN
    )
    assert worst >= source_power


def test_efficiency_ladder_is_monotonic() -> None:
    power = crafting.craft_power(45)
    values = [crafting.apply_efficiency(power, e) for e in (80, 90, 100, 110, 120)]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_roll_spends_the_whole_budget() -> None:
    rng = Rng(3)
    for _ in range(200):
        base, _ = crafting.roll_crafted_stats(rng, cc.SPEC_SUPPORT, 45, "int", 2, "epic")
        assert sum(base.values()) == crafting.craft_power(45)


def test_chunk_split_does_not_leak_or_invent_points() -> None:
    rng = Rng(4)
    for total in (1, 7, 58, 999):
        for parts in (1, 2, 6, 20):
            sizes = crafting._split(rng, total, parts)
            assert sum(sizes) == total
            assert all(size >= 0 for size in sizes)


def test_stats_do_not_come_out_in_round_multiples() -> None:
    """Равные порции выдавали бы механику наружу: все статы были бы кратны
    десяти. Проверяем, что значения выглядят обычными числами."""
    rng = Rng(5)
    values = []
    for _ in range(200):
        base, _ = crafting.roll_crafted_stats(rng, cc.SPEC_TANK, 45, "str", 3, "common")
        values.extend(base.values())
    multiples_of_ten = sum(1 for v in values if v % 10 == 0)
    assert multiples_of_ten / len(values) < 0.25


# --- Эффективность и подъём ступеней --------------------------------------------


def test_ladder_result_does_not_depend_on_the_path() -> None:
    """Главное свойство хранения базового ролла: предмет, поднятый по
    ступеням 80→90→...→120, обязан совпасть со скованным сразу на 120."""
    rng = Rng(6)
    base, _ = crafting.roll_crafted_stats(rng, cc.SPEC_TANK, 45, "str", 1, "rare")

    climbed = base
    efficiency = cc.EFFICIENCY_MIN
    while (nxt := crafting.next_efficiency(efficiency)) is not None:
        efficiency = nxt
        climbed = crafting.stats_at_efficiency(base, efficiency)

    assert climbed == crafting.stats_at_efficiency(base, cc.EFFICIENCY_MAX)


def test_upgrading_keeps_the_layout() -> None:
    """Игрок, которому повезло с раскладкой, не должен терять удачу при
    улучшении — проценты множат сумму, а не перекидывают статы."""
    base = {"vit": 40, "wil": 15, "agi": 3}
    low = crafting.stats_at_efficiency(base, 80)
    high = crafting.stats_at_efficiency(base, 120)
    assert set(low) == set(high) == set(base)
    assert sorted(low, key=low.get) == sorted(high, key=high.get)


def test_craft_cannot_reach_the_system_cap() -> None:
    """110 и 120 берутся ТОЛЬКО инструментами — иначе лестница улучшений
    никому не нужна: проще накопить руду на один хороший крафт."""
    for tier in range(1, 10):
        assert cc.craft_efficiency_for(tier) <= cc.EFFICIENCY_CRAFT_MAX
    assert cc.EFFICIENCY_CRAFT_MAX < cc.EFFICIENCY_MAX


def test_ore_above_craft_cap_gives_nothing_extra() -> None:
    """Поэтому руду тира 4+ в крафт и не принимаем: она бы просто сгорела."""
    assert cc.craft_efficiency_for(cc.CRAFT_MAX_ORE_TIER) == cc.EFFICIENCY_CRAFT_MAX
    assert cc.craft_efficiency_for(cc.CRAFT_MAX_ORE_TIER + 1) == cc.EFFICIENCY_CRAFT_MAX


# --- Инструменты ----------------------------------------------------------------


def test_tool_ceiling_grows_with_ore_tier() -> None:
    ceilings = [cc.TOOL_CEILING_BY_ORE_TIER[t] for t in sorted(cc.TOOL_CEILING_BY_ORE_TIER)]
    assert ceilings == sorted(ceilings)
    assert max(ceilings) == cc.EFFICIENCY_MAX


def test_weak_tool_cannot_close_a_high_step() -> None:
    assert not crafting.can_upgrade_with(100, tool_ceiling=90)
    assert crafting.can_upgrade_with(100, tool_ceiling=110)


def test_strong_tool_may_close_a_low_step() -> None:
    """Расточительно, но запрещать игроку тратить своё незачем."""
    assert crafting.can_upgrade_with(80, tool_ceiling=120)


def test_nothing_upgrades_past_the_cap() -> None:
    assert crafting.next_efficiency(cc.EFFICIENCY_MAX) is None
    assert not crafting.can_upgrade_with(cc.EFFICIENCY_MAX, tool_ceiling=120)


def test_upgrade_cost_grows_towards_the_cap() -> None:
    """Без подорожания игрок добирается до 120 за пару вечеров, и у предмета
    не остаётся цели."""
    costs = [cc.tool_ore_cost(e) for e in (90, 100, 110, 120)]
    assert costs == sorted(costs)
    assert costs[-1] > costs[0] * 3


def test_every_reachable_step_has_a_price() -> None:
    """Страховка от ступени, до которой можно дойти, но нечем заплатить."""
    efficiency = cc.EFFICIENCY_MIN
    while (nxt := crafting.next_efficiency(efficiency)) is not None:
        assert nxt in cc.TOOL_ORE_COST_BY_TARGET, f"нет цены для ступени {nxt}"
        assert any(c >= nxt for c in cc.TOOL_CEILING_BY_ORE_TIER.values()), \
            f"ступень {nxt} не закрывается ни одним инструментом"
        efficiency = nxt


# --- Перекрафт -------------------------------------------------------------------


def test_recraft_gets_more_expensive() -> None:
    costs = [cc.recraft_ore_cost(n) for n in range(4)]
    assert costs == sorted(costs)
    assert costs[0] > cc.CRAFT_ORE_COST, "первый перекрафт должен стоить дороже первой ковки"


# --- Боссовые предметы ------------------------------------------------------------


def test_boss_item_leans_on_the_primary_stat_but_is_not_pure() -> None:
    """Боссовая вещь — сырьё для крафта, но носить её можно: перекос в
    основной стат остаётся, а вот одинаковыми два скальпеля быть не должны."""
    rng = Rng(8)
    rolls = [crafting.roll_boss_item_stats(rng, 45, "str") for _ in range(400)]
    share = statistics.mean(r.get("str", 0) / sum(r.values()) for r in rolls)
    assert 0.3 < share < 0.6
    assert len({tuple(sorted(r.items())) for r in rolls}) > 300


# --- Контент ----------------------------------------------------------------------


def test_every_recipe_covers_every_spec() -> None:
    """Рецепт без одной специализации оставил бы в мини-аппе мёртвую кнопку."""
    for source_id, recipe in crafting._all().items():
        assert set(recipe.outputs) == set(cc.SPECS), f"{source_id}: {set(recipe.outputs)}"
        for spec, output in recipe.outputs.items():
            assert output.name.strip(), f"{source_id}/{spec}: пустое имя"


def test_scalpel_is_craftable() -> None:
    assert crafting.is_craftable("surgeon_scalpel")
    assert not crafting.is_craftable(None)
    assert not crafting.is_craftable("нет такого")
