"""Патч 39, ч.3: навыки подклассов, не покрытые test_calibration.py/test_resolver.py —
Глухая оборона (BLOCK_STANCE/BLOCK_HEAL), Клинок теней (Метка добычи), Отравитель
(Дурманящий дротик/Токсический выброс), Элементалист (Горение/Цепь молний/Схождение),
Тёмный мистик (Оберег/Иссушение/Круг тьмы)."""


from game.combat import balance_config as bc
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from tests.conftest import NoCritRng, combatant


def make_session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


class AlwaysRollsRng(NoCritRng):
    """Как NoCritRng, но .random() всегда 0.0 — гарантирует срабатывание чанс-роллов."""

    def random(self) -> float:
        return 0.0


# --- Страж: Глухая оборона ---


def test_guardian_block_reduces_damage_for_two_turns() -> None:
    rng = NoCritRng()
    guardian = combatant(1, side=0, subclass_id="guardian", agility=0)
    enemy = combatant(2, side=1)
    state = make_session(guardian, enemy)

    resolve_tick(state, {1: skill("guardian_block"), 2: attack(1)}, rng)
    assert guardian.has_effect(EffectKind.BLOCK_STANCE)
    hp_after_hit1 = guardian.current_hp

    # второй ход: страж НЕ переобъявляет блок — стойка должна ещё действовать
    resolve_tick(state, {1: attack(2), 2: attack(1)}, rng)
    reduced_hit = hp_after_hit1 - guardian.current_hp

    # эталон: страж без блока вообще
    plain_guardian = combatant(3, side=0, subclass_id="guardian", agility=0)
    plain_enemy = combatant(4, side=1)
    plain_state = make_session(plain_guardian, plain_enemy)
    resolve_tick(plain_state, {4: attack(3)}, rng)
    plain_hit = plain_guardian.max_hp - plain_guardian.current_hp

    assert reduced_hit < plain_hit


def test_guardian_block_heals_on_blocked_hit() -> None:
    rng = NoCritRng()
    guardian = combatant(1, side=0, subclass_id="guardian", agility=0)
    guardian.current_hp = round(guardian.max_hp * 0.5)
    enemy = combatant(2, side=1)
    state = make_session(guardian, enemy)

    hp_before = guardian.current_hp
    resolve_tick(state, {1: skill("guardian_block"), 2: attack(1)}, rng)
    # хил от блока минус сам входящий (срезанный) урон — итог может быть
    # выше или ниже старта, но БЕЗ хила урон был бы строго больше
    took_with_heal = hp_before - guardian.current_hp

    plain_guardian = combatant(3, side=0, subclass_id="guardian", agility=0)
    plain_guardian.current_hp = round(plain_guardian.max_hp * 0.5)
    plain_enemy = combatant(4, side=1)
    plain_state = make_session(plain_guardian, plain_enemy)
    hp_before2 = plain_guardian.current_hp
    resolve_tick(plain_state, {4: attack(3)}, rng)
    took_plain = hp_before2 - plain_guardian.current_hp

    assert took_with_heal < took_plain


# --- Клинок теней: Метка добычи ---


def test_marked_strike_stacks_and_harvest_consumes() -> None:
    rng = NoCritRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(blade, enemy)

    resolve_tick(state, {1: skill("shadow_blade_marked_strike", 2)}, rng)
    mark = enemy.effect_from(EffectKind.MARK, 1)
    assert mark is not None and mark.stacks == bc.SHADOW_BLADE_MARKED_STRIKE_STACKS

    resolve_tick(state, {1: attack(2)}, rng)  # обычная атака — стак НЕ растёт и НЕ тратится
    mark = enemy.effect_from(EffectKind.MARK, 1)
    assert mark is not None and mark.stacks == bc.SHADOW_BLADE_MARKED_STRIKE_STACKS

    hp_before = enemy.current_hp
    resolve_tick(state, {1: skill("shadow_blade_mark_harvest", 2)}, rng)
    assert enemy.effect_from(EffectKind.MARK, 1) is None  # стаки потрачены
    assert enemy.current_hp < hp_before


def test_execute_doubles_damage_below_30_percent_hp() -> None:
    rng = NoCritRng()
    blade = combatant(1, side=0, subclass_id="shadow_blade")
    low_hp_enemy = combatant(2, side=1, vitality=500)
    low_hp_enemy.current_hp = round(low_hp_enemy.max_hp * 0.2)
    state1 = make_session(blade, low_hp_enemy)
    hp_before = low_hp_enemy.current_hp
    resolve_tick(state1, {1: skill("shadow_blade_execute", 2)}, rng)
    low_hp_damage = hp_before - low_hp_enemy.current_hp

    blade2 = combatant(3, side=0, subclass_id="shadow_blade")
    full_hp_enemy = combatant(4, side=1, vitality=500)
    state2 = make_session(blade2, full_hp_enemy)
    resolve_tick(state2, {3: skill("shadow_blade_execute", 4)}, rng)
    full_hp_damage = full_hp_enemy.max_hp - full_hp_enemy.current_hp

    assert low_hp_damage == full_hp_damage * 2


# --- Отравитель: Дурманящий дротик / Токсический выброс ---


def test_disrupt_applies_weaken_and_can_control() -> None:
    rng = AlwaysRollsRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", agility=0)
    enemy = combatant(2, side=1, will=0)
    state = make_session(poisoner, enemy)

    result = resolve_tick(state, {1: skill("poisoner_disrupt", 2)}, rng)
    assert enemy.effect_total(EffectKind.WEAKEN) > 0
    # с AlwaysRollsRng и WIL=0 контроль обязан сработать (шанс 60% + резист 0)
    assert any("теряет ход" in line or "пропускает" in line for line in result.lines) or enemy.has_effect(EffectKind.FREEZE)


def test_toxic_burst_deals_damage_and_clears_the_poison() -> None:
    """Подробные проверки выброса - в tests/test_toxic_burst.py. Здесь только
    то, что он срабатывает по наложенному яду и снимает его целиком, как
    обещает описание: «взрывает весь яд... стаки сгорают»."""
    rng = NoCritRng()
    poisoner = combatant(1, side=0, subclass_id="poisoner", will=100, agility=50)
    enemy = combatant(2, side=1, vitality=5000)
    state = make_session(poisoner, enemy)

    resolve_tick(state, {1: skill("poisoner_venom", 2)}, rng)
    assert enemy.has_effect(EffectKind.DOT)

    hp_before = enemy.current_hp
    resolve_tick(state, {1: skill("poisoner_toxic_burst", 2)}, rng)
    assert enemy.current_hp < hp_before
    assert not enemy.has_effect(EffectKind.DOT)


# --- Элементалист: Горение / Цепь молний / Схождение ---


def test_fire_whip_applies_burning_dot() -> None:
    rng = NoCritRng()
    ele = combatant(1, side=0, subclass_id="elementalist")
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(ele, enemy)

    resolve_tick(state, {1: skill("elementalist_fire", 2)}, rng)
    assert enemy.has_effect(EffectKind.DOT)
    hp_before = enemy.current_hp
    resolve_tick(state, {}, rng)
    assert enemy.current_hp < hp_before  # горение тикает


def test_chain_lightning_hits_three_targets() -> None:
    rng = NoCritRng()
    ele = combatant(1, side=0, subclass_id="elementalist")
    e1 = combatant(2, side=1, vitality=500)
    e2 = combatant(3, side=1, vitality=500)
    e3 = combatant(4, side=1, vitality=500)
    state = make_session(ele, e1, e2, e3)

    resolve_tick(state, {1: skill("elementalist_lightning", 2)}, rng)
    assert e1.current_hp < e1.max_hp
    assert e2.current_hp < e2.max_hp
    assert e3.current_hp < e3.max_hp


def _convergence_damage(*effects) -> int:
    """Урон одного Схождения по свежей цели с заданными эффектами."""
    from game.combat.session import Effect

    ele = combatant(1, side=0, subclass_id="elementalist")
    enemy = combatant(2, side=1, vitality=500)
    # Источники эффектов - настоящие союзники в сессии (резолвер ищет источник DoT).
    allies = [combatant(sid, side=0, subclass_id="elementalist") for sid in (98, 99)]
    for kind, source_id, tag in effects:
        enemy.effects.append(Effect(kind=kind, value=1, remaining_ticks=3, source_id=source_id, tag=tag))
    state = make_session(ele, enemy, *allies)
    result = resolve_tick(state, {1: skill("elementalist_convergence", 2)}, NoCritRng())
    # Только сам удар Схождения: тики горения/яда в этот ход не в счёт.
    return sum(h.amount for h in result.hit_renders if not h.is_tick and h.source_id == 1)


def test_convergence_bonus_with_burning_target() -> None:
    """Своё Горение усиливает Схождение (как и раньше)."""
    from game.combat.session import BURN_TAG

    assert _convergence_damage((EffectKind.DOT, 1, BURN_TAG)) > _convergence_damage()


def test_convergence_bonus_from_allys_burning() -> None:
    """Горение ЛЮБОГО игрока усиливает Схождение, не только своё (репорт Степы)."""
    from game.combat.session import BURN_TAG

    ally_burn = _convergence_damage((EffectKind.DOT, 99, BURN_TAG))
    own_burn = _convergence_damage((EffectKind.DOT, 1, BURN_TAG))
    assert ally_burn > _convergence_damage()
    assert ally_burn == own_burn


def test_convergence_bonus_does_not_stack_with_several_burns() -> None:
    """Несколько огней - один бонус: достаточно, чтобы один игрок поджёг."""
    from game.combat.session import BURN_TAG

    one = _convergence_damage((EffectKind.DOT, 1, BURN_TAG))
    several = _convergence_damage(
        (EffectKind.DOT, 1, BURN_TAG), (EffectKind.DOT, 98, BURN_TAG), (EffectKind.DOT, 99, BURN_TAG),
    )
    assert several == one


def test_convergence_ignores_poison_and_other_dots() -> None:
    """Яд и прочие DoT'ы - не Горение: бонуса нет."""
    assert _convergence_damage((EffectKind.DOT, 99, None)) == _convergence_damage()


def test_ice_frosts_control_immune_boss_and_convergence_crits() -> None:
    """2026-10-22, владелец: босса Ледяные оковы не замораживают, но
    покрывают инеем - Схождение следующим ходом бьёт его критом, как по
    замороженной цели. Ход босс не теряет."""
    ele = combatant(1, side=0, subclass_id="elementalist")
    boss = combatant(2, side=1, vitality=500)
    boss.control_immune_always = True
    state = make_session(ele, boss)

    result = resolve_tick(state, {1: skill("elementalist_ice", 2)}, NoCritRng())
    assert not boss.has_effect(EffectKind.FREEZE)
    assert boss.has_effect(EffectKind.CHILLED)
    assert any("инеем" in line for line in result.lines)

    result = resolve_tick(state, {1: skill("elementalist_convergence", 2)}, NoCritRng())
    assert any(h.crit for h in result.hit_renders if not h.is_tick and h.source_id == 1)


def test_other_stuns_do_not_frost_a_boss() -> None:
    """Иней - только от Ледяных оков: прочие оглушения по боссу как раньше."""
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    stun = next(s for s in SUBCLASS_SKILL_DEFS.values() if s.effect == "stun" and s.id != "elementalist_ice")
    actor = combatant(1, side=0, subclass_id=stun.subclass_id)
    boss = combatant(2, side=1, vitality=500)
    boss.control_immune_always = True
    state = make_session(actor, boss)
    resolve_tick(state, {1: skill(stun.id, 2)}, NoCritRng())
    assert not boss.has_effect(EffectKind.CHILLED)


def test_fire_whip_marks_its_dot_as_burning() -> None:
    ele = combatant(1, side=0, subclass_id="elementalist")
    enemy = combatant(2, side=1, vitality=500)
    state = make_session(ele, enemy)
    resolve_tick(state, {1: skill("elementalist_fire", 2)}, NoCritRng())
    assert enemy.has_burning()


# --- Тёмный мистик: Оберег / Иссушение / Круг тьмы ---


def test_ward_shields_and_converts_remainder_to_heal_on_expiry() -> None:
    rng = NoCritRng()
    mystic = combatant(1, side=0, subclass_id="dark_mystic", will=100)
    state = make_session(mystic)

    resolve_tick(state, {1: skill("dark_mystic_ward")}, rng)
    pool = mystic.effect_from(EffectKind.SHIELD_POOL, 1)
    assert pool is not None and pool.value > 0

    # никто не бьёт — щит должен полностью истечь лечением (patch 16 — как «Второе сердце»)
    mystic.current_hp = max(mystic.current_hp - round(mystic.max_hp * 0.3), 1)
    hp_before_expiry = mystic.current_hp
    for _ in range(4):
        resolve_tick(state, {1: DeclaredAction(type=ActionType.SKIP)}, rng)
    assert mystic.current_hp > hp_before_expiry
    assert not mystic.has_effect(EffectKind.SHIELD_POOL)


def test_drain_bonus_damage_on_controlled_target() -> None:
    rng = NoCritRng()
    mystic = combatant(1, side=0, subclass_id="dark_mystic")
    frozen_enemy = combatant(2, side=1, vitality=500)
    frozen_enemy.effects.append(
        __import__("game.combat.session", fromlist=["Effect"]).Effect(
            kind=EffectKind.FREEZE, value=1, remaining_ticks=1, source_id=99
        )
    )
    state1 = make_session(mystic, frozen_enemy)
    resolve_tick(state1, {1: skill("dark_mystic_drain", 2)}, rng)
    frozen_damage = frozen_enemy.max_hp - frozen_enemy.current_hp

    mystic2 = combatant(3, side=0, subclass_id="dark_mystic")
    plain_enemy = combatant(4, side=1, vitality=500)
    state2 = make_session(mystic2, plain_enemy)
    resolve_tick(state2, {3: skill("dark_mystic_drain", 4)}, rng)
    plain_damage = plain_enemy.max_hp - plain_enemy.current_hp

    assert frozen_damage > plain_damage


def test_circle_of_dark_heals_share_of_each_target_hp() -> None:
    """2026-10-31: Круг лечит долю здоровья ЛЕЧИМОГО - хрупкий союзник
    больше не встаёт с нуля почти до полной от здоровья толстого мистика."""
    from game.combat import stat_model
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    mystic = combatant(1, side=0, subclass_id="dark_mystic", will=200, vitality=400)
    ally = combatant(2, side=0)
    mystic.current_hp, ally.current_hp = 1, 1
    resolve_tick(make_session(mystic, ally), {1: skill("dark_mystic_circle")}, NoCritRng())
    share = stat_model.ACTIVE.support_power(mystic.stats) * SUBCLASS_SKILL_DEFS["dark_mystic_circle"].effect_value
    assert abs(ally.current_hp - 1 - ally.max_hp * share) <= 1
    assert ally.current_hp < ally.max_hp * 0.5


def test_circle_of_dark_heals_whole_group_with_mystic() -> None:
    """2026-10-16: Круг тьмы в группе лечит и самого мистика (раньше - только
    союзников, и в группе мистик себя почти не лечил)."""
    rng = NoCritRng()
    mystic = combatant(1, side=0, subclass_id="dark_mystic", will=100)
    ally = combatant(2, side=0)
    ally.current_hp = round(ally.max_hp * 0.5)
    mystic.current_hp = round(mystic.max_hp * 0.5)
    state = make_session(mystic, ally)

    hp_before = mystic.current_hp
    ally_hp_before = ally.current_hp
    cost = round(hp_before * bc.DARK_MYSTIC_CIRCLE_HP_COST)
    resolve_tick(state, {1: skill("dark_mystic_circle")}, rng)
    assert ally.current_hp > ally_hp_before  # союзник исцелён
    assert mystic.current_hp > hp_before - cost  # плата заплачена, но и себя подлечил
