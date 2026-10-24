"""Производные характеристики персонажа — ЕДИНЫЙ источник для бота и мини-аппа.

Использует те же formulas.py/balance_config.py, что и боевой резолвер, чтобы
предпросмотр в мини-аппе не мог разойтись с реальным боем.
"""

from dataclasses import dataclass

from game.classes.poisoner import poison_tick_damage_per_stack
from game.combat import balance_config as bc
from game.combat import formulas, stat_model
from game.combat.session import Stats
from models import Character, CharacterStats


@dataclass(frozen=True)
class DerivedStats:
    max_hp: int
    damage: float
    crit_chance: float
    mitigation: float
    control_resist: float
    support_power: float
    dodge_chance: float
    ability_dodge_chance: float
    #: Урон ядом Отравителя за ход при полном числе стаков. Считается НЕ от
    #: урона атаки, а от Воли и Ловкости, поэтому по остальным статам его
    #: не видно вовсе - без этой строки игрок не может понять, что качать.
    poison_power: float


#: Баффы пресета и еды, которые работают в бою всегда (без условий «на низком
#: здоровье», «в группе», «после уворота») - их видно в сводке (2026-10-24).
SHOWN_MODS = (
    "damage_bonus", "reckless_damage_bonus", "crit_chance_bonus", "dodge_bonus",
    "incoming_damage_reduction", "max_hp_bonus",
)


def shown_mods(mods: dict | None) -> dict[str, float]:
    return {k: float(v) for k, v in (mods or {}).items() if k in SHOWN_MODS and v}


def compute(
    character: Character, stats: CharacterStats, gear_bonus: dict[str, int] | None = None,
    mods: dict[str, float] | None = None,
) -> DerivedStats:
    """gear_bonus (патч 11, блок 2) — сумма статов надетой экипировки
    (services.item_service.gear_bonus), прибавляется к собственным статам ДО
    расчёта формул. None/пусто — экипировка не учитывается (как раньше).
    mods - баффы активного пресета и еды (preset_service.resolve_active_modifiers):
    из них в сводку идут SHOWN_MODS, как в бою (skills.compute_hit). None -
    без пресета; здоровье от еды тогда берётся напрямую, как раньше."""
    bonus = gear_bonus or {}
    strength = stats.strength + bonus.get("str", 0)
    agility = stats.agility + bonus.get("agi", 0)
    intellect = stats.intellect + bonus.get("int", 0)
    vitality = stats.vitality + bonus.get("vit", 0)
    will = stats.will + bonus.get("wil", 0)

    tier = formulas.tier_for_level(character.level)
    tier_mult = formulas.tier_multiplier(tier)

    primary_stat = bc.PRIMARY_STAT_BY_CLASS[character.base_class]
    primary_value = {"str": strength, "agi": agility, "int": intellect}[primary_stat]
    k_dmg = formulas.k_dmg_for(primary_stat)
    # Проценты и урон - той же моделью статов, что и бой (game/combat/stat_model).
    model = stat_model.ACTIVE
    s = Stats(strength=strength, agility=agility, intellect=intellect, vitality=vitality, will=will)
    m = shown_mods(mods)
    hp_mult = (1 + m.get("max_hp_bonus", 0.0)) if mods is not None else _food_hp_mult(character)
    dmg_mult = (1 + m.get("damage_bonus", 0.0)) * (1 + m.get("reckless_damage_bonus", 0.0))
    stat_dodge = model.dodge(s, False) + stat_model.subclass_dodge_bonus(character.subclass)
    ability_dodge = model.dodge(s, True) + stat_model.subclass_dodge_bonus(character.subclass)
    extra = m.get("dodge_bonus", 0.0)

    return DerivedStats(
        max_hp=round(round(formulas.hp(character.level, vitality, tier_mult)
                           * formulas.class_hp_mult(character.base_class, character.subclass))
                     * hp_mult),
        damage=round(formulas.damage(
            tier_mult, model.primary_value(primary_value, character.level, True), k_dmg) * dmg_mult, 1),
        crit_chance=min(model.crit_chance(s) + stat_model.subclass_crit_bonus(character.subclass)
                        + formulas.class_crit_bonus(character.base_class, character.subclass)
                        + m.get("crit_chance_bonus", 0.0), 1.0),
        # Снижение от Выносливости и от баффа - множителями, как в бою.
        mitigation=1 - (1 - model.mitigation(s)) * (1 - m.get("incoming_damage_reduction", 0.0)),
        control_resist=model.control_resist(will),
        support_power=model.support_power(s),
        # Бафф уворота от навыков - вдвое слабее (EFFECT_ABILITY_DODGE_RATIO), как в бою; общий потолок.
        dodge_chance=min(stat_dodge + extra, bc.DODGE_HARD_CAP),
        ability_dodge_chance=min(ability_dodge + extra * bc.EFFECT_ABILITY_DODGE_RATIO, bc.DODGE_HARD_CAP),
        poison_power=round(
            poison_tick_damage_per_stack(will, agility) * bc.POISONER_MAX_STACKS, 1
        ),
    )


def _food_hp_mult(character) -> float:
    """Еда (2026-10-21): здоровье в карточке - с баффом, как в бою."""
    from services import cooking_service

    return cooking_service.hp_mult(character) if hasattr(character, "food_dish") else 1.0
