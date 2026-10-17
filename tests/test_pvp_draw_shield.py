"""Щит после ничьей в PvP (2026-10-17): та сторона, на которую напали,
две минуты под щитом - иначе нападали сразу снова, пока не кончатся зелья."""

import time

from game.combat import balance_config as bc
from bot.handlers import pvp


def test_draw_shield_goes_to_attacked_side_only():
    battle = pvp.Battle(battle_type="duel", location=(0, 0), side_of={1: 0, 2: 1})
    try:
        assert pvp._grant_draw_shield(battle, [1, 2]) == [2]
        assert 0 < pvp.draw_shield_left(2) <= bc.PVP_DRAW_SHIELD_SECONDS + 1
        assert pvp.draw_shield_left(1) == 0
    finally:
        pvp._draw_shield.clear()


def test_draw_shield_expires_and_skips_sieges():
    pvp._draw_shield[5] = time.time() - 1
    assert pvp.draw_shield_left(5) == 0 and 5 not in pvp._draw_shield
    siege = pvp.Battle(battle_type="mass", location=(0, 0), side_of={7: 1}, siege_id=3)
    assert pvp._grant_draw_shield(siege, [7]) == []
