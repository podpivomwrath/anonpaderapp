"""Дуэльный движок (1×1 открытое PvP) — НЕ переиспользует tick_engine:
логика принципиально другая (очередь ходов, а не окно+одновременный резолв).

Правила (п.3.2):
  - рандом решает, кто ходит первым, дальше жёсткое чередование;
  - второй игрок ВИДИТ результат хода первого (ход резолвится сразу);
  - таймер хода 1 минута; не успел — ход пропускается (без штрафа);
  - «оба сходили раньше таймера» → мгновенный переход хода (при строгом
    чередовании происходит естественно: ход резолвится сразу после действия;
    проверка оставлена хуком advance_early на случай «быстрого ответа»);
  - ничья (взаимное истощение) — валидный исход, ресурсы не переходят никому.
"""

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from loguru import logger

from game.combat import balance_config as bc
from game.combat import control, display
from game.combat.session import (
    ActionType,
    CombatantState,
    DeclaredAction,
    EffectKind,
)
from game.combat.skills import DEFENSIVE_SKILLS, OFFENSIVE_SKILLS, SkillContext, compute_hit
from game.combat.session import CombatMode, CombatSessionState


@dataclass
class DuelResult:
    lines: list[str] = field(default_factory=list)
    finished: bool = False
    winner_id: int | None = None
    draw: bool = False


@dataclass
class DuelState:
    session_id: int
    combatants: dict[int, CombatantState]
    order: tuple[int, int]  # (первый, второй)
    turn_number: int = 1
    finished: bool = False

    @property
    def current_actor_id(self) -> int:
        return self.order[(self.turn_number - 1) % 2]

    def opponent_of(self, actor_id: int) -> CombatantState:
        other_id = self.order[1] if actor_id == self.order[0] else self.order[0]
        return self.combatants[other_id]

    def as_session_state(self) -> CombatSessionState:
        """Обёртка для переиспользования SkillContext/умений."""
        state = CombatSessionState(session_id=self.session_id, mode=CombatMode.DUEL)
        state.combatants = self.combatants
        return state


TurnResolvedCallback = Callable[[int, int, DuelResult], Awaitable[None]]
DuelFinishedCallback = Callable[[int, DuelResult], Awaitable[None]]


class DuelEngine:
    def __init__(
        self,
        turn_seconds: float = bc.DUEL_TURN_SECONDS,
        rng: random.Random | None = None,
        scheduler: AsyncIOScheduler | None = None,
        on_turn_resolved: TurnResolvedCallback | None = None,
        on_duel_finished: DuelFinishedCallback | None = None,
    ) -> None:
        self.turn_seconds = turn_seconds
        self.rng = rng or random.Random()
        self.scheduler = scheduler or AsyncIOScheduler()
        self.on_turn_resolved = on_turn_resolved
        self.on_duel_finished = on_duel_finished
        self.duels: dict[int, DuelState] = {}

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    # --- Жизненный цикл дуэли ---

    def start_duel(
        self, session_id: int, first: CombatantState, second: CombatantState
    ) -> int:
        """Возвращает id игрока, который ходит первым (рандом)."""
        pair = [first, second]
        self.rng.shuffle(pair)
        state = DuelState(
            session_id=session_id,
            combatants={first.id: first, second.id: second},
            order=(pair[0].id, pair[1].id),
        )
        self.duels[session_id] = state
        logger.info(
            "Дуэль {}: {} против {}, первым ходит {}",
            session_id,
            first.name,
            second.name,
            pair[0].name,
        )
        self._schedule_timeout(state)
        return pair[0].id

    def _job_id(self, session_id: int) -> str:
        return f"duel:{session_id}:turn_timeout"

    def _schedule_timeout(self, state: DuelState) -> None:
        resolve_at = datetime.now(timezone.utc) + timedelta(seconds=self.turn_seconds)
        self.scheduler.add_job(
            self._on_timeout,
            trigger=DateTrigger(run_date=resolve_at),
            args=[state.session_id, state.turn_number],
            id=self._job_id(state.session_id),
            replace_existing=True,
            misfire_grace_time=30,
        )

    async def act(
        self, session_id: int, actor_id: int, action: DeclaredAction
    ) -> DuelResult:
        state = self.duels.get(session_id)
        if state is None:
            raise KeyError(f"Дуэль {session_id} не активна")
        if actor_id != state.current_actor_id:
            raise ValueError("Сейчас не твой ход")
        try:
            self.scheduler.remove_job(self._job_id(session_id))
        except Exception:
            pass
        return await self._resolve_turn(state, action)

    async def _on_timeout(self, session_id: int, turn_number: int) -> None:
        state = self.duels.get(session_id)
        if state is None or state.turn_number != turn_number:
            return
        await self._resolve_turn(state, None)

    # --- Резолв одного хода ---

    async def _resolve_turn(
        self, state: DuelState, action: DeclaredAction | None
    ) -> DuelResult:
        actor = state.combatants[state.current_actor_id]
        result = DuelResult()
        turn = state.turn_number

        # Однотиковая защита актёра действовала до начала его нового хода
        actor.reset_transient()

        # ДоТы на актёре тикают в начале его собственного хода
        for effect in actor.effects_of(EffectKind.DOT):
            dot = max(round(effect.value * effect.stacks), 1)
            before = actor.current_hp
            actor.current_hp -= dot
            result.lines.append(
                display.action_line(
                    "ДоТ", "разъедает", actor.name,
                    before, actor.current_hp, actor.max_hp, display.MODE_PVP,
                )
            )

        if action is None:
            result.lines.append(f"⏳ {actor.name} не успел походить — ход пропущен")
        elif actor.has_effect(EffectKind.FREEZE):
            # пропуск ИЗ-ЗА контроля — засчитывается в стрик DR (control-patch-8)
            actor.skipped_by_control_this_turn = True
            result.lines.append(f"{actor.name} заморожен и пропускает ход ❄️")
        elif action.type == ActionType.SKIP:
            result.lines.append(f"{actor.name} пропускает ход")
        else:
            self._apply_action(state, actor, action, result)

        # Эффекты, кулдауны и контроль актёра тикают в конце его собственного хода
        for effect in actor.effects:
            effect.remaining_ticks -= 1
        actor.effects = [e for e in actor.effects if e.remaining_ticks > 0]
        actor.tick_cooldowns()
        control.tick_control(actor, pvp=True)  # дуэль — всегда PvP

        # Исход: последовательные ходы, но взаимное истощение возможно
        alive = [c for c in state.combatants.values() if c.alive]
        if len(alive) == 0:
            result.finished, result.draw = True, True
            result.lines.append("Ничья: взаимное истощение — ресурсы не переходят никому")
        elif len(alive) == 1:
            result.finished = True
            result.winner_id = alive[0].id
            result.lines.append(f"🏆 Победитель дуэли: {alive[0].name}")

        if self.on_turn_resolved is not None:
            await self.on_turn_resolved(state.session_id, turn, result)

        if result.finished:
            state.finished = True
            self.duels.pop(state.session_id, None)
            if self.on_duel_finished is not None:
                await self.on_duel_finished(state.session_id, result)
        else:
            state.turn_number += 1
            self._schedule_timeout(state)
        return result

    def _apply_action(
        self,
        state: DuelState,
        actor: CombatantState,
        action: DeclaredAction,
        result: DuelResult,
    ) -> None:
        session_view = state.as_session_state()
        ctx = SkillContext(session=session_view, actor=actor, action=action, rng=self.rng)

        if action.type == ActionType.SKILL and action.skill_id in DEFENSIVE_SKILLS:
            # защита сохраняется до начала следующего хода актёра
            DEFENSIVE_SKILLS[action.skill_id](ctx)
        elif action.type == ActionType.ATTACK or (
            action.type == ActionType.SKILL and action.skill_id in OFFENSIVE_SKILLS
        ):
            handler = (
                OFFENSIVE_SKILLS["attack"]
                if action.type == ActionType.ATTACK
                else OFFENSIVE_SKILLS[action.skill_id]
            )
            handler(ctx)
        else:
            result.lines.append(
                f"{actor.name}: умение «{action.skill_id}» ещё не реализовано (TODO: content)"
            )

        # Ход резолвится СРАЗУ — противник увидит результат перед своим ходом
        for hit in ctx.hits:
            target = state.combatants[hit.target_id]
            if hit.missed:
                result.lines.append(f"{target.name} уходит от удара — мимо.")
                continue
            before = target.current_hp
            amount = hit.amount
            if target.shield > 0:
                absorbed = min(target.shield, amount)
                target.shield -= absorbed
                amount -= absorbed
                if absorbed:
                    result.lines.append(f"Щит {target.name} поглощает {absorbed} урона 🛡")
            target.current_hp -= amount
            result.lines.append(
                display.action_line(
                    actor.name, hit.label, target.name,
                    before, target.current_hp, target.max_hp,
                    display.MODE_PVP,  # дуэль — PvP: целые проценты
                    suffix=" (крит!)" if hit.crit else "",
                )
            )
        for heal in ctx.heals:
            target = state.combatants[heal.target_id]
            before = target.current_hp
            target.current_hp = min(target.current_hp + heal.amount, target.max_hp)
            result.lines.append(
                display.action_line(
                    actor.name, heal.label, target.name,
                    before, target.current_hp, target.max_hp, display.MODE_PVP,
                )
            )
        result.lines.extend(ctx.lines)
