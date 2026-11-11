"""Путеводитель под руны-навыки (2026-11-10): пересобирает две главы
miniapp/src/handbook.json из живых данных - каталога навыков, ступеней,
пассивок подклассов и огранок. Числа берутся оттуда же, что читает бой.

- «Подкласс и пресеты»: вместо микробаффов и пресетов баффов - руны-навыки,
  ступени, огранки, пассивки и пресеты-раскладки;
- «Навыки и формулы»: вместо навыков классов и микробаффов - стартовые руны
  классов, пассивки подклассов и все руны-навыки со ступенями.

Запуск: python tools/handbook_skill_runes.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loguru import logger  # noqa: E402

logger.remove()

import game.classes  # noqa: E402, F401 - регистрирует навыки
from game.combat import skill_catalog  # noqa: E402
from game.economy import ability_config as ac  # noqa: E402
from game.economy import passives_config  # noqa: E402
from game.economy import runes_config as rc  # noqa: E402

OUT = ROOT / "miniapp" / "src" / "handbook.json"
CLASS_TITLES = {"warrior": "Воин", "rogue": "Разбойник", "mage": "Маг"}
RARITY = {ac.COMMON: "обычная", ac.RARE: "редкая", ac.EPIC: "эпическая", ac.MYTHIC: "мифическая"}
STEP = {1: "I", 2: "II", 3: "III", 4: "IV"}

#: Группы навыков в справочнике - как в документе дизайна.
GROUPS = [
    ("Удары", ["warrior_cleave", "rogue_double_stab", "rogue_shadow_dash", "shadow_blade_marked_strike",
               "shadow_blade_mark_harvest", "shadow_blade_execute", "guardian_shield_bash"]),
    ("Вампиризм", ["blood_knight_lifesteal_strike", "blood_knight_harvest", "blood_knight_blood_seal",
                   "blood_knight_crimson_feast", "dark_mystic_drain"]),
    ("Урон за ход", ["poisoner_venom", "elementalist_fire", "poisoner_toxic_burst"]),
    ("Стихии", ["elementalist_lightning", "elementalist_convergence"]),
    ("Контроль и ослабления", ["warrior_stagger", "elementalist_ice", "poisoner_disrupt", "poisoner_decay", "mute",
                               "bitter_wound", "strip_veil", "shatter"]),
    ("Защита и усиления себя", ["warrior_warcry", "rogue_smoke", "guardian_block", "guardian_unbreakable",
                                "counter_strike", "breather"]),
    ("Поддержка", ["dark_mystic_blood_pact", "dark_mystic_ward", "dark_mystic_circle", "cleanse_water", "cover_ally"]),
    ("Мифические", ["close_ranks", "reckoning"]),
]


def copies(n: int) -> str:
    from game import plural

    return plural.count(n, "копия", "копии", "копий")


def skill_details(sid: str) -> dict:
    skill = skill_catalog.ALL_SKILL_DEFS[sid]
    ability = ac.BY_ID[sid]
    need = ac.step_thresholds(ability.curve)
    head = (f"{RARITY[ability.rarity].capitalize()} руна, перезарядка {skill.cd}. {ability.summary}")
    scale = ac.scaling(sid, skill.multiplier)
    if scale:
        head += " Бьёт от характеристик: " + " и ".join(
            f"{round(coef * 100)}% {ac.STAT_TITLES[stat]}" for stat, coef in scale.items()) + "."
    steps = [
        f"<b>Ступень I</b> ({copies(need[0])}) - {ability.one.text}",
        f"<b>Ступень II</b> ({copies(need[1])}) - {ability.two.text} Открывает второе гнездо огранки.",
        f"<b>Ступень III</b> ({copies(need[2])}) - на выбор: а) {ability.fork[0].text} б) {ability.fork[1].text}",
        f"<b>Ступень IV</b> ({copies(need[3])}) - {ability.four.text} В PvP - вполсилы.",
    ]
    return {"t": "details", "title": skill.name, "blocks": [{"t": "p", "text": head}, {"t": "ul", "items": steps}]}


def runes_chapter_blocks() -> list[dict]:
    """Блоки главы «Подкласс и пресеты» вместо микробаффов и пресетов баффов."""
    starters = "; ".join(
        f"{CLASS_TITLES[cls]} - " + ", ".join(f"«{skill_catalog.ALL_SKILL_DEFS[s].name}»" for s in ids)
        for cls, ids in skill_catalog.STARTER_SKILLS.items()
    )
    normal = ac.step_thresholds("normal")
    return [
        {"t": "h3", "text": "Навыки - это руны"},
        {"t": "p", "text": "Навыков у класса нет: навык - это руна-навык. У героя три слота навыков. "
                           "Вставили руну в слот - навык появился в бою, сняли - пропал. Любой навык "
                           "подходит любому классу. Урон навыка считается от основной характеристики "
                           "вашего класса, лечение и щиты - от Воли."},
        {"t": "p", "text": f"При выборе класса Хранитель выдаёт три стартовые руны: {starters}. "
                           "Это обычные руны: их можно продать или передать."},
        {"t": "p", "text": "Руны-навыки падают с мобов, в руинах и разломах, их покупают и продают на рынке. "
                           "Переставлять руны можно только в родном городе, бесплатно."},
        {"t": "h3", "text": "Мастерство и ступени"},
        {"t": "p", "text": "Лишние копии руны впитываются в мастерство: каждая немного усиливает навык. "
                           "На порогах мастерства навык получает ступени, и каждая следующая добавляется к прошлым."},
        {"t": "ul", "items": [
            f"<b>Ступень I</b> - {copies(normal[0])}: первое улучшение навыка.",
            f"<b>Ступень II</b> - {copies(normal[1])}: второе улучшение и второе гнездо огранки.",
            f"<b>Ступень III</b> - {copies(normal[2])}: развилка, одно из двух усилений на выбор. "
            "Менять выбор можно дома, бесплатно.",
            f"<b>Ступень IV</b> - {copies(normal[3])}: пробуждение, навык меняет поведение. В PvP - вполсилы.",
        ]},
        {"t": "p", "text": "Это числа для обычных и редких рун. Эпическим рунам нужно вдвое больше копий, "
                           "мифическим - вчетверо. Все ступени каждого навыка - в главе «Навыки и формулы»."},
        {"t": "h3", "text": "Огранки"},
        {"t": "p", "text": "В каждой руне-навыке есть гнездо огранки, второе открывается на ступени II. "
                           "Огранка меняет свой навык: бьёт сильнее, держит эффект дольше, не уходит на "
                           "перезарядку. Огранка встаёт только в подходящий навык: например, «Холодный счёт» - "
                           "в навык с перезарядкой от 4 ходов."},
        {"t": "h3", "text": "Пассивка подкласса"},
        {"t": "p", "text": "Подкласс даёт пассивку: она усиливает свой стиль боя, и с ней одни навыки "
                           "выгоднее других. Тёмный мистик лечит союзников сильнее, Страж крепче держит "
                           "удар. Пассивка видна в разделе «Руны» на вкладке «Герой»."},
        {"t": "h3", "text": "Испытания"},
        {"t": "p", "text": "У каждого подкласса свои испытания. За пройденное испытание в сумку приходит "
                           "руна-навык или огранка: какая - видно в разделе «Испытания»."},
        {"t": "h3", "text": "Пресеты"},
        {"t": "p", "text": "Пресет запоминает раскладку рун: навыки, огранки, руны героя и экипировки. "
                           "Переключились на пресет в родном городе - руны встали сами."},
    ]


def skills_chapter_blocks() -> list[dict]:
    """Блоки главы «Навыки и формулы» вместо навыков классов и микробаффов."""
    blocks: list[dict] = [
        {"t": "h3", "text": "Стартовые руны классов"},
        {"t": "ul", "items": [
            f"<b>{CLASS_TITLES[cls]}</b> - " + ", ".join(f"«{skill_catalog.ALL_SKILL_DEFS[s].name}»" for s in ids)
            for cls, ids in skill_catalog.STARTER_SKILLS.items()
        ]},
        {"t": "h3", "text": "Пассивки подклассов"},
    ]
    for passive in passives_config.PASSIVES.values():
        blocks.append({"t": "h4", "text": passive.title})
        blocks.append({"t": "ul", "items": list(passive.lines)})
    blocks.append({"t": "h3", "text": "Руны-навыки"})
    blocks.append({"t": "p", "text": "Навык бьёт от своих характеристик, а не от основной характеристики класса: "
                                     "«330% Силы» - каждое очко Силы даёт 3,3 урона, к этому прибавляется база "
                                     "по уровню. Полностью считается до 30 + 2 за уровень очков каждой "
                                     "характеристики, дальше - на треть. Числа ниже - для 100% мастерства, "
                                     "каждая впитанная копия поднимает проценты."})
    listed = set()
    for title, ids in GROUPS:
        blocks.append({"t": "h4", "text": title})
        for sid in ids:
            blocks.append(skill_details(sid))
            listed.add(sid)
    missing = set(skill_catalog.ALL_SKILL_DEFS) - listed
    assert not missing, f"навыки без группы: {missing}"
    facets = [r for r in rc.RUNES if r.kind == rc.SKILL]
    blocks.append({"t": "h3", "text": "Огранки"})
    blocks.append({"t": "ul", "items": [
        f"<b>{r.name}</b>: {r.text.replace('{v}', str(round(r.value * 100)) + '%')}"
        + (f" (только в {rc.SKILL_TAG_TITLES[r.tag]})" if r.tag else "")
        for r in facets
    ]})
    return blocks


def _cut(blocks: list[dict], start_text: str, end_text: str | None) -> tuple[int, int]:
    start = next(i for i, b in enumerate(blocks) if b.get("text") == start_text)
    end = len(blocks) if end_text is None else next(
        i for i, b in enumerate(blocks) if i > start and b.get("text") == end_text)
    return start, end


def main() -> None:
    hb = json.loads(OUT.read_text(encoding="utf-8"))
    for ch in hb["chapters"]:
        if ch["title"] in ("Подкласс и пресеты", "Руны-навыки и подкласс"):
            ch["title"] = "Руны-навыки и подкласс"
            blocks = ch["blocks"]
            marker = "Микробаффы и испытания" if any(b.get("text") == "Микробаффы и испытания" for b in blocks) \
                else "Навыки - это руны"
            start = next(i for i, b in enumerate(blocks) if b.get("text") == marker)
            # хвост главы - абзац про смену класса у Хранителя («Передумали?»)
            tail = [b for b in blocks[start:] if b.get("t") == "p" and "Передумали?" in b.get("text", "")]
            ch["blocks"] = blocks[:start] + runes_chapter_blocks() + tail
        if ch["title"] == "Навыки и формулы":
            blocks = ch["blocks"]
            marker = "Базовые классы" if any(b.get("text") == "Базовые классы" for b in blocks) \
                else "Стартовые руны классов"
            start = next(i for i, b in enumerate(blocks) if b.get("text") == marker)
            ch["blocks"] = blocks[:start] + skills_chapter_blocks()
    OUT.write_text(json.dumps(hb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("handbook.json пересобран")


if __name__ == "__main__":
    main()
