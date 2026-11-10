"""Все навыки игры одним реестром (руны-навыки, 2026-11-10).

Навык больше не принадлежит классу: это руна, вставленная в один из трёх
слотов. Здесь:
- ALL_SKILL_DEFS - определения всех навыков (базовые, бывшие навыки
  подклассов и новые из content/skills/rune_skills.json);
- STARTER_SKILLS - три стартовые руны класса от Хранителя Списков;
- skill_ids_of - какие навыки у бойца (ключи "ability:<id>" в buff_modifiers,
  их кладёт services/rune_service.recompute);
- tuned - определение навыка с поправками ступеней этого бойца.
"""

from game.combat.base_skills import BASE_SKILL_DEFS
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
from game.content_loader import load_rune_skills

RUNE_SKILL_DEFS = {s.id: s for s in load_rune_skills()}

ALL_SKILL_DEFS: dict = {**BASE_SKILL_DEFS, **SUBCLASS_SKILL_DEFS, **RUNE_SKILL_DEFS}

#: Стартовые руны-навыки класса (документ дизайна, раздел 2). Маг - с
#: Огненной плети: «Рассекающий удар не вяжется с магом» (владелец).
STARTER_SKILLS: dict[str, tuple[str, ...]] = {
    "warrior": ("warrior_cleave", "warrior_stagger", "warrior_warcry"),
    "rogue": ("rogue_double_stab", "rogue_shadow_dash", "rogue_smoke"),
    "mage": ("elementalist_fire", "elementalist_ice", "poisoner_decay"),
}

#: Префикс ключа «навык вставлен» в buff_modifiers: значение - номер слота + 1.
ABILITY_PREFIX = "ability:"
SLOTS = 3


def skill_def(skill_id: str | None):
    return ALL_SKILL_DEFS.get(skill_id) if skill_id else None


def ability_key(skill_id: str) -> str:
    return f"{ABILITY_PREFIX}{skill_id}"


def skill_ids_of(mods: dict[str, float] | None) -> list[str]:
    """Навыки бойца по порядку слотов. Пусто - навыков нет (моб, руны не вставлены)."""
    found = [(value, key[len(ABILITY_PREFIX):]) for key, value in (mods or {}).items()
             if key.startswith(ABILITY_PREFIX) and value]
    return [sid for _, sid in sorted(found) if sid in ALL_SKILL_DEFS]


def skills_of(mods: dict[str, float] | None) -> list:
    return [ALL_SKILL_DEFS[sid] for sid in skill_ids_of(mods)]


def has_skill(mods: dict[str, float] | None, skill_id: str | None) -> bool:
    return bool(skill_id) and bool((mods or {}).get(ability_key(skill_id)))


def tuned(ctx_or_actor, skill_id: str):
    """Определение навыка с поправками ступеней бойца: skill_bonus (+к
    множителю урона), skill_cd (-ходов перезарядки, не меньше 1),
    skill_duration (+ходов эффекта), skill_value (+к силе эффекта). Ключи
    вида "<вид>:<id навыка>" - их дают ступени руны (ability_config) и пути
    базовых классов. Без поправок - тот же объект, без копии."""
    actor = getattr(ctx_or_actor, "actor", ctx_or_actor)
    skill = ALL_SKILL_DEFS[skill_id]
    mods = getattr(actor, "buff_modifiers", None) or {}
    bonus = mods.get(f"skill_bonus:{skill_id}", 0.0)
    cd = round(mods.get(f"skill_cd:{skill_id}", 0.0))
    duration = round(mods.get(f"skill_duration:{skill_id}", 0.0))
    value = mods.get(f"skill_value:{skill_id}", 0.0)
    if not (bonus or cd or duration or value):
        return skill
    return skill.model_copy(update={
        "multiplier": skill.multiplier + bonus if skill.multiplier else skill.multiplier,
        "cd": max(1, skill.cd - cd),
        "effect_duration": skill.effect_duration + duration,
        "effect_value": skill.effect_value + value,
    })
