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
STAT_TITLES = {"STR": "Сила", "AGI": "Ловкость", "INT": "Интеллект", "VIT": "Выносливость", "WIL": "Воля"}
PRIMARY_TITLES = {"str": "Сила", "agi": "Ловкость", "int": "Интеллект"}
ROLE_TITLES = {
    "dd": "урон", "tank": "танк", "healer": "лекарь", "support": "поддержка",
}
CATEGORY_TITLES = {
    "damage": "Урон",
    "defense": "Оборона",
    "control_utility": "Контроль и польза",
    "group_support": "Групповая поддержка",
    "healing": "Лечение",
}
EFFECT_TITLES = {
    "stun": "оглушает цель: она пропускает ход",
    "target_vuln": "урон по цели от всех больше на",
    "self_dodge_buff": "шанс уклониться +",
    "self_damage_buff": "весь твой урон больше на",
    "double_hit": "бьёт два раза подряд",
    "guaranteed_crit": "всегда критический удар",
}


def pct(value: float) -> str:
    return f"{round(value * 100)}%"


def _s(skill_id: str):
    return SUBCLASS_SKILL_DEFS[skill_id]


def skill_mechanics() -> dict[str, str]:
    """Что навык ДЕЛАЕТ - простыми словами и с живыми числами (2026-10-15:
    без жаргона, понятно самому неопытному игроку).

    Флейвор-текст настроение передаёт, но механику не объясняет, а у половины
    навыков подклассов эффект самописный и по полю effect не читается вовсе.
    """
    return {
        "guardian_shield_bash":
            f"Провокация на {turns(bc.PROVOKE_PVP_DURATION_TICKS)}. В бою с мобами все мобы бьют только тебя. "
            f"В бою с игроками противник, который бьёт не тебя, наносит на "
            f"{pct(bc.PROVOKE_PVP_DAMAGE_REDUCTION)} меньше урона.",
        "guardian_block":
            f"Глухая оборона: каждый удар по тебе на {pct(_s('guardian_block').effect_value)} слабее, "
            f"а за каждый такой удар ты восстанавливаешь {pct(bc.GUARDIAN_BLOCK_HEAL_PCT)} своего "
            f"максимального здоровья. Действует в ход применения и ещё {turns(_s('guardian_block').effect_duration)}.",
        "guardian_stonegrip":
            "Оглушает цель: она пропускает ход. Если союзный Элементалист сразу следующим ходом "
            "ударит её Схождением стихий, удар будет критическим.",
        "guardian_unbreakable":
            f"{turns(_s('guardian_unbreakable').effect_duration).capitalize()} ни один удар не может снять "
            f"с тебя больше {pct(_s('guardian_unbreakable').effect_value)} максимального здоровья за раз.",
        "blood_knight_lifesteal_strike":
            f"Ты восстанавливаешь здоровье: {pct(_s('blood_knight_lifesteal_strike').effect_value)} "
            "от нанесённого урона.",
        "blood_knight_harvest":
            f"Если у тебя меньше половины здоровья, восстанавливаешь "
            f"{pct(_s('blood_knight_harvest').effect_value)} от нанесённого урона.",
        "blood_knight_blood_seal":
            f"Помечает цель на {turns(_s('blood_knight_blood_seal').effect_duration)}: лечение от урона "
            f"по ней в {num(bc.BLOOD_KNIGHT_BLOOD_SEAL_MULT)} раза больше.",
        "blood_knight_crimson_feast":
            f"Забирает у тебя {pct(bc.BLOOD_KNIGHT_CRIMSON_FEAST_HP_COST)} текущего здоровья, а потом "
            f"лечит на {pct(_s('blood_knight_crimson_feast').effect_value)} от нанесённого урона.",
        "shadow_blade_marked_strike":
            f"Вешает на цель заряд Метки добычи (всего не больше {bc.SHADOW_BLADE_MARK_MAX_STACKS}). "
            "Заряды тратит Жатва меток.",
        "shadow_blade_mark_harvest":
            f"Снимает с цели все заряды Метки добычи: каждый заряд делает этот удар сильнее на "
            f"{pct(_s('shadow_blade_mark_harvest').effect_value)}.",
        "shadow_blade_shadow_dance":
            f"Шанс уклониться от удара +{pct(_s('shadow_blade_shadow_dance').effect_value)} на "
            f"{turns(_s('shadow_blade_shadow_dance').effect_duration)}.",
        "shadow_blade_execute":
            f"Всегда критический удар. Если у цели меньше {pct(bc.SHADOW_BLADE_EXECUTE_HP_THRESHOLD)} "
            f"здоровья, урон ещё и умножается на {num(bc.SHADOW_BLADE_EXECUTE_LOW_HP_MULT)}.",
        "poisoner_venom":
            f"Отравляет цель: каждый ход {turns(bc.POISONER_POISON_DURATION_TICKS)} яд наносит урон. "
            f"Можно отравить до {bc.POISONER_MAX_STACKS} раз подряд - тогда яд бьёт за все разы сразу. "
            "Сила яда зависит не от урона удара, а от твоих Воли и Ловкости (Воля важнее): "
            f"каждое очко Воли даёт {bc.POISONER_POISON_WIL_COEF / bc.POISONER_MAX_STACKS:.2f} урона за ход "
            f"за каждое отравление, очко Ловкости - {bc.POISONER_POISON_AGI_COEF / bc.POISONER_MAX_STACKS:.2f}. "
            "Яд всегда попадает и не бывает критическим, но щит цели его задерживает.",
        "poisoner_decay":
            f"Цель становится уязвимой на {turns(_s('poisoner_decay').effect_duration)}: "
            f"урон по ней от всех больше на {pct(_s('poisoner_decay').effect_value)}.",
        "poisoner_disrupt":
            f"С шансом {pct(_s('poisoner_disrupt').effect_value)} цель не делает своё действие в этот ход. "
            f"Кроме того, она {turns(3)} бьёт на {pct(bc.POISONER_DISRUPT_WEAKEN)} слабее.",
        "poisoner_toxic_burst":
            f"Взрывает весь яд на цели разом: урон - {pct(_s('poisoner_toxic_burst').effect_value)} "
            "от того, что яд ещё нанёс бы до конца, если бы его не трогать. После взрыва яда на цели нет.",
        "elementalist_fire":
            f"Поджигает цель на {turns(_s('elementalist_fire').effect_duration)}: каждый ход Горение "
            f"наносит {pct(_s('elementalist_fire').effect_value)} от урона этого удара. Горящую цель "
            "сильнее бьёт Схождение стихий.",
        "elementalist_ice":
            "Замораживает цель: она пропускает ход. Если сразу следующим ходом ударить её Схождением "
            "стихий, удар будет критическим. Того, кого контроль не берёт (боссы рейдов), оковы не "
            "замораживают, а покрывают инеем: Схождение следующим ходом бьёт его критом так же.",
        "elementalist_lightning":
            f"Молния перескакивает ещё на двух врагов: каждый получает "
            f"{pct(_s('elementalist_lightning').effect_value)} от урона по основной цели.",
        "elementalist_convergence":
            f"Если цель горит (твоё Горение или союзника), урон больше на "
            f"{pct(_s('elementalist_convergence').effect_value)}. Если цель оглушена или заморожена - "
            "или была в прошлый ход, - удар всегда критический. Неважно, кто её оглушил: ты или союзник.",
        "dark_mystic_blood_pact":
            f"{pct(_s('dark_mystic_blood_pact').effect_value)} нанесённого урона превращается в лечение "
            "самого раненого в группе - союзника или тебя самого. Без союзников лечит тебя, но слабее.",
        "dark_mystic_ward":
            f"Ставит на тебя щит на {turns(_s('dark_mystic_ward').effect_duration)}: он принимает урон "
            "вместо здоровья. Чем больше Воля, тем крепче щит. Что осталось от щита в конце - "
            "превращается в лечение.",
        "dark_mystic_drain":
            f"Восстанавливает тебе {pct(_s('dark_mystic_drain').effect_value)} от нанесённого урона. "
            f"Если цель оглушена или заморожена (или была в прошлый ход), урон в "
            f"{num(bc.DARK_MYSTIC_DRAIN_CONTROLLED_MULT)} раза больше.",
        "dark_mystic_circle":
            f"Забирает у тебя {pct(bc.DARK_MYSTIC_CIRCLE_HP_COST)} текущего здоровья и лечит всю группу, "
            "включая тебя самого: каждого на часть его собственного здоровья, чем больше Воля, тем больше. "
            "Без союзников лечит только тебя, и слабее.",
    }


def num(value: float) -> str:
    return f"{value:g}".replace(".", ",")


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
          "любых из пула своего подкласса. Ограничений по категориям нет - "
          "хоть пять баффов урона.")
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
