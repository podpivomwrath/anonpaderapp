"""Ребаланс статов: замер на живых сборках и поиск лучшего распределения (2026-10-24).

Игроки качают один стат: остальные почти ничего не дают, а обычное PvE не
наказывает голую сборку (соло закрывают разломы, фармят на 7-10 уровней
выше). Инструмент ничего не меняет в игре - модель статов подменяется только
на время прогона (game/combat/stat_model.use).

    python tools/sim_stat_model.py live builds.json [--rounds 30]
        Живые сборки (статы + вещи + баффы пресета, выгрузка с прода) против
        мобов своего кольца: свой уровень, +5, +10 - и соло обычный разлом.
        Каждая модель статов - отдельная таблица.

    python tools/sim_stat_model.py builds builds.json [--rounds 30]
        Для каждого подкласса на 60 уровне перебор распределений очков (доля
        основного стата и куда остальное) под каждой моделью. Вещи - средние
        по живым игрокам этого подкласса. Оценка - PvE (+5 и +10) и дуэли
        против живых сборок. Итог: лучшая сборка и сколько теряет моностат.

Модели - MODELS ниже. Бои - настоящий резолвер и ИИ из tools/sim_balance.py,
так что числа - сравнение моделей между собой, а не прогноз винрейта.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sim_balance as sb
import sim_rift

from game.classes.base import REGISTRY
from game.combat import balance_config as bc
from game.combat import stat_model
from game.combat.session import Stats, build_combatant
from game.economy import rift_config as rc
from game.world import encounters
from game.world import world_config as wc

FIELD = {"str": "strength", "agi": "agility", "int": "intellect", "vit": "vitality", "wil": "will"}
KEYS = ("str", "agi", "int", "vit", "wil")

#: Разбойникам компенсация: крит и уворот уходят с Ловкости на убывающую отдачу.
ROGUE_CRIT = {"shadow_blade": 0.10, "poisoner": 0.10}
ROGUE_DODGE = {"shadow_blade": 0.05, "poisoner": 0.05}

MODELS: dict[str, stat_model.StatModel] = {
    "сейчас": stat_model.CURRENT,
    "A убыв.": stat_model.HyperModel(name="A"),
    "B +уворот от Воли": stat_model.HyperModel(name="B", dodge_stat="will"),
    "C +Сила крит/Инт эффекты": stat_model.HyperModel(
        name="C", dodge_stat="will", crit_dmg_per_str=0.004, effect_per_int=0.003,
        base_crit=ROGUE_CRIT, base_dodge=ROGUE_DODGE,
    ),
    # D: B + убывание урона основного стата (порог 30 + 2 x уровень: 130 на 50,
    # 150 на 60 - примерно столько у сборки «половина в основной» с вещами).
    "D B+урон сверх порога x0.5": stat_model.HyperModel(name="D", dodge_stat="will", primary_over=0.5),
    "D2 B+урон сверх порога x0.35": stat_model.HyperModel(name="D2", dodge_stat="will", primary_over=0.35),
    # D3: D2, но урон основного стата x1.45 - сборка «65% + Выносливость»
    # бьёт как нынешний моностат, моностат с большими вещами - почти как сейчас.
    "D3 D2+урон x1.45": stat_model.HyperModel(name="D3", dodge_stat="will", primary_over=0.35,
                                              primary_k_mult=1.45),
    "D4 D2+урон x1.3": stat_model.HyperModel(name="D4", dodge_stat="will", primary_over=0.35,
                                             primary_k_mult=1.3),
}

#: Варианты PvE: правки констант balance_config на время прогона.
PVE = {
    "сейчас": {},
    # Моб выше уровнем бьёт +12% за уровень (было 8), обычные мобы на треть
    # больнее (MOB_DAMAGE_MULTIPLIER 0.7 -> 0.93).
    "E": {"LVL_DIFF_DMG_BONUS": 0.12, "MOB_DAMAGE_MULTIPLIER": 0.93},
    # Крутая кривая разницы уровней (2026-10-24, владелец: «сложности уже на
    # +2-3»): за уровень моб бьёт больнее и держит удар лучше, свой уровень
    # не меняется. F: +15% урона и -8% входящего за уровень; G: +20% и -10%.
    "F": {"LVL_DIFF_DMG_BONUS": 0.15, "LVL_DIFF_DEF_BONUS": 0.08},
    "G": {"LVL_DIFF_DMG_BONUS": 0.20, "LVL_DIFF_DEF_BONUS": 0.10},
    # F и обычные мобы чуть больнее (свой уровень тоже стоит здоровья).
    "F+": {"LVL_DIFF_DMG_BONUS": 0.15, "LVL_DIFF_DEF_BONUS": 0.08, "MOB_DAMAGE_MULTIPLIER": 0.85},
}


def use_pve(name: str) -> None:
    for key, value in PVE_DEFAULTS.items():
        setattr(bc, key, value)
    for key, value in PVE[name].items():
        setattr(bc, key, value)


PVE_DEFAULTS = {k: getattr(bc, k) for v in PVE.values() for k in v}


# ----------------------------------------------------------------------------
# Бойцы и мобы
# ----------------------------------------------------------------------------

def fighter(cid: int, side: int, b: dict, stats: dict | None = None) -> object:
    """Боец из живой сборки: свои статы + вещи + баффы пресета."""
    own = stats or b["stats"]
    total = {k: own.get(k, 0) + b["gear"].get(k, 0) for k in KEYS}
    sub = b["subclass"]
    primary = REGISTRY[sub].primary_stat if sub else bc.PRIMARY_STAT_BY_CLASS[b["base_class"]]
    c = build_combatant(
        id=cid, side=side, kind="character", name=f"{sub or b['base_class']}#{cid}", level=b["level"],
        stats=Stats(**{FIELD[k]: v for k, v in total.items()}), primary_stat=primary,
        subclass_id=sub, buff_modifiers=dict(b["mods"]), base_class=b["base_class"],
        gear_vit=b["gear"].get("vit", 0),
    )
    c.sim_skills = sb._skills_for(sub, b["base_class"])
    c.sim_role = REGISTRY[sub].natural_role.value if sub else "dd"
    return c


def _dist_for_level(level: int) -> int:
    for dmin, _dmax, (lo, hi) in wc.ZONE_TABLE:
        if lo <= level <= hi:
            return dmin
    return wc.ZONE_TABLE[-1][0]


def mob_at(pid: int, level: int, rng: random.Random, elite: bool = False):
    """Моб кольца, где живёт этот уровень, - ровно этого уровня. Обычный
    spawn_mob берёт уровень от клетки, а здесь нужен точный разрыв с игроком."""
    keep = encounters.mob_level_at_dist
    encounters.mob_level_at_dist = lambda dist, r: level
    try:
        region = sb.REGIONS[rng.randrange(len(sb.REGIONS))]
        return encounters.spawn_mob(pid, region, level, _dist_for_level(level), rng, elite=elite).combatant
    finally:
        encounters.mob_level_at_dist = keep


def pve(b: dict, diff: int, rounds: int, rng: random.Random, stats: dict | None = None,
        elite: bool = False) -> dict:
    wins, lost, turns = 0, [], []
    level = min(b["level"] + diff, bc.MAX_LEVEL)
    for _ in range(rounds):
        p = fighter(1, 0, b, stats)
        res = sb.run_tick_fight([p], [mob_at(2, level, rng, elite=elite)], rng)
        wins += res.won
        turns.append(res.turns)
        lost.append(1.0 - res.hp_left_share if res.won else 1.0)
    return {"win": wins / rounds, "lost": statistics.fmean(lost), "turns": statistics.fmean(turns)}


def rift_solo(b: dict, rounds: int, rng: random.Random) -> float:
    keep = sim_rift._party
    sim_rift._party = lambda size, level: [fighter(1, 0, b)]
    try:
        kinds = [k for k in rc.RIFT_TYPES]
        won = sum(sim_rift.run(kinds[i % len(kinds)], 1, b["level"], rng)["won"] for i in range(rounds))
    finally:
        sim_rift._party = keep
    return won / rounds


# ----------------------------------------------------------------------------
# Режим live: живые сборки как есть
# ----------------------------------------------------------------------------

DIFFS = (0, 2, 3, 5, 10)


def live(builds: list[dict], rounds: int, models: list[str], with_rift: bool = False) -> None:
    """Разница уровней считается только у тех, кому есть куда расти: игрок
    58 ур. против «+5» дрался бы с мобом 60, то есть почти своим."""
    builds = [b for b in builds if b["subclass"]]
    for name in models:
        stat_model.use(MODELS[name])
        rng = random.Random(5)
        rows: dict = defaultdict(lambda: defaultdict(list))
        rifts = defaultdict(list)
        for b in builds:
            for d in DIFFS:
                if b["level"] + d <= bc.MAX_LEVEL:
                    rows[b["subclass"]][d].append(pve(b, d, rounds, rng))
            if with_rift:
                rifts[b["subclass"]].append(rift_solo(b, max(rounds // 3, 6), rng))
        print(f"\n=== Модель: {name}  (живые сборки 30+; побед / сколько HP теряет за бой; n - игроков в колонке)")
        print(f"{'подкласс':14}" + "".join(f"{('свой' if d == 0 else f'+{d}'):>16}" for d in DIFFS)
              + ("  разлом соло" if with_rift else ""))
        for sub, by_diff in sorted(rows.items()):
            cells = []
            for d in DIFFS:
                rs = by_diff.get(d, [])
                cells.append(
                    f"{100 * statistics.fmean(r['win'] for r in rs):3.0f}%/{100 * statistics.fmean(r['lost'] for r in rs):3.0f}% n{len(rs):<2}"
                    if rs else "-")
            line = f"{sub:14}" + "".join(f"{c:>16}" for c in cells)
            if with_rift:
                line += f"  {100 * statistics.fmean(rifts[sub]):5.0f}%"
            print(line)
    stat_model.use(stat_model.CURRENT)


# ----------------------------------------------------------------------------
# Режим content: кровавый разлом и Скупщик реликвий (2026-10-24, владелец:
# «они сейчас сделаны очень хорошо») - правка статов не должна их сдвинуть.
# ----------------------------------------------------------------------------

def respec(b: dict, share: float = 0.65) -> dict:
    """Свои очки сборки заново: share в основной стат, остальное в Выносливость
    - так игрок пересоберётся под новую модель (сброс бесплатный)."""
    sub = b["subclass"]
    start = {k.lower(): v for k, v in bc.STARTING_STATS[b["base_class"]].items()}
    points = sum(b["stats"].values()) - sum(start.values())
    prim = REGISTRY[sub].primary_stat if sub else bc.PRIMARY_STAT_BY_CLASS[b["base_class"]]
    out = dict(start)
    out[prim] += round(points * share)
    out["vit"] += points - round(points * share)
    return out


def dealer_fight(b: dict, rng: random.Random, stats: dict | None = None) -> tuple[bool, float]:
    from game.world import relic_dealer

    p = fighter(1, 0, b, stats)
    dist = _dist_for_level(b["level"])
    mob = relic_dealer.build_dealer(2, dist, rng, {1}).combatant
    res = sb.run_tick_fight([p], [mob], rng)
    return res.won, (1.0 - res.hp_left_share if res.won else 1.0)


def blood_rift(party: list[dict], rng: random.Random, respecced: bool) -> bool:
    level = min(b["level"] for b in party)
    keep_party, keep_stage = sim_rift._party, sim_rift.rift.build_stage
    orig = keep_stage
    sim_rift._party = lambda size, lvl: [
        fighter(i + 1, 0, b, respec(b) if respecced else None) for i, b in enumerate(party)
    ]
    sim_rift.rift.build_stage = lambda *a, **k: orig(*a, blood=True, **k)
    try:
        kinds = list(rc.RIFT_TYPES)
        return sim_rift.run(kinds[rng.randrange(len(kinds))], len(party), level, rng)["won"]
    finally:
        sim_rift._party, sim_rift.rift.build_stage = keep_party, keep_stage


def content(builds: list[dict], rounds: int, models: list[str]) -> None:
    builds = [b for b in builds if b["subclass"]]
    high = [b for b in builds if b["level"] >= 50]
    for name in models:
        stat_model.use(MODELS[name])
        variants = [("как есть", False)] + ([("пересобраны 65%+Вын", True)] if name != "сейчас" else [])
        for vname, re_ in variants:
            rng = random.Random(21)
            dealer = defaultdict(list)
            for b in builds:
                for _ in range(rounds):
                    dealer[b["subclass"]].append(dealer_fight(b, rng, respec(b) if re_ else None))
            parties = 0
            won = 0
            for _ in range(rounds * 4):
                party = rng.sample(high, 3)
                parties += 1
                won += blood_rift(party, rng, re_)
            print(f"\n=== Модель: {name}, сборки {vname}")
            print(f"  кровавый разлом, группа из 3 живых 50+: {100 * won / parties:.0f}% прохождений")
            print("  Скупщик соло (побед / HP-):  " + "  ".join(
                f"{sub} {100 * statistics.fmean(w for w, _ in rs):.0f}%/{100 * statistics.fmean(lo for _, lo in rs):.0f}%"
                for sub, rs in sorted(dealer.items())))
    stat_model.use(stat_model.CURRENT)


# ----------------------------------------------------------------------------
# Режим builds: перебор распределений на 60 уровне
# ----------------------------------------------------------------------------

LEVEL = 50  # +10 от него - моб 60: на 60 уровне выше некого


def _avg_gear(builds: list[dict], sub: str) -> dict:
    pool = [b for b in builds if b["subclass"] == sub and abs(b["level"] - LEVEL) <= 6] or \
           [b for b in builds if b["subclass"] == sub]
    return {k: round(statistics.fmean(b["gear"].get(k, 0) for b in pool)) for k in KEYS}


def _avg_mods(builds: list[dict], sub: str) -> dict:
    pool = [b for b in builds if b["subclass"] == sub]
    counts = defaultdict(list)
    for b in pool:
        for k, v in b["mods"].items():
            counts[k].append(v)
    # Бафф, который стоит у большинства, - в «типичный пресет».
    return {k: statistics.fmean(v) for k, v in counts.items() if len(v) * 2 >= len(pool)}


def candidate_builds(sub: str) -> dict[str, dict]:
    """Распределения на 60: стартовые статы класса + 177 очков. Доля основного
    стата и куда остальное."""
    cls = REGISTRY[sub]
    start = {k.lower(): v for k, v in bc.STARTING_STATS[cls.base_class].items()}
    prim = cls.primary_stat
    points = bc.STAT_POINTS_PER_LEVEL * (LEVEL - 1)
    others = [k for k in KEYS if k != prim]
    targets = {"vit": ["vit"], "wil": ["wil"], "vit+wil": ["vit", "wil"]}
    for k in others:
        if k not in ("vit", "wil"):
            targets[k] = [k]
    targets["всё понемногу"] = others
    out = {}
    for share in (1.0, 0.8, 0.65, 0.5, 0.35):
        for tname, keys in targets.items():
            if share == 1.0 and tname != "vit":
                continue
            s = dict(start)
            main = round(points * share)
            s[prim] += main
            rest = points - main
            for i, k in enumerate(keys):
                s[k] += rest // len(keys) + (1 if i < rest % len(keys) else 0)
            label = "моностат" if share == 1.0 else f"{round(share * 100)}% основной + {tname}"
            out[label] = s
    return out


def builds_mode(builds: list[dict], rounds: int, models: list[str]) -> None:
    subs = sorted({b["subclass"] for b in builds if b["subclass"]})
    # Соперники в дуэлях - живые сборки 55+ (их реальные распределения).
    rivals = [b for b in builds if b["subclass"] and abs(b["level"] - LEVEL) <= 6]
    for name in models:
        stat_model.use(MODELS[name])
        print(f"\n=== Модель: {name}  ({LEVEL} ур., вещи - средние по подклассу; PvE: вожак своего уровня "
              f"и моб +10; дуэли - живые сборки {LEVEL}±6)")
        for sub in subs:
            rng = random.Random(9)
            base = {"level": LEVEL, "subclass": sub, "base_class": REGISTRY[sub].base_class,
                    "gear": _avg_gear(builds, sub), "mods": _avg_mods(builds, sub)}
            scored = []
            for label, stats in candidate_builds(sub).items():
                p5 = pve(base, 0, rounds, rng, stats, elite=True)
                p10 = pve(base, 10, rounds, rng, stats)
                duel_w = duel_n = 0
                for i, rv in enumerate(rivals):
                    if rv["subclass"] == sub:
                        continue
                    for _ in range(max(rounds // 6, 3)):
                        a = fighter(1, 0, base, stats)
                        bb = fighter(2, 1, rv)
                        w = sb.run_duel(a, bb, rng)
                        duel_w += w == a.id
                        duel_n += 1
                duel = duel_w / duel_n if duel_n else 0.0
                # PvE: победа и сколько здоровья осталось; дуэли - отдельно
                pve_score = (p5["win"] * (1 - p5["lost"] / 2) + p10["win"] * (1 - p10["lost"] / 2)) / 2
                scored.append((label, pve_score, duel, p5, p10))
            best_pve = max(scored, key=lambda r: r[1])
            best_duel = max(scored, key=lambda r: r[2])
            mono = next(r for r in scored if r[0] == "моностат")
            print(f"\n  {sub}")
            for label, ps, du, p5, p10 in sorted(scored, key=lambda r: -(r[1] + r[2]))[:6]:
                print(f"    {label:34} PvE {ps:.2f} (вожак {100 * p5['win']:3.0f}% за {p5['turns']:4.1f} х., "
                      f"+10 {100 * p10['win']:3.0f}% за {p10['turns']:4.1f} х.)  дуэли {100 * du:3.0f}%")
            print(f"    моностат: PvE {mono[1]:.2f} (вожак за {mono[3]['turns']:.1f} х., +10 за {mono[4]['turns']:.1f} х.), "
                  f"дуэли {100 * mono[2]:3.0f}%  |  "
                  f"лучшее PvE: {best_pve[0]}, лучшие дуэли: {best_duel[0]}")
    stat_model.use(stat_model.CURRENT)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("live", "builds", "content"))
    ap.add_argument("builds")
    ap.add_argument("--rounds", type=int, default=30)
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--pve", default="сейчас", choices=tuple(PVE))
    ap.add_argument("--rift", action="store_true", help="live: ещё соло обычный разлом")
    args = ap.parse_args()
    data = json.loads(Path(args.builds).read_text(encoding="utf-8"))
    models = [m for m in args.models.split(",") if m in MODELS]
    use_pve(args.pve)
    print(f"PvE: {args.pve} {PVE[args.pve] or ''}")
    if args.mode == "live":
        live(data, args.rounds, models, with_rift=args.rift)
    elif args.mode == "content":
        content(data, args.rounds, models)
    else:
        builds_mode(data, args.rounds, models)


if __name__ == "__main__":
    main()
