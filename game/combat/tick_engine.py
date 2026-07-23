"""Тиковый движок: PvE (соло/группа) и групповой PvP.

Режимы отличаются ТОЛЬКО таймером и условием завершения хода (п.3.1):
  - PVE: таймера нет — тик ждёт, пока все живые игроки-участники не объявят
    действие;
  - PVP_GROUP: таймер хода 1 минута (APScheduler). Если все участники обеих
    сторон объявили раньше — досрочный резолв. Кто не успел — пропускает ход.

Объявленные-но-не-резолвленные действия хранятся в ActionStore (Redis в
проде, память в тестах). Резолв — game.combat.resolver.resolve_tick.
"""

import asyncio
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Protocol

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from loguru import logger

from game.combat import balance_config as bc
from game.combat.resolver import TickResult, resolve_tick
from game.combat.session import CombatMode, CombatSessionState, DeclaredAction

# (session_id, tick_number, result)
TickResolvedCallback = Callable[[int, int, TickResult], Awaitable[None]]
# (session_id, result последнего тика)
BattleFinishedCallback = Callable[[int, TickResult], Awaitable[None]]


class ActionStore(Protocol):
    """Хранилище объявленных действий текущего тика."""

    async def declare(self, session_id: int, participant_id: int, action: dict) -> None: ...

    async def declared_ids(self, session_id: int) -> set[int]: ...

    async def pop_all(self, session_id: int) -> dict[int, dict]:
        """Атомарно забрать и очистить все действия сессии."""
        ...


class InMemoryActionStore:
    """Для тестов и демо."""

    def __init__(self) -> None:
        self._actions: dict[int, dict[int, dict]] = {}

    async def declare(self, session_id: int, participant_id: int, action: dict) -> None:
        self._actions.setdefault(session_id, {})[participant_id] = action

    async def declared_ids(self, session_id: int) -> set[int]:
        return set(self._actions.get(session_id, {}))

    async def pop_all(self, session_id: int) -> dict[int, dict]:
        return self._actions.pop(session_id, {})


class RedisActionStore:
    """Прод-хранилище: hash в Redis на каждую сессию."""

    def __init__(self, redis) -> None:  # redis.asyncio.Redis
        self._redis = redis

    @staticmethod
    def _key(session_id: int) -> str:
        return f"combat:session:{session_id}:actions"

    async def declare(self, session_id: int, participant_id: int, action: dict) -> None:
        await self._redis.hset(self._key(session_id), str(participant_id), json.dumps(action))

    async def declared_ids(self, session_id: int) -> set[int]:
        keys = await self._redis.hkeys(self._key(session_id))
        return {int(k) for k in keys}

    async def pop_all(self, session_id: int) -> dict[int, dict]:
        key = self._key(session_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hgetall(key)
            pipe.delete(key)
            raw, _ = await pipe.execute()
        return {int(pid): json.loads(payload) for pid, payload in raw.items()}


class TickEngine:
    def __init__(
        self,
        store: ActionStore,
        pvp_window_seconds: float = bc.PVP_GROUP_TURN_SECONDS,
        rng: random.Random | None = None,
        scheduler: AsyncIOScheduler | None = None,
        on_tick_resolved: TickResolvedCallback | None = None,
        on_battle_finished: BattleFinishedCallback | None = None,
    ) -> None:
        self.store = store
        self.pvp_window_seconds = pvp_window_seconds
        self.rng = rng or random.Random()
        self.scheduler = scheduler or AsyncIOScheduler()
        self.on_tick_resolved = on_tick_resolved
        self.on_battle_finished = on_battle_finished
        self.sessions: dict[int, CombatSessionState] = {}
        self._resolve_locks: dict[int, asyncio.Lock] = {}

    # --- Жизненный цикл ---

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Тиковый движок запущен")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def start_session(self, state: CombatSessionState) -> None:
        if state.mode not in (CombatMode.PVE, CombatMode.PVP_GROUP):
            raise ValueError("Тиковый движок обслуживает pve и pvp_group; дуэль — duel_engine")
        self.sessions[state.session_id] = state
        self._resolve_locks[state.session_id] = asyncio.Lock()
        self._open_tick(state)

    def abort_session(self, session_id: int) -> None:
        """Немедленно прерывает сессию без резолва тика и колбэков (побег из PvE)."""
        self.sessions.pop(session_id, None)
        self._resolve_locks.pop(session_id, None)
        try:
            self.scheduler.remove_job(self._job_id(session_id))
        except Exception:
            pass

    # --- Тик ---

    def _job_id(self, session_id: int) -> str:
        return f"combat:{session_id}:tick_timeout"

    def _open_tick(self, state: CombatSessionState) -> None:
        state.tick_number += 1
        if state.mode == CombatMode.PVP_GROUP:
            resolve_at = datetime.now(timezone.utc) + timedelta(seconds=self.pvp_window_seconds)
            self.scheduler.add_job(
                self._resolve,
                trigger=DateTrigger(run_date=resolve_at),
                args=[state.session_id],
                id=self._job_id(state.session_id),
                replace_existing=True,
                misfire_grace_time=30,
            )
            logger.info(
                "Сессия {}: тик {} (PvP) — окно до {:%H:%M:%S}, не успевшие пропустят ход",
                state.session_id,
                state.tick_number,
                resolve_at,
            )
        else:
            logger.info(
                "Сессия {}: тик {} (PvE) — ждём действия всех живых игроков (без таймера)",
                state.session_id,
                state.tick_number,
            )

    async def declare_action(
        self, session_id: int, participant_id: int, action: DeclaredAction
    ) -> None:
        state = self.sessions.get(session_id)
        if state is None:
            raise KeyError(f"Сессия {session_id} не активна")
        combatant = state.combatants.get(participant_id)
        if combatant is None or not combatant.alive or combatant.kind != "character":
            raise ValueError("Объявлять действия могут только живые игроки-участники")

        await self.store.declare(session_id, participant_id, action.model_dump(mode="json"))
        logger.debug(
            "Сессия {}: {} объявил {}", session_id, combatant.name, action.type
        )

        # Общее правило PvP + условие PvE: все объявили — резолвим досрочно
        declared = await self.store.declared_ids(session_id)
        if state.expected_declarers() <= declared:
            await self._resolve(session_id)

    async def _resolve(self, session_id: int) -> None:
        state = self.sessions.get(session_id)
        if state is None:
            return  # уже разрешён (гонка таймера и досрочного резолва)
        lock = self._resolve_locks[session_id]
        async with lock:
            state = self.sessions.get(session_id)
            if state is None:
                return
            try:
                self.scheduler.remove_job(self._job_id(session_id))
            except Exception:
                pass  # PvE-режим или job уже отработал

            raw = await self.store.pop_all(session_id)
            actions = {pid: DeclaredAction(**data) for pid, data in raw.items()}
            tick = state.tick_number
            result = resolve_tick(state, actions, self.rng)

            logger.info("Сессия {}: тик {} разрешён одновременно", session_id, tick)
            for line in result.lines:
                logger.info("  {}", line)

            if self.on_tick_resolved is not None:
                await self.on_tick_resolved(session_id, tick, result)

            if result.finished:
                self.sessions.pop(session_id, None)
                self._resolve_locks.pop(session_id, None)
                logger.info(
                    "Сессия {}: бой окончен ({})",
                    session_id,
                    "ничья" if result.draw else f"победила сторона {result.winner_side}",
                )
                if self.on_battle_finished is not None:
                    await self.on_battle_finished(session_id, result)
            else:
                self._open_tick(state)
