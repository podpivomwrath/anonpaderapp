"""Глава путеводителя «Навыки и формулы» - HTML-фрагмент из живых данных.

    python tools/guide_skills_chapter.py > <файл>

Числа берутся из того же, что считает бой: balance_config, контент навыков,
описания микробаффов (как tools/gen_handbook.py). Подкрутили баланс -
пересобрали главу, руками ничего не переписывать.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

logger.remove()

from game.classes.base import REGISTRY  # noqa: E402
from game.combat import balance_config as bc  # noqa: E402
from game.combat.base_skills import skills_for_class  # noqa: E402
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS  # noqa: E402
from game.economy import buff_descriptions as bd  # noqa: E402
from game.world import world_config as wc  # noqa: E402
from tools import gen_handbook as gh  # noqa: E402

E = html.escape


def num(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def pct(v: float) -> str:
    return num(round(v * 100, 3)) + "%"


def table(head: list[str], rows: list[list[str]], num_cols: tuple[int, ...] = ()) -> str:
    out = ['    <div class="scroller"><table>', "      <tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in rows:
        cells = "".join(
            f'<td class="num">{c}</td>' if i in num_cols else f"<td>{c}</td>" for i, c in enumerate(row)
        )
        out.append(f"      <tr>{cells}</tr>")
    out.append("    </table></div>")
    return "\n".join(out)


def base_effect(skill) -> str:
    if not skill.effect or skill.effect not in gh.EFFECT_TITLES:
        return "-"
    text = gh.EFFECT_TITLES[skill.effect]
    if skill.effect_value:
        text += f" {pct(skill.effect_value)}"
    if skill.effect_duration:
        text += f" на {gh.turns(skill.effect_duration)}"
    return text


def formulas_part() -> str:
    t = bc.TIER_MULTIPLIERS
    tiers = [["1-15", num(t["grey"])], ["16-30", num(t["white"])], ["31-45", num(t["green"])], ["46-60", num(t["blue"])]]
    passives = []
    for cls, mult in bc.BASE_CLASS_HP_MULT.items():
        passives.append(f"<li><b>{gh.CLASS_TITLES[cls]}</b>: +{pct(mult - 1)} к итоговому здоровью.</li>")
    for cls, bonus in bc.BASE_CLASS_CRIT_BONUS.items():
        passives.append(f"<li><b>{gh.CLASS_TITLES[cls]}</b>: +{pct(bonus)} к шансу крита.</li>")
    ring_mid = ", ".join(
        f"{lo}-{hi} → {(lo + hi) // 2}" for lo, hi in (lv for _a, _b, lv in wc.ZONE_TABLE[1:4])
    )
    return f"""    <h3>Характеристики</h3>
    <p>Каждый уровень даёт {bc.STAT_POINTS_PER_LEVEL} очка характеристик, их раздаёшь сам. Основной стат класса (Сила у воина, Ловкость у разбойника, Разум у мага) даёт урон. Вещи прибавляют к характеристикам до всех расчётов.</p>
{table(["Что", "Формула", "Потолок"], [
    ["Здоровье", f"{bc.HP_BASE} + {bc.HP_PER_LEVEL} × уровень + {bc.HP_PER_VIT} × Живучесть + {bc.HP_PER_TIER} × множитель уровня", "-"],
    ["Урон обычной атаки", f"{bc.WEAPON_BASE_PER_TIER} × множитель уровня + K × основной стат; K = {num(bc.K_DMG['str'])} (Сила, Разум), {num(bc.K_DMG['agi'])} (Ловкость)", "-"],
    ["Шанс крита", f"{num(bc.CRIT_PER_AGI * 100)}% за 1 Ловкость, крит бьёт ×{num(bc.CRIT_MULTIPLIER)}", pct(bc.CRIT_CAP)],
    ["Уклонение от атаки", f"{num(bc.DODGE_PER_AGI * 100)}% за 1 Ловкость", f"{pct(bc.DODGE_STAT_CAP)} от стата, {pct(bc.DODGE_HARD_CAP)} всего"],
    ["Уклонение от навыка", f"{pct(bc.ABILITY_DODGE_RATIO)} от уклонения от атаки", "-"],
    ["Снижение урона", f"{num(bc.MITIGATION_PER_VIT * 100)}% за 1 Живучесть", pct(bc.MITIGATION_CAP)],
    ["Сопротивление контролю", f"{num(bc.CONTROL_RESIST_PER_WIL * 100)}% за 1 Волю", pct(bc.CONTROL_RESIST_CAP)],
    ["Сила поддержки (лечение, щиты)", f"{num(bc.SUPPORT_POWER_PER_WIL * 100)}% за 1 Волю", "нет"],
])}
    <p>Множитель уровня зависит от уровня персонажа:</p>
{table(["Уровни", "Множитель"], tiers, (1,))}
    <h3>Как считается удар</h3>
    <p>По порядку, каждый шаг умножает результат предыдущего:</p>
    <ol>
      <li><b>Уклонение.</b> Цель уходит от удара целиком с шансом своего уклонения (от навыков - вчетверо реже). Дымовая завеса и бафы складываются со статом, общий потолок {pct(bc.DODGE_HARD_CAP)}.</li>
      <li><b>Основа:</b> урон обычной атаки × процент навыка. «145% от обычной атаки» - это ×1,45.</li>
      <li><b>Крит</b> ×{num(bc.CRIT_MULTIPLIER)}, если выпал (у Теневого рывка всегда).</li>
      <li><b>Свои усиления:</b> Боевой клич, бафы пресета, эффекты подклассов. Ослабление на бьющем - минус.</li>
      <li><b>Уязвимость цели</b> (Кровавая печать и т.п.): +её процент.</li>
      <li><b>Снижение урона цели</b> от Живучести, затем её блоки и защитные бафы.</li>
      <li>Фиксированные прибавки (эликсиры) - в конце, без множителей. Меньше 1 урона удар не наносит.</li>
    </ol>
    <h3>Разница уровней с тварью</h3>
    <p>Если тварь выше тебя уровнем, за каждый уровень разницы она бьёт на {pct(bc.LVL_DIFF_DMG_BONUS)} сильнее (до ×{num(bc.LVL_DIFF_DMG_CAP)}), а твой урон по ней ниже на {pct(bc.LVL_DIFF_DEF_BONUS)} (но не меньше {pct(bc.LVL_DIFF_DEF_FLOOR)}). Твари ниже тебя ничего не теряют и не получают.</p>
    <p>Уровень твари: внутри кольца - твой, но не выше потолка кольца. Зашёл в кольцо выше своего уровня - тварь <b>середины кольца</b>: {ring_mid}. Сюжетные враги считаются так же и сильнее обычных тварей того же уровня.</p>
    <h3>Контроль</h3>
    <p>Оглушение и заморозка: цель пропускает ход. Сопротивление Воли может сбросить контроль. В PvP каждый следующий контроль подряд проверяет Волю в {num(bc.CC_RESIST_MULT_PER_HIT)} раза строже, а после {bc.CC_MAX_HITS_BEFORE_IMMUNE} контролей подряд следующий не проходит вовсе. В бою с тварями контроль всегда проходит полностью, если его не сбросила Воля.</p>
    <h3>Пассивки до подкласса</h3>
    <p>Работают с 1 по {bc.SUBCLASS_UNLOCK_MIN_LEVEL - 1} уровень, с выбором подкласса исчезают - у подклассов свой баланс.</p>
    <ul>
      {"".join(passives)}
    </ul>"""


def base_classes_part() -> str:
    out = ['    <h3>Базовые классы</h3>',
           f'    <p>Навыки до {bc.SUBCLASS_UNLOCK_MIN_LEVEL} уровня. Подкласс заменяет их своими.</p>']
    for cls, title in gh.CLASS_TITLES.items():
        start = bc.STARTING_STATS[cls]
        stats = ", ".join(f"{gh.STAT_TITLES[k]} {v}" for k, v in start.items())
        out.append(f"    <h4>{title}</h4>")
        out.append(f'    <p class="levels">Стартовые характеристики: {stats}</p>')
        rows = [[E(s.name), gh.damage_line(s.multiplier), gh.turns(s.cd), base_effect(s)] for s in skills_for_class(cls)]
        out.append(table(["Навык", "Урон", "Перезарядка", "Эффект"], rows))
    return "\n".join(out)


def subclasses_part(mechanics: dict[str, str]) -> str:
    out = ['    <h3>Подклассы</h3>',
           f'    <p>Выбираются на {bc.SUBCLASS_UNLOCK_MIN_LEVEL} уровне. В пресете от {bc.PRESET_MIN_BUFFS} до {bc.PRESET_MAX_BUFFS} микробаффов из пула своего подкласса.</p>']
    for sub_id, sub in REGISTRY.items():
        out.append(f"    <h4>{E(sub.title)}</h4>")
        out.append(f'    <p class="levels">База: {gh.CLASS_TITLES[sub.base_class]} · основной стат: '
                   f'{gh.PRIMARY_TITLES[sub.primary_stat]} · роль: {gh.ROLE_TITLES[sub.natural_role.value]}</p>')
        rows = []
        for skill_id in sub.skills:
            if skill_id == "attack":
                continue
            s = SUBCLASS_SKILL_DEFS[skill_id]
            rows.append([f"<b>{E(s.name)}</b>", gh.damage_line(s.multiplier), gh.turns(s.cd),
                         E(mechanics.get(skill_id, "") or "-")])
        out.append(table(["Навык", "Урон", "Перезарядка", "Что делает"], rows))
        buffs = [b for b in gh.CONTENT.buffs.values() if b.subclass == sub_id]
        by_cat: dict[str, list] = {}
        for b in buffs:
            by_cat.setdefault(b.category, []).append(b)
        items = []
        for cat, group in sorted(by_cat.items()):
            items.append(f"      <p><b>{gh.CATEGORY_TITLES.get(cat, cat)}</b></p>\n      <ul>")
            for b in group:
                items.append(f"        <li><b>{E(b.name)}</b> - {E(bd.describe(b) or 'в разработке')}</li>")
            items.append("      </ul>")
        out.append(f'    <details class="buffs"><summary>Микробаффы ({len(buffs)})</summary>\n'
                   + "\n".join(items) + "\n    </details>")
    return "\n".join(out)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    mechanics = gh.skill_mechanics()
    print(f"""  <section class="chapter" id="skills">
    <span class="chapter-no">Глава XVI</span>
    <h2>Навыки и формулы</h2>
    <p>Все числа здесь - ровно то, что считает бой. «30%» значит, что движок берёт именно 30%.</p>
{formulas_part()}
{base_classes_part()}
{subclasses_part(mechanics)}
  </section>""")


if __name__ == "__main__":
    main()
