"""Элементалист — Маг, ДД (стихийный урон), дотягивается до Саппорта (контроль).

TODO: content — реализовать по структуре guardian.py:
  - Огонь: ДоТ горение (EffectKind.DOT);
  - Лёд: шанс «заморозки» (EffectKind.FREEZE — цель пропускает следующий тик),
    с учётом control_resist цели;
  - Молния: удар по основной цели + N дополнительных целей одновременно.
"""

from game.classes.base import Role, SubclassDef, register

ELEMENTALIST = register(
    SubclassDef(
        id="elementalist",
        title="Элементалист",
        base_class="mage",
        primary_stat="int",
        natural_role=Role.DD,
        flexible_roles=(Role.SUPPORT,),
        skills=("attack", "elementalist_fire", "elementalist_ice", "elementalist_lightning"),
    )
)

# TODO: content
# @offensive_skill("elementalist_fire") — урон + Effect(DOT)
# @offensive_skill("elementalist_ice") — урон + шанс Effect(FREEZE, 1 тик)
# @offensive_skill("elementalist_lightning") — основная цель + N дополнительных
