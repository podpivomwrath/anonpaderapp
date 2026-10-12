"""Пассивки базовых классов до подкласса (2026-10-12): воину +10% здоровья,
разбойнику +10 п.п. крита. После выбора подкласса - их нет."""

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.session import Stats, build_combatant


def _fighter(base_class: str, subclass: str | None = None):
    stats = Stats(strength=40, agility=40, intellect=40, vitality=40, will=30)
    return build_combatant(
        id=1, side=0, kind="character", name="Тест", level=10, stats=stats,
        primary_stat=bc.PRIMARY_STAT_BY_CLASS[base_class], subclass_id=subclass, base_class=base_class,
    )


def test_warrior_gets_ten_percent_hp_before_subclass() -> None:
    plain = _fighter("mage").max_hp
    assert _fighter("warrior").max_hp == round(plain * 1.10)
    assert _fighter("warrior", subclass="berserker").max_hp == plain


def test_rogue_crit_bonus_only_before_subclass() -> None:
    assert formulas.class_crit_bonus("rogue", None) == bc.BASE_CLASS_CRIT_BONUS["rogue"]
    assert formulas.class_crit_bonus("rogue", "shadow_blade") == 0.0
    assert formulas.class_crit_bonus("warrior", None) == 0.0


def test_mobs_get_no_passives() -> None:
    stats = Stats(strength=40, agility=40, intellect=40, vitality=40, will=30)
    mob = build_combatant(id=2, side=1, kind="mob", name="Моб", level=10, stats=stats,
                          primary_stat="str", base_class="warrior")
    assert mob.max_hp == _fighter("mage").max_hp
