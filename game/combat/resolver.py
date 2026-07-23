"""Одновременный резолв хода (PvE и групповой PvP).

Порядок фаз внутри хода (progression-patch-4, §5):
  1. защитные/баф-умения;
  2. контроль-умения — вешают оглушение/заморозку В ЭТОТ ЖЕ ход;
  3. проверка «кто способен действовать» (замороженные пропускают ход);
  4. атакующие действия способных + ходы мобов (по снимку после защиты);
  5. одновременное применение урона/хила;
  6. тик длительностей эффектов, КД, стрика/иммунитета контроля; смерти, исход.

Контроль, наложенный в этот ход, действует немедленно: мобы и цели-игроки,
получившие FREEZE, не действуют. FREEZE тикает в тот же ход (потребляется).
"""

import random
from dataclasses import dataclass, field

import game.classes  # noqa: F401  — регистрация умений подклассов
import game.combat.base_skills as base_skills  # регистрация базовых навыков + метаданные
from game.combat import combat_flavor, control, display
from game.combat.session import (
    ActionType,
    CombatantState,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from game.combat.skills import (
    DEFENSIVE_SKILLS,
    OFFENSIVE_SKILLS,
    PendingHeal,
    PendingHit,
    SkillContext,
    compute_hit,
)


@dataclass
class TickResult:
    lines: list[str] = field(default_factory=list)
    deaths: list[int] = field(default_factory=list)
    finished: bool = False
    winner_side: int | None = None
    draw: bool = False


def _display_mode(session: CombatSessionState) -> str:
    return display.MODE_PVE_RAID if session.is_raid else display.MODE_PVP


def _run_offensive(ctx: SkillContext, cid: int, action: DeclaredAction, session, result) -> None:
    ctx.actor = session.combatants[cid]
    ctx.action = action
    if action.type == ActionType.ATTACK:
        OFFENSIVE_SKILLS["attack"](ctx)
    elif action.type == ActionType.SKILL and action.skill_id in OFFENSIVE_SKILLS:
        OFFENSIVE_SKILLS[action.skill_id](ctx)
    elif action.type == ActionType.SKILL and action.skill_id not in DEFENSIVE_SKILLS:
        result.lines.append(
            f"{ctx.actor.name}: умение «{action.skill_id}» ещё не реализовано (TODO: content)"
        )


def resolve_tick(
    session: CombatSessionState,
    actions: dict[int, DeclaredAction],
    rng: random.Random,
) -> TickResult:
    result = TickResult()
    mode = _display_mode(session)
    alive_before = {c.id for c in session.combatants.values() if c.alive}
    hp_before = {c.id: c.current_hp for c in session.combatants.values()}
    # Эффекты, существовавшие НА НАЧАЛО хода: только они (кроме FREEZE) тикают
    # уроном/длительностью в этот ход. Свежий яд/дебаф начинает работать со
    # следующего хода; FREEZE — исключение, срабатывает и потребляется в этот ход.
    preexisting_effects = {id(e) for c in session.combatants.values() for e in c.effects}

    # Кто заморожен НА НАЧАЛО хода (лингер многоходового контроля) — не действует
    frozen_at_start = {
        cid for cid in session.combatants
        if session.combatants[cid].has_effect(EffectKind.FREEZE)
    }

    normalized: dict[int, DeclaredAction] = {}
    for cid in session.expected_declarers():
        normalized[cid] = actions.get(cid) or DeclaredAction(type=ActionType.SKIP)

    ctx = SkillContext(
        session=session,
        actor=next(iter(session.combatants.values())),
        action=DeclaredAction(),
        rng=rng,
    )

    # --- Фаза 1: защитные/баф-умения (только не замороженных на старте) ---
    for cid, action in normalized.items():
        if cid in frozen_at_start:
            continue
        if action.type == ActionType.SKILL and action.skill_id in DEFENSIVE_SKILLS:
            ctx.actor = session.combatants[cid]
            ctx.action = action
            DEFENSIVE_SKILLS[action.skill_id](ctx)

    # --- Фаза 2: контроль-умения — вешают FREEZE в этот же ход ---
    control_actors: set[int] = set()
    for cid, action in normalized.items():
        if cid in frozen_at_start:
            continue
        if action.type == ActionType.SKILL and base_skills.is_control_skill(action.skill_id):
            _run_offensive(ctx, cid, action, session, result)
            control_actors.add(cid)

    # --- Фаза 3: кто способен действовать (заморожен на старте ИЛИ получил контроль) ---
    def is_frozen(c: CombatantState) -> bool:
        return c.has_effect(EffectKind.FREEZE)

    # --- Фаза 4a: атакующие действия игроков (кроме уже сходивших контролем) ---
    for cid, action in normalized.items():
        if cid in control_actors:
            continue
        combatant = session.combatants[cid]
        if cid in frozen_at_start or is_frozen(combatant):
            # пропуск ИЗ-ЗА контроля — засчитывается в стрик DR (control-patch-8)
            combatant.skipped_by_control_this_turn = True
            result.lines.append(f"{combatant.name} скован — ход потерян ❄️")
            continue
        if action.type == ActionType.SKIP:
            result.lines.append(f"{combatant.name} медлит и пропускает ход")
            continue
        _run_offensive(ctx, cid, action, session, result)

    # --- Фаза 4b: ходы мобов (замороженные контролем этого хода пропускают) ---
    for mob in [c for c in session.combatants.values() if c.kind == "mob" and c.alive]:
        if is_frozen(mob):
            mob.skipped_by_control_this_turn = True  # пропуск из-за контроля (стрик DR)
            result.lines.append(f"{mob.name} скован — ход потерян ❄️")
            continue
        target = None
        if mob.taunted_by is not None:
            taunter = session.combatants.get(mob.taunted_by)
            if taunter is not None and taunter.alive:
                target = taunter
        if target is None:
            enemies = session.alive_enemies_of(mob)
            target = rng.choice(enemies) if enemies else None
        if target is not None:
            ctx.hits.append(compute_hit(mob, target, rng, label="кусает"))

    # --- ДоТы тикают в фазу применения (только висевшие с начала хода) ---
    for combatant in session.combatants.values():
        if not combatant.alive:
            continue
        for effect in combatant.effects_of(EffectKind.DOT):
            if id(effect) not in preexisting_effects:
                continue
            ctx.hits.append(
                PendingHit(
                    source_id=effect.source_id,
                    target_id=combatant.id,
                    amount=max(round(effect.value * effect.stacks), 1),
                    label="обжигает (ДоТ)",
                    is_dot=True,
                )
            )

    # --- Одновременное применение: net-дельта по каждому участнику ---
    damage_taken: dict[int, int] = {}
    heal_taken: dict[int, int] = {}
    for hit in ctx.hits:
        target = session.combatants[hit.target_id]
        amount = hit.amount
        if target.shield > 0:
            absorbed = min(target.shield, amount)
            target.shield -= absorbed
            amount -= absorbed
            if absorbed:
                result.lines.append(f"Щит {target.name} поглощает {absorbed} урона 🛡")
        damage_taken[hit.target_id] = damage_taken.get(hit.target_id, 0) + amount
    for heal in ctx.heals:
        heal_taken[heal.target_id] = heal_taken.get(heal.target_id, 0) + heal.amount

    for cid in set(damage_taken) | set(heal_taken):
        combatant = session.combatants[cid]
        delta = heal_taken.get(cid, 0) - damage_taken.get(cid, 0)
        combatant.current_hp = min(combatant.current_hp + delta, combatant.max_hp)

    # --- Строки лога (атмосферные шаблоны + итоговое состояние после хода) ---
    result.lines.extend(ctx.lines)
    for hit in ctx.hits:
        source = session.combatants[hit.source_id]
        target = session.combatants[hit.target_id]
        result.lines.append(
            combat_flavor.render_hit(
                source, target,
                amount=hit.amount, crit=hit.crit, missed=hit.missed, is_dot=hit.is_dot,
                hp_before=hp_before[target.id], hp_after=target.current_hp,
                max_hp=target.max_hp, rng=rng, mode=mode,
            )
        )
    for heal in ctx.heals:
        source = session.combatants[heal.source_id]
        target = session.combatants[heal.target_id]
        result.lines.append(
            display.action_line(
                source.name, heal.label, target.name,
                hp_before[target.id], target.current_hp, target.max_hp, mode,
            )
        )

    # --- Тик длительностей, КД, контроля; очистка однотиковых состояний ---
    pvp = session.mode != CombatMode.PVE  # DR-стрик считаем только в PvP
    for combatant in session.combatants.values():
        for effect in combatant.effects:
            # FREEZE тикает всегда (контроль потребляется в тот же ход);
            # прочие свежие эффекты не тикают в ход наложения
            if id(effect) in preexisting_effects or effect.kind == EffectKind.FREEZE:
                effect.remaining_ticks -= 1
        combatant.effects = [e for e in combatant.effects if e.remaining_ticks > 0]
        combatant.tick_cooldowns()
        control.tick_control(combatant, pvp)
        combatant.reset_transient()

    # --- Смерти и исход ---
    result.deaths = [cid for cid in alive_before if not session.combatants[cid].alive]
    for cid in result.deaths:
        result.lines.append(f"☠ {session.combatants[cid].name} погибает")

    sides = session.sides_alive()
    if len(sides) == 0:
        result.finished = True
        result.draw = True
        result.lines.append("Ничья: обе стороны пали одновременно")
    elif len(sides) == 1:
        result.finished = True
        result.winner_side = sides.pop()
    return result
