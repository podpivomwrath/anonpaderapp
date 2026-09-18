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
    duration_bonus: int = 0,
    chance_bonus: float = 0.0,
) -> ControlResult:
    """duration_bonus/chance_bonus (патч 47) — микробаффы «Оцепенение»/«Глубокая
    заморозка» Элементалиста; 0 для всех остальных источников контроля."""
    # Ясность крови (патч 16) — иммунитет от эликсира, работает в ОБОИХ режимах,
    # проверяется раньше DR/резиста: профилактика, а не спасение от уже
    # наложенного контроля.
    if target.has_effect(EffectKind.CONTROL_IMMUNE):
        return ControlResult(applied=False, immune=True)

    # DR-иммунитет проверяется только в PvP
    if pvp and target.control_immune_turns > 0:
        return ControlResult(applied=False, immune=True)

    # Эскалация: третий контроль подряд не проходит вообще.
    if pvp and target.control_hits >= bc.CC_MAX_HITS_BEFORE_IMMUNE:
        return ControlResult(applied=False, immune=True)

    # Против ИГРОКОВ контроль не удлиняется: два пропущенных хода подряд - это
    # уже половина размена, а защита от чейн-контроля считает подряд идущие
    # пропуски и на двух ходах не срабатывает. Прибавка длительности остаётся
    # только в PvE, где она ни у кого не отнимает ход в размене.
    if not pvp:
        base_duration += duration_bonus

    # Резист Воли — в обоих режимах; chance_bonus (баффы кастера) и
    # CONTROL_RESIST_DOWN (эффект НА цели — «Тепловой шок»/«Ледяное поле»,
    # патч 49) оба снижают эффективный резист.
    resist_down = target.effect_total(EffectKind.CONTROL_RESIST_DOWN)
    # Каждое уже прошедшее наложение удваивает проверяемую Волю: 100 WIL на
    # втором контроле считаются как 200. В PvE эскалации нет.
    effective_will = target.stats.will
    if pvp:
        effective_will = round(effective_will * bc.CC_RESIST_MULT_PER_HIT ** target.control_hits)
    resist = max(formulas.control_resist(effective_will) - chance_bonus - resist_down, 0.0)
    if rng.random() < resist:
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
    target.control_hits += 1
    target.control_hits_reset_in = bc.CC_HITS_RESET_TURNS

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
        # Счётчик наложений живёт своим таймером, а не «подряд пропущенными»
        # ходами: иначе свободный ход между контролями обнулял бы защиту.
        if combatant.control_hits_reset_in > 0:
            combatant.control_hits_reset_in -= 1
            if combatant.control_hits_reset_in == 0:
                combatant.control_hits = 0
        if combatant.control_immune_turns > 0:
            combatant.control_immune_turns -= 1
    combatant.skipped_by_control_this_turn = False
