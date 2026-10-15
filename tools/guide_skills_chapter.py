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
        text += ("" if text.endswith("+") else " ") + pct(skill.effect_value)
    if skill.effect_duration:
        text += f" на {gh.turns(skill.effect_duration)}"
    return text


def formulas_part() -> str:
    t = bc.TIER_MULTIPLIERS
    tiers = [["1-15", num(t["grey"])], ["16-30", num(t["white"])], ["31-45", num(t["green"])], ["46-60", num(t["blue"])]]
    passives = []
    for cls, mult in bc.BASE_CLASS_HP_MULT.items():
        passives.append(f"<li><b>{gh.CLASS_TITLES[cls]}</b>: здоровья на {pct(mult - 1)} больше.</li>")
    for cls, bonus in bc.BASE_CLASS_CRIT_BONUS.items():
        passives.append(f"<li><b>{gh.CLASS_TITLES[cls]}</b>: шанс критического удара +{pct(bonus)}.</li>")
    ring_mid = ", ".join(
        f"{lo}-{hi} → {(lo + hi) // 2}" for lo, hi in (lv for _a, _b, lv in wc.ZONE_TABLE[1:4])
    )
    return f"""    <h3>Словарь</h3>
    <dl class="events">
      <dt>Моб</dt><dd>Любой противник, которым управляет игра (твари, боссы). «Бой с мобами» - всё, кроме боёв с игроками.</dd>
      <dt>PvP</dt><dd>Бой с другими игроками.</dd>
      <dt>Ход</dt><dd>Один круг боя: все выбирают действие, потом всё происходит одновременно.</dd>
      <dt>Перезарядка</dt><dd>Сколько ходов ждать, прежде чем применить навык снова. Видна прямо на кнопке.</dd>
      <dt>Критический удар (крит)</dt><dd>Удар в {num(bc.CRIT_MULTIPLIER)} раза сильнее обычного. Шанс зависит от Ловкости.</dd>
      <dt>Уклонение</dt><dd>Удар по тебе целиком пролетает мимо. Шанс зависит от Ловкости.</dd>
      <dt>Оглушение, заморозка</dt><dd>Цель пропускает свой ход. Воля помогает устоять.</dd>
      <dt>Уязвимость</dt><dd>Цель получает больше урона от всех. «Уязвимость 35%» - урон по ней на 35% больше.</dd>
      <dt>Ослабление</dt><dd>Цель бьёт слабее. «Ослабление 22%» - её урон на 22% меньше.</dd>
      <dt>Щит</dt><dd>Запас, который принимает урон вместо здоровья, пока не кончится.</dd>
      <dt>Лечение от урона</dt><dd>Часть урона, которую ты нанёс, возвращается тебе здоровьем. «Лечит на 20% от урона»: нанёс 100 - восстановил 20.</dd>
      <dt>Заряды</dt><dd>Эффект, который можно наложить несколько раз подряд, и каждый раз он сильнее (яд Отравителя, Метка добычи Клинка теней).</dd>
      <dt>Микробафф, пресет</dt><dd>Микробафф - небольшое постоянное усиление подкласса. Пресет - набор из нескольких микробаффов, который ты выбираешь в мини-аппе.</dd>
    </dl>
    <h3>Характеристики</h3>
    <p>Каждый уровень даёт {bc.STAT_POINTS_PER_LEVEL} очка характеристик, их раздаёшь сам. Основная характеристика класса даёт урон: Сила у воина, Ловкость у разбойника, Интеллект у мага. Вещи прибавляют к характеристикам до всех расчётов.</p>
{table(["Что", "Как считается", "Не больше"], [
    ["Здоровье", f"{bc.HP_BASE} + {bc.HP_PER_LEVEL} за каждый уровень + {bc.HP_PER_VIT} за каждое очко Выносливости + {bc.HP_PER_TIER} × множитель уровня", "-"],
    ["Урон обычной атаки", f"{bc.WEAPON_BASE_PER_TIER} × множитель уровня + основная характеристика × {num(bc.K_DMG['str'])} (у Силы и Интеллекта) или × {num(bc.K_DMG['agi'])} (у Ловкости)", "-"],
    ["Шанс критического удара", f"{num(bc.CRIT_PER_AGI * 100)}% за каждое очко Ловкости", pct(bc.CRIT_CAP)],
    ["Уклонение от обычной атаки", f"{num(bc.DODGE_PER_AGI * 100)}% за каждое очко Ловкости", f"{pct(bc.DODGE_STAT_CAP)} от Ловкости, {pct(bc.DODGE_HARD_CAP)} вместе с навыками и эффектами"],
    ["Уклонение от навыка", f"в {round(1 / bc.ABILITY_DODGE_RATIO)} раза реже, чем от обычной атаки", "-"],
    ["Снижение урона по тебе", f"{num(bc.MITIGATION_PER_VIT * 100)}% за каждое очко Выносливости", pct(bc.MITIGATION_CAP)],
    ["Шанс устоять против оглушения и заморозки", f"{num(bc.CONTROL_RESIST_PER_WIL * 100)}% за каждое очко Воли", pct(bc.CONTROL_RESIST_CAP)],
    ["Сила лечения и щитов", f"+{num(bc.SUPPORT_POWER_PER_WIL * 100)}% за каждое очко Воли", "нет"],
])}
    <p>Множитель уровня зависит от уровня персонажа:</p>
{table(["Уровни", "Множитель"], tiers, (1,))}
    <h3>Как считается удар</h3>
    <p>По порядку, каждый шаг умножает то, что получилось на прошлом шаге:</p>
    <ol>
      <li><b>Уклонение.</b> Сначала проверяется, не увернулась ли цель. Если увернулась - урона нет. От навыков уворачиваются в {round(1 / bc.ABILITY_DODGE_RATIO)} раза реже.</li>
      <li><b>Основа:</b> урон обычной атаки × процент навыка. «145% от обычной атаки» - это урон обычной атаки × 1,45.</li>
      <li><b>Критический удар</b> × {num(bc.CRIT_MULTIPLIER)}, если выпал (Теневой рывок и Казнь - всегда).</li>
      <li><b>Твои усиления:</b> Боевой клич, микробаффы, эффекты подкласса. Если ты ослаблен - урон меньше.</li>
      <li><b>Уязвимость цели</b>: урон больше на её процент.</li>
      <li><b>Защита цели</b>: снижение урона от её Выносливости, потом её оборона и защитные баффы.</li>
      <li>Прибавки от эликсиров (например, +10 урона) - в самом конце, без умножений. Удар всегда наносит хотя бы 1 урона.</li>
    </ol>
    <h3>Разница уровней с мобом</h3>
    <p>Если моб выше тебя уровнем, за каждый уровень разницы он бьёт на {pct(bc.LVL_DIFF_DMG_BONUS)} сильнее (максимум в {num(bc.LVL_DIFF_DMG_CAP)} раза), а твой урон по нему на {pct(bc.LVL_DIFF_DEF_BONUS)} меньше (но не меньше {pct(bc.LVL_DIFF_DEF_FLOOR)} от обычного). Пример: моб выше на 4 уровня - он бьёт на {pct(bc.LVL_DIFF_DMG_BONUS * 4)} сильнее, ты по нему - на {pct(bc.LVL_DIFF_DEF_BONUS * 4)} слабее. Если моб ниже тебя, ничего не меняется.</p>
    <p>Какого уровня моб: если ты в кольце своего уровня - твоего уровня (но не выше верхней границы кольца). Если зашёл в кольцо выше своего уровня - моб середины этого кольца: {ring_mid}. Враги из поручений считаются так же, но они сильнее обычных мобов того же уровня.</p>
    <h3>Оглушение и заморозка</h3>
    <p>Цель пропускает ход. Перед этим проверяется её Воля: с некоторым шансом она устоит. В бою с игроками каждое следующее оглушение подряд проходит в {num(bc.CC_RESIST_MULT_PER_HIT)} раза труднее, а после {bc.CC_MAX_HITS_BEFORE_IMMUNE} подряд следующее не пройдёт вовсе - так нельзя держать игрока в оглушении весь бой. В бою с мобами такого ограничения нет.</p>
    <h3>Бонусы класса до подкласса</h3>
    <p>Действуют с 1 по {bc.SUBCLASS_UNLOCK_MIN_LEVEL - 1} уровень. После выбора подкласса исчезают - у подклассов свои сильные стороны.</p>
    <ul>
      {"".join(passives)}
    </ul>"""


def base_classes_part() -> str:
    out = ['    <h3>Базовые классы</h3>',
           f'    <p>Эти навыки у тебя с 1 по {bc.SUBCLASS_UNLOCK_MIN_LEVEL - 1} уровень. После выбора подкласса их заменяют навыки подкласса.</p>']
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
           f'    <p>Подкласс выбирается у Хранителя на {bc.SUBCLASS_UNLOCK_MIN_LEVEL} уровне. В пресет берёшь от {bc.PRESET_MIN_BUFFS} до {bc.PRESET_MAX_BUFFS} микробаффов своего подкласса. Нажми «Микробаффы», чтобы раскрыть список.</p>']
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
    <p>Все числа здесь - ровно то, что считает бой. Непонятное слово - смотри «Словарь» ниже.</p>
{formulas_part()}
{base_classes_part()}
{subclasses_part(mechanics)}
  </section>""")


if __name__ == "__main__":
    main()
