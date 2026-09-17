"""Патч 56: микробаффы Стража + общие правила патча.

Страж отстаёт в дуэлях (винрейт 14%), поэтому его кит намеренно конвертирует
защиту в урон и пользу: отражение блока, контрудар, накопительное Возмездие.
"""

from game.combat import balance_config as bc
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from services.preset_service import resolve_buff_modifiers
from tests.conftest import NoCritRng, combatant


class AlwaysLowRng(NoCritRng):
    """random() = 0.0: все шансовые проверки срабатывают (полный блок и т.п.)."""

    def random(self) -> float:
        return 0.0


def make_session(*combatants, mode=CombatMode.PVP_GROUP) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=mode)
    for c in combatants:
        state.add(c)
    return state


def skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


# --- Общее правило: модификаторы одного типа не складываются, берётся больший ---


def test_same_modifier_takes_maximum_not_last() -> None:
    from game.content_loader import BuffDef

    catalog = {
        "small": BuffDef(id="small", name="a", subclass="guardian", category="defense",
                         description="", stat_modifiers={"damage_bonus": 0.10}),
        "big": BuffDef(id="big", name="b", subclass="guardian", category="defense",
                       description="", stat_modifiers={"damage_bonus": 0.30}),
    }
    # Порядок не должен влиять: раньше dict.update отдавал победу последнему.
    assert resolve_buff_modifiers(["big", "small"], catalog)["damage_bonus"] == 0.30
    assert resolve_buff_modifiers(["small", "big"], catalog)["damage_bonus"] == 0.30


# --- Оборона ---


def test_sturdy_armor_reduces_incoming_damage() -> None:
    rng = NoCritRng()
    plain = combatant(1, side=0, subclass_id="guardian")
    resolve_tick(make_session(plain, combatant(2, side=1)), {2: attack(1)}, rng)
    plain_taken = plain.max_hp - plain.current_hp

    armored = combatant(1, side=0, subclass_id="guardian")
    armored.buff_modifiers = {"incoming_damage_reduction": bc.GUARDIAN_STURDY_ARMOR_REDUCTION}
    resolve_tick(make_session(armored, combatant(2, side=1)), {2: attack(1)}, rng)
    assert armored.max_hp - armored.current_hp < plain_taken


def test_resilience_uses_its_own_hp_threshold() -> None:
    """Порог Стойкости 30%, у Кровавого рыцаря 40%: раньше в коде был жёстко
    зашит порог рыцаря сразу на оба подкласса."""
    mods = {
        "low_hp_damage_reduction": bc.GUARDIAN_RESILIENCE_REDUCTION,
        "low_hp_damage_reduction_threshold": bc.GUARDIAN_RESILIENCE_HP_THRESHOLD,
    }
    rng = NoCritRng()

    high = combatant(1, side=0, subclass_id="guardian")
    high.buff_modifiers = dict(mods)
    high.current_hp = int(high.max_hp * 0.35)  # выше порога Стража
    before_high = high.current_hp
    resolve_tick(make_session(high, combatant(2, side=1)), {2: attack(1)}, rng)
    taken_high = before_high - high.current_hp

    low = combatant(1, side=0, subclass_id="guardian")
    low.buff_modifiers = dict(mods)
    low.current_hp = int(low.max_hp * 0.20)  # ниже порога
    before_low = low.current_hp
    resolve_tick(make_session(low, combatant(2, side=1)), {2: attack(1)}, rng)
    taken_low = before_low - low.current_hp

    assert taken_low < taken_high


def test_guard_bonus_is_wired_to_config() -> None:
    from game.content_loader import load_content

    buffs = load_content().buffs
    assert buffs["guardian_guard"].stat_modifiers["guard_block_bonus"] == bc.GUARDIAN_GUARD_BLOCK_BONUS
    assert bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE + bc.GUARDIAN_GUARD_BLOCK_BONUS > bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE


# --- Урон из защиты ---


def test_reflection_returns_part_of_blocked_damage() -> None:
    rng = AlwaysLowRng()
    # agility=0: иначе AlwaysLowRng заставляет Стража УКЛОНИТЬСЯ от удара, и
    # блокировать становится нечего - тест не про уворот.
    guardian = combatant(1, side=0, subclass_id="guardian", agility=0)
    guardian.buff_modifiers = {
        "full_block_chance": 1.0,
        "block_reflect_pct": bc.GUARDIAN_REFLECTION_PCT,
    }
    attacker = combatant(2, side=1, agility=0)
    hp_before = attacker.current_hp

    result = resolve_tick(
        make_session(guardian, attacker), {1: skill("guardian_block"), 2: attack(1)}, rng
    )

    incoming = next(h for h in result.hits if h.source_id == attacker.id)
    reflected = next(h for h in result.hits if h.label == "отражает щитом")
    assert incoming.blocked > 0                      # блок действительно сработал
    assert reflected.target_id == attacker.id        # вернулось именно атакующему
    assert reflected.amount == max(round(incoming.blocked * bc.GUARDIAN_REFLECTION_PCT), 1)
    assert attacker.current_hp < hp_before
    # Полный блок срезает удар до минимума, который движок всё равно пропускает
    # (нижняя граница урона = 1), поэтому сравниваем с ней, а не с нулём.
    assert guardian.max_hp - guardian.current_hp <= 1


def test_counterattack_requires_full_block() -> None:
    rng = AlwaysLowRng()
    guardian = combatant(1, side=0, subclass_id="guardian")
    guardian.buff_modifiers = {"counterstrike_mult": bc.GUARDIAN_COUNTERATTACK_MULT}
    enemy = combatant(2, side=1, agility=0)
    resolve_tick(make_session(guardian, enemy), {1: skill("guardian_block")}, rng)
    assert enemy.current_hp == enemy.max_hp

    guardian2 = combatant(1, side=0, subclass_id="guardian")
    guardian2.buff_modifiers = {
        "counterstrike_mult": bc.GUARDIAN_COUNTERATTACK_MULT, "full_block_chance": 1.0,
    }
    enemy2 = combatant(2, side=1, agility=0)
    resolve_tick(make_session(guardian2, enemy2), {1: skill("guardian_block")}, rng)
    assert enemy2.current_hp < enemy2.max_hp


def test_retribution_grows_damage_after_blocking() -> None:
    from game.combat.skills import retribution_bonus

    guardian = combatant(1, side=0, subclass_id="guardian")
    guardian.buff_modifiers = {
        "retribution_damage_per_10pct": bc.GUARDIAN_RETRIBUTION_PER_10PCT,
        "retribution_cap": bc.GUARDIAN_RETRIBUTION_CAP,
    }
    assert retribution_bonus(guardian) == 0.0  # ничего не заблокировано

    guardian.blocked_recent = [round(guardian.max_hp * 0.10)]
    assert abs(retribution_bonus(guardian) - bc.GUARDIAN_RETRIBUTION_PER_10PCT) < 0.01

    guardian.blocked_recent = [guardian.max_hp]  # заведомо выше потолка
    assert retribution_bonus(guardian) == bc.GUARDIAN_RETRIBUTION_CAP


def test_blocked_window_keeps_only_recent_turns() -> None:
    rng = NoCritRng()
    guardian = combatant(1, side=0, subclass_id="guardian")
    state = make_session(guardian, combatant(2, side=1))
    for _ in range(bc.GUARDIAN_RETRIBUTION_WINDOW_TURNS + 3):
        resolve_tick(state, {1: DeclaredAction(type=ActionType.SKIP)}, rng)
    assert len(guardian.blocked_recent) == bc.GUARDIAN_RETRIBUTION_WINDOW_TURNS


# --- Групповые: в соло эффекта нет ---


def test_group_buffs_do_nothing_without_allies() -> None:
    rng = AlwaysLowRng()
    guardian = combatant(1, side=0, subclass_id="guardian")
    guardian.buff_modifiers = {
        "ally_shield_share_pct": bc.GUARDIAN_ALLYS_SHIELD_SHARE, "wall_cleanse": 1.0,
    }
    result = resolve_tick(
        make_session(guardian, combatant(2, side=1)), {1: skill("guardian_block")}, rng
    )
    assert not any("прикрывает щитом" in line for line in result.lines)


def test_allys_shield_and_wall_help_weakest_ally() -> None:
    rng = AlwaysLowRng()
    guardian = combatant(1, side=0, subclass_id="guardian")
    guardian.buff_modifiers = {
        "ally_shield_share_pct": bc.GUARDIAN_ALLYS_SHIELD_SHARE, "wall_cleanse": 1.0,
    }
    ally = combatant(3, side=0)
    ally.current_hp = int(ally.max_hp * 0.2)  # самый слабый по проценту HP
    ally.apply_effect(EffectKind.WEAKEN, 0.3, 3, 2)

    resolve_tick(
        make_session(guardian, ally, combatant(2, side=1)), {1: skill("guardian_block")}, rng
    )

    assert ally.has_effect(EffectKind.BLOCK_STANCE)  # Щит соратника
    assert not ally.has_effect(EffectKind.WEAKEN)    # Стена сняла дебафф
