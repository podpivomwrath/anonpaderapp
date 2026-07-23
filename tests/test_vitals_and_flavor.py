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


# --- Атмосферный контент ---


def test_combat_flavor_pools_render() -> None:
    from game.combat import combat_flavor
    from tests.conftest import combatant

    rng = random.Random(1)
    player = combatant(1, side=0, kind="character")
    mob = combatant(2, side=1, kind="mob")

    # удар игрока по мобу — атмосферная строка с числом урона и HP%
    line = combat_flavor.render_hit(
        player, mob, amount=25, crit=False, missed=False, is_dot=False,
        hp_before=100, hp_after=75, max_hp=100, rng=rng,
    )
    assert "25" in line and "%" in line

    # промах
    miss = combat_flavor.render_hit(
        player, mob, amount=0, crit=False, missed=True, is_dot=False,
        hp_before=100, hp_after=100, max_hp=100, rng=rng,
    )
    assert "%" not in miss  # промах без процентов


def test_world_flavor_pools_load() -> None:
    from game.world import flavor

    rng = random.Random(1)
    assert flavor.travel_line(rng)
    assert flavor.rest_start() and flavor.rest_done()
    assert flavor.death_line()
    assert "Кряж" in flavor.respawn_line("🏰 Обетованный Кряж")
    assert flavor.location_line("ridge", rng)


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
