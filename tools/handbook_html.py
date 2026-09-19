"""HTML-версия справочника: та же сборка из живых данных, но страницей.

Держим отдельно от gen_handbook.py, чтобы разметка не мешалась с текстом.

    python tools/handbook_html.py            > tools/handbook.html
    python tools/handbook_html.py --offline  > tools/handbook_local.html

--offline собирает файл, который можно просто отдать игроку: он открывается
двойным кликом и работает без интернета. Отличие одно — не подтягиваются шрифты
с Google Fonts, вместо них системные. Нужно это потому, что не у всех есть
доступ к клоду, где лежит онлайн-версия, а страницу с битыми ссылками на CDN
показывать игрокам нельзя: без сети она молча теряет всю типографику.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

logger.remove()

from game.classes.base import REGISTRY
from game.combat import balance_config as bc
from game.combat.base_skills import skills_for_class
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
from game.economy import buff_descriptions as bd
from tools.gen_handbook import (
    CATEGORY_TITLES,
    CLASS_TITLES,
    CONTENT,
    EFFECT_TITLES,
    LORE,
    PRIMARY_TITLES,
    ROLE_TITLES,
    STAT_TITLES,
    damage_line,
    skill_mechanics,
    turns,
)

E = html.escape

STYLE = """
<style>
  :root {
    --ground: #e9e6e0;
    --surface: #f4f2ee;
    --sunken: #dedad2;
    --ink: #1c1a1e;
    --ink-soft: #55505a;
    --ink-faint: #837d88;
    --rule: #c7c1b8;
    --blood: #8a2321;
    --blood-soft: #a8443f;
    --ember: #8a6a2f;
    --shadow: rgba(28, 26, 30, 0.10);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --ground: #131217;
      --surface: #1a181f;
      --sunken: #100f14;
      --ink: #e4e0e6;
      --ink-soft: #a7a1ad;
      --ink-faint: #746e7a;
      --rule: #2e2b35;
      --blood: #c4514b;
      --blood-soft: #9c3b36;
      --ember: #b99553;
      --shadow: rgba(0, 0, 0, 0.5);
    }
  }
  :root[data-theme="dark"] {
    --ground: #131217;
    --surface: #1a181f;
    --sunken: #100f14;
    --ink: #e4e0e6;
    --ink-soft: #a7a1ad;
    --ink-faint: #746e7a;
    --rule: #2e2b35;
    --blood: #c4514b;
    --blood-soft: #9c3b36;
    --ember: #b99553;
    --shadow: rgba(0, 0, 0, 0.5);
  }

  body {
    background: var(--ground);
    color: var(--ink);
    font-family: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 16px;
    line-height: 1.6;
  }
  .wrap {
    max-width: 78rem;
    margin: 0 auto;
    padding-inline: 20px;
    padding-block: 3rem 5rem;
    display: grid;
    grid-template-columns: 15rem minmax(0, 1fr);
    gap: 3rem;
    align-items: start;
  }
  h1, h2, h3 {
    font-family: "Old Standard TT", Georgia, "Times New Roman", serif;
    font-weight: 400;
    text-wrap: balance;
    margin: 0;
  }
  h1 { font-size: clamp(2rem, 5vw, 2.9rem); line-height: 1.12; letter-spacing: -0.01em; }
  h2 {
    font-size: 1.05rem; text-transform: uppercase; letter-spacing: 0.16em;
    color: var(--ink-faint); margin-block: 3.5rem 1.25rem;
    padding-bottom: 0.5rem; border-bottom: 1px solid var(--rule);
  }
  h3 { font-size: 1.7rem; letter-spacing: -0.01em; }

  .lede { color: var(--ink-soft); max-width: 42rem; margin-block: 1rem 0; }
  .stamp {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.7rem; letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--blood); margin-bottom: 0.9rem;
  }

  nav.index {
    position: sticky; top: calc(env(safe-area-inset-top, 0px) + 2rem);
    max-height: 80vh; overflow-y: auto;
    font-size: 0.87rem;
  }
  nav.index p {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.68rem; letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--ink-faint); margin: 1.5rem 0 0.5rem;
  }
  nav.index p:first-child { margin-top: 0; }
  nav.index a {
    display: block; padding: 0.28rem 0; color: var(--ink-soft);
    text-decoration: none; border-bottom: 1px solid transparent;
  }
  nav.index a:hover { color: var(--blood); }
  nav.index a:focus-visible { outline: 2px solid var(--blood); outline-offset: 2px; }

  .entry { margin-block: 2.75rem; scroll-margin-top: 2rem; }
  .meta {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.78rem; color: var(--ink-soft);
    display: flex; flex-wrap: wrap; gap: 0.35rem 1.4rem;
    margin-top: 0.7rem;
  }
  .meta b { color: var(--ink); font-weight: 600; }

  blockquote.keeper {
    margin: 1.2rem 0 0; padding: 0.9rem 0 0.9rem 1.2rem;
    border-left: 2px solid var(--blood-soft);
    color: var(--ink-soft); font-family: "Old Standard TT", Georgia, serif;
    font-size: 1.05rem; font-style: italic;
  }

  .skills { display: grid; gap: 0.9rem; margin-top: 1.6rem; }
  .skill {
    background: var(--surface); border: 1px solid var(--rule);
    padding: 1rem 1.15rem;
  }
  .skill h4 {
    margin: 0; font-size: 1.05rem; font-weight: 600;
    font-family: "IBM Plex Sans", system-ui, sans-serif;
  }
  .numbers {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-variant-numeric: tabular-nums;
    font-size: 0.78rem; color: var(--ember); margin-top: 0.25rem;
  }
  .skill .does { margin: 0.55rem 0 0; color: var(--ink); }
  .skill .flavor { margin: 0.5rem 0 0; color: var(--ink-faint); font-style: italic; font-size: 0.93rem; }

  .buffs { margin-top: 2rem; }
  .cat {
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 0.68rem; letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--ink-faint); margin: 1.6rem 0 0.6rem;
  }
  .buffs dl { margin: 0; display: grid; gap: 0.1rem; }
  .buffs dt {
    font-weight: 600; margin-top: 0.75rem;
  }
  .buffs dd { margin: 0.1rem 0 0; color: var(--ink-soft); }
  .buffs dd:first-of-type { margin-top: 0.1rem; }

  table.stats {
    width: 100%; border-collapse: collapse; margin-top: 1rem;
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-variant-numeric: tabular-nums; font-size: 0.82rem;
  }
  table.stats th, table.stats td {
    text-align: left; padding: 0.4rem 0.9rem 0.4rem 0;
    border-bottom: 1px solid var(--rule);
  }
  table.stats th { color: var(--ink-faint); font-weight: 400; }
  .scroller { overflow-x: auto; }

  footer {
    margin-top: 4rem; padding-top: 1.2rem; border-top: 1px solid var(--rule);
    color: var(--ink-faint); font-size: 0.85rem;
  }

  /* Узкий экран. Блок стоит В КОНЦЕ намеренно: медиазапрос не добавляет
     специфичности, поэтому раньше базовое nav.index{position:sticky} ниже по
     файлу перебивало его обратно — оглавление оставалось прилипшим, и текст
     уезжал под него. На телефоне страница была нечитаема. */
  @media (max-width: 900px) {
    .wrap { grid-template-columns: minmax(0, 1fr); gap: 2rem; }
    nav.index { position: static; max-height: none; overflow-y: visible; }
  }
</style>
"""


def skill_card(skill, mechanics: str | None, *, generic_effect: bool) -> str:
    bits = [damage_line(skill.multiplier), f"перезарядка {turns(skill.cd)}"]
    if generic_effect and skill.effect in EFFECT_TITLES:
        extra = EFFECT_TITLES[skill.effect]
        if skill.effect_value:
            extra += f" {round(skill.effect_value * 100)}%"
        if skill.effect_duration:
            extra += f" на {turns(skill.effect_duration)}"
        bits.append(extra)
    out = [
        '<article class="skill">',
        f"<h4>{E(skill.name)}</h4>",
        f'<p class="numbers">{E(" · ".join(bits))}</p>',
    ]
    if mechanics:
        out.append(f'<p class="does">{E(mechanics)}</p>')
    if skill.flavor:
        out.append(f'<p class="flavor">{E(skill.flavor)}</p>')
    out.append("</article>")
    return "\n".join(out)


def main(offline: bool = False) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    mech = skill_mechanics()
    o: list[str] = []
    a = o.append

    a("<title>Список Хранителя</title>")
    a('<meta charset="utf-8">')
    a('<meta name="viewport" content="width=device-width,initial-scale=1">')
    if not offline:
        a('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
        a('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
          'family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&'
          'family=Old+Standard+TT:ital@0;1&display=swap">')
    a(STYLE)
    if offline:
        # Шрифтов из сети нет — подменяем семейства системными, иначе браузер
        # свалится на дефолтный Times и страница поедет.
        a("<style>"
          ":root{--ground:#e9e6e0;--surface:#f4f2ee;color-scheme:light dark}"
          'body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}'
          'h1,h2,h3,blockquote.keeper{font-family:Georgia,"Times New Roman",serif}'
          '.numbers,.meta,.stamp,.cat,nav.index p,table.stats'
          '{font-family:ui-monospace,Consolas,"DejaVu Sans Mono",monospace}'
          "</style>")
    a('<div class="wrap">')

    # --- боковой указатель ---
    a('<nav class="index" aria-label="Содержание">')
    a("<p>Классы</p>")
    for cid, title in CLASS_TITLES.items():
        a(f'<a href="#{cid}">{E(title)}</a>')
    a("<p>Подклассы</p>")
    for sid, sub in REGISTRY.items():
        a(f'<a href="#{sid}">{E(sub.title)}</a>')
    a("</nav>")

    a("<main>")
    a('<p class="stamp">Реестр путей и умений</p>')
    a("<h1>Список Хранителя</h1>")
    a('<p class="lede">Всё, что здесь написано, движок считает именно так. '
      f'Класс выбирается на старте, подкласс - на {bc.SUBCLASS_UNLOCK_MIN_LEVEL} уровне; '
      'навыки подкласса заменяют классовые. В пресет берётся '
      f'от {bc.PRESET_MIN_BUFFS} до {bc.PRESET_MAX_BUFFS} микробаффов - любых из пула '
      'своего подкласса, ограничений по категориям нет.</p>')

    # --- базовые классы ---
    a('<h2 id="classes">Базовые классы</h2>')
    for cid, title in CLASS_TITLES.items():
        a(f'<section class="entry" id="{cid}">')
        a(f"<h3>{E(title)}</h3>")
        start = bc.STARTING_STATS[cid]
        a('<div class="meta">'
          f'<span>Основной стат: <b>{E(PRIMARY_TITLES[bc.PRIMARY_STAT_BY_CLASS[cid]])}</b></span>'
          "</div>")
        a('<div class="scroller"><table class="stats"><tr>'
          + "".join(f"<th>{E(STAT_TITLES[k])}</th>" for k in start)
          + "</tr><tr>"
          + "".join(f"<td>{v}</td>" for v in start.values())
          + "</tr></table></div>")
        a('<div class="skills">')
        for skill in skills_for_class(cid):
            a(skill_card(skill, None, generic_effect=True))
        a("</div></section>")

    # --- подклассы ---
    a('<h2 id="subclasses">Подклассы</h2>')
    for sid, sub in REGISTRY.items():
        roles = [ROLE_TITLES[sub.natural_role.value]] + [
            ROLE_TITLES[r.value] for r in sub.flexible_roles
        ]
        a(f'<section class="entry" id="{sid}">')
        a(f"<h3>{E(sub.title)}</h3>")
        a('<div class="meta">'
          f"<span>База: <b>{E(CLASS_TITLES[sub.base_class])}</b></span>"
          f"<span>Стат: <b>{E(PRIMARY_TITLES[sub.primary_stat])}</b></span>"
          f"<span>Роль: <b>{E(roles[0])}</b></span>"
          + (f"<span>Вытягивает: <b>{E(', '.join(roles[1:]))}</b></span>" if len(roles) > 1 else "")
          + "</div>")
        lore = LORE.get(sid, "").strip()
        if lore:
            a(f'<blockquote class="keeper">{E(lore)}</blockquote>')
        a('<div class="skills">')
        for skill_id in sub.skills:
            if skill_id == "attack":
                continue
            a(skill_card(SUBCLASS_SKILL_DEFS[skill_id], mech.get(skill_id), generic_effect=False))
        a("</div>")

        a('<div class="buffs">')
        by_cat: dict[str, list] = {}
        for b in (x for x in CONTENT.buffs.values() if x.subclass == sid):
            by_cat.setdefault(b.category, []).append(b)
        for cat, items in sorted(by_cat.items()):
            a(f'<p class="cat">{E(CATEGORY_TITLES.get(cat, cat))}</p>')
            a("<dl>")
            for b in items:
                a(f"<dt>{E(b.name)}</dt><dd>{E(bd.describe(b) or 'в разработке')}</dd>")
            a("</dl>")
        a("</div></section>")

    total = len(CONTENT.buffs)
    a(f"<footer>Микробаффов в реестре: {total}. "
      "Справочник собирается прямо из боевых данных, поэтому расходиться с игрой ему не с чего."
      "</footer>")
    a("</main></div>")
    print("\n".join(o))


if __name__ == "__main__":
    main(offline="--offline" in sys.argv)
