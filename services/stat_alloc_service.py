"""Окно распределения статов в чате (патч 11, блок 1) — рендер текста и
финализация с перепроверкой очков (гонка с мини-аппом, которое пишет в то же
поле unspent_points).
"""

from dataclasses import dataclass

from sqlalchemy import select, update
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


def render_readonly(
    header: str, char_stats: dict[str, int],
    pvp_wins: int | None = None, pvp_losses: int | None = None, title: str | None = None,
) -> str:
    """unspent_points = 0 — только текущие статы, без кнопок вложения.

    pvp_wins/pvp_losses (патч 22) — добавляет строку "⚔️ PvP: N побед · M
    поражений" под статами, если переданы (None — не показывать вовсе,
    для вызовов, где профиль ни при чём). title (патч 23) — активный титул,
    показывается рядом с заголовком, если задан."""
    header_line = f"{header} «{title}»" if title else header
    lines = [header_line, ""]
    for key in STAT_ORDER:
        emoji, name = STAT_META[key]
        lines.append(f"{emoji} {name}: {char_stats[key]}")
    if pvp_wins is not None and pvp_losses is not None:
        lines.append("")
        lines.append(f"⚔️ PvP: {pvp_wins} побед · {pvp_losses} поражений")
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


class NotEnoughPoints(ValueError):
    pass


async def allocate(db: AsyncSession, stats: CharacterStats, increments: dict[str, int]) -> None:
    """Atomic budget check shared by chat and HTTP; caller owns the transaction."""
    if any(k not in STAT_ATTR or type(v) is not int or v < 0 for k, v in increments.items()):
        raise ValueError("invalid_increment")
    total = sum(increments.values())
    if total <= 0:
        raise ValueError("nothing_to_apply")
    values = {STAT_ATTR[k]: getattr(CharacterStats, STAT_ATTR[k]) + v for k, v in increments.items() if v}
    values["unspent_points"] = CharacterStats.unspent_points - total
    result = await db.execute(
        update(CharacterStats)
        .where(CharacterStats.character_id == stats.character_id, CharacterStats.unspent_points >= total)
        .values(**values).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise NotEnoughPoints("not_enough_points")
    await db.refresh(stats)


async def finalize(
    db: AsyncSession, stats: CharacterStats, pending: dict[str, int]
) -> FinalizeResult:
    """Перепроверяет unspent_points из БД перед применением: если игрок уже
    потратил часть очков в другом месте (мини-апп) параллельно с открытым
    окном в чате, применяет столько, сколько реально доступно (в порядке
    STAT_ORDER), а не всё запрошенное."""
    stats = await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == stats.character_id)
        .with_for_update().execution_options(populate_existing=True)
    )
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

    applied_total = sum(applied.values())
    if applied_total:
        await allocate(db, stats, applied)

    return FinalizeResult(applied_total, requested_total, snapshot(stats))
