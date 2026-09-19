"""Патч 69: общие итоги рейда - одна таблица на всех — урон, лечение, впитанное.

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
    удар или урон по союзнику поднимал бы человека в таблице."""
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


def test_table_ranks_each_column_separately() -> None:
    """Лучший танк редко совпадает с лучшим уроном - общий порядок строк врал
    бы про две колонки из трёх."""
    rows = [
        ("Танк", raid.RaidContribution(damage=1000, healed=0, absorbed=50_000)),
        ("Дамагер", raid.RaidContribution(damage=90_000, healed=0, absorbed=1000)),
        ("Хилер", raid.RaidContribution(damage=5000, healed=40_000, absorbed=2000)),
    ]
    table = rt.contribution_table(rows).split(chr(10))

    def section(title: str) -> list[str]:
        i = table.index(title)
        return [line.split(" - ")[0] for line in table[i + 1:i + 4]]

    assert section("⚔️ Урона нанесено:") == ["Дамагер", "Хилер", "Танк"]
    assert section("💚 Здоровья восполнено:") == ["Хилер", "Дамагер", "Танк"]
    assert section("🛡 Урона впитано:") == ["Танк", "Хилер", "Дамагер"]


def test_table_lists_everyone_including_zeroes() -> None:
    """Ради этих строк таблицу и смотрят: прятать нули - прятать ровно тех,
    кого игроки пытаются отсеять."""
    rows = [
        ("pupsik", raid.RaidContribution(damage=10_000)),
        ("Пассажир", raid.RaidContribution()),
    ]
    table = rt.contribution_table(rows)
    assert "Пассажир - 0" in table
    assert table.count("Пассажир") == 3  # во всех трёх разделах


def test_table_is_identical_for_everyone() -> None:
    """Таблица общая: её строят один раз и рассылают как есть."""
    rows = [("a", raid.RaidContribution(damage=1)), ("b", raid.RaidContribution(damage=2))]
    assert rt.contribution_table(rows) == rt.contribution_table(list(reversed(rows)))


def test_ties_are_ordered_by_name_not_by_luck() -> None:
    """Иначе порядок двух нулей скакал бы от сообщения к сообщению и читался
    как разные результаты."""
    rows = [("Яна", raid.RaidContribution()), ("Антон", raid.RaidContribution())]
    table = rt.contribution_table(rows).split(chr(10))
    i = table.index("⚔️ Урона нанесено:")
    assert table[i + 1].startswith("Антон")
    assert table[i + 2].startswith("Яна")


def test_table_groups_thousands() -> None:
    table = rt.contribution_table([("pupsik", raid.RaidContribution(damage=1234567, absorbed=890))])
    assert "1 234 567" in table
    assert "890" in table
