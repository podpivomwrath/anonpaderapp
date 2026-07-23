"""Клинок теней / Ассасин — Разбойник, ДД (крит/бурст), дотягивается до Танка (уклонение).

TODO: content — реализовать по структуре guardian.py:
  - обычные удары вешают стаки «Метка добычи» (EffectKind.MARK);
  - добивающий удар тратит стаки: усиленный крит.
"""

from game.classes.base import Role, SubclassDef, register

SHADOW_BLADE = register(
    SubclassDef(
        id="shadow_blade",
        title="Клинок теней",
        base_class="rogue",
        primary_stat="agi",
        natural_role=Role.DD,
        flexible_roles=(Role.TANK,),
        skills=("attack", "shadow_blade_marked_strike", "shadow_blade_execute"),
    )
)

# TODO: content
# @offensive_skill("shadow_blade_marked_strike") — удар + стак MARK на цель
# @offensive_skill("shadow_blade_execute") — тратит стаки MARK, крит усилен
