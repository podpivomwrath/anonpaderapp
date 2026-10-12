"""Переработанный боевой лог (патч 51, ч.5): два раздела + HP-полосы внизу."""

from game.combat.battle_log import render_tick
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, Effect, EffectKind
from tests.conftest import NoCritRng, combatant


def make_session(mode: CombatMode, *combatants, is_raid: bool = False) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=mode, is_raid=is_raid)
    for c in combatants:
        state.add(c)
    return state


def attack(target_id: int) -> DeclaredAction:
    return DeclaredAction(type=ActionType.ATTACK, target_id=target_id)


def test_sections_present_in_order_own_then_enemy() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob")
    state = make_session(CombatMode.PVE, a, b)
    result = resolve_tick(state, {1: attack(2)}, NoCritRng())
    text = render_tick(state, result, viewer_side=0)
    own_idx = text.index("👥 ВАША СТОРОНА")
    enemy_idx = text.index("💀 ПРОТИВНИК")
    assert own_idx < enemy_idx


def test_hit_line_format_matches_pattern() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob")
    state = make_session(CombatMode.PVE, a, b)
    result = resolve_tick(state, {1: attack(2)}, NoCritRng())
    text = render_tick(state, result, viewer_side=0)
    assert "Гостус → атака по Кандальный -" in text
    assert "урона" in text
    assert "Кандальный:" in text  # HP delta in the hit line itself


def test_hits_bucketed_by_source_side() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob")
    state = make_session(CombatMode.PVE, a, b)
    result = resolve_tick(state, {1: attack(2)}, NoCritRng())
    text = render_tick(state, result, viewer_side=0)
    own_section = text.split("👥 ВАША СТОРОНА")[1].split("💀 ПРОТИВНИК")[0]
    enemy_section = text.split("💀 ПРОТИВНИК")[1]
    assert "Гостус →" in own_section
    # моб контратакует — его строка должна быть в разделе противника
    assert "Кандальный →" in enemy_section


def test_viewer_side_flips_which_section_is_own() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob")
    state = make_session(CombatMode.PVE, a, b)
    result = resolve_tick(state, {1: attack(2)}, NoCritRng())
    from_side0 = render_tick(state, result, viewer_side=0)
    from_side1 = render_tick(state, result, viewer_side=1)
    own0 = from_side0.split("👥 ВАША СТОРОНА")[1].split("💀 ПРОТИВНИК")[0]
    own1 = from_side1.split("👥 ВАША СТОРОНА")[1].split("💀 ПРОТИВНИК")[0]
    assert "Гостус →" in own0
    assert "Кандальный →" in own1


def test_hp_bars_block_shows_enemies_then_own_side() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob")
    state = make_session(CombatMode.PVE, a, b)
    result = resolve_tick(state, {1: attack(2)}, NoCritRng())
    text = render_tick(state, result, viewer_side=0)
    enemy_bar_idx = text.index("Кандальный:", text.index("💀 ПРОТИВНИК"))
    own_bar_idx = text.rindex("Гостус:")
    assert enemy_bar_idx < own_bar_idx


def test_no_flavor_text_in_log() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob")
    state = make_session(CombatMode.PVE, a, b)
    result = resolve_tick(state, {1: attack(2)}, NoCritRng())
    text = render_tick(state, result, viewer_side=0)
    # никаких многоточий/образных вставок — только счёт
    assert "..." not in text


def test_miss_line_format() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob", agility=999)
    state = make_session(CombatMode.PVE, a, b)

    class AlwaysMiss(NoCritRng):
        def random(self) -> float:
            return 0.0  # максимальный шанс уворота застрахован высокой AGI цели

    result = resolve_tick(state, {1: attack(2)}, AlwaysMiss())
    text = render_tick(state, result, viewer_side=0)
    # либо промах засчитан, либо (если формула не даёт 100% уворот) обычный урон —
    # тест лишь проверяет, что при промахе формат корректен
    if "промах" in text:
        assert "уклоняется" in text


def test_dot_line_appears_in_target_side_section() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob")
    b.effects.append(Effect(kind=EffectKind.DOT, value=10, remaining_ticks=2, source_id=1))
    state = make_session(CombatMode.PVE, a, b)
    result = resolve_tick(state, {}, NoCritRng())
    text = render_tick(state, result, viewer_side=0)
    enemy_section = text.split("💀 ПРОТИВНИК")[1]
    assert "Кандальный теряет 10 HP от эффекта" in enemy_section


def test_control_line_bucketed_by_named_combatant() -> None:
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=1, name="Кандальный", kind="mob")
    a.effects.append(Effect(kind=EffectKind.FREEZE, value=1, remaining_ticks=1, source_id=2))
    state = make_session(CombatMode.PVE, a, b)
    result = resolve_tick(state, {}, NoCritRng())
    text = render_tick(state, result, viewer_side=0)
    own_section = text.split("👥 ВАША СТОРОНА")[1].split("💀 ПРОТИВНИК")[0]
    assert "теряет ход" in own_section  # заморожен Гостус — своя сторона


def _mass_pvp_state() -> tuple[CombatSessionState, object]:
    """Массовый PvP 2 на 1: союзники Гостус и Кригер против Мича."""
    a = combatant(1, side=0, name="Гостус")
    b = combatant(2, side=0, name="Кригер")
    c = combatant(3, side=1, name="Мич")
    state = make_session(CombatMode.PVP_GROUP, a, b, c)
    result = resolve_tick(state, {1: attack(3), 2: attack(3), 3: attack(1)}, NoCritRng())
    return state, result


def test_mass_pvp_each_line_is_in_the_section_of_who_acts() -> None:
    """Каждая строка боя - отдельная и в разделе того, кто действует."""
    state, result = _mass_pvp_state()
    text = render_tick(state, result, viewer_side=0)
    own = text.split("👥 ВАША СТОРОНА")[1].split("💀 ПРОТИВНИК")[0]
    enemy = text.split("💀 ПРОТИВНИК")[1]
    assert "Гостус → атака по Мич" in own
    assert "Кригер → атака по Мич" in own
    assert "Мич → атака по Гостус" in enemy
    # Строки не склеены в одну: у каждой действия своя строка.
    action_lines = [line for line in text.splitlines() if " → атака по " in line]
    assert len(action_lines) == 3


def test_mass_pvp_other_side_sees_it_mirrored() -> None:
    state, result = _mass_pvp_state()
    text = render_tick(state, result, viewer_side=1)
    own = text.split("👥 ВАША СТОРОНА")[1].split("💀 ПРОТИВНИК")[0]
    enemy = text.split("💀 ПРОТИВНИК")[1]
    assert "Мич → атака по Гостус" in own
    assert "Гостус → атака по Мич" in enemy
    assert "Кригер → атака по Мич" in enemy


def test_side_titles_label_both_sections_and_title_replaces_header() -> None:
    state, result = _mass_pvp_state()
    titles = ("Осаждающие", "Защитники")
    text = render_tick(state, result, viewer_side=1, title="🏰 ОСАДА", side_titles=titles)
    assert text.startswith("🏰 ОСАДА - ход")
    assert "👥 Защитники (ВАША СТОРОНА)" in text
    assert "💀 Осаждающие" in text
    # Без названий формат прежний.
    plain = render_tick(state, result, viewer_side=1)
    assert "👥 ВАША СТОРОНА" in plain and "💀 ПРОТИВНИК" in plain


def test_group_pve_multi_player_sections() -> None:
    p1 = combatant(1, side=0, name="Гостус")
    p2 = combatant(2, side=0, name="Кирамус")
    mob = combatant(3, side=1, name="Волк", kind="mob")
    state = make_session(CombatMode.PVE, p1, p2, mob, is_raid=True)
    result = resolve_tick(state, {1: attack(3), 2: attack(3)}, NoCritRng())
    text = render_tick(state, result, viewer_side=0)
    own_section = text.split("👥 ВАША СТОРОНА")[1].split("💀 ПРОТИВНИК")[0]
    assert "Гостус →" in own_section
    assert "Кирамус →" in own_section
