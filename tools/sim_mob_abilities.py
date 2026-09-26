"""Вклад способности каждого моба (патч 103): бой против него со способностью и без.

Запуск:  python tools/sim_mob_abilities.py [раундов на подкласс, по умолчанию 20]

Моб своего кольца, уровень игрока = верх зоны моба (не ниже 30, чтобы был
подкласс), три подкласса: ДД, танк, хил. Бои идут через настоящий резолвер
(tools/sim_balance.py), так что способность меряется ровно такой, какой она
будет в игре.

Зачем. Общий замер показывает, что мобы стали опаснее, но не КТО именно.
Первая версия способностей так и не прошла: «Сердце пущи» с регенерацией 6%
за ход опускало победы до 33%, а мобы с замахом оказались СЛАБЕЕ, чем без
способности, - пропущенный ход замаха не окупался. Увидеть это можно было
только по каждому мобу отдельно.

Ориентир при подкрутке: против моба своего уровня - 100% побед, способность
отнимает не больше ~15% здоровья сверх прежнего (и это для IV кольца и
центра; на первом кольце - около нуля, там способности задуманы мягкими).
"""
import random
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import sim_balance as sb

from game.classes import REGISTRY
from game.combat import balance_config as bc
from game.combat import formulas, mob_abilities
from game.combat.session import build_combatant
from game.content_loader import load_bestiary
from game.world import encounters as enc

ROUNDS = int(sys.argv[1]) if len(sys.argv) > 1 else 20
SUBS = ["shadow_blade", "guardian", "dark_mystic"]


def make_mob(mob, level, with_ability: bool):
    zone = (mob.zone_min, mob.zone_max)
    hp_mult = bc.MOB_HP_MULTIPLIER * formulas.mob_ring_multiplier(*zone)
    dmg_mult = bc.MOB_DAMAGE_MULTIPLIER * formulas.mob_ring_damage_multiplier(*zone)
    mlevel = enc.mob_level_for_player(level, mob)
    stats = enc._scale_stats_split(enc.balanced_mob_stats(mlevel, mob.primary_stat), hp_mult, dmg_mult)
    c = build_combatant(id=2, side=1, kind="mob", name=mob.name, level=mlevel,
                        stats=stats, primary_stat=mob.primary_stat)
    if with_ability:
        mob_abilities.prepare(c, mob.ability)
    return c


rows = []
mobs = [m for ms in load_bestiary().values() for m in ms]
for mob in sorted(mobs, key=lambda m: (m.zone_min, m.id)):
    level = min(max(mob.zone_max, 30), bc.MAX_LEVEL)
    res = {}
    for with_ability in (False, True):
        wins = 0
        hp = 0.0
        for sub in SUBS:
            mods = sb.modifiers_for(sb.preset_variants(sub)["без баффов"])
            role = REGISTRY[sub].natural_role.value
            for i in range(ROUNDS):
                rng = random.Random(f"{mob.id}-{sub}-{i}")
                player = sb.make_fighter(1, 0, sub, level, role, mods)
                r = sb.run_tick_fight([player], [make_mob(mob, level, with_ability)], rng)
                wins += r.won
                hp += r.hp_left_share
        n = ROUNDS * len(SUBS)
        res[with_ability] = (wins / n, hp / n)
    (w0, h0), (w1, h1) = res[False], res[True]
    rows.append((h0 - h1, mob, w0, h0, w1, h1))
    print(f"{mob.zone_min:>2} {mob.name:<26} {mob.ability.title:<20} "
          f"без: {w0:4.0%}/{h0:4.0%}  с: {w1:4.0%}/{h1:4.0%}  Δздоровья {h0 - h1:+5.0%}", flush=True)

print("\nСАМЫЕ ОПАСНЫЕ СПОСОБНОСТИ (больше всего отнимают здоровья):")
for delta, mob, w0, h0, w1, h1 in sorted(rows, key=lambda r: -r[0])[:12]:
    print(f"  {delta:+5.0%}  {mob.name} ({mob.ability.title}) - победы {w1:.0%}")
