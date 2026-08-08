"""Атмосферный рендер боевого лога (atmosphere-patch-3).

Пулы шаблонов в content/flavor/combat_log.json; выбор случайный, число урона
подставляется, процент HP добавляется по прежним правилам (display).
Разделение игрок/моб — по kind атакующего.

ПРАВИЛО (патч 32, ч.2): render_hit/control_*_line — ТОЛЬКО PvE (образность,
"тварь" и т.п. уместны — цель всегда моб). В PvP (групповой бой и дуэль) ОБА
combatant.kind == "character" — render_hit не отличит игрока от игрока сам,
поэтому вызывающий код обязан явно выбрать render_pvp_hit/pvp_control_*_line
(строгий формат ниже, без образности). Любой НОВЫЙ шаблон, который может
показаться и в PvE, и в PvP, и вне боя (события/находки — см.
services/trophy_service.py::DROP_SOURCE_PREFIXES для того же принципа с
трофеями), обязан быть либо нейтральным, либо иметь отдельную версию под
каждый контекст — PvE-пул сюда молча не переиспользовать.
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
    crit: bool,
    missed: bool,
    is_dot: bool,
    hp_before: float,
    hp_after: float,
    max_hp: float,
    rng: random.Random,
    mode: str = display.MODE_PVP,
) -> str:
    """Одна атмосферная строка боя: шаблон + единая числовая скобка (патч 13,
    ч.2) — число урона больше не встраивается в текст шаблона."""
    by_player = attacker.kind == "character"

    if missed:
        pool = "player_miss" if by_player else "mob_miss"
        return _pick(rng, pool)

    if is_dot:
        text = _pick(rng, "dot")
    elif by_player:
        text = _pick(rng, "player_crit" if crit else "player_hit")
    else:
        text = _pick(rng, "mob_crit" if crit else "mob_hit")

    delta_line = display.hp_delta_line(hp_before, hp_after, max_hp, mode)
    return f"{text} {delta_line}"


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


# --- PvP (патч 32, ч.2): отдельный, СТРОГИЙ формат — никакой образности и
# никаких "тварь"/"оно"/"существо". Пулы выше (render_hit, control_*_line) —
# ТОЛЬКО для PvE, где атакующий бьёт моба или моб бьёт игрока; для PvP
# (групповой бой и дуэль — оба combatant.kind == "character", поэтому
# render_hit не может их различить сам) вызывающий код обязан явно выбрать
# эти функции вместо PvE-пула. Правило на будущее: шаблон, который мог бы
# показаться и в PvE, и в PvP, и вне боя — либо нейтральный, либо с отдельной
# версией под каждый контекст; PvE-шаблоны выше сюда не переиспользовать.


def render_pvp_hit(
    attacker_name: str,
    target_name: str,
    *,
    label: str,
    amount: int,
    crit: bool,
    missed: bool,
    is_dot: bool,
    hp_before: float,
    hp_after: float,
    max_hp: float,
    mode: str = display.MODE_PVP,
) -> str:
    """`[Ник] использует [Способность] на [Ник цели] — X урона. (Ник цели: A% → B%)`
    Промах — `[Ник] уклоняется от атаки [Ник].`, крит — суффикс `(крит!)`."""
    if missed:
        return f"{target_name} уклоняется от атаки {attacker_name}."
    pct_before = display.hp_percent(hp_before, max_hp, mode)
    pct_after = display.hp_percent(hp_after, max_hp, mode)
    crit_suffix = " (крит!)" if crit else ""
    delta = f"({target_name}: {pct_before} → {pct_after})"
    if is_dot:
        return f"{target_name} теряет {amount} HP от эффекта «{label}». {delta}"
    verb = f"атакует {target_name}" if label == "бьёт" else f"использует {label} на {target_name}"
    return f"{attacker_name} {verb} — {amount} урона{crit_suffix}. {delta}"


def pvp_control_line(target_name: str) -> str:
    return f"{target_name} скован."


def pvp_control_resisted_line(target_name: str) -> str:
    return f"{target_name} сопротивляется контролю."


def pvp_control_reduced_line(target_name: str) -> str:
    return f"Контроль на {target_name} слабее обычного (сопротивление)."


def pvp_control_immune_line(target_name: str, turns: int) -> str:
    return f"{target_name} получает иммунитет к контролю на {turns} хода."


def pvp_control_blocked_line(target_name: str) -> str:
    return f"{target_name} уже недавно был под контролем — новый не наложен."
