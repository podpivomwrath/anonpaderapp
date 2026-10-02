"""Общий лимит расходников за бой (зелья и эликсиры вместе) - одна точка
для всех видов боя: обычного, группового, PvP и рейда."""

from game.economy import elixir_config as ec

LIMIT = ec.CONSUMABLES_PER_BATTLE
EXHAUSTED_TEXT = f"Больше зелий в этом бою не выпить: лимит {LIMIT} за бой исчерпан."


def left(combatant) -> int:
    return max(LIMIT - getattr(combatant, "consumables_used", 0), 0)


def items_header(combatant) -> str:
    """Шапка окна «🎒 Что использовать?» со счётчиком на этот бой."""
    n = left(combatant)
    if n <= 0:
        return f"🎒 Что использовать?\n{EXHAUSTED_TEXT}"
    return f"🎒 Что использовать?\nОсталось зелий: {n} из {LIMIT}"


def spend(combatant) -> None:
    combatant.consumables_used = getattr(combatant, "consumables_used", 0) + 1
