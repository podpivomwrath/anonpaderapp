"""Ремесленные инструменты (2026-10-23): чистые правила эффектов и требований.

Числа - game/economy/craft_gear_config.py. На вход - тиры инструментов
(0 - инструмента нет), чтобы всё проверялось без базы.
"""

from game.economy import craft_gear_config as gc


def tool_def(tool_id: str) -> gc.ToolDef | None:
    return gc.TOOLS.get(tool_id)


def tools_of(craft: str) -> list[gc.ToolDef]:
    return sorted((t for t in gc.TOOLS.values() if t.craft == craft), key=lambda t: t.slot)


def level_for(tool: gc.ToolDef, tier: int) -> int:
    """Уровень ремесла, нужный для инструмента этого тира."""
    return gc.TIER_LEVEL[tool.craft].get(tier, 10**9)


def max_tier(tool: gc.ToolDef, craft_level: int) -> int:
    return max((t for t, need in gc.TIER_LEVEL[tool.craft].items() if craft_level >= need), default=1)


# --- Эффекты -----------------------------------------------------------------


def pick_speed(pick_tier: int, mine_tier: int) -> float:
    """Доля, на которую добыча короче. Кирка ниже тира рудника - вдвое слабее."""
    if pick_tier <= 0:
        return 0.0
    speed = gc.PICK_SPEED_PER_TIER * pick_tier
    return speed / 2 if pick_tier < mine_tier else speed


def pick_grade_k_mult(pick_tier: int) -> float:
    return 1.0 - gc.PICK_GRADE_PER_TIER * max(pick_tier, 0)


def rod_weight_bonus(rod_tier: int) -> float:
    return gc.ROD_WEIGHT_PER_TIER * max(rod_tier, 0)


def rod_tier_up_chance(rod_tier: int) -> float:
    return gc.ROD_TIER_UP_PER_TIER * max(rod_tier, 0)


def line_break_mult(line_tier: int) -> float:
    return 1.0 - gc.LINE_BREAK_CUT_PER_TIER * max(line_tier, 0)


def pot_extra_chance(pot_tier: int) -> float:
    return gc.POT_EXTRA_PER_TIER * max(pot_tier, 0)


def spice_boost(spice_tier: int) -> float:
    return gc.SPICE_BOOST_PER_TIER * max(spice_tier, 0)


def still_extra_chance(still_tier: int) -> float:
    return gc.STILL_EXTRA_PER_TIER * max(still_tier, 0)


def sickle_cuts(sickle_tier: int, herb_tier: int) -> bool:
    """Серп срезает траву своего тира и ниже."""
    return sickle_tier > 0 and herb_tier <= sickle_tier


def effect_line(tool_id: str, tier: int) -> str:
    """Что даёт инструмент - строка для мини-аппа."""
    pct = lambda x: f"{round(x * 100)}%"  # noqa: E731
    # Формулировки переписаны 2026-10-23 (владелец: «очень непонятно»).
    if tool_id == "sickle":
        return f"Сам срезает траву до {tier} тира на клетке, куда ты заходишь"
    if tool_id == "almanac":
        return ("Когда заходишь на клетку, пишет, на каких из 8 соседних клеток растёт трава. "
                "Показывает только ту, которую ты уже различаешь")
    if tool_id == "pick":
        return (f"Копаешь на {pct(gc.PICK_SPEED_PER_TIER * tier)} быстрее и чаще достаёшь руду лучшей градации. "
                f"В руднике тира выше кирки ускорение вдвое меньше")
    if tool_id == "lamp":
        return (f"Жилу, найденную при исследовании, копаешь на {pct(gc.LAMP_VEIN_SPEED)} быстрее. "
                f"С каждого куска руды шанс {pct(gc.LAMP_GEM_CHANCE)} найти 💎 самоцвет")
    if tool_id == "rod":
        return (f"Рыба попадается тяжелее. Шанс {pct(rod_tier_up_chance(tier))}, что клюнет рыба на тир выше, "
                f"чем позволяет уровень рыбалки (но не выше тира озера)")
    if tool_id == "line":
        return f"Леска рвётся на {pct(gc.LINE_BREAK_CUT_PER_TIER * tier)} реже"
    if tool_id == "pot":
        return f"Шанс {pct(pot_extra_chance(tier))} приготовить лишнюю порцию"
    if tool_id == "spices":
        return f"Бафф от еды на {pct(spice_boost(tier))} сильнее. Каждая съеденная порция тратит 1 заряд"
    if tool_id == "still":
        return f"Шанс {pct(still_extra_chance(tier))} сварить лишнее зелье"
    if tool_id == "flasks":
        return (f"В групповом бою и рейде зелье можно метнуть на всю группу, кроме «Последнего вздоха». "
                f"Действует с силой {pct(gc.FLASK_POWER)}")
    if tool_id == "bait":
        return (f"Рассыпь из сумки (раздел еды): {gc.BAIT_MINUTES} минут рыба клюёт на "
                f"{round(gc.BAIT_SPEED * 100)}% быстрее")
    return ""
