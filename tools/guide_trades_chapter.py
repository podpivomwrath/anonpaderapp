"""Глава путеводителя «Рыбалка, рудники, торговля» - HTML из живых данных.

    python tools/guide_trades_chapter.py > <файл>

Все числа - из того же, что считает игра: fishing_config, mining_config,
trade_config и контент озёр, рудников, рыбы и руды. Подкрутили баланс -
пересобрали главу, руками ничего не переписывать (как guide_skills_chapter).
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

logger.remove()

from bot.onboarding_texts import REGION_TITLES  # noqa: E402
from game.content_loader import load_fish_defs, load_lakes, load_mines  # noqa: E402
from game.economy import fishing, mining  # noqa: E402
from game.economy import fishing_config as fc  # noqa: E402
from game.economy import mining_config as mc  # noqa: E402
from game.economy import trade_config as tc  # noqa: E402
from game.world import world_config as wc  # noqa: E402

E = html.escape
RING = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}


def num(v: float) -> str:
    return f"{v:g}".replace(".", ",")


def pct(v: float) -> str:
    return num(round(v * 100, 1)) + "%"


def money(v: int) -> str:
    return f"{int(v):,}".replace(",", " ")


def kg(grams: int) -> str:
    return num(round(grams / 1000, 1)) + " кг"


def ring_levels(tier: int) -> str:
    lo, hi = wc.ZONE_TABLE[tier - 1][2]
    return "у Монолита" if tier == 5 else f"{lo}-{hi} ур."


def table(head: list[str], rows: list[list[str]], num_cols: tuple[int, ...] = ()) -> str:
    out = ['    <div class="scroller"><table>', "      <tr>" + "".join(f"<th>{h}</th>" for h in head) + "</tr>"]
    for row in rows:
        cells = "".join(
            f'<td class="num">{c}</td>' if i in num_cols else f"<td>{c}</td>" for i, c in enumerate(row)
        )
        out.append(f"      <tr>{cells}</tr>")
    out.append("    </table></div>")
    return "\n".join(out)


def p(text: str) -> str:
    return f"    <p>{text}</p>"


def ul(items: list[str]) -> str:
    return "    <ul>\n" + "\n".join(f"      <li>{i}</li>" for i in items) + "\n    </ul>"


def places_by_tier(defs) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {}
    for d in sorted(defs, key=lambda d: (d.tier, d.name)):
        out.setdefault(d.tier, []).append(f"{E(d.name)} ({d.x}; {d.y})")
    return out


def grade_chances(k: float, thresholds: list[float]) -> list[str]:
    """Шанс градации не хуже порога t при броске rng ** k: 1 - t ** (1 / k)."""
    out = []
    for i, t in enumerate(thresholds):
        upper = thresholds[i + 1] if i + 1 < len(thresholds) else 1.0
        chance = (1 - t ** (1 / k)) - (1 - upper ** (1 / k)) if upper < 1.0 else 1 - t ** (1 / k)
        out.append(pct(chance))
    return out


# --- Рыбалка ------------------------------------------------------------------


def fishing_part() -> str:
    parts = ["    <h3>Рыбалка</h3>"]
    parts.append(p(
        "На карте есть озёра - клетки с 🎣. Встань на клетку, нажми «🎣 К воде» и «🎣 Забросить». "
        "Поклёвка приходит отдельным сообщением с кнопкой «🪝 Подсечь». Пустых забросов нет: "
        "клюёт всегда, вопрос только когда."
    ))
    modes = [
        f"{pct(w)} забросов - {num(lo)}-{num(hi)} с" + (f", рыба тяжелее (+{pct(b)} к весу)" if b else "")
        for w, lo, hi, b in fc.BITE_MODES
    ]
    parts.append(ul([
        "Ожидание поклёвки: " + "; ".join(modes) + ". Долгое ожидание - к крупной рыбе.",
        f"На подсечку - {num(fc.STRIKE_WINDOW_SECONDS)} секунд. Опоздал - рыба уходит.",
        f"Между забросами - {num(fc.CAST_COOLDOWN_SECONDS)} секунд.",
        f"Озёра колец I-{RING[fc.PVP_SAFE_MAX_LAKE_TIER]} - мирные: там на рыбака не нападут игроки.",
        "Перезапуск бота рыбалку не сбивает: поклёвка придёт, а потерянная - придёт заново с полным окном.",
    ]))

    parts.append("    <h4>Озёра</h4>")
    parts.append(p(
        "Тир озера - его кольцо. Рыбачить можно где угодно, но рыба тира открывается уровнем рыбалки: "
        "на озере выше твоего уровня ловится только та рыба, до которой ты дорос, и чаще рвётся леска."
    ))
    lakes = places_by_tier(load_lakes())
    rows = []
    for tier in range(1, 6):
        rows.append([
            f"{RING[tier]} ({ring_levels(tier)})", str(fc.LAKE_REQUIRED_LEVEL[tier]),
            pct(fc.LINE_BREAK_BASE[tier]), ", ".join(lakes.get(tier, [])),
        ])
    parts.append(table(["Кольцо", "Ур. рыбалки", "Обрыв лески (база)", "Озёра"], rows, (1, 2)))

    parts.append("    <h4>Виды рыбы</h4>")
    fish = load_fish_defs()
    rows = []
    for tier in range(1, 7):
        pool = fc.LAKE_POOLS.get(tier, {})
        total = sum(pool.values()) or 1
        for f in [f for f in fish if f.tier == tier]:
            lo, hi, _price = fc.FISH_STATS[f.id]
            if f.id == fc.NAMELESS_ID:
                where = f"любое озеро, {pct(fc.NAMELESS_CHANCE)} с заброса"
            else:
                where = f"озёра {RING[tier]}: {pct(pool.get(f.id, 0) / total)} улова"
                leak = [t for t, pl in fc.LAKE_POOLS.items() if t != tier and f.id in pl]
                for t in leak:
                    share = fc.LAKE_POOLS[t][f.id] / sum(fc.LAKE_POOLS[t].values())
                    where += f"; озёра {RING[t]}: {pct(share)}"
            rows.append([f"{f.emoji} {E(f.name)}", str(tier), f"от {num(round(lo / 1000, 1))} до {kg(hi)}", where])
    parts.append(table(["Рыба", "Тир", "Вес", "Где ловится"], rows, (1,)))
    parts.append(p(
        "Цена рыбы - за килограмм, у каждого вида своя; чем выше тир, тем дороже улов в целом. "
        "Скупщик в городе берёт рыбу целиком по видам. Изредка у воды стоит 🎣 «Рыбак у воды» - "
        "он платит больше, и тем больше, чем глубже кольцо: "
        + ", ".join(f"{RING[t]} - до {pct(hi - 1)} сверху" for t, (lo, hi) in fc.BUYER_EVENT_MARKUP.items())
        + "."
    ))

    parts.append("    <h4>Вес и градация</h4>")
    parts.append(p(
        "Вес рыбы - случайный в пределах вида; уровень рыбалки сдвигает бросок к тяжёлой рыбе. "
        "От доли веса от максимума зависит градация и цена:"
    ))
    rows = []
    for i, (t, _gid, name, mult) in enumerate(fc.GRADES):
        nxt = fc.GRADES[i + 1][0] if i + 1 < len(fc.GRADES) else 1.0
        emoji = fc.GRADE_EMOJI[_gid]
        rows.append([f"{emoji} {name}".strip(), f"от {pct(t)} до {pct(nxt)}", f"×{num(mult)}"])
    parts.append(table(["Градация", "Вес от максимума", "К цене"], rows, (2,)))
    thresholds = [g[0] for g in fc.GRADES]
    rows = []
    for level in (1, 25, 50, 100, 200):
        rows.append([str(level)] + grade_chances(fishing.weight_k(level), thresholds))
    parts.append(p("Шанс градации на заброс (без бонуса долгой поклёвки):"))
    parts.append(table(["Ур. рыбалки"] + [g[2] for g in fc.GRADES], rows, tuple(range(6))))

    parts.append("    <h4>Обрыв лески</h4>")
    parts.append(p(
        f"Обрыв = база озера - навык + {pct(fc.LINE_BREAK_BY_WEIGHT)} × доля веса; "
        f"от {pct(fc.LINE_BREAK_MIN)} до {pct(fc.LINE_BREAK_MAX)}. Навык растёт с уровнем и упирается в "
        f"{pct(fc.LINE_BREAK_REDUCTION_MAX)}: на 50 уровне - {pct(fishing.line_break_reduction(50))}, "
        f"на 100 - {pct(fishing.line_break_reduction(100))}. Чем тяжелее рыба, тем чаще рвёт. "
        f"Сорвавшаяся рыба даёт {pct(fc.FISHING_XP_ON_BREAK)} опыта."
    ))

    parts.append("    <h4>Уровень рыбалки и садок</h4>")
    parts.append(p(
        "Опыт за пойманную рыбу: " + ", ".join(f"тир {t} - {x}" for t, x in fc.FISHING_TIER_XP.items())
        + f", и до ×{num(1 + fc.FISHING_XP_WEIGHT_BONUS)} за вес. Уровень без потолка, каждый следующий дороже."
    ))
    rows = []
    total = 0
    marks = {1, 10, 25, 50, 80, 100, 150}
    for level in range(1, 151):
        if level in marks:
            rows.append([str(level), money(fishing.xp_to_next(level)), money(total),
                         kg(fishing.bag_capacity_grams(level))])
        total += fishing.xp_to_next(level)
    parts.append(table(["Уровень", "Опыта до следующего", "Всего опыта с 1-го", "Садок"], rows, (0, 1, 2)))
    parts.append(p("Садок полон - заброс не завершится, пока не продашь улов. Последняя рыба влезает целиком, если в садке было хоть немного места."))

    parts.append("    <h4>Хлам и находки</h4>")
    junk = ", ".join(f"{e} {n}" for e, n, _g in fc.JUNK_ITEMS.values())
    parts.append(p(
        f"{pct(fc.JUNK_CHANCE)} забросов вытаскивают не рыбу. Чаще это хлам ({junk}) - его сразу покупают за "
        f"пару монет. Иногда - 📦 отсыревший ящик ({pct(fc.JUNK_CHEST_CHANCE)} находок) с трофеями, в нём "
        f"бывает снаряжение ({pct(fc.JUNK_ITEM_CHANCE)}) или 🗝 Ключ Монолита ({pct(fc.JUNK_RAID_KEY_CHANCE)})."
    ))
    return "\n".join(parts)


# --- Рудники ------------------------------------------------------------------


def mining_part() -> str:
    parts = ["    <h3>Рудники</h3>"]
    parts.append(p(
        "Рудники - клетки с ⛏. Встань на клетку, нажми «⛏ В выработку», затем «⛏ Добыть». Пока идёт добыча, "
        "другими делами не займёшься; «Бросить кирку» отменяет её, и кусок возвращается в жилу."
    ))
    parts.append(ul([
        f"Руда в руднике не бесконечна: в жиле до {mc.MINE_ORE_CAP} кусков. Её наполняют исследования всех "
        f"игроков - каждое с шансом {pct(mc.ORE_SPAWN_CHANCE_PER_EXPLORATION)} кладёт кусок в случайный рудник.",
        f"Один кусок в своём руднике копается {num(mc.STATIC_MINE_SECONDS[0] / 60)}-"
        f"{num(mc.STATIC_MINE_SECONDS[1] / 60)} минут. Время куска не меняется, если выйти и сесть заново, - "
        "новое выпадет только после добытого куска.",
        f"Жила из события исследования копается быстрее (кнопка «⛏ Копать жилу»), {num(mc.EVENT_VEIN_SECONDS[0] / 60)}-"
        f"{num(mc.EVENT_VEIN_SECONDS[1] / 60)} минут, но руда в ней беднее и исчезает, если уйти.",
        f"Рудники колец I-{RING[mc.PVP_SAFE_MAX_MINE_TIER]} - мирные: там на горняка не нападут игроки.",
        "Перезапуск бота добычу не сбивает: руда придёт в срок.",
    ]))

    parts.append("    <h4>Руда</h4>")
    ores = mining.ore_defs_ordered()
    rows = []
    for o in ores:
        if o.id == mc.LIVING_STONE_ID:
            where = f"в любом руднике, {pct(mc.LIVING_STONE_CHANCE)} с куска"
        else:
            spots = []
            for tier, pool in mc.MINE_POOLS.items():
                if o.id in pool:
                    spots.append(f"{RING[tier]}: {pct(pool[o.id] / sum(pool.values()))}")
            where = "рудники " + ", ".join(spots)
        rows.append([f"{o.emoji} {E(o.name)}", str(o.tier), where])
    parts.append(table(["Руда", "Тир", "Где добывается"], rows, (1,)))

    parts.append("    <h4>Рудники по кольцам</h4>")
    mines = places_by_tier(load_mines())
    rows = []
    for tier in range(1, 6):
        mult = [mining.time_multiplier(tier, lvl) for lvl in (1, mc.MINE_REQUIRED_LEVEL[tier], 100)]
        rows.append([
            f"{RING[tier]} ({ring_levels(tier)})", str(mc.MINE_REQUIRED_LEVEL[tier]),
            " / ".join("×" + num(round(m, 2)) for m in mult), ", ".join(mines.get(tier, [])),
        ])
    parts.append(table(
        ["Кольцо", "Ур. горного дела", "Время куска: ур. 1 / свой / 100", "Рудники"], rows, (1,),
    ))
    parts.append(p(
        f"Рудник выше твоего уровня не закрыт, но каждый недостающий уровень - +{pct(mc.TIME_PENALTY_PER_LEVEL)} "
        f"ко времени (до ×{num(mc.TIME_PENALTY_MAX)}); переросший рудник копается быстрее, до ×{num(mc.TIME_PENALTY_MIN)}. "
        "И руда тира выше твоего уровня не выпадает - вместо неё будет та, до которой ты дорос."
    ))

    parts.append("    <h4>Градация руды</h4>")
    parts.append(p(
        "Градация разыгрывается в момент добычи. Чем глубже рудник и выше уровень горного дела, тем чаще "
        "хорошая руда. Шанс на кусок:"
    ))
    thresholds = [g[0] for g in mc.GRADES]
    rows = []
    for tier in (1, 3, 5):
        for level in (1, 50, 100):
            rows.append([f"{RING[tier]}, ур. {level}"] + grade_chances(mining.grade_k(tier, level), thresholds))
    head = ["Рудник, уровень"] + [f"{mc.GRADE_EMOJI[g[1]] or ''} {g[2]}".strip() for g in mc.GRADES]
    parts.append(table(head, rows, tuple(range(1, 5))))

    parts.append("    <h4>Уровень горного дела</h4>")
    parts.append(p(
        "Опыт за кусок: " + ", ".join(f"тир {t} - {x}" for t, x in mc.MINING_TIER_XP.items())
        + "; градация умножает: " + ", ".join(f"{n} ×{num(mc.MINING_GRADE_XP_MULT[g])}" for _t, g, n in mc.GRADES) + "."
    ))
    rows = []
    total = 0
    for level in range(1, 151):
        if level in {1, 10, 25, 50, 80, 100, 150}:
            rows.append([str(level), money(mining.xp_to_next(level)), money(total)])
        total += mining.xp_to_next(level)
    parts.append(table(["Уровень", "Опыта до следующего", "Всего опыта с 1-го"], rows, (0, 1, 2)))

    parts.append("    <h4>Куда идёт руда</h4>")
    parts.append(ul([
        "Мастерская: ковка вещей с рейд-боссов (руда тиров 1-3) и инструменты для улучшения (тиры 1-5) - глава XIV.",
        "Улучшения торговой повозки.",
        "Гильдия: знамёна, стройка, подъём баз, призыв Стража - её сдают на склад гильдии.",
        "Скупщик руду не берёт: она нужна в деле, а не на продажу.",
    ]))
    return "\n".join(parts)


# --- Торговля ------------------------------------------------------------------


def trade_part() -> str:
    from game.economy import faction_config as fc

    parts = ["    <h3>Торговля</h3>", f'    <p class="levels">с {tc.TRADE_MIN_LEVEL} уровня</p>']
    parts.append(p(
        f"Торговая фирма стоит {money(tc.FIRM_PRICE)} золота, у неё уникальное название. Всё управление - в "
        "мини-аппе, вкладка «Фракция». Персонаж никуда не едет: повозки ездят сами, а ты в это время "
        "занимаешься чем хочешь. Каждую повозку отправляешь сам, на одно плечо: закупаешь товар города, где "
        "она стоит, выбираешь город и путь - по прибытии она продаёт весь груз по цене на месте и ждёт там."
    ))
    parts.append(p(
        f"В фирме до {tc.MAX_CARTS} повозок. "
        + "; ".join(f"повозка №{slot} - с {lvl} уровня торговли за {money(gold)} золота"
                    for slot, (lvl, gold) in tc.CART_SLOTS.items())
        + "."
    ))

    parts.append("    <h4>Товары и цены</h4>")
    rows = []
    for g in tc.GOODS:
        base = tc.TIER_BASE_PRICE[g.tier]
        rows.append([
            f"{g.emoji} {E(g.name)}", E(REGION_TITLES.get(g.city, g.city)), tc.TIER_NAMES[g.tier],
            str(tc.TIER_MIN_TRADE_LEVEL[g.tier]), money(round(base * tc.BUY_MULT)),
            money(round(base * tc.SELL_MULT_DEFICIT)), money(round(base * tc.SELL_MULT_FAR)),
        ])
    parts.append(table(
        ["Товар", "Где делают", "Сорт", "Ур. торговли", "Купить", "У соседа", "Напротив"], rows, (3, 4, 5, 6),
    ))
    parts.append(p(
        f"Цены за ящик. Город-производитель продаёт за {pct(tc.BUY_MULT)} базы. Соседний город (у него "
        f"нехватка) платит {pct(tc.SELL_MULT_DEFICIT)}, город напротив - {pct(tc.SELL_MULT_FAR)}: путь туда "
        "вдвое длиннее. Свой товар город не покупает."
    ))
    parts.append(ul([
        f"Рынок насыщается: каждый ящик сбивает цену продажи на {pct(tc.SATURATION_PER_CRATE)} и поднимает "
        f"цену закупки на столько же; за час рынок отходит на {pct(tc.RECOVERY_PER_HOUR)}. Цена не падает ниже "
        f"{pct(1 - tc.MAX_PRESSURE)} и не растёт выше {pct(1 + tc.MAX_PRESSURE)}. Чередуй товары и города.",
        "Опыт торговли - за каждый проданный ящик: "
        + ", ".join(f"{tc.TIER_NAMES[t]} - {x}" for t, x in tc.XP_PER_CRATE.items())
        + f". До следующего уровня нужно 60 + 40 × текущий уровень. Каждый уровень - "
        f"+{pct(tc.SELL_BONUS_PER_LEVEL)} к выручке, до +{pct(tc.SELL_BONUS_MAX)}.",
        "С каждого проданного ящика - шанс на 🗃️ Пепельный ларец: "
        + ", ".join(f"{tc.TIER_NAMES[t]} {pct(c)}" for t, c in tc.CHEST_CHANCE_PER_CRATE.items()) + ".",
    ]))

    parts.append("    <h4>Повозка</h4>")
    rows = []
    for part in tc.PARTS:
        rows.append([f"{part.emoji} {E(part.name)}", " → ".join(num(v) for v in part.values), E(part.unit)])
    parts.append(table(["Часть", "По уровням", "Что это"], rows))
    ores = {o.id: o for o in mining.ore_defs_ordered()}
    parts.append(p(
        "Подъём части на уровень: "
        + "; ".join(
            f"{i + 2} - {money(g)} золота и {n} {ores[o].emoji} {E(ores[o].name)}"
            for i, (g, o, n) in enumerate(tc.UPGRADE_COST)
        )
        + f". Ремонт обшивки - {money(tc.REPAIR_PER_POINT)} золота за единицу прочности."
    ))

    parts.append("    <h4>Пути и риски</h4>")
    parts.append(ul([
        "Короткий путь - напрямик: быстрее, но ближе к центру мира нападают чаще. Через Монолит к городу "
        "напротив - больше половины рейсов с нападением.",
        f"Безопасный путь - вдоль края мира: нападений мало, но едешь в {num(tc.SAFE_ROUTE_TIME_MULT)} раза дольше.",
        "Охрана снижает шанс нападения до ×" + num(tc.PARTS_BY_ID["guard"].values[-1]) + ". Боя нет: каждое "
        f"нападение снимает единицу обшивки, выбитая обшивка - рассыпается {pct(tc.LOSS_ON_BREAK)} груза. "
        "С выбитой обшивкой повозку не отправить - сначала ремонт.",
    ]))

    parts.append("    <h4>Процветание городов</h4>")
    parts.append(p(
        "Каждый проданный ящик приносит очки процветания РОДНОМУ городу торговца, куда бы он ни возил: "
        + ", ".join(f"{tc.TIER_NAMES[t]} - {x}" for t, x in fc.POINTS_PER_CRATE.items())
        + f". Один торговец даёт не больше {fc.DAILY_CAP_BASE} очков в сутки, +{fc.DAILY_CAP_PER_10_LEVELS} "
        f"за каждые 10 уровней торговли. Процветание само падает на {pct(fc.DECAY_PER_DAY)} в сутки."
    ))
    rows = [
        [f"{t.emoji} {E(t.name)}", money(t.min_points), f"{round((t.elixir_mult - 1) * 100):+d}%",
         f"{round((t.relic_mult - 1) * 100):+d}%"]
        for t in fc.TIERS
    ]
    parts.append(table(["Ступень", "От очков", "Зелья в лавке", "Реликвии у скупщика"], rows, (1,)))
    parts.append(p("Скидки и надбавки действуют для всех, кто торгует в этом городе."))

    parts.append("    <h4>Срочные заказы</h4>")
    parts.append(p(
        f"Время от времени город просит {tc.ORDER_CRATES[0]}-{tc.ORDER_CRATES[1]} ящиков одного товара "
        f"на {tc.ORDER_HOURS} часа: платит на {pct(tc.ORDER_PRICE_MULT - 1)} дороже и даёт вдвое больше "
        f"процветания. Заказов разом не больше {tc.ORDER_MAX_ACTIVE}. Заказ общий: каждый довезённый ящик "
        "оплачивается по цене заказа, пока он не закрыт. Закрыли, пока повозка в пути, - груз уйдёт по обычной "
        "цене. О новых заказах можно получать сообщения - галочка во вкладке."
    ))

    parts.append("    <h4>События в пути</h4>")
    parts.append(p(
        f"Примерно в {pct(tc.TRIP_EVENT_CHANCE)} рейсов что-то случается: "
        + "; ".join(e.text.rstrip(".").lower() for e in tc.TRIP_EVENTS)
        + ". На безопасном пути плохое случается вдвое реже."
    ))

    parts.append("    <h4>Итоги недели</h4>")
    places = {1: "первый", 2: "второй", 3: "третий"}
    names = {"ashen": "Пепельный ларец", "ore": "Ларец руды", "supply": "Ларец расходников"}
    parts.append(p(
        "Каждый понедельник по Москве подводятся итоги недели каждой фракции - по очкам торговли без дневного "
        "потолка. Награда: "
        + "; ".join(
            f"{places[pl]} - " + ", ".join(f"{names[k]} ×{n}" for k, n in r.items())
            for pl, r in tc.WEEK_REWARDS.items()
        )
        + ". Первый поставщик всю следующую неделю получает долю налога с переводов (ниже)."
    ))

    parts.append("    <h4>Налог на переводы</h4>")
    parts.append(p(
        f"Золото и самоцветы передают от {fc.TRANSFER_MIN}. С каждого перевода {pct(fc.TRANSFER_TAX_PCT / 100)} "
        "(с округлением вниз) уходит в казну фракции получателя - получатель получает остаток. "
        f"{pct(fc.LEADER_SHARE_PCT / 100)} этого налога копится первому поставщику фракции и приходит ему раз в "
        "сутки. Налог гильдии с переводов не берётся."
    ))
    return "\n".join(parts)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print('  <section class="chapter" id="crafts">')
    print('    <span class="chapter-no">Глава IX</span>')
    print("    <h2>Рыбалка, рудники, торговля</h2>")
    print(fishing_part())
    print(mining_part())
    print(trade_part())
    print("  </section>")


if __name__ == "__main__":
    main()
