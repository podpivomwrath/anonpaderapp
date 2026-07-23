"""Окно распределения статов в чате (патч 11, блок 1) — рендер текста и
финализация с перепроверкой очков (гонка с мини-аппом, которое пишет в то же
поле unspent_points).
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from models import CharacterStats

STAT_ORDER = ["str", "agi", "int", "vit", "wil"]
STAT_ATTR = {"str": "strength", "agi": "agility", "int": "intellect", "vit": "vitality", "wil": "will"}
STAT_META = {
    "str": ("💪", "Сила"),
    "agi": ("🏃", "Ловкость"),
    "int": ("🧠", "Интеллект"),
    "vit": ("❤️", "Выносливость"),
    "wil": ("✨", "Воля"),
}


def snapshot(stats: CharacterStats) -> dict[str, int]:
    return {
        "str": stats.strength,
        "agi": stats.agility,
        "int": stats.intellect,
        "vit": stats.vitality,
        "wil": stats.will,
    }


def levelup_header(level: int) -> str:
    return f"✨ Метка окрепла. Уровень {level}."


def render_window(header: str, unspent: int, char_stats: dict[str, int], pending: dict[str, int]) -> str:
    """Свободных очков — ОСТАТОК пула с учётом уже вложенного в этой сессии
    (та же логика, что в мини-аппе — согласованность важнее буквального
    примера из дизайн-документа, где число статично)."""
    remaining = unspent - sum(pending.values())
    lines = [header, "", f"Свободных очков: {remaining}", ""]
    for key in STAT_ORDER:
        emoji, name = STAT_META[key]
        value = char_stats[key]
        add = pending.get(key, 0)
        suffix = f" (+{add})" if add else ""
        lines.append(f"{emoji} {name}: {value}{suffix}")
    return "\n".join(lines)


def render_readonly(header: str, char_stats: dict[str, int]) -> str:
    """unspent_points = 0 — только текущие статы, без кнопок вложения."""
    lines = [header, ""]
    for key in STAT_ORDER:
        emoji, name = STAT_META[key]
        lines.append(f"{emoji} {name}: {char_stats[key]}")
    return "\n".join(lines)


def render_final(char_stats: dict[str, int], shortfall_note: str | None) -> str:
    parts = " · ".join(f"{STAT_META[k][0]} {STAT_META[k][1]} {char_stats[k]}" for k in STAT_ORDER)
    text = "✨ Характеристики закреплены.\n\n" + parts
    if shortfall_note:
        text = f"{shortfall_note}\n\n{text}"
    return text


@dataclass
class FinalizeResult:
    applied_total: int
    requested_total: int
    char_stats: dict[str, int]


async def finalize(
    db: AsyncSession, stats: CharacterStats, pending: dict[str, int]
) -> FinalizeResult:
    """Перепроверяет unspent_points из БД перед применением: если игрок уже
    потратил часть очков в другом месте (мини-апп) параллельно с открытым
    окном в чате, применяет столько, сколько реально доступно (в порядке
    STAT_ORDER), а не всё запрошенное."""
    requested_total = sum(pending.values())
    budget = stats.unspent_points
    applied: dict[str, int] = {}
    for key in STAT_ORDER:
        want = pending.get(key, 0)
        if want <= 0 or budget <= 0:
            continue
        give = min(want, budget)
        applied[key] = give
        budget -= give

    for key, amount in applied.items():
        attr = STAT_ATTR[key]
        setattr(stats, attr, getattr(stats, attr) + amount)
    applied_total = sum(applied.values())
    stats.unspent_points -= applied_total

    return FinalizeResult(applied_total, requested_total, snapshot(stats))
