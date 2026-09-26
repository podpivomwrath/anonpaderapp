"""Способности мобов (патч 103).

Главные правила, ради которых этот файл:
  1. от добивающего удара НИЧЕГО не срабатывает - ни отражение, ни рассол,
     ни контрудар. Игрок, добивший моба, ответа не получает никогда;
  2. у мобов нет контроля - оглушение отбирает у игрока ход и только
     деморализует, владелец игры убрал его сознательно;
  3. промах не накладывает ничего.
"""

import random

import pytest

from game.combat import mob_abilities
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from game.content_loader import MobAbilityDef, MobTraitDef, load_bestiary
from game.world import encounters
from tests.conftest import combatant

BESTIARY = [m for mobs in load_bestiary().values() for m in mobs]


class _Rng(random.Random):
    """Без критов и без уворотов: random() всегда у верхней границы."""

    def random(self) -> float:
        return 0.999

    def choice(self, seq):
        return seq[0]


def _ability(*traits: MobTraitDef, title: str = "Проба") -> MobAbilityDef:
    return MobAbilityDef(title=title, hint="проба", traits=list(traits))


def _duel(ability: MobAbilityDef, player_str: int = 10, mob_vit: int = 10):
    player = combatant(1, 0, strength=player_str, vitality=30)
    mob = combatant(2, 1, kind="mob", name="Моб", strength=10, vitality=mob_vit)
    mob_abilities.prepare(mob, ability)
    session = CombatSessionState(session_id=1, mode=CombatMode.PVE)
    session.combatants = {1: player, 2: mob}
    return session, player, mob


def _attack() -> dict[int, DeclaredAction]:
    return {1: DeclaredAction(type=ActionType.ATTACK, target_id=2)}


def _skip() -> dict[int, DeclaredAction]:
    return {1: DeclaredAction(type=ActionType.SKIP)}


# --- Контент --------------------------------------------------------------------


def test_every_mob_has_an_ability() -> None:
    missing = [m.id for m in BESTIARY if m.ability is None]
    assert not missing, f"мобы без способности: {missing}"


def test_every_trait_is_a_known_mechanic() -> None:
    """Опечатка в kind не должна превратиться в моба без способности молча."""
    unknown = [
        (m.id, t.kind) for m in BESTIARY for t in m.ability.traits if t.kind not in mob_abilities.KINDS
    ]
    assert not unknown, f"неизвестные механики: {unknown}"


def test_no_mob_can_stun() -> None:
    """Контроля у мобов нет: эффекты на игрока - только яд, ослабление,
    уязвимость. FREEZE сюда не должен вернуться ни через какой kind."""
    assert "freeze" not in mob_abilities.PLAYER_EFFECTS
    assert EffectKind.FREEZE not in mob_abilities.PLAYER_EFFECTS.values()
    for mob in BESTIARY:
        for trait in mob.ability.traits:
            if trait.effect:
                assert trait.effect in mob_abilities.PLAYER_EFFECTS, (mob.id, trait.effect)


def test_center_mobs_have_two_mechanics() -> None:
    center = [m for m in BESTIARY if m.zone_min >= 60]
    assert center
    for mob in center:
        assert len(mob.ability.traits) == 2, mob.id


def test_every_ability_tells_the_player_what_it_does() -> None:
    for mob in BESTIARY:
        assert mob.ability.title.strip() and mob.ability.hint.strip(), mob.id


# --- Добивающий удар --------------------------------------------------------------


@pytest.mark.parametrize("kind", ["reflect", "brine_spray"])
def test_killing_blow_is_never_answered(kind) -> None:
    trait = MobTraitDef(kind=kind, value=0.5, threshold=0.01, duration=2)
    session, player, mob = _duel(_ability(trait), player_str=400, mob_vit=1)
    hp_before = player.current_hp

    resolve_tick(session, _attack(), _Rng())

    assert not mob.alive, "удар должен был добить моба"
    assert player.current_hp == hp_before, f"{kind}: добивающий удар получил ответ"
    assert not player.has_effect(EffectKind.DOT), f"{kind}: добивающий удар наложил яд"


def test_reflect_works_while_the_mob_survives() -> None:
    session, player, mob = _duel(_ability(MobTraitDef(kind="reflect", value=0.5)), mob_vit=200)
    hp_before = player.current_hp

    result = resolve_tick(session, _attack(), _Rng())

    assert mob.alive
    assert player.current_hp < hp_before
    assert any("возвращает урон" in line for line in result.lines)


def test_capped_mob_survives_and_still_attacks() -> None:
    """Раньше «умрёт ли моб» считалось по сырой сумме урона: моб с лимитом
    урона за удар выживал, но ход пропускал, будто умер."""
    session, player, mob = _duel(
        _ability(MobTraitDef(kind="damage_cap", value=0.15)), player_str=400, mob_vit=30,
    )
    hp_before = player.current_hp

    resolve_tick(session, _attack(), _Rng())

    assert mob.alive, "лимит 15% за удар не даёт убить с одного удара"
    assert player.current_hp < hp_before, "выживший моб обязан ударить в ответ"


# --- Промах и замах ----------------------------------------------------------------


def test_missed_hit_applies_nothing() -> None:
    trait = MobTraitDef(kind="on_hit", effect="dot", value=0.5, duration=2, chance=1.0)
    session, player, _mob = _duel(_ability(trait))
    player.apply_effect(EffectKind.DODGE, 1.0, 5, player.id)

    class _Dodge(_Rng):
        def random(self) -> float:
            return 0.0  # уворот срабатывает всегда

    resolve_tick(session, _skip(), _Dodge())

    assert not player.has_effect(EffectKind.DOT), "промах не должен поджигать"


def test_windup_warns_first_and_strikes_next_turn() -> None:
    session, player, _mob = _duel(_ability(MobTraitDef(kind="windup", period=1, mult=2.0)))
    hp_start = player.current_hp

    first = resolve_tick(session, _skip(), _Rng())
    assert player.current_hp == hp_start, "в ход замаха моб не бьёт"
    assert any("замахивается" in line for line in first.lines)

    resolve_tick(session, _skip(), _Rng())
    assert player.current_hp < hp_start, "следующим ходом - удар с замаха"


def test_control_breaks_the_windup() -> None:
    """Сбить замах - и есть ответ игрока на сильный удар.

    Сбитый замах не переносится на потом: сильного удара не будет вовсе. Моб
    при этом не теряет весь ход - он кусает как обычно. Игрок тратит контроль
    на то, чтобы сбить ОПАСНЫЙ удар, а не чтобы оставить моба без хода.
    """
    session, player, mob = _duel(_ability(MobTraitDef(kind="windup", period=99, mult=3.0)))
    mob.mob_brain.turns = 98  # следующий ход моба - 99-й, с замахом
    resolve_tick(session, _skip(), _Rng())  # замах
    mob.apply_effect(EffectKind.FREEZE, 1.0, 1, player.id)
    resolve_tick(session, _skip(), _Rng())  # моб под контролем - удара нет
    hp_before = player.current_hp

    result = resolve_tick(session, _skip(), _Rng())
    taken = hp_before - player.current_hp

    plain_session, plain_player, _ = _duel(_ability(MobTraitDef(kind="dodge", value=0.0)))
    plain_before = plain_player.current_hp
    resolve_tick(plain_session, _skip(), _Rng())
    plain_bite = plain_before - plain_player.current_hp

    assert any("замах сбит" in line for line in result.lines)
    assert taken == plain_bite, f"после сбитого замаха - обычный укус ({plain_bite}), а не {taken}"


# --- Отдельные механики --------------------------------------------------------------


def test_ignore_dodge_hits_a_perfect_dodger() -> None:
    session, player, _mob = _duel(_ability(MobTraitDef(kind="ignore_dodge")))
    player.apply_effect(EffectKind.DODGE, 1.0, 5, player.id)
    hp_before = player.current_hp

    class _Dodge(_Rng):
        def random(self) -> float:
            return 0.0

    resolve_tick(session, _skip(), _Dodge())

    assert player.current_hp < hp_before


def test_regen_heals_the_mob() -> None:
    session, _player, mob = _duel(_ability(MobTraitDef(kind="regen", value=0.10)), mob_vit=200)
    mob.current_hp = mob.max_hp // 2
    before = mob.current_hp

    resolve_tick(session, _skip(), _Rng())

    assert mob.current_hp > before


def test_last_breath_mob_line_names_its_ability() -> None:
    session, _player, mob = _duel(
        _ability(MobTraitDef(kind="last_breath"), title="Не уйду"), player_str=400, mob_vit=1,
    )
    result = resolve_tick(session, _attack(), _Rng())
    assert mob.current_hp == 1
    assert any("не уйду" in line for line in result.lines), result.lines


# --- Подключение -------------------------------------------------------------------


def test_every_spawned_mob_carries_its_ability() -> None:
    rng = random.Random(7)
    for dist in (45, 30, 15, 5, 1):
        encounter = encounters.spawn_mob(2, "ridge", 40, dist, rng)
        assert encounter.combatant.mob_brain is not None, dist
        assert encounter.ability_line and encounter.ability_line.startswith("✦ ")


def test_story_enemy_inherits_the_ability_of_its_base_mob() -> None:
    """То же правило, что с картинкой (патч 36): производная сущность берёт
    своё у базовой, если своего не задано."""
    base = next(m for m in BESTIARY if m.id == "shard_golem")
    encounter = encounters.spawn_named_enemy(
        2, "Осколочный голем-страж", "проба", 20, 1.2, base_mob_id="shard_golem",
    )
    assert encounter.combatant.mob_brain is not None
    assert encounter.combatant.mob_brain.ability.title == base.ability.title
    assert encounter.combatant.has_effect(EffectKind.SHIELD_POOL)


def test_story_enemy_without_a_base_mob_fights_plainly() -> None:
    encounter = encounters.spawn_named_enemy(2, "Безымянный", "проба", 20, 1.0)
    assert encounter.combatant.mob_brain is None
    assert encounter.ability_line is None
