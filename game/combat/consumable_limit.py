"""Общий лимит расходников за бой (зелья и эликсиры вместе) - одна точка
для всех видов боя: обычного, группового, PvP и рейда."""

from game.economy import elixir_config as ec

LIMIT = ec.CONSUMABLES_PER_BATTLE
EXHAUSTED_TEXT = f"Больше зелий в этом бою не выпить: лимит {LIMIT} за бой исчерпан."
#: Лечебное - одно за ход (2026-10-19), ход при этом не тратится.
HEAL_TAKEN_TEXT = "Лечебное зелье в этот ход уже выпито. Следующее - в новом ходу."


def heal_taken(combatant) -> bool:
    return getattr(combatant, "heal_drunk_this_turn", False)


def mark_heal(combatant) -> None:
    combatant.heal_drunk_this_turn = True


def visible_stock(combatant, stock, combat_limit_reached: bool):
    """Что показать в окне зелий: лимит на бой, боевые эликсиры сверх своего
    лимита и второе лечебное за ход - скрыты."""
    if left(combatant) <= 0:
        return []
    return [
        (d, count) for d, count in stock
        if (d.category != "heal" or not heal_taken(combatant))
        and (d.category == "heal" or not combat_limit_reached)
    ]


def left(combatant) -> int:
    return max(LIMIT - getattr(combatant, "consumables_used", 0), 0)


def items_header(combatant) -> str:
    """Шапка окна «🎒 Что использовать?» со счётчиком на этот бой."""
    n = left(combatant)
    if n <= 0:
        return f"🎒 Что использовать?\n{EXHAUSTED_TEXT}"
    text = f"🎒 Что использовать?\nОсталось зелий: {n} из {LIMIT}"
    if heal_taken(combatant):
        text += "\n" + HEAL_TAKEN_TEXT
    return text


def spend(combatant) -> None:
    combatant.consumables_used = getattr(combatant, "consumables_used", 0) + 1
