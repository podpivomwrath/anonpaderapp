"""Сценарные реплики рейд-босса - это ДЕЙСТВИЯ противника.

Раньше рейд клеил их над всей доской (`notice + доска`), и «Инструмент находит
цель. pupsik падает замертво.» висело ВЫШЕ строки «⚔️ БОЙ - ход N» - будто
относилось к прошлому ходу. Личные сообщения игроку (добыча, опыт, уровень)
над доской остаются: к ходу боя они отношения не имеют.
"""

from game.combat.battle_log import render_tick
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
)
from tests.conftest import NoCritRng, combatant

BOSS_LINE = "Он успевает. Работает коротко и аккуратно."


def _board(enemy_lines):
    player = combatant(1, side=0)
    boss = combatant(2, side=1, kind="mob", vitality=500)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    state.add(player)
    state.add(boss)
    state.tick_number = 2
    result = resolve_tick(
        state, {1: DeclaredAction(type=ActionType.ATTACK, target_id=2)}, NoCritRng()
    )
    return render_tick(state, result, viewer_side=0, enemy_lines=enemy_lines).split("\n")


def test_boss_line_goes_under_the_enemy_header() -> None:
    lines = _board([BOSS_LINE])
    header = lines.index("⚔️ БОЙ - ход 2")
    enemy_header = lines.index("💀 ПРОТИВНИК")
    boss = next(i for i, line in enumerate(lines) if BOSS_LINE in line)
    assert boss > header        # не выше заголовка боя
    assert boss > enemy_header  # и именно в разделе противника


def test_boss_line_comes_before_the_hits_it_explains() -> None:
    """Реплика объясняет, что босс сделал в этот ход: после неё удары читаются,
    до неё - выглядят беспричинными."""
    lines = _board([BOSS_LINE])
    boss = next(i for i, line in enumerate(lines) if BOSS_LINE in line)
    hit = next(i for i, line in enumerate(lines) if "→ атака по" in line and i > boss)
    assert boss < hit


def test_board_without_boss_lines_is_unchanged() -> None:
    assert not any(BOSS_LINE in line for line in _board(None))
