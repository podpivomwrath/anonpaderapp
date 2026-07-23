"""Наложение контроля (оглушение/заморозка).

Резист Воли (WIL) работает В ОБОИХ режимах. Защита от чейн-контроля (DR) —
ТОЛЬКО в PvP (control-patch-6): против мобов игрок может контролить каждый ход.

Стрик (control-patch-8) считает подряд идущие ходы, ПРОПУЩЕННЫЕ из-за контроля
(а не число наложений). Долгая заморозка накручивает стрик каждым пропущенным
ходом — так игрока нельзя удержать ни цепочкой коротких, ни одним длинным
эффектом в обход DR. Стрик обновляется в конце хода (tick_control) по факту
пропуска; try_apply_control решает урезание/иммунитет по «будущему» стрику
(текущий + 1 за пропуск, который вызовет это наложение).

Пороги (PvP): стрик 3 → длительность −50%; стрик 4 → иммунитет на 2 хода.

FREEZE потребляется в тот же ход (см. resolver): контроль срабатывает немедленно.
"""

import random
from dataclasses import dataclass

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.session import CombatantState, EffectKind


@dataclass
class ControlResult:
    applied: bool
    immune: bool = False       # заблокировано иммунитетом DR (только PvP)
    resisted: bool = False     # отбито резистом WIL (оба режима)
    reduced: bool = False      # длительность урезана DR (только PvP)
    immunity_granted: bool = False  # выдан иммунитет после серии (только PvP)


def try_apply_control(
    target: CombatantState,
    base_duration: int,
    source_id: int,
    rng: random.Random,
    pvp: bool,
) -> ControlResult:
    # DR-иммунитет проверяется только в PvP
    if pvp and target.control_immune_turns > 0:
        return ControlResult(applied=False, immune=True)

    # Резист Воли — в обоих режимах
    if rng.random() < formulas.control_resist(target.stats.will):
        return ControlResult(applied=False, resisted=True)

    # PvE: контроль всегда проходит полной длительностью, DR не трогаем
    if not pvp:
        target.apply_effect(EffectKind.FREEZE, 1.0, base_duration, source_id)
        return ControlResult(applied=True)

    # PvP: DR по «будущему» стрику — этот контроль вызовет пропуск в текущем ходу,
    # который станет (control_streak + 1)-м подряд пропущенным.
    prospective = target.control_streak + 1
    duration = base_duration
    reduced = False
    if prospective >= bc.CC_STREAK_REDUCE_AT:
        duration = max(1, round(base_duration * bc.CC_STREAK_REDUCE_FACTOR))
        reduced = True

    target.apply_effect(EffectKind.FREEZE, 1.0, duration, source_id)

    immunity_granted = False
    if prospective >= bc.CC_IMMUNITY_AT:
        # +1 компенсирует немедленный декремент в конце этого же хода (tick_control),
        # чтобы иммунитет накрыл CC_IMMUNITY_DURATION следующих ходов
        target.control_immune_turns = bc.CC_IMMUNITY_DURATION + 1
        immunity_granted = True

    return ControlResult(applied=True, reduced=reduced, immunity_granted=immunity_granted)


def tick_control(combatant: CombatantState, pvp: bool) -> None:
    """Конец хода: стрик += 1 если ход пропущен из-за контроля, иначе сброс в 0;
    декремент иммунитета. В PvE DR не работает — стрик/иммунитет не трогаем."""
    if pvp:
        if combatant.skipped_by_control_this_turn:
            combatant.control_streak += 1
        else:
            combatant.control_streak = 0
        if combatant.control_immune_turns > 0:
            combatant.control_immune_turns -= 1
    combatant.skipped_by_control_this_turn = False
