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

from game.combat import balance_config as bc
from game.combat import display

# Метки-ГЛАГОЛЫ (уже согласованное действие: «Волк кусает», «Страж
# контратакует») — в отличие от НАЗВАНИЙ навыков, которые подставляются в
# конструкцию «использует [Название] на»: «использует Кровопуск на».
_VERB_LABELS = {"бьёт", "кусает", "контратакует"}


def is_basic_attack_label(label: str) -> bool:
    """Патч 51, ч.5 (game/combat/battle_log.py) — метка обычной атаки
    (не название навыка), та же граница, что использует render_hit ниже."""
    return label in _VERB_LABELS


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
    shielded: int = 0,
    blocked: int = 0,
) -> str:
    """`[Имя] использует [Навык] на [Цель] — X урона. (Цель: A% → B%)`.
    shielded - сколько из удара съел щит: тогда X - полный удар и суффикс
    «(щит поглотил N)». Раньше писалось «0 урона» отдельно от строки щита,
    и игроки решали, что урон в барьер считается неправильно (2026-10-12).
    Промах — `[Цель] уклоняется от [способности/атаки] [Имя]`; крит —
    суффикс `(крит!)`; периодический урон (ДоТ) — отдельная фраза без глагола."""
    if missed:
        what = "атаки" if label in _VERB_LABELS else f"способности «{label}»"
        return f"{target_name} уклоняется от {what} {source_name}."
    pct_before = display.hp_text(hp_before, max_hp, mode)
    pct_after = display.hp_text(hp_after, max_hp, mode)
    crit_suffix = " (крит!)" if crit else ""
    shield_suffix = f" (щит поглотил {shielded})" if shielded > 0 else ""
    if blocked > 0:  # блок стойки (Глухая оборона) - виден в каждом ударе, не только в ход навыка
        shield_suffix += f" (🛡 блок срезал {blocked})"
    amount += max(shielded, 0)
    delta = f"({target_name}: {pct_before} → {pct_after})"
    if is_dot:
        return f"{target_name} теряет {amount} HP от эффекта «{label}»{shield_suffix}. {delta}"
    verb = f"атакует {target_name}" if label in _VERB_LABELS else f"использует {label} на {target_name}"
    return f"{source_name} {verb} - {amount} урона{crit_suffix}{shield_suffix}. {delta}"


def self_buff_line(actor_name: str, skill_name: str, what: str, value: float, turns: int) -> str:
    """Навык без урона, усиливающий самого бойца (Боевой клич, Дымовая
    завеса). Без строки он молча пропадал из лога: удар есть только у
    атакующих навыков, а эффект на себя отдельной строки не давал."""
    return f"{actor_name} → {skill_name}: {what} +{round(value * 100)}% на {turns} хода"


def control_resisted_line(target_name: str) -> str:
    return f"{target_name} сопротивляется контролю."


def control_reduced_line(target_name: str) -> str:
    return f"Контроль на {target_name} слабее обычного (сопротивление)."


def control_immune_line(target_name: str, turns: int) -> str:
    return f"{target_name} получает иммунитет к контролю на {turns} хода."


def control_blocked_line(target_name: str, reason: str | None = None) -> str:
    """Контроль не лёг из-за защиты цели. Без согласования по роду (патч 47).

    Раньше одна строка «уже под контролем» печаталась на любую защиту - и у
    Хирурга, которого контроль не берёт вовсе, выходила на каждую попытку."""
    if reason == "always":
        return f"{target_name} не поддаётся контролю."
    if reason == "effect":
        return f"{target_name}: защита от контроля - эффект не наложен."
    return f"{target_name}: защита от повторного контроля - эффект не наложен."


def frost_line(target_name: str) -> str:
    """Ледяные оковы по тому, кого контроль не берёт: иней вместо заморозки."""
    return f"{target_name} не замерзает, но покрывается инеем ❄️ Схождение стихий следующим ходом ударит критом."


def unimplemented_skill_line(actor_name: str, skill_id: str | None) -> str:
    """Навык объявлен, но обработчика к нему нет.

    Ветка страховочная — сейчас все навыки каталога обработаны, и тест это
    удерживает. Но раньше здесь печаталось «умение «dark_mystic_ward» ещё не
    реализовано (TODO: content)»: игроку показывали внутренний id и записку
    разработчика. Если страховка всё же сработает, пусть выглядит как часть
    игры, а не как утечка из исходников.
    """
    from game.combat.base_skills import BASE_SKILL_DEFS
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    definition = BASE_SKILL_DEFS.get(skill_id) or SUBCLASS_SKILL_DEFS.get(skill_id)
    name = definition.name if definition is not None else "приём"
    return f"{actor_name} пытается применить «{name}», но ничего не выходит."


def defend_line(name: str) -> str:
    """«Защититься» (2026-10-19): ход пропущен добровольно."""
    pct = round(bc.DEFEND_DAMAGE_REDUCTION * 100)
    return f"🛡️ {name} защищается: входящий урон -{pct}% до следующего хода"
