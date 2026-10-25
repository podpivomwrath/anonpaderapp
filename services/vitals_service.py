"""HP персонажа между боями (combat-patch-2: отдых и респавн восстанавливают HP).

max HP считается по той же формуле v2, что и в бою (build_combatant): тир по
уровню + бонус VIT от надетой экипировки (патч 11, блок 2 — services.item_service
.compute_gear_bonus). current_hp = NULL означает полное HP.
"""

from game.combat import formulas
from models import Character, CharacterStats


#: Кого город вылечил после последнего боя: для испытаний это отдых и рвёт
#: серию «подряд без отдыха» (2026-10-25). trial_service.record_battle
#: забирает отметку. В памяти: перезапуск её теряет - серия просто не рвётся.
_city_healed: set[int] = set()


def heal_in_city(character: Character) -> None:
    """В городе здоровье восстанавливается само и молча (2026-10-13, решение
    владельца): вызывать там, где персонаж приходит на клетку."""
    from game.world import grid

    if character.pos_x is not None and grid.city_region_at(character.pos_x, character.pos_y) is not None:
        if character.current_hp is not None and getattr(character, "id", None) is not None:
            _city_healed.add(character.id)
        character.current_hp = None  # NULL - полное здоровье


def take_city_heal(character_id: int) -> bool:
    """Был ли город отдыхом после прошлого боя (и снять отметку)."""
    if character_id in _city_healed:
        _city_healed.discard(character_id)
        return True
    return False


def max_hp(character: Character, stats: CharacterStats, vit_bonus: int = 0) -> int:
    from services import cooking_service

    tier = formulas.tier_for_level(character.level)
    base = round(
        formulas.hp(character.level, stats.vitality + vit_bonus, formulas.tier_multiplier(tier))
        * formulas.class_hp_mult(getattr(character, "base_class", None), getattr(character, "subclass", None))
    )
    # Еда (2026-10-21): та же доля, что в бою (session.build_combatant).
    mult = cooking_service.hp_mult(character) if hasattr(character, "food_dish") else 1.0
    return round(base * mult) if mult != 1.0 else base


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
