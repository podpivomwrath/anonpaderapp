"""Форматирование боевого текстового UI (п.11 дизайна).

- PvP: проценты округляются до целых (скрывает точность от противника)
- PvE рейд-боссы: один знак после запятой
- Никогда не показывать 0%, если HP > 0, и 100%, если HP не полный
"""

BAR_FILLED = "▰"
BAR_EMPTY = "▱"
BAR_WIDTH = 10

# режимы точности
MODE_PVP = "pvp"          # целые проценты (и обычный PvE)
MODE_PVE_RAID = "pve_raid"  # один знак после запятой


def hp_percent(current: float, maximum: float, mode: str = MODE_PVP) -> str:
    """Процент HP строкой с защитой от визуального искажения при округлении."""
    if maximum <= 0:
        return "0%"
    ratio = max(current, 0) / maximum

    if mode == MODE_PVE_RAID:
        value = round(ratio * 100, 1)
        if value <= 0 and current > 0:
            value = 0.1
        if value >= 100 and current < maximum:
            value = 99.9
        text = f"{value:.1f}"
    else:
        value = round(ratio * 100)
        if value <= 0 and current > 0:
            value = 1
        if value >= 100 and current < maximum:
            value = 99
        text = str(value)
    return f"{text}%"


def health_bar(current: float, maximum: float, mode: str = MODE_PVP) -> str:
    """Текстовый health-bar: блоки + процент рядом."""
    ratio = 0.0 if maximum <= 0 else max(min(current / maximum, 1.0), 0.0)
    filled = round(ratio * BAR_WIDTH)
    if filled == 0 and current > 0:
        filled = 1
    if filled == BAR_WIDTH and current < maximum:
        filled = BAR_WIDTH - 1
    return BAR_FILLED * filled + BAR_EMPTY * (BAR_WIDTH - filled) + " " + hp_percent(current, maximum, mode)


def action_line(
    actor_name: str,
    verb: str,
    target_name: str,
    hp_before: float,
    hp_after: float,
    max_hp: float,
    mode: str = MODE_PVP,
    suffix: str = "",
) -> str:
    """Лог действия: разовый эффект + итоговое состояние.

    Пример: `Ты наносишь удар → Волк: -14% (68% → 54%)`
    """
    before = hp_percent(hp_before, max_hp, mode)
    after = hp_percent(hp_after, max_hp, mode)
    if max_hp > 0:
        delta_value = (hp_after - hp_before) / max_hp * 100
    else:
        delta_value = 0.0
    if mode == MODE_PVE_RAID:
        delta = f"{delta_value:+.1f}%"
    else:
        delta = f"{round(delta_value):+d}%"
    return f"{actor_name} {verb} → {target_name}: {delta} ({before} → {after}){suffix}"
