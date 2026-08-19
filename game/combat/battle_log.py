"""Переработанный боевой лог (патч 51, ч.5): два раздела (своя сторона /
противник, всегда в этом порядке), формат строки `[Кто] → [Что] по [Кому] —
[урон] ([цель]: было% → стало%)`, ДоТ-эффекты — отдельной строкой в конце
раздела цели, HP-полосы отдельным блоком внизу (сначала противники, потом
своя сторона). Никакой образности — тот же принцип, что и патч 43.

Строит лог из result.hit_renders/heal_renders (структурные, см.
game/combat/resolver.py::RenderedHit/RenderedHeal) для урона/лечения — точная
атрибуция по стороне без разбора текста. Остальные строки (контроль/щиты/
смерти/ничья — result.lines[:prelude_line_count] и хвост после hit/heal-
рендеров) раскладываются по разделам эвристикой: чьё имя комбатанта
встречается в строке, того и сторона (эти строки уже человекочитаемы и
называют участника по имени — комбатанты в одном бою уникальны по имени)."""

from game.combat import combat_flavor, display
from game.combat.resolver import RenderedHeal, RenderedHit, TickResult
from game.combat.session import CombatSessionState

_SEP = "━━━━━━━━━━━━━━"


def _mode(session: CombatSessionState) -> str:
    return display.MODE_PVE_RAID if session.is_raid else display.MODE_PVP


def _action_word(label: str) -> str:
    return "атака" if combat_flavor.is_basic_attack_label(label) else label


def _hit_line(hit: RenderedHit, source_name: str, target_name: str, mode: str) -> str:
    if hit.missed:
        return f"{source_name} → атака по {target_name} — промах, {target_name} уклоняется"
    word = _action_word(hit.label)
    crit = " (крит!)" if hit.crit else ""
    before = display.hp_percent(hit.hp_before, hit.max_hp, mode)
    after = display.hp_percent(hit.hp_after, hit.max_hp, mode)
    return f"{source_name} → {word} по {target_name} — {hit.amount} урона{crit} ({target_name}: {before} → {after})"


def _dot_line(hit: RenderedHit, target_name: str) -> str:
    return f"{target_name} теряет {hit.amount} HP от эффекта «{hit.label}»"


def _heal_line(heal: RenderedHeal, source_name: str, target_name: str, mode: str) -> str:
    before = display.hp_percent(heal.hp_before, heal.max_hp, mode)
    after = display.hp_percent(heal.hp_after, heal.max_hp, mode)
    who = "" if source_name == target_name else f"{target_name}: "
    return f"{source_name} → {heal.label} — восполнено {heal.amount} HP ({who}{before} → {after})"


def _guess_side(session: CombatSessionState, line: str) -> int | None:
    """Строка уже называет участника по имени (control_line и т.п.) —
    сопоставляем по вхождению имени. None — общее сообщение без привязки
    к конкретному участнику (напр. "Ничья: обе стороны пали одновременно")."""
    for combatant in session.combatants.values():
        if combatant.name in line:
            return combatant.side
    return None


def render_tick(session: CombatSessionState, result: TickResult, viewer_side: int = 0) -> str:
    """Личный боевой лог этого хода с точки зрения стороны viewer_side —
    ВСЕГДА показывает "своя сторона" первой, "противник" второй, независимо
    от того, чьи это были действия внутри хода (одновременный резолв)."""
    mode = _mode(session)
    own: list[str] = []
    enemy: list[str] = []

    def bucket(side: int) -> list[str]:
        return own if side == viewer_side else enemy

    non_dot = [h for h in result.hit_renders if not h.is_dot]
    dot_hits = [h for h in result.hit_renders if h.is_dot]

    for hit in non_dot:
        source_name = session.combatants[hit.source_id].name
        target_name = session.combatants[hit.target_id].name
        bucket(hit.source_side).append(_hit_line(hit, source_name, target_name, mode))

    for heal in result.heal_renders:
        source_name = session.combatants[heal.source_id].name
        target_name = session.combatants[heal.target_id].name
        bucket(heal.source_side).append(_heal_line(heal, source_name, target_name, mode))

    hit_heal_span = len(result.hit_renders) + len(result.heal_renders)
    other_lines = (
        result.lines[: result.prelude_line_count]
        + result.lines[result.prelude_line_count + hit_heal_span :]
    )
    for line in other_lines:
        side = _guess_side(session, line)
        bucket(side if side is not None else 1 - viewer_side).append(line)

    for hit in dot_hits:
        target_name = session.combatants[hit.target_id].name
        bucket(hit.target_side).append(_dot_line(hit, target_name))

    header = f"⚔️ БОЙ — ход {session.tick_number}"
    parts = [
        header, "",
        "👥 ВАША СТОРОНА",
        *(own or ["Без изменений."]),
        "",
        "💀 ПРОТИВНИК",
        *(enemy or ["Без изменений."]),
        "",
        _SEP,
    ]
    for c in session.combatants.values():
        if c.side != viewer_side and c.alive:
            parts.append(f"{c.name}: {display.health_bar(c.current_hp, c.max_hp, mode)}")
    parts.append(_SEP)
    for c in session.combatants.values():
        if c.side == viewer_side and c.alive:
            parts.append(f"{c.name}: {display.health_bar(c.current_hp, c.max_hp, mode)}")
    return "\n".join(parts)
