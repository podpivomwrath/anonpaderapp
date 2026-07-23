"""HP персонажа между боями (combat-patch-2: отдых и респавн восстанавливают HP).

max HP считается по той же формуле v2, что и в бою (build_combatant): тир по
уровню + бонус VIT от надетой экипировки (патч 11, блок 2 — services.item_service
.compute_gear_bonus). current_hp = NULL означает полное HP.
"""

from game.combat import formulas
from models import Character, CharacterStats


def max_hp(character: Character, stats: CharacterStats, vit_bonus: int = 0) -> int:
    tier = formulas.tier_for_level(character.level)
    return round(
        formulas.hp(character.level, stats.vitality + vit_bonus, formulas.tier_multiplier(tier))
    )


def current_hp(character: Character, stats: CharacterStats, vit_bonus: int = 0) -> int:
    """Текущее HP; NULL трактуется как полное."""
    mx = max_hp(character, stats, vit_bonus)
    if character.current_hp is None:
        return mx
    return max(0, min(character.current_hp, mx))


def set_hp(character: Character, stats: CharacterStats, value: int, vit_bonus: int = 0) -> None:
    mx = max_hp(character, stats, vit_bonus)
    clamped = max(0, min(value, mx))
    # полное HP храним как NULL, чтобы рост max (левелап/VIT/гир) автоматически лечил
    character.current_hp = None if clamped >= mx else clamped


def restore_full(character: Character) -> None:
    character.current_hp = None
