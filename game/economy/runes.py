"""Чистая логика рун: эффективность от мастерства, совместимость, тексты.

Без БД - состояние игрока (сумка, мастерство, слоты) в services/rune_service.py.
"""

import random

from game.economy import runes_config as rc


def threshold(curve: str, step: int) -> int:
    """Сколько копий нужно впитать для 100 + 10*step %."""
    if step <= 0:
        return 0
    first, mult = rc.CURVES[curve]
    if step == 1:
        return first
    return mult * (step - 1) ** 2


def efficiency(curve: str, absorbed: int) -> float:
    """Эффективность в долях (1.0 = 100%). Между порогами - линейно: каждая
    впитанная копия видна, а следующие +10% стоят заметного порога."""
    absorbed = max(absorbed, 0)
    step = 0
    while threshold(curve, step + 1) <= absorbed:
        step += 1
    low, high = threshold(curve, step), threshold(curve, step + 1)
    return 1.0 + 0.1 * step + 0.1 * (absorbed - low) / (high - low)


def next_threshold(curve: str, absorbed: int) -> tuple[int, int]:
    """(копий до следующих +10%, какой это процент)."""
    step = 0
    while threshold(curve, step + 1) <= absorbed:
        step += 1
    return threshold(curve, step + 1), 100 + 10 * (step + 1)


def craft_xp(character, xp: int, rng=None) -> int:
    """Опыт ремесла с руной «Мозоли» - копия эффектов лежит на персонаже.

    Дробная часть - шансом (репорт 327): ремёсла дают по 3-8 опыта, и
    round(5 * 1.06) возвращал те же 5 - руна не давала ничего."""
    bonus = (getattr(character, "rune_effects", None) or {}).get("rune:calluses", 0.0)
    if not bonus or xp <= 0:
        return xp
    exact = xp * (1 + bonus)
    whole = int(exact)
    return whole + (1 if (rng or random).random() < exact - whole else 0)


def rune(rune_id: str) -> rc.RuneDef | None:
    return rc.BY_ID.get(rune_id)


def value(rune_def: rc.RuneDef, absorbed: int) -> float:
    return rune_def.value * efficiency(rune_def.curve, absorbed)


def describe(rune_def: rc.RuneDef, absorbed: int = 0) -> str:
    v = value(rune_def, absorbed) * 100
    shown = f"{v:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    return rune_def.text.replace("{v}", f"{shown}%")


def skill_tags(skill) -> set[str]:
    """Типы навыка для рун навыков. skill - BaseSkillDef/SubclassSkillDef."""
    from game.economy import ability_config as ac

    ability = ac.BY_ID.get(skill.id)
    tags = set(ability.tags) if ability else set()
    if (getattr(skill, "multiplier", 0) or 0) > 0:
        tags.add("damage")
    if (getattr(skill, "cd", 0) or 0) >= 4:
        tags.add("long_cd")
    return tags


def fits_skill(rune_def: rc.RuneDef, skill) -> bool:
    return rune_def.kind == rc.SKILL and (not rune_def.tag or rune_def.tag in skill_tags(skill))


def fits_gear(rune_def: rc.RuneDef, place: str) -> bool:
    """Руна экипировки встаёт любому классу (2026-11-11): навыки общие -
    и руны под них тоже."""
    if rune_def.kind != rc.GEAR:
        return False
    if rune_def.place == "weapon":
        return place == "weapon"
    return place in rc.ARMOR_PLACES


def hero_slot_price(index: int) -> int | None:
    """Цена слота героя с номером index (с нуля); None - бесплатный или сверх максимума."""
    paid = index - rc.HERO_SLOTS_FREE
    if paid < 0 or paid >= len(rc.HERO_SLOT_PRICES):
        return None
    return rc.HERO_SLOT_PRICES[paid]


def effect_key(rune_id: str, skill_id: str | None = None) -> str:
    return f"rune:{rune_id}@{skill_id}" if skill_id else f"rune:{rune_id}"


def pvp_scaled(effects: dict[str, float], pvp: bool) -> dict[str, float]:
    """Эффекты рун с поправкой на PvP (вполсилы / не действует)."""
    if not pvp:
        return dict(effects)
    out = {}
    for key, val in effects.items():
        rune_id = key.split(":", 1)[1].split("@", 1)[0]
        definition = rc.BY_ID.get(rune_id)
        mult = rc.PVP_MULT[definition.pvp] if definition else 1.0
        if mult:
            out[key] = val * mult
    return out
