"""Опыт и уровни (progression-patch-4).

character.experience = опыт, накопленный В ТЕКУЩЕМ уровне (не общий). При
достижении xp_to_next(level) — левелап (в цикле, если начислили много сразу),
опыт переносится в новый уровень. Штраф смерти бьёт по опыту текущего уровня.
"""

from dataclasses import dataclass

from game.combat import balance_config as bc
from models import Character, CharacterStats


def xp_to_next(level: int) -> int:
    """Опыт, нужный чтобы уйти с текущего уровня на следующий."""
    base = bc.XP_BASE * bc.XP_PLATEAU_LEVEL ** bc.XP_EXP
    if level < bc.XP_PLATEAU_LEVEL:
        return int(bc.XP_BASE * level ** bc.XP_EXP)
    # «полка» после 50 — прогрессия резко замедляется (линейный рост)
    return int(base * (1 + bc.XP_PLATEAU_SLOPE * (level - (bc.XP_PLATEAU_LEVEL - 1))))


def xp_per_mob(mob_level: int) -> int:
    return bc.XP_MOB_FLAT + bc.XP_MOB_PER_LEVEL * mob_level


def mob_xp_level_diff_multiplier(mob_level: int, player_level: int) -> float:
    """Патч 26: бонус опыта за убийство моба выше уровнем — риск = награда.
    Симметричен по форме level_diff_modifiers (game.combat.formulas), но
    отдельные константы: калибровка урона и опыта не обязана совпадать."""
    diff = mob_level - player_level
    if diff <= 0:
        return 1.0
    return min(1 + bc.XP_LEVEL_DIFF_BONUS * diff, bc.XP_LEVEL_DIFF_CAP)


def xp_for_kill(mob_level: int, player_level: int) -> tuple[int, float]:
    """Опыт за убийство КОНКРЕТНОГО моба с учётом разницы уровней.
    Возвращает (итоговый опыт, множитель) — множитель нужен вызывающему коду
    только для текста «×N за опасность» (показывается, если > 1)."""
    mult = mob_xp_level_diff_multiplier(mob_level, player_level)
    return int(xp_per_mob(mob_level) * mult), mult


def event_xp(zone_level: int, player_level: int, share: float) -> int:
    """Опыт с небоевого события/находки (патч 36) — доля от опыта, который
    дал бы обычный моб УРОВНЯ ЗОНЫ (не уровня игрока) на этой клетке,
    включая множитель за разницу уровней патча 26 (тот же xp_for_kill, что
    и у настоящего убийства) — заход в опасную зону вознаграждается и через
    события, не только через бой. zone_level — game.world.grid.mob_level_at."""
    base, _ = xp_for_kill(zone_level, player_level)
    return round(base * share)


@dataclass
class LevelUp:
    levels_gained: int
    new_level: int


def add_experience(character: Character, stats: CharacterStats, amount: int) -> LevelUp:
    """Начисляет опыт в текущий уровень, обрабатывает левелап(ы) в цикле.

    При левелапе: +1 уровень, +STAT_POINTS_PER_LEVEL очков в unspent_points
    (тратятся позже через мини-апп). max HP пересчитывается автоматически
    (vitals_service берёт формулу от level/vit), current_hp остаётся как есть.
    """
    if amount > 0:
        character.experience += amount
    levels = 0
    while character.level < bc.MAX_LEVEL:
        need = xp_to_next(character.level)
        if character.experience < need:
            break
        character.experience -= need
        character.level += 1
        stats.unspent_points += bc.STAT_POINTS_PER_LEVEL
        levels += 1
    if character.level >= bc.MAX_LEVEL:
        character.experience = 0  # на потолке опыт не копится
    if levels > 0:
        character.current_hp = None  # патч 25, п.2: левелап лечит до полного HP
    return LevelUp(levels_gained=levels, new_level=character.level)


def apply_death_penalty(character: Character) -> int:
    """Штраф смерти: теряется доля опыта ТЕКУЩЕГО уровня (без понижения уровня,
    не ниже 0). Возвращает величину потери для лорного сообщения."""
    penalty = int(character.experience * bc.DEATH_XP_PENALTY)
    character.experience = max(0, character.experience - penalty)
    return penalty
