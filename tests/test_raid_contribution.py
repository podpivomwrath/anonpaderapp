"""Патч 69: личная сводка после рейда — урон, лечение, впитанное.

Копится по ходам, потому что TickResult живёт ровно один ход. Один battle_id
держит весь рейд, поэтому копилка обязана пережить смену этапа.
"""

from bot import raid_texts as rt
from bot.handlers import raid_combat as raid
from game.combat.resolver import RenderedHeal, RenderedHit, TickResult

PLAYER = 1
ALLY = 2
BOSS = 900


def _battle() -> raid.RaidBattle:
    import random

    participants = {
        PLAYER: raid.Participant(character_id=PLAYER, peer_id=11, name="pupsik",
                                 base_class="mage", subclass_id=None),
        ALLY: raid.Participant(character_id=ALLY, peer_id=22, name="Гостус",
                               base_class="warrior", subclass_id=None),
    }
    return raid.RaidBattle(group_id=None, participants=participants,
                           member_inputs=[], rng=random.Random(0))


def _hit(source, target, amount, *, missed=False, absorbed=0, source_side=0, target_side=1):
    return RenderedHit(
        source_id=source, target_id=target, source_side=source_side, target_side=target_side,
        label="бьёт", amount=amount, crit=False, missed=missed, is_dot=False,
        hp_before=100, hp_after=100 - amount, max_hp=100, absorbed=absorbed,
    )


def _heal(source, target, amount):
    return RenderedHeal(
        source_id=source, target_id=target, source_side=0, target_side=0,
        label="лечит", amount=amount, hp_before=10, hp_after=10 + amount, max_hp=100,
    )


def _tick(hits=(), heals=()) -> TickResult:
    result = TickResult()
    result.hit_renders.extend(hits)
    result.heal_renders.extend(heals)
    return result


def test_damage_healing_and_absorb_are_counted() -> None:
    battle = _battle()
    raid._record_contribution(battle, _tick(
        hits=[
            _hit(PLAYER, BOSS, 500),
            _hit(BOSS, PLAYER, 80, absorbed=120, source_side=1, target_side=0),
        ],
        heals=[_heal(PLAYER, ALLY, 40)],
    ))
    mine = battle.contribution[PLAYER]
    assert mine.damage == 500
    assert mine.healed == 40
    assert mine.absorbed == 120


def test_totals_survive_across_ticks_and_stages() -> None:
    battle = _battle()
    for _ in range(3):
        raid._record_contribution(battle, _tick(hits=[_hit(PLAYER, BOSS, 100)]))
    battle.stage = 2  # смена этапа не трогает копилку
    raid._record_contribution(battle, _tick(hits=[_hit(PLAYER, BOSS, 100)]))
    assert battle.contribution[PLAYER].damage == 400


def test_miss_adds_nothing() -> None:
    battle = _battle()
    raid._record_contribution(battle, _tick(hits=[_hit(PLAYER, BOSS, 0, missed=True)]))
    assert PLAYER not in battle.contribution


def test_friendly_fire_is_not_counted_as_damage_dealt() -> None:
    """Урон засчитывается только по ЧУЖОЙ стороне: иначе отражённый щитом
    удар или урон по союзнику попадал бы в личный счёт как достижение."""
    battle = _battle()
    raid._record_contribution(battle, _tick(
        hits=[_hit(PLAYER, ALLY, 50, source_side=0, target_side=0)],
    ))
    assert battle.contribution.get(PLAYER, raid.RaidContribution()).damage == 0


def test_absorb_is_credited_to_the_one_who_took_the_hit() -> None:
    battle = _battle()
    raid._record_contribution(battle, _tick(
        hits=[_hit(BOSS, ALLY, 10, absorbed=300, source_side=1, target_side=0)],
    ))
    assert battle.contribution[ALLY].absorbed == 300
    assert PLAYER not in battle.contribution


def test_block_reports_zeroes_for_a_player_who_did_nothing() -> None:
    """Нули - тоже разбор захода. Пустая сводка была бы хуже: игрок решил бы,
    что сводка сломалась, а не что он ничего не успел."""
    block = rt.contribution_block(None, "Гостус")
    assert "Гостус" in block
    assert block.count("0") >= 3


def test_block_groups_thousands() -> None:
    block = rt.contribution_block(raid.RaidContribution(damage=1234567, healed=0, absorbed=890), "pupsik")
    assert "1 234 567" in block
    assert "890" in block
