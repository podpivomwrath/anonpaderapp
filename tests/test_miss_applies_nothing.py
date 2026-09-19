"""Удар мимо не оставляет последствий.

Три навыка считали свой побочный эффект от НАНЕСЁННОГО урона, но страховали
результат через max(..., 1). При промахе урон равен нулю, и эта страховка
превращала ноль в единицу:

  - Огненная плеть вешала Горение силой 1 - три хода по 1 урону из ничего;
  - Кровавый пакт рассылал всей группе «восполнено 1 HP», не двигая ни одной
    полоски здоровья (именно это видно на скриншоте с прода);
  - Иссушение лечило мистика на 1 HP за промах.

Промах форсируется через second_chance_active - настоящий механизм игры
(«Второй шанс» Клинка теней), который делает следующий удар по бойцу
гарантированно мимо. Это надёжнее подкрутки RNG: тот же бросок решает ещё и
крит, и контроль.
"""

from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from tests.conftest import NoCritRng, combatant


def _session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVP_GROUP)
    for c in combatants:
        state.add(c)
    return state


def _cast(attacker, target, skill_id: str, *extra):
    """Один ход: attacker бьёт target навыком, который ГАРАНТИРОВАННО мимо."""
    session = _session(attacker, target, *extra)
    # Флаг нельзя выставить напрямую: resolve_tick в начале хода
    # ПЕРЕСЧИТЫВАЕТ его из buff_modifiers (shared_rules.begin_turn_flags),
    # затирая всё, что поставили снаружи. Поэтому даём сам бафф с интервалом 1
    # - «Второй шанс» срабатывает каждый ход.
    target.buff_modifiers = dict(target.buff_modifiers, second_chance_interval=1)
    # Тем же баффом укрываем атакующего: моб в PvE-резолве бьёт в ответ, и
    # без этого его урон двигал бы HP, по которому мы проверяем лечение.
    attacker.buff_modifiers = dict(attacker.buff_modifiers, second_chance_interval=1)
    result = resolve_tick(
        session,
        {attacker.id: DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target.id)},
        NoCritRng(),
    )
    assert any(h.missed for h in result.hits), "удар обязан быть мимо - иначе тест ничего не проверяет"
    return result, session


def test_missed_fire_whip_does_not_ignite() -> None:
    mage = combatant(1, side=0, subclass_id="elementalist", intellect=60)
    mob = combatant(2, side=1, kind="mob", vitality=200)
    _result, _session = _cast(mage, mob, "elementalist_fire")
    assert not mob.has_effect(EffectKind.DOT)


def test_landed_fire_whip_still_ignites() -> None:
    """Страховка: проверка выше зелёная не потому, что Горение сломано вовсе."""
    mage = combatant(1, side=0, subclass_id="elementalist", intellect=60)
    mob = combatant(2, side=1, kind="mob", vitality=200)
    session = _session(mage, mob)
    resolve_tick(
        session,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="elementalist_fire", target_id=2)},
        NoCritRng(),
    )
    assert mob.has_effect(EffectKind.DOT)


def test_missed_blood_pact_heals_nobody() -> None:
    mystic = combatant(1, side=0, subclass_id="dark_mystic", intellect=60)
    mob = combatant(2, side=1, kind="mob", vitality=200)
    ally = combatant(3, side=0)
    ally.current_hp = ally.max_hp // 2
    result, _session = _cast(mystic, mob, "dark_mystic_blood_pact", ally)
    assert result.heal_renders == []
    assert ally.current_hp == ally.max_hp // 2


def test_missed_blood_pact_does_not_fire_shared_pact_or_circle() -> None:
    """Производные пакта считаются долей от его лечения - нуля им тоже хватало,
    чтобы разослать по единице каждому союзнику."""
    mystic = combatant(1, side=0, subclass_id="dark_mystic", intellect=60)
    mystic.buff_modifiers = {"shared_pact_pct": 0.5, "circle_interval": 1, "circle_pct": 0.5}
    mob = combatant(2, side=1, kind="mob", vitality=200)
    ally = combatant(3, side=0)
    ally.current_hp = ally.max_hp // 2
    result, _session = _cast(mystic, mob, "dark_mystic_blood_pact", ally)
    assert result.heal_renders == []


def test_missed_drain_heals_nothing() -> None:
    mystic = combatant(1, side=0, subclass_id="dark_mystic", intellect=60)
    mystic.current_hp = mystic.max_hp // 2
    mob = combatant(2, side=1, kind="mob", vitality=200)
    result, _session = _cast(mystic, mob, "dark_mystic_drain")
    assert result.heal_renders == []


def test_heal_line_reports_what_was_actually_restored() -> None:
    """Лечение поверх полного HP не печатается вовсе.

    Раньше строка показывала ЗАПРОШЕННОЕ число рядом с фактическими
    процентами и противоречила сама себе: «восполнено 1 HP (100.0% -> 100.0%)».
    """
    mystic = combatant(1, side=0, subclass_id="dark_mystic", intellect=60)
    mystic.buff_modifiers = {"second_chance_interval": 1}  # ответный удар моба - мимо
    mob = combatant(2, side=1, kind="mob", vitality=200)
    session = _session(mystic, mob)
    result = resolve_tick(
        session,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="dark_mystic_blood_pact", target_id=2)},
        NoCritRng(),
    )
    # Мистик бьёт с полного HP, лечить его некуда - строки быть не должно.
    assert all(h.target_id != mystic.id for h in result.heal_renders)
    assert not any("восполнено" in line for line in result.lines)


def test_heal_line_amount_matches_hp_delta() -> None:
    mystic = combatant(1, side=0, subclass_id="dark_mystic", intellect=60)
    mystic.current_hp = 1  # ранен - лечение точно уместится целиком
    mob = combatant(2, side=1, kind="mob", vitality=200)
    session = _session(mystic, mob)
    result = resolve_tick(
        session,
        {1: DeclaredAction(type=ActionType.SKILL, skill_id="dark_mystic_blood_pact", target_id=2)},
        NoCritRng(),
    )
    assert result.heal_renders, "пакт с попадания обязан лечить"
    for heal in result.heal_renders:
        assert heal.amount == heal.hp_after - heal.hp_before
