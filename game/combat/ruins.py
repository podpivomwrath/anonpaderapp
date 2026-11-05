"""Руины культа: бой комнаты. Интерфейс этапа тот же, что у разломов и поля
(setup -> строки, after_tick -> StageTick, reward_ids); оркестрация -
bot/handlers/raid_combat.py, переход по комнатам - bot/handlers/ruins.py.

Противники - обычные мобы IV кольца уровня этажа (rift.build_mob), усиленные
множителями ruins_config. Элита и босс этажа - один усиленный моб, остальные
- свита из обычных (решение владельца: элита без свиты слишком проста).
"""

from __future__ import annotations

import random

from game import ruins as rules
from game.combat.raid_field import StageTick
from game.combat.resolver import TickResult
from game.combat.rift import build_mob
from game.combat.session import CombatSessionState
from game.economy import ruins_config as rc


class RoomStage:
    is_boss = False
    ruins = True

    def __init__(self, start_id: int, layout: dict, room: str, party: int) -> None:
        self._next_id = start_id
        self.floor = int(layout.get("floor", 1))
        self.level = rc.mob_level(self.floor)
        self.room = room
        self.party = party
        self.name, self.elite_name, self.primary, self.label = rules.mob_kind(layout)
        self.ids: list[int] = []
        self.ticks = 0
        self.is_boss = room == rules.BOSS

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _mob(self, name: str, hp: float, dmg: float):
        return build_mob(self._new_id(), name, self.level, rc.MOB_RING, hp, dmg, self.primary, self.label)

    def setup(self, session: CombatSessionState) -> list[str]:
        count = rc.mob_count(self.party)
        mobs = []
        if self.room == rules.BOSS:
            mobs.append(self._mob(f"{self.elite_name}, хозяин этажа", rc.BOSS_HP, rc.BOSS_DMG))
            count -= 1
        elif self.room == rules.ELITE:
            mobs.append(self._mob(self.elite_name, rc.ELITE_HP, rc.ELITE_DMG))
            count -= 1
        mobs += [self._mob(self.name, rc.MOB_HP, rc.MOB_DMG) for _ in range(count)]
        for mob in mobs:
            self.ids.append(mob.id)
            session.add(mob)
        return []

    @property
    def reward_ids(self) -> set[int]:
        return set(self.ids)

    def after_tick(self, session: CombatSessionState, result: TickResult, rng: random.Random) -> StageTick:
        self.ticks += 1
        return StageTick()
