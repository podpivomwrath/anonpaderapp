"""Персистентное HP (отдых/респавн) и загрузка атмосферного контента."""

import random
from dataclasses import dataclass

from game.combat import formulas
from services import vitals_service as vs


@dataclass
class FakeStats:
    vitality: int = 20


@dataclass
class FakeCharacter:
    level: int = 5
    current_hp: int | None = None


def test_max_hp_matches_formula() -> None:
    char, stats = FakeCharacter(level=5), FakeStats(vitality=20)
    tier = formulas.tier_for_level(5)
    expected = round(formulas.hp(5, 20, formulas.tier_multiplier(tier)))
    assert vs.max_hp(char, stats) == expected


def test_current_hp_null_means_full() -> None:
    char, stats = FakeCharacter(current_hp=None), FakeStats()
    assert vs.current_hp(char, stats) == vs.max_hp(char, stats)


def test_set_hp_clamps_and_nulls_full() -> None:
    char, stats = FakeCharacter(), FakeStats()
    mx = vs.max_hp(char, stats)
    vs.set_hp(char, stats, mx // 2)
    assert char.current_hp == mx // 2
    # установка полного → NULL (чтобы рост max автоматически лечил)
    vs.set_hp(char, stats, mx)
    assert char.current_hp is None
    # перелив выше max → NULL
    vs.set_hp(char, stats, mx + 100)
    assert char.current_hp is None
    # ниже нуля → 0
    vs.set_hp(char, stats, -50)
    assert char.current_hp == 0


def test_restore_full() -> None:
    char = FakeCharacter(current_hp=10)
    vs.restore_full(char)
    assert char.current_hp is None


# --- Боевой лог: единый краткий формат (патч 43, ч.1 — без образности,
# везде, PvE/PvP/рейды) ---


def test_render_hit_strict_format_no_flavor() -> None:
    from game.combat import combat_flavor

    line = combat_flavor.render_hit(
        "Валгар", "Мирэль", label="Рассекающий удар", amount=184, crit=False,
        missed=False, is_dot=False, hp_before=72, hp_after=58, max_hp=100,
    )
    assert line == "Валгар использует Рассекающий удар на Мирэль — 184 урона. (Мирэль: 72% → 58%)"

    crit_line = combat_flavor.render_hit(
        "Гримм", "Тень_В_Ночи", label="бьёт", amount=143, crit=True,
        missed=False, is_dot=False, hp_before=100, hp_after=57, max_hp=100,
    )
    assert crit_line.startswith("Гримм атакует Тень_В_Ночи — 143 урона (крит!).")

    miss_line = combat_flavor.render_hit(
        "Мирэль", "Валгар", label="Ледяные оковы", amount=0, crit=False,
        missed=True, is_dot=False, hp_before=50, hp_after=50, max_hp=100,
    )
    assert miss_line == "Валгар уклоняется от способности «Ледяные оковы» Мирэль."
    for banned in ("тварь", "Тварь", "оно", "существо"):
        assert banned not in line and banned not in crit_line and banned not in miss_line


def test_render_hit_mob_bite_uses_verb_not_skill_name() -> None:
    """Метки-глаголы (бьёт/кусает/контратакует) идут в "атакует", не в
    "использует [label] на" — иначе "использует кусает на" читалось бы криво."""
    from game.combat import combat_flavor

    line = combat_flavor.render_hit(
        "Волк", "Валгар", label="кусает", amount=12, crit=False,
        missed=False, is_dot=False, hp_before=88, hp_after=76, max_hp=100,
    )
    assert line == "Волк атакует Валгар — 12 урона. (Валгар: 88% → 76%)"


def test_render_hit_dot_line_has_no_verb() -> None:
    from game.combat import combat_flavor

    line = combat_flavor.render_hit(
        "Отравитель", "Цель", label="яд", amount=8, crit=False,
        missed=False, is_dot=True, hp_before=60, hp_after=52, max_hp=100,
    )
    assert line == "Цель теряет 8 HP от эффекта «яд». (Цель: 60% → 52%)"


def test_world_flavor_pools_load() -> None:
    from game.world import flavor

    rng = random.Random(1)
    assert flavor.travel_line(rng)
    assert flavor.rest_start() and flavor.rest_done()
    assert flavor.death_line()
    assert "Кряж" in flavor.respawn_line("🏰 Обетованный Кряж")


def test_world_edge_line_pool_loads() -> None:
    """Патч 31, п.7: лорный отказ у границы карты (content/flavor/world_edge.json)."""
    from game.world import flavor

    rng = random.Random(1)
    line = flavor.world_edge_line(rng)
    assert isinstance(line, str) and line


def test_ashen_song_has_ten_parts() -> None:
    import json
    from pathlib import Path

    data = json.loads(
        (Path("content/flavor/ashen_song.json")).read_text(encoding="utf-8")
    )
    assert len(data["parts"]) == 10


def test_explore_fragment_probabilistic() -> None:
    from game.world import flavor

    # с rng, дающим 0.0 — фрагмент показывается; 0.99 — нет
    class LowRng(random.Random):
        def random(self):
            return 0.0

        def choice(self, seq):
            return seq[0]

    class HighRng(random.Random):
        def random(self):
            return 0.99

    assert flavor.explore_fragment(LowRng()) is not None
    assert flavor.explore_fragment(HighRng()) is None
