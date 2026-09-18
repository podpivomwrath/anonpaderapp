"""Собирает справочник классов, подклассов, навыков и микробаффов для игроков.

Всё берётся из живого контента и balance_config, поэтому числа в справочнике
совпадают с тем, что реально считает бой. После каждой правки баланса
справочник перегенерируется, а не правится руками - иначе он разойдётся с игрой
ровно так же, как раньше расходились buffs.json и константы.

Запуск:  python tools/gen_handbook.py > tools/handbook.md
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from loguru import logger

logger.remove()

import game.classes  # noqa: F401  - регистрация подклассов
from game.classes.base import REGISTRY
from game.combat import balance_config as bc
from game.combat.base_skills import skills_for_class
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
from game.content_loader import load_content
from game.economy import buff_descriptions as bd

CONTENT = load_content()
MECHANICS: dict[str, str] = {}
LORE = json.loads(
    pathlib.Path("content/npc/list_keeper.json").read_text(encoding="utf-8")
)["subclass_select"]["path_descriptions"]

CLASS_TITLES = {"warrior": "Воин", "rogue": "Разбойник", "mage": "Маг"}
STAT_TITLES = {"STR": "Сила", "AGI": "Ловкость", "INT": "Разум", "VIT": "Живучесть", "WIL": "Воля"}
PRIMARY_TITLES = {"str": "Сила", "agi": "Ловкость", "int": "Разум"}
ROLE_TITLES = {
    "dd": "урон", "tank": "танк", "healer": "лекарь", "support": "поддержка",
}
CATEGORY_TITLES = {
    "damage": "Урон",
    "defense": "Оборона",
    "control_utility": "Контроль и утилита",
    "group_support": "Групповая поддержка",
    "healing": "Лечение",
}
EFFECT_TITLES = {
    "stun": "оглушение",
    "target_vuln": "уязвимость на цели",
    "self_dodge_buff": "уклонение себе",
    "self_damage_buff": "усиление своего урона",
    "double_hit": "двойной удар",
    "guaranteed_crit": "гарантированный крит",
}


def pct(value: float) -> str:
    return f"{round(value * 100)}%"


def _s(skill_id: str):
    return SUBCLASS_SKILL_DEFS[skill_id]


def skill_mechanics() -> dict[str, str]:
    """Что навык ДЕЛАЕТ, словами и с живыми числами.

    Флейвор-текст настроение передаёт, но механику не объясняет, а у половины
    навыков подклассов эффект самописный и по полю effect не читается вовсе.
    """
    return {
        "guardian_shield_bash":
            f"Провокация на {turns(bc.PROVOKE_PVP_DURATION_TICKS)}: в PvE мобы переключаются на "
            f"Стража, в PvP чужие цели получают на {pct(bc.PROVOKE_PVP_DAMAGE_REDUCTION)} меньше урона.",
        "guardian_block":
            f"Снижает входящий урон на {pct(_s('guardian_block').effect_value)} и лечит за каждый "
            f"срезанный блоком удар. Держится {turns(_s('guardian_block').effect_duration)}.",
        "guardian_stonegrip": "Оглушает цель.",
        "guardian_unbreakable":
            f"Один удар не может снять больше {pct(_s('guardian_unbreakable').effect_value)} "
            f"максимума здоровья. Держится {turns(_s('guardian_unbreakable').effect_duration)}.",
        "blood_knight_lifesteal_strike":
            f"Лечит на {pct(_s('blood_knight_lifesteal_strike').effect_value)} нанесённого урона.",
        "blood_knight_harvest":
            f"Если своё здоровье ниже половины - лечит на "
            f"{pct(_s('blood_knight_harvest').effect_value)} нанесённого урона.",
        "blood_knight_blood_seal":
            f"Метит цель на {turns(_s('blood_knight_blood_seal').effect_duration)}: весь лайфстил "
            f"по ней сильнее в {bc.BLOOD_KNIGHT_BLOOD_SEAL_MULT} раза.",
        "blood_knight_crimson_feast":
            f"Стоит {pct(bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST)} текущего здоровья, лечит на "
            f"{pct(_s('blood_knight_crimson_feast').effect_value)} нанесённого урона.",
        "shadow_blade_marked_strike":
            f"Добавляет стак Метки добычи, максимум {bc.SHADOW_BLADE_MARK_MAX_STACKS}.",
        "shadow_blade_mark_harvest":
            f"Тратит все стаки Метки: каждый добавляет "
            f"{pct(_s('shadow_blade_mark_harvest').effect_value)} урона.",
        "shadow_blade_shadow_dance":
            f"Добавляет {pct(_s('shadow_blade_shadow_dance').effect_value)} уклонения на "
            f"{turns(_s('shadow_blade_shadow_dance').effect_duration)}.",
        "shadow_blade_execute":
            "Гарантированный крит. По цели ниже трети здоровья урон удваивается.",
        "poisoner_venom":
            f"Накладывает стак яда, максимум {bc.POISONER_MAX_STACKS}. Яд держится "
            f"{turns(bc.POISONER_POISON_DURATION_TICKS)} и тикает уроном каждый ход.",
        "poisoner_decay":
            f"Уязвимость {pct(_s('poisoner_decay').effect_value)} на "
            f"{turns(_s('poisoner_decay').effect_duration)}: цель получает больше урона от ВСЕХ.",
        "poisoner_disrupt":
            f"С шансом {pct(_s('poisoner_disrupt').effect_value)} сбивает действие цели в этот же "
            f"ход и накладывает Ослабление {pct(bc.POISONER_DISRUPT_WEAKEN)} на 3 хода.",
        "poisoner_toxic_burst":
            f"Взрывает весь яд на цели: урон - {pct(_s('poisoner_toxic_burst').effect_value)} "
            "от суммарного тик-урона этого яда. Стаки сгорают.",
        "elementalist_fire":
            f"Поджигает цель на {turns(_s('elementalist_fire').effect_duration)}.",
        "elementalist_ice": "Оглушает цель.",
        "elementalist_lightning":
            f"Бьёт ещё двух противников на {pct(_s('elementalist_lightning').effect_value)} "
            "от основного урона.",
        "elementalist_convergence":
            f"Если на цели горит Горение этого элементалиста - урон больше на "
            f"{pct(_s('elementalist_convergence').effect_value)}.",
        "dark_mystic_blood_pact":
            f"{pct(_s('dark_mystic_blood_pact').effect_value)} нанесённого урона уходит лечением "
            "самому раненому союзнику, а без союзников - себе, но слабее.",
        "dark_mystic_ward":
            f"Щит на {turns(_s('dark_mystic_ward').effect_duration)}, величина зависит от Воли. "
            "Непробитый остаток превращается в лечение.",
        "dark_mystic_drain":
            f"Лечит на {pct(_s('dark_mystic_drain').effect_value)} нанесённого урона. По цели под "
            "контролем урон выше.",
        "dark_mystic_circle":
            f"Стоит {pct(bc.DARK_MYSTIC_CIRCLE_HP_COST)} текущего здоровья, лечит всех союзников. "
            "Без союзников лечит себя, но слабее.",
    }


def turns(n: int) -> str:
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        word = "ход"
    elif n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        word = "хода"
    else:
        word = "ходов"
    return f"{n} {word}"


def damage_line(multiplier: float) -> str:
    if multiplier <= 0:
        return "без прямого урона"
    return f"{round(multiplier * 100)}% от обычной атаки"


def skill_block(skill, *, effect: str | None, effect_value: float, effect_duration: int,
                flavor: str) -> list[str]:
    parts = [damage_line(skill.multiplier), f"перезарядка {turns(skill.cd)}"]
    if effect and effect in EFFECT_TITLES:
        extra = EFFECT_TITLES[effect]
        if effect_value:
            extra += f" {round(effect_value * 100)}%"
        if effect_duration:
            extra += f" на {turns(effect_duration)}"
        parts.append(extra)
    out = [f"**{skill.name}** - {', '.join(parts)}."]
    if flavor:
        out.append(f"> {flavor}")
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    global MECHANICS
    MECHANICS = skill_mechanics()
    print("# Справочник: классы, подклассы, навыки и микробаффы")
    print()
    print("Все числа здесь - то, что реально считает бой. Если где-то написано "
          "«30%», значит движок берёт именно 30%.")
    print()

    # --- Базовые классы ---
    print("## Базовые классы")
    print()
    print("Класс выбирается на старте и определяет основной боевой стат и три "
          f"навыка. Подкласс открывается на {bc.SUBCLASS_UNLOCK_MIN_LEVEL} уровне "
          "и ЗАМЕНЯЕТ базовые навыки своими.")
    print()
    for class_id, title in CLASS_TITLES.items():
        start = bc.STARTING_STATS[class_id]
        stats = ", ".join(f"{STAT_TITLES[k]} {v}" for k, v in start.items())
        print(f"### {title}")
        print()
        print(f"Основной стат: {PRIMARY_TITLES[bc.PRIMARY_STAT_BY_CLASS[class_id]]}. "
              f"Стартовое распределение: {stats}.")
        print()
        for skill in skills_for_class(class_id):
            for line in skill_block(
                skill, effect=skill.effect, effect_value=skill.effect_value,
                effect_duration=skill.effect_duration, flavor=skill.flavor,
            ):
                print(line)
            print()

    # --- Подклассы ---
    print("## Подклассы")
    print()
    print(f"Пресет баффов: от {bc.PRESET_MIN_BUFFS} до {bc.PRESET_MAX_BUFFS} штук, "
          "минимум один из обороны или контроля и утилиты - чистый моно-урон собрать нельзя.")
    print()
    for sub_id, sub in REGISTRY.items():
        roles = [ROLE_TITLES[sub.natural_role.value]]
        roles += [ROLE_TITLES[r.value] for r in sub.flexible_roles]
        print(f"### {sub.title}")
        print()
        lore = LORE.get(sub_id, "").strip()
        if lore:
            print(f"> {lore}")
            print()
        print(f"База: {CLASS_TITLES[sub.base_class]}. "
              f"Основной стат: {PRIMARY_TITLES[sub.primary_stat]}. "
              f"Роль: {roles[0]}; вытягивает также {', '.join(roles[1:])}."
              if len(roles) > 1 else
              f"База: {CLASS_TITLES[sub.base_class]}. "
              f"Основной стат: {PRIMARY_TITLES[sub.primary_stat]}. Роль: {roles[0]}.")
        print()
        print("**Навыки**")
        print()
        for skill_id in sub.skills:
            if skill_id == "attack":
                continue
            skill = SUBCLASS_SKILL_DEFS[skill_id]
            parts = [damage_line(skill.multiplier), f"перезарядка {turns(skill.cd)}"]
            print(f"**{skill.name}** - {', '.join(parts)}.")
            mechanics = MECHANICS.get(skill_id)
            if mechanics:
                print(mechanics)
            if skill.flavor:
                print(f"> {skill.flavor}")
            print()

        print("**Микробаффы**")
        print()
        buffs = [b for b in CONTENT.buffs.values() if b.subclass == sub_id]
        by_category: dict[str, list] = {}
        for b in buffs:
            by_category.setdefault(b.category, []).append(b)
        for category, items in sorted(by_category.items()):
            print(f"*{CATEGORY_TITLES.get(category, category)}*")
            print()
            for b in items:
                text = bd.describe(b) or "в разработке"
                print(f"- **{b.name}** - {text}")
            print()


if __name__ == "__main__":
    main()
