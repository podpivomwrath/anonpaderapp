"""Щит после ничьей в PvP (2026-10-17): та сторона, на которую напали,
две минуты под защитой - иначе нападали снова сразу, пока не кончатся зелья.
Щит от снайпинга (2026-10-18): выход из разлома/рейда и вход на Монолит."""

import time
from types import SimpleNamespace

from game.combat import balance_config as bc
from bot.handlers import pvp
from services import pvp_shield


def test_draw_shield_goes_to_attacked_side_only():
    battle = pvp.Battle(battle_type="duel", location=(0, 0), side_of={1: 0, 2: 1})
    try:
        assert pvp._grant_draw_shield(battle, [1, 2]) == [2]
        assert 0 < pvp.draw_shield_left(2) <= bc.PVP_DRAW_SHIELD_SECONDS + 1
        assert pvp.draw_shield_left(1) == 0
    finally:
        pvp_shield._shields.clear()


def test_draw_shield_expires_and_skips_sieges():
    pvp_shield._shields[5] = (time.time() - 1, pvp_shield.DRAW)
    assert pvp.draw_shield_left(5) == 0 and 5 not in pvp_shield._shields
    siege = pvp.Battle(battle_type="mass", location=(0, 0), side_of={7: 1}, siege_id=3)
    assert pvp._grant_draw_shield(siege, [7]) == []


def test_monolith_cell_gives_shield_other_cells_do_not():
    try:
        pvp_shield.on_moved(SimpleNamespace(id=11, pos_x=0, pos_y=0))
        pvp_shield.on_moved(SimpleNamespace(id=12, pos_x=0, pos_y=1))
        left, why = pvp_shield.left(11)
        assert 0 < left <= bc.PVP_SAFE_SECONDS + 1 and why == pvp_shield.MONOLITH
        assert pvp_shield.left(12) == (0, "")
    finally:
        pvp_shield._shields.clear()


def test_shield_is_never_shortened_and_drops_on_attack():
    try:
        pvp_shield.grant(3, pvp_shield.RAID, 300)
        pvp_shield.grant(3, pvp_shield.MONOLITH, 60)
        left, why = pvp_shield.left(3)
        assert left > 200 and why == pvp_shield.RAID
        pvp_shield.drop(3)
        assert pvp_shield.left(3) == (0, "")
    finally:
        pvp_shield._shields.clear()
