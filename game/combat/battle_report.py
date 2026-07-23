"""Сводка боя игрока для трекера классовых испытаний (патч 12).

Строится инкрементально по TickResult каждого хода (BattleTracker.update),
финализируется on_battle_finished. Бой всегда 1 игрок vs 1 моб (см.
bot/handlers/combat.py: PLAYER_ID=1, MOB_ID=2) — групповых/дуэльных
условий испытания не имеют (см. патч 12, "не делать").
"""

from dataclasses import dataclass, field

from game.combat.resolver import TickResult
from game.combat.session import ActionType

# Скилы стихий элементалиста (game/classes/elementalist.py) — многие ещё TODO:
# content и не зарегистрированы как хендлеры, прогресс по ним появится, когда
# скилы будут реализованы; трекер уже готов их подхватить.
ELEMENT_SKILLS = {
    "elementalist_fire": "fire",
    "elementalist_ice": "ice",
    "elementalist_lightning": "lightning",
}

# base_skills.json effect-типы, которые считаются "навыком-дебаффом"
DEBUFF_SKILL_EFFECTS = {"target_vuln"}


@dataclass
class BattleReport:
    won: bool = False
    turns: int = 0
    mob_level: int = 0
    start_hp_pct: float = 1.0
    hp_min_pct: float = 1.0
    total_damage_taken: int = 0
    max_hp: int = 0
    crits_dealt: int = 0
    hits_taken: int = 0
    crit_taken: bool = False
    control_landed: int = 0
    only_basic_attack: bool = True
    only_skills: bool = True
    debuff_skill_used: bool = False
    finisher_is_crit: bool = False
    finisher_skill_id: str | None = None
    consecutive_crits: bool = False
    all_elements_used: bool = False
    skill_combo_streak_count: int = 0


class BattleTracker:
    def __init__(self, player_id: int, mob_id: int, mob_level: int, max_hp: int, start_hp: int) -> None:
        self.player_id = player_id
        self.mob_id = mob_id
        start_pct = (start_hp / max_hp) if max_hp else 1.0
        self.report = BattleReport(mob_level=mob_level, max_hp=max_hp, start_hp_pct=start_pct, hp_min_pct=start_pct)
        self._last_player_crit = False
        self._elements_seen: set[str] = set()
        self._last_skill_id: str | None = None
        self._last_was_skill = False

    def update(self, result: TickResult, current_hp: int, mob_died: bool) -> None:
        r = self.report
        r.turns += 1
        if r.max_hp:
            r.hp_min_pct = min(r.hp_min_pct, max(current_hp, 0) / r.max_hp)

        action = result.actions.get(self.player_id)
        if action is not None:
            if action.type == ActionType.SKILL:
                r.only_basic_attack = False
                skill_id = action.skill_id
                if skill_id in ELEMENT_SKILLS:
                    self._elements_seen.add(ELEMENT_SKILLS[skill_id])
                    if len(self._elements_seen) == 3:
                        r.all_elements_used = True
                from game.combat.base_skills import BASE_SKILL_DEFS  # избегаем цикла импортов

                skill_def = BASE_SKILL_DEFS.get(skill_id)
                if skill_def is not None and skill_def.effect in DEBUFF_SKILL_EFFECTS:
                    r.debuff_skill_used = True
                if self._last_was_skill and self._last_skill_id is not None and self._last_skill_id != skill_id:
                    r.skill_combo_streak_count += 1
                self._last_was_skill = True
                self._last_skill_id = skill_id
            elif action.type == ActionType.ATTACK:
                r.only_skills = False
                self._last_was_skill = False
                self._last_skill_id = None

        if self.player_id in result.control_landed_by:
            r.control_landed += 1

        for hit in result.hits:
            if hit.is_dot or hit.missed:
                continue
            if hit.source_id == self.player_id and hit.target_id == self.mob_id:
                if hit.crit:
                    r.crits_dealt += 1
                    if self._last_player_crit:
                        r.consecutive_crits = True
                self._last_player_crit = hit.crit
                if mob_died:
                    r.finisher_is_crit = hit.crit
                    r.finisher_skill_id = (
                        action.skill_id if action is not None and action.type == ActionType.SKILL else None
                    )
            elif hit.target_id == self.player_id and hit.source_id == self.mob_id:
                r.hits_taken += 1
                r.total_damage_taken += hit.amount
                if hit.crit:
                    r.crit_taken = True

    def finalize(self, won: bool) -> BattleReport:
        self.report.won = won
        return self.report
