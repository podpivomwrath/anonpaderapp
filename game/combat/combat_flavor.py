"""Атмосферный рендер боевого лога (atmosphere-patch-3).

Пулы шаблонов в content/flavor/combat_log.json; выбор случайный, число урона
подставляется, процент HP добавляется по прежним правилам (display).
Разделение игрок/моб — по kind атакующего.
"""

import json
import random
from pathlib import Path

from game.combat import display
from game.combat.session import CombatantState

_CONTENT = Path(__file__).resolve().parent.parent.parent / "content" / "flavor"

with (_CONTENT / "combat_log.json").open(encoding="utf-8") as _f:
    _POOLS: dict = json.load(_f)


def _pick(rng: random.Random, key: str) -> str:
    return rng.choice(_POOLS[key])


def render_hit(
    attacker: CombatantState,
    target: CombatantState,
    *,
    amount: int,
    crit: bool,
    missed: bool,
    is_dot: bool,
    hp_before: float,
    hp_after: float,
    max_hp: float,
    rng: random.Random,
    mode: str = display.MODE_PVP,
) -> str:
    """Одна атмосферная строка боя: шаблон + число урона + процент HP цели."""
    by_player = attacker.kind == "character"

    if missed:
        pool = "player_miss" if by_player else "mob_miss"
        return _pick(rng, pool)

    if is_dot:
        text = _pick(rng, "dot").format(dmg=amount)
    elif by_player:
        text = _pick(rng, "player_crit" if crit else "player_hit").format(dmg=amount)
    else:
        text = _pick(rng, "mob_crit" if crit else "mob_hit").format(dmg=amount)

    before = display.hp_percent(hp_before, max_hp, mode)
    after = display.hp_percent(hp_after, max_hp, mode)
    # Урон по мобу — показываем его HP; урон по игроку — тоже (кратко)
    return f"{text} ({target.name}: {before} → {after})"


def control_line(rng: random.Random) -> str:
    return _pick(rng, "control_applied")


def control_resisted_line(rng: random.Random) -> str:
    return _pick(rng, "control_resisted")


def control_reduced_line(rng: random.Random) -> str:
    return _pick(rng, "control_reduced")


def control_immune_line(rng: random.Random, turns: int) -> str:
    return _pick(rng, "control_immune").format(turns=turns)


def control_blocked_line(rng: random.Random) -> str:
    return _pick(rng, "control_blocked")
