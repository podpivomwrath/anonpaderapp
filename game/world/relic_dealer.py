"""Пепельный меняла (2026-10-17, решение владельца): событие исследования,
соло и групповое. Бродячий скупщик берёт реликвии на 25% дороже скупщика
в городе - одна сделка: всё разом или одна градация, как у Иргала. С шансом
5% это ловушка: меняла нападает, и сделки нет.

Меняла - не обычный моб: сильнее вожака, слабее босса. Его способность
«Голод на реликвии»: каждый удар, прошедший по продавцу, срывает долю
выставленной партии, и с каждой кражей меняла бьёт сильнее. Победил -
реликвии при тебе (продать их теперь - другому меняле или в городе) и
награда за бой. Пал - украденное меняла уносит.

В группе с ним приходят «Скупленные тени» - слабые подручные, по одной на
каждого участника сверх первого.

Чистая логика без БД: числа, сборка противников, доля украденного.
Запись - services/relic_dealer_service.py, показ - bot/handlers/*.
"""

import random

from game.combat import balance_config as bc
from game.combat import formulas, mob_abilities
from game.combat.session import build_combatant
from game.content_loader import MobAbilityDef, MobTraitDef
from game.world import encounters, grid

#: Надбавка к цене скупщика (со всеми множителями игрока).
PRICE_BONUS = 0.25
#: Шанс, что меняла нападает вместо сделки.
ATTACK_CHANCE = 0.05

#: Сила менялы: вожак события - x1.8 HP, x1.3 урона; босс разлома - x3.5, x2.4.
DEALER_HP_MULT = 2.2
DEALER_DMG_MULT = 1.3
#: В группе его здоровье растёт на эту долю за каждого участника сверх первого.
DEALER_GROUP_HP_PER_MEMBER = 0.4
#: Подручные: слабее обычного моба клетки.
SHADE_HP_MULT = 0.7
SHADE_DMG_MULT = 0.8

#: «Голод на реликвии»: доля партии за каждый прошедший удар, потолок,
#: прибавка к урону менялы за каждую кражу.
STEAL_PER_HIT = 0.10
STEAL_CAP = 0.50
RAGE_PER_STEAL = 0.04

#: Награда за победу над менялой (2026-10-17, решение владельца): опыт как
#: за WIN_MOBS обычных мобов клетки и столько же бросков добычи, как с
#: WIN_MOBS убитых мобов (трофеи, вещь, зелье - каждый бросок сам по себе).
#: Босс разлома даёт 10 мобов; нападение случается в 5% сделок, и победа
#: должна быть событием. За саму сделку опыта нет.
WIN_MOBS = 20


def win_result():
    """Опыт победы (добычу бросает relic_dealer_service.grant_win_loot)."""
    from game.world.scene_events import SceneResult

    return SceneResult(xp=float(WIN_MOBS))

DEALER_NAME = "Пепельный меняла"
DEALER_FLAVOR = (
    "Под капюшоном нет лица - только реликвии, сросшиеся в подобие тела. "
    "Он и есть товар, и ему всегда мало."
)
SHADE_NAME = "Скупленная тень"
SHADE_FLAVOR = "Тень того, кто продал меняле всё, что имел. Теперь служит ему."

ABILITY = MobAbilityDef(
    title="Голод на реликвии",
    hint=(
        f"каждый удар срывает {round(STEAL_PER_HIT * 100)}% выставленных реликвий "
        f"(до {round(STEAL_CAP * 100)}%), и с каждой кражей он бьёт сильнее"
    ),
    traits=[MobTraitDef(kind="relic_hunger", value=STEAL_PER_HIT, cap=STEAL_CAP, step=RAGE_PER_STEAL)],
)


def max_steals() -> int:
    return round(STEAL_CAP / STEAL_PER_HIT)


def stolen_share(steals: int) -> float:
    return min(steals * STEAL_PER_HIT, STEAL_CAP)


def stolen_from(lot: dict[str, int], steals: int) -> dict[str, int]:
    """Что уносит меняла из партии lot после steals краж (с округлением вниз,
    но хотя бы по одной штуке каждой градации, если кража была)."""
    share = stolen_share(steals)
    if share <= 0:
        return {}
    out = {}
    for trophy_id, count in lot.items():
        taken = min(count, max(1, int(count * share)))
        if taken > 0:
            out[trophy_id] = taken
    return out


def _mob(participant_id: int, name: str, dist: int, rng: random.Random, hp_k: float, dmg_k: float,
         primary: str) -> "encounters.CombatantState":
    zone = grid.zone_level_range(dist)
    level = encounters.mob_level_at_dist(dist, rng)
    hp = bc.MOB_HP_MULTIPLIER * formulas.mob_ring_multiplier(*zone) * hp_k
    dmg = bc.MOB_DAMAGE_MULTIPLIER * formulas.mob_ring_damage_multiplier(*zone) * dmg_k
    stats = encounters._scale_stats_split(encounters.balanced_mob_stats(level, primary), hp, dmg)
    return build_combatant(id=participant_id, side=1, kind="mob", name=name, level=level,
                           stats=stats, primary_stat=primary)


def build_dealer(participant_id: int, dist: int, rng: random.Random, sellers: set[int],
                 members: int = 1) -> encounters.Encounter:
    """sellers - id персонажей, выставивших реликвии: только у них есть что
    срывать (у остальных удар - просто удар)."""
    hp_k = DEALER_HP_MULT * (1 + DEALER_GROUP_HP_PER_MEMBER * max(0, members - 1))
    mob = _mob(participant_id, DEALER_NAME, dist, rng, hp_k, DEALER_DMG_MULT, "agi")
    mob_abilities.prepare(mob, ABILITY)
    mob.mob_brain.relic_sellers = set(sellers)
    return encounters.Encounter(
        combatant=mob, flavor=DEALER_FLAVOR, ability_line=encounters.ability_line(ABILITY),
    )


def build_shades(start_id: int, dist: int, rng: random.Random, count: int) -> list[encounters.Encounter]:
    return [
        encounters.Encounter(
            combatant=_mob(start_id + i, SHADE_NAME, dist, rng, SHADE_HP_MULT, SHADE_DMG_MULT, "str"),
            flavor=SHADE_FLAVOR,
        )
        for i in range(max(0, count))
    ]


def steals_of(dealer, character_id: int) -> int:
    """Сколько раз меняла сорвал реликвии с этого персонажа за бой."""
    brain = getattr(dealer, "mob_brain", None)
    return (getattr(brain, "relic_steals", None) or {}).get(character_id, 0)
