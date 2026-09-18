"""Симулятор рыбалки (патч 58): золото/час и опыт/час по (тир озера x уровень).

Зачем: у рыбалки нет расходника и нет суточного лимита, поэтому её доход
держится ТОЛЬКО на длительности цикла и цене за килограмм. Ошибиться в них на
глаз легко, а гасить ошибку нечем — калибруем измерением.

Якорь для сравнения посчитан из уже работающей экономики, не выдуман:
ожидание с одного броска трофеев = sum(шанс * цена) по loot_config, число
бросков на кольцо — оттуда же. Целевой коридор — FISHING_TARGET_SHARE от
фарма мобов на том же кольце.

    python tools/sim_fishing.py                # сводка по всем кольцам
    python tools/sim_fishing.py --hours 200    # длиннее прогон
    python tools/sim_fishing.py --records      # ещё и распределение градаций
"""

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.economy import fishing
from game.economy import fishing_config as fc
from game.economy import loot_config as lc
from game.world import world_config as wc

#: Сколько секунд занимает один бой с мобом целиком (исследование + бой +
#: сводка). Оценка по длительности хода и типичной длине боя — служит только
#: для перевода «золото за убийство» в «золото в час».
MOB_CYCLE_SECONDS = 75.0

def trip_seconds(lake_tier: int) -> float:
    """Дорога от озера этого тира до ближайшего города и обратно.

    Без этого симулятор считал бы садок бесконечным, а продажу мгновенной —
    и переоценивал глубокие озёра вдвое. У них рыба тяжёлая (садок забивается
    за 10-15 минут), а до города 40-50 клеток; у первого кольца наоборот:
    озёра в 6-9 клетках от своего города, и дорога почти ничего не стоит.
    Именно это, а не отдельный искусственный потолок, держит доход глубоких
    озёр в рамках.
    """
    nearest = min(
        min(max(abs(lake.x - cx), abs(lake.y - cy)) for cx, cy in wc.CITY_COORDS.values())
        for lake in fishing.all_lakes()
        if lake.tier == lake_tier
    )
    return 2 * nearest * wc.CELL_TRAVEL_SECONDS


#: Целевая доля дохода рыбалки от фарма мобов на том же кольце. Рыбалка
#: безопасна и не даёт боевого опыта — она обязана проигрывать по деньгам,
#: иначе фармить мобов станет незачем.
FISHING_TARGET_SHARE = (0.60, 0.70)


def mob_gold_per_hour(ring_tier: int) -> float:
    """Якорь: сколько золота в час даёт обычный фарм мобов на этом кольце."""
    per_roll = sum(
        chance * next(t["sell_price"] for t in _TROPHIES if t["id"] == trophy_id)
        for trophy_id, chance in lc.TROPHY_ROLL_CHANCES.items()
    )
    dist = {1: 45, 2: 32, 3: 18, 4: 7, 5: 1}[ring_tier]
    rolls = next(r for lo, hi, r in lc.ROLLS_BY_DIST if lo <= dist <= hi)
    return per_roll * rolls * (3600.0 / MOB_CYCLE_SECONDS)


def _load_trophies() -> list[dict]:
    import json

    path = Path(__file__).resolve().parent.parent / "content" / "trophies.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


_TROPHIES = _load_trophies()


class Result:
    def __init__(self) -> None:
        self.seconds = 0.0
        self.gold = 0
        self.xp = 0
        self.casts = 0
        self.empty = 0
        self.breaks = 0
        self.landed = 0
        self.junk = 0
        self.trips = 0
        self.grades: Counter = Counter()
        self.grams = 0
        #: Садок: (вид, градация) -> суммарный вес. Цена считается ОТ СТАКА,
        #: ровно как при продаже в игре. Поштучный расчёт врал: у мелкой рыбы
        #: цена экземпляра округлялась до минимума в 1 золотой почти в половине
        #: случаев, и этот минимум искусственно подпирал доход первого кольца.
        self.bag: dict[tuple[str, str], int] = {}
        self.species: Counter = Counter()
        self.heaviest: tuple[int, str] = (0, "")


def simulate(lake_tier: int, fishing_level: int, hours: float, rng: random.Random) -> Result:
    """Гоняет реальные функции game/economy/fishing.py, а не их пересказ —
    иначе симулятор калибровал бы не ту игру, в которую играют."""
    res = Result()
    horizon = hours * 3600.0
    capacity = fishing.bag_capacity_grams(fishing_level)
    trip = trip_seconds(lake_tier)
    while res.seconds < horizon:
        res.casts += 1
        res.seconds += fc.CAST_COOLDOWN_SECONDS

        wait, f_bonus = fishing.roll_bite(rng)
        res.seconds += wait + 2.0  # ожидание + сама подсечка

        if rng.random() < fc.JUNK_CHANCE:
            res.junk += 1
            # хлам/сундук: в деньгах это копейки, считаем по среднему хламу
            res.gold += 1
            continue

        fish_id = fishing.roll_fish_id(rng, lake_tier)
        grams, fraction = fishing.roll_weight(rng, fish_id, fishing_level, f_bonus)

        if rng.random() < fishing.line_break_chance(lake_tier, fishing_level, fraction):
            res.breaks += 1
            res.xp += fishing.catch_xp(fish_id, fraction, landed=False)
            continue

        grade_id, _name, _mult = fishing.grade_for(fraction)
        res.landed += 1
        res.grades[grade_id] += 1
        res.species[fish_id] += 1
        res.grams += grams
        key = (fish_id, grade_id)
        res.bag[key] = res.bag.get(key, 0) + grams
        res.xp += fishing.catch_xp(fish_id, fraction)
        if grams > res.heaviest[0]:
            res.heaviest = (grams, fish_id)

        if sum(res.bag.values()) >= capacity:
            res.gold += _sell(res.bag)
            res.bag.clear()
            res.seconds += trip
            res.trips += 1

    res.gold += _sell(res.bag)  # остаток садка на момент конца прогона
    return res


def _sell(bag: dict[tuple[str, str], int]) -> int:
    """Продажа Иргалу — тот самый гарантированный пол цены. Цена считается от
    СТАКА целиком, ровно как в игре."""
    return sum(
        round(fishing.price_of(fish_id, total, grade_id) * fc.APPRAISER_FISH_MULTIPLIER)
        for (fish_id, grade_id), total in bag.items()
    )


def hours_to_level(fishing_level: int, xp_per_hour: float) -> float:
    if xp_per_hour <= 0:
        return float("inf")
    return fishing.xp_to_next(fishing_level) / xp_per_hour


#: Уровень, на котором озеро КАЖДОГО тира обязано попадать в целевой коридор.
#: Свой на тир, а не общий: глубокое озеро по замыслу окупается мастерством.
#: Новичок на пятом кольце и должен зарабатывать мало - его туда никто не
#: звал, а запрета рыбачить там нет принципиально (решение по п.5).
CALIBRATION_LEVEL: dict[int, int] = {1: 10, 2: 25, 3: 50, 4: 75, 5: 100}


def calibrate(hours: float, seed: int) -> dict[str, float]:
    """Подбирает цену за килограмм для каждого вида так, чтобы доход на
    профильном для тира уровне попал в середину целевого коридора.

    Руками эти 18 чисел не подбираются: цена входит в доход умножением вместе
    с весом, градацией и шансом обрыва, и каждое из них зависит от тира. Здесь
    считается ОДИН масштабный коэффициент на тир — относительные цены видов
    внутри тира (они несут редкость и лор) сохраняются как заданы.
    """
    target_share = sum(FISHING_TARGET_SHARE) / 2
    scales: dict[int, float] = {}
    # Тиры считаются по возрастанию: пул тира N содержит небольшую протечку
    # вида тира N+1, поэтому к моменту его калибровки нижние уже зафиксированы.
    for lake_tier in (1, 2, 3, 4, 5):
        rng = random.Random(seed + lake_tier)
        res = simulate(lake_tier, CALIBRATION_LEVEL[lake_tier], hours, rng)
        gold_per_hour = res.gold / (res.seconds / 3600.0)
        target = mob_gold_per_hour(lake_tier) * target_share
        scales[lake_tier] = target / gold_per_hour if gold_per_hour else 1.0

    suggested: dict[str, float] = {}
    for fish_id, (lo, hi, per_kg) in fc.FISH_STATS.items():
        definition = fishing.fish_def(fish_id)
        tier = definition.tier if definition else 1
        # Безымянное (тир 6) не принадлежит ни одному озеру — масштабируем его
        # по самому дорогому тиру, иначе оно осталось бы некалиброванным.
        scale = scales.get(tier, scales[5])
        # Дробная цена за килограмм: она нигде не показывается игроку (в игре
        # видна только стоимость СТАКА), зато целочисленное округление ломало
        # заданные соотношения внутри тира - 6:5:9:4 превращалось в 3:2:4:2.
        suggested[fish_id] = max(round(per_kg * scale, 2), 0.01)
    return suggested


def print_calibration(hours: float, seed: int) -> None:
    suggested = calibrate(hours, seed)
    print("Подобранные цены за килограмм (вставить в FISH_STATS):\n")
    for fish_id, (lo, hi, per_kg) in fc.FISH_STATS.items():
        definition = fishing.fish_def(fish_id)
        name = definition.name if definition else fish_id
        arrow = "->" if suggested[fish_id] != per_kg else "  "
        print(f'    "{fish_id}":{" " * (18 - len(fish_id))}({lo}, {hi}, '
              f"{suggested[fish_id]}),  # {name}: {per_kg} {arrow} {suggested[fish_id]}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hours", type=float, default=120.0)
    parser.add_argument("--seed", type=int, default=20250918)
    parser.add_argument("--records", action="store_true")
    parser.add_argument("--calibrate", action="store_true",
                        help="подобрать цены за килограмм под целевой коридор")
    args = parser.parse_args()

    if args.calibrate:
        print_calibration(args.hours, args.seed)
        return

    levels = (1, 10, 25, 50, 100, 200)
    print(f"Прогон: {args.hours:.0f} игровых часов на каждую пару, seed={args.seed}\n")

    for lake_tier in (1, 2, 3, 4, 5):
        anchor = mob_gold_per_hour(lake_tier)
        lo, hi = FISHING_TARGET_SHARE
        print(f"=== ОЗЕРО ТИРА {lake_tier} (кольцо {lake_tier}) ===")
        print(f"    мобы дают {anchor:,.0f} зол/час -> цель для рыбалки "
              f"{anchor * lo:,.0f}-{anchor * hi:,.0f}".replace(",", " "))
        print(f"    дорога до города и обратно: {trip_seconds(lake_tier) / 60:.0f} мин")
        print(f"    {'ур.':>5} {'зол/час':>10} {'% от мобов':>11} {'опыт/час':>10} "
              f"{'обрыв':>7} {'ч. до ур.':>10} {'рыб/час':>8} {'зол/рыбу':>9} "
              f"{'ср.вес':>8}")
        for level in levels:
            rng = random.Random(args.seed + level * 7 + lake_tier)
            res = simulate(lake_tier, level, args.hours, rng)
            gph = res.gold / (res.seconds / 3600.0)
            xph = res.xp / (res.seconds / 3600.0)
            attempts = res.casts - res.empty - res.junk
            break_pct = res.breaks / attempts * 100 if attempts else 0.0
            share = gph / anchor * 100 if anchor else 0.0
            mark = "  " if lo * 100 <= share <= hi * 100 else " !"
            hours_run = res.seconds / 3600.0
            landed_ph = res.landed / hours_run
            per_fish = res.gold / res.landed if res.landed else 0.0
            avg_kg = res.grams / res.landed / 1000 if res.landed else 0.0
            print(f"    {level:>5} {gph:>10,.0f} {share:>10.0f}%{mark} {xph:>10,.0f} "
                  f"{break_pct:>6.0f}% {hours_to_level(level, xph):>10,.1f} "
                  f"{landed_ph:>8.0f} {per_fish:>9.1f} {avg_kg:>7.2f}кг"
                  .replace(",", " "))
            if args.records:
                total = sum(res.grades.values()) or 1
                dist = " ".join(
                    f"{fishing.grade_name(g)} {res.grades.get(g, 0) / total * 100:.1f}%"
                    for _t, g, _n, _m in fc.GRADES
                )
                heaviest = fishing.fish_def(res.heaviest[1])
                print(f"          {dist}")
                print(f"          рекорд: {fishing.format_kg(res.heaviest[0])} "
                      f"{heaviest.name if heaviest else ''}")
        print()


if __name__ == "__main__":
    main()
