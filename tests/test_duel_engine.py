"""Дуэльный движок: чередование, видимость результата, таймер, исходы."""

import asyncio

import pytest

from game.combat.duel_engine import DuelEngine, DuelResult
from game.combat.session import ActionType, DeclaredAction
from tests.conftest import NoCritRng, combatant


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


def block() -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id="guardian_block")


def skip() -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKIP)


def heal_item(item_id: str, target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ITEM, item_id=item_id, target_id=target_id)


def make_engine(**kwargs) -> DuelEngine:
    return DuelEngine(rng=NoCritRng(), **kwargs)


async def test_random_first_then_strict_alternation() -> None:
    engine = make_engine()
    engine.start()
    try:
        a = combatant(1, side=0)
        b = combatant(2, side=1)
        first = engine.start_duel(10, a, b)
        assert first == 1  # NoCritRng.shuffle сохраняет порядок

        # не твой ход
        with pytest.raises(ValueError):
            await engine.act(10, 2, attack(1))

        await engine.act(10, 1, attack(2))
        # снова первый — нельзя (жёсткое чередование)
        with pytest.raises(ValueError):
            await engine.act(10, 1, attack(2))
        await engine.act(10, 2, attack(1))
    finally:
        engine.shutdown()


async def test_second_player_sees_result_immediately() -> None:
    """Ход первого резолвится сразу — второй видит новое HP до своего хода."""
    engine = make_engine()
    engine.start()
    try:
        a = combatant(1, side=0)
        b = combatant(2, side=1)
        engine.start_duel(10, a, b)
        result = await engine.act(10, 1, attack(2))
        assert b.current_hp < b.max_hp          # урон применён немедленно
        assert any("→" in line for line in result.lines)
    finally:
        engine.shutdown()


async def test_timeout_skips_turn_without_penalty() -> None:
    turns: list[DuelResult] = []

    async def on_turn(session_id: int, turn: int, result: DuelResult) -> None:
        turns.append(result)

    engine = make_engine(turn_seconds=0.3, on_turn_resolved=on_turn)
    engine.start()
    try:
        a = combatant(1, side=0)
        b = combatant(2, side=1)
        engine.start_duel(10, a, b)
        await asyncio.sleep(1.0)  # первый проспал ход
        assert turns and any("пропущен" in line for line in turns[0].lines)
        # ход перешёл ко второму
        state = engine.duels[10]
        assert state.current_actor_id == 2
        # оба целы — пропуск без штрафа
        assert a.current_hp == a.max_hp and b.current_hp == b.max_hp
    finally:
        engine.shutdown()


async def test_win_finishes_duel() -> None:
    finished: list[DuelResult] = []

    async def on_finish(session_id: int, result: DuelResult) -> None:
        finished.append(result)

    engine = make_engine(on_duel_finished=on_finish)
    engine.start()
    try:
        a = combatant(1, side=0)
        b = combatant(2, side=1)
        b.current_hp = 1
        engine.start_duel(10, a, b)
        result = await engine.act(10, 1, attack(2))
        assert result.finished and result.winner_id == 1
        assert finished and finished[0].winner_id == 1
        assert 10 not in engine.duels
    finally:
        engine.shutdown()


async def test_heal_item_restores_hp_and_consumes_turn() -> None:
    """Патч 30, баг 3, п.3: ActionType.ITEM раньше не обрабатывался вообще
    внутри duel_engine._apply_action — зелье молча пропадало без эффекта
    (падало в ветку "TODO: content"). Теперь лечит и тратит ход, как атака."""
    engine = make_engine()
    engine.start()
    try:
        a = combatant(1, side=0)
        b = combatant(2, side=1)
        a.current_hp = round(a.max_hp * 0.5)
        first = engine.start_duel(10, a, b)
        assert first == 1

        result = await engine.act(10, 1, heal_item("heal_medium", 1))
        assert a.current_hp > round(a.max_hp * 0.5)  # heal_medium = +55% max_hp
        assert any("пьёт зелье" in line or "→" in line for line in result.lines)
        # ход перешёл ко второму — зелье потратило ход, как обычное действие
        assert engine.duels[10].current_actor_id == 2
    finally:
        engine.shutdown()


async def test_turn_limit_forces_draw() -> None:
    """Патч 30: оба игрока просто пропускают ходы (никто не умирает) — по
    достижении max_turns бой обязан завершиться ничьей, а не длиться вечно."""
    finished: list[DuelResult] = []

    async def on_finish(session_id: int, result: DuelResult) -> None:
        finished.append(result)

    engine = make_engine(on_duel_finished=on_finish, max_turns=3)
    engine.start()
    try:
        a = combatant(1, side=0)
        b = combatant(2, side=1)
        first = engine.start_duel(10, a, b)
        assert first == 1  # NoCritRng.shuffle сохраняет порядок -> order = (1, 2)

        await engine.act(10, 1, skip())  # ход 1
        await engine.act(10, 2, skip())  # ход 2
        result = await engine.act(10, 1, skip())  # ход 3 — лимит достигнут

        assert result.finished and result.draw and result.draw_reason == "turn_limit"
        assert result.winner_id is None
        assert finished and finished[0].draw_reason == "turn_limit"
        assert 10 not in engine.duels
        assert a.alive and b.alive  # ничья по лимиту — оба живы, не взаимное истощение
    finally:
        engine.shutdown()


async def test_turn_limit_warning_appears_from_threshold() -> None:
    """С (max_turns - PVP_MAX_TURNS_WARNING_AT)-го хода игроки должны видеть,
    сколько ходов осталось — иначе внезапная ничья выглядит как баг."""
    engine = make_engine(max_turns=20)
    engine.start()
    try:
        a = combatant(1, side=0)
        b = combatant(2, side=1)
        engine.start_duel(10, a, b)

        result = None
        for _ in range(14):  # ходы 1..14 — до предупреждения (20-14=6 > 5)
            actor = engine.duels[10].current_actor_id
            result = await engine.act(10, actor, skip())
            assert not any("Ходов до исхода" in line for line in result.lines)

        actor = engine.duels[10].current_actor_id
        result = await engine.act(10, actor, skip())  # ход 15: 20-15=5 <= 5
        assert any("Ходов до исхода: 5" in line for line in result.lines)
    finally:
        engine.shutdown()


async def test_block_protects_until_own_next_turn() -> None:
    """Защита, поставленная в свой ход, работает против ответного хода."""
    engine = make_engine()
    engine.start()
    try:
        # без блока
        a1 = combatant(1, side=0, subclass_id="guardian")
        b1 = combatant(2, side=1)
        engine.start_duel(10, a1, b1)
        await engine.act(10, 1, attack(2))
        await engine.act(10, 2, attack(1))
        plain_damage = a1.max_hp - a1.current_hp

        # с блоком
        a2 = combatant(3, side=0, subclass_id="guardian")
        b2 = combatant(4, side=1)
        engine.start_duel(20, a2, b2)
        await engine.act(20, 3, block())
        await engine.act(20, 4, attack(3))
        blocked_damage = a2.max_hp - a2.current_hp

        assert blocked_damage < plain_damage
    finally:
        engine.shutdown()
