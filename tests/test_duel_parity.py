"""Правила слияния модификаторов (shared_rules): интервалы и перезарядки.

Раньше здесь была сверка дуэльного движка с тиковым; дуэль с 2026-10-29 идёт
на тиковом движке, а game/combat/duel_engine.py удалён (аудит 2026-11-05).
"""


from game.combat import shared_rules
from game.combat.resolver import resolve_tick
from game.combat.session import (
    CombatMode,
    CombatSessionState,
    Effect,
    EffectKind,
)
from tests.conftest import NoCritRng, combatant


def poison(target, source_id: int, stacks: int = 3, value: float = 20.0, ticks: int = 3) -> Effect:
    effect = Effect(kind=EffectKind.DOT, value=value, remaining_ticks=ticks,
                    source_id=source_id, stacks=stacks)
    target.effects.append(effect)
    return effect


def tick_poison_damage(mods: dict, *, pool: int = 0, stacks: int = 3) -> int:
    poisoner = combatant(1, side=0, subclass_id="poisoner")
    poisoner.buff_modifiers = dict(mods)
    victim = combatant(2, side=1, vitality=500)
    if pool:
        victim.effects.append(Effect(kind=EffectKind.SHIELD_POOL, value=pool,
                                     remaining_ticks=5, source_id=victim.id))
    poison(victim, source_id=poisoner.id, stacks=stacks)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    state.add(poisoner)
    state.add(victim)
    state.tick_number = 1
    before = victim.current_hp
    resolve_tick(state, {}, NoCritRng())
    return before - victim.current_hp


# --- Урон ядом одинаков в обоих движках ---


# --- Щиты держат яд в дуэли так же, как в групповом бою ---


# --- Номер хода доезжает до правил ---


# --- Память Клинка теней ведётся и в дуэли ---


# --- Мерж модификаторов: направление «выгодно игроку» ---


def test_interval_keys_merge_towards_lower_value() -> None:
    from game.content_loader import BuffDef
    from services.preset_service import resolve_buff_modifiers

    def buff(buff_id: str, **mods: float) -> BuffDef:
        return BuffDef(id=buff_id, name=buff_id, subclass="x", category="damage",
                       description="", stat_modifiers=mods, duration_ticks=1, implemented=True)

    catalog = {
        "slow": buff("slow", bloodlust_cooldown=8.0, damage_bonus=0.05),
        "fast": buff("fast", bloodlust_cooldown=4.0, damage_bonus=0.10),
    }
    merged = resolve_buff_modifiers(["slow", "fast"], catalog)
    assert merged["bloodlust_cooldown"] == 4.0   # кулдаун: меньше = лучше
    assert merged["damage_bonus"] == 0.10        # прибавка: больше = лучше


def test_lower_is_better_covers_cooldowns_and_intervals() -> None:
    assert shared_rules is not None  # модуль общих правил на месте
    from services.preset_service import is_lower_better

    assert is_lower_better("bloodlust_cooldown")
    assert is_lower_better("second_chance_interval")
    assert not is_lower_better("damage_bonus")
    assert not is_lower_better("ward_shield_bonus")


def _capped_guardian():
    """Страж под «Несокрушимым»: удар не выше 5% его макс. HP."""
    g = combatant(2, side=1, subclass_id="guardian", vitality=200)
    g.effects.append(Effect(kind=EffectKind.DAMAGE_CAP, value=0.05, remaining_ticks=3, source_id=2))
    return g


