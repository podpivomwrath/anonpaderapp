"""Рендер боевого лога — единый краткий формат (патч 43, ч.1).

До патча 43 PvE использовал атмосферные шаблоны (content/flavor/combat_log.json,
удалён), PvP/дуэль — строгий формат без образности (патч 32, ч.2). В рейдах с
несколькими участниками и множеством действий за ход образные описания
превращались в стену нечитаемого текста, поэтому образность убрана из
пошагового боевого лога ПОВСЕМЕСТНО — PvE, PvP, рейды используют один и тот
же формат. Атмосферность остаётся вне боя (начало/конец боя, события,
локации, NPC, сюжет) — те тексты этот модуль не трогает.

Формат: `[Имя] использует [Навык] на [Цель] — X урона. (Цель: 72% → 58%)`,
базовая атака — «атакует», крит — суффикс `(крит!)`, промах — «уклоняется».
"""

from game.combat import display

# Метки-ГЛАГОЛЫ (уже согласованное действие: «Волк кусает», «Страж
# контратакует») — в отличие от НАЗВАНИЙ навыков, которые подставляются в
# конструкцию «использует [Название] на»: «использует Кровопуск на».
_VERB_LABELS = {"бьёт", "кусает", "контратакует"}


def render_hit(
    source_name: str,
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
    """`[Имя] использует [Навык] на [Цель] — X урона. (Цель: A% → B%)`.
    Промах — `[Цель] уклоняется от [способности/атаки] [Имя]`; крит —
    суффикс `(крит!)`; периодический урон (ДоТ) — отдельная фраза без глагола."""
    if missed:
        what = "атаки" if label in _VERB_LABELS else f"способности «{label}»"
        return f"{target_name} уклоняется от {what} {source_name}."
    pct_before = display.hp_percent(hp_before, max_hp, mode)
    pct_after = display.hp_percent(hp_after, max_hp, mode)
    crit_suffix = " (крит!)" if crit else ""
    delta = f"({target_name}: {pct_before} → {pct_after})"
    if is_dot:
        return f"{target_name} теряет {amount} HP от эффекта «{label}». {delta}"
    verb = f"атакует {target_name}" if label in _VERB_LABELS else f"использует {label} на {target_name}"
    return f"{source_name} {verb} — {amount} урона{crit_suffix}. {delta}"


def control_line(target_name: str) -> str:
    return f"{target_name} скован."


def control_resisted_line(target_name: str) -> str:
    return f"{target_name} сопротивляется контролю."


def control_reduced_line(target_name: str) -> str:
    return f"Контроль на {target_name} слабее обычного (сопротивление)."


def control_immune_line(target_name: str, turns: int) -> str:
    return f"{target_name} получает иммунитет к контролю на {turns} хода."


def control_blocked_line(target_name: str) -> str:
    return f"{target_name} уже недавно был под контролем — новый не наложен."
