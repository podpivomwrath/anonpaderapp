"""Манекен на арене (2026-10-30, владелец): цель для замеров урона.

10 ходов, 99999 здоровья, в ответ не бьёт. Два вида:
  - «босс» - как рейдовый босс: статы босса 60 уровня, контроль не ложится
    (оглушение, заморозка и прочее), как на Хирурге и других;
  - «моб» - обычный моб уровня игрока в его кольце, контроль работает.
"""

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat import raid_bosses
from game.combat import session as combat_session
from game.combat.session import CombatantState
from game.world import encounters
from game.world import world_config as wc

HP = 99_999
TURNS = 10
BOSS = "boss"
MOB = "mob"
NAME = "Манекен"


def _stands_still(mob: CombatantState, session, rng) -> list:
    return []


def _zone_of_level(level: int) -> tuple[int, int]:
    for _lo, _hi, zone in wc.ZONE_TABLE:
        if zone[0] <= level <= zone[1]:
            return zone
    return wc.ZONE_TABLE[-1][2]


def build(participant_id: int, kind: str, player_level: int) -> CombatantState:
    if kind == BOSS:
        dummy = raid_bosses._boss_combatant(
            participant_id, NAME, HP, raid_bosses.SURGEON_STAT_MULT, fighter=False,
        )
        dummy.control_immune_always = True
    else:
        zone = _zone_of_level(player_level)
        hp_mult = bc.MOB_HP_MULTIPLIER * formulas.mob_ring_multiplier(*zone)
        dmg_mult = bc.MOB_DAMAGE_MULTIPLIER * formulas.mob_ring_damage_multiplier(*zone)
        stats = encounters._scale_stats_split(encounters.balanced_mob_stats(player_level), hp_mult, dmg_mult)
        dummy = combat_session.build_combatant(
            id=participant_id, side=1, kind="mob", name=NAME, level=player_level,
            stats=stats, primary_stat="str",
        )
    dummy.max_hp = dummy.current_hp = HP
    dummy.scripted_hit = _stands_still
    return dummy
