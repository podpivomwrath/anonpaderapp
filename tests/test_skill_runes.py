"""Руны-навыки (2026-11-10): руна = навык, 3 слота, ступени, огранки,
пассивки подклассов, 10 новых навыков. Документ - output/skill_runes_design.md."""

import random

import pytest

from game.combat import skill_catalog
from game.combat.resolver import resolve_tick
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, EffectKind
from game.combat.skills import DEFENSIVE_SKILLS, OFFENSIVE_SKILLS
from game.economy import ability_config as ac
from game.economy import runes_config as rc
from game.world import world_config as wc
from services import rune_service
from tests.conftest import NoCritRng, combatant


def _session(*combatants, mode=CombatMode.PVP_GROUP) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=mode)
    for c in combatants:
        state.add(c)
    return state


def _skill(skill_id: str, target_id: int | None = None) -> DeclaredAction:
    return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=target_id)


def _equip(c, *skill_ids: str) -> None:
    for i, sid in enumerate(skill_ids):
        c.buff_modifiers[skill_catalog.ability_key(sid)] = i + 1


def _home(character) -> None:
    character.region = "ridge"
    character.pos_x, character.pos_y = wc.CITY_COORDS["ridge"]


# --- Каталог -----------------------------------------------------------------------


def test_every_skill_is_a_rune_with_a_handler_and_steps() -> None:
    assert len(skill_catalog.ALL_SKILL_DEFS) == 38
    for sid in skill_catalog.ALL_SKILL_DEFS:
        assert sid in OFFENSIVE_SKILLS or sid in DEFENSIVE_SKILLS, sid
        assert sid in ac.BY_ID, sid
        rune = rc.BY_ID[sid]
        assert rune.kind == rc.ABILITY and rune.ready, sid
        ability = ac.BY_ID[sid]
        assert ability.one.text and ability.two.text and ability.four.text, sid
        assert all(s.text for s in ability.fork), sid


def test_rune_ids_and_socket_keys_fit_db_columns() -> None:
    """SQLite в тестах длину строк не проверяет, Postgres - проверяет: на
    выкатке 2026-11-11 «blood_knight_lifesteal_strike» не влез в String(24)."""
    from models import CharacterRune, CharacterRuneMastery, CharacterRuneSlot

    longest = max(len(r.id) for r in rc.RUNES)
    for model in (CharacterRune, CharacterRuneMastery, CharacterRuneSlot):
        assert longest <= model.__table__.c.rune_id.type.length, model
    socket = max(len(f"{sid}:1") for sid in skill_catalog.ALL_SKILL_DEFS)
    assert socket <= CharacterRuneSlot.__table__.c.slot.type.length
    assert max(len(k) for k in rc.KINDS) <= CharacterRuneSlot.__table__.c.kind.type.length


def test_merged_duplicates_are_gone() -> None:
    for sid in ("mage_shard_volley", "mage_ice_bonds", "mage_blood_seal", "guardian_stonegrip",
                "shadow_blade_shadow_dance"):
        assert sid not in skill_catalog.ALL_SKILL_DEFS


def test_starter_runes_are_real_skills_and_mage_starts_with_fire() -> None:
    for skills in skill_catalog.STARTER_SKILLS.values():
        assert len(skills) == 3 and all(s in skill_catalog.ALL_SKILL_DEFS for s in skills)
    assert skill_catalog.STARTER_SKILLS["mage"][0] == "elementalist_fire"


def test_step_thresholds_follow_the_mastery_curve() -> None:
    assert ac.step_thresholds("normal") == (25, 81, 800, 3200)
    assert ac.step_thresholds("tight") == (50, 162, 1600, 6400)
    assert ac.step_thresholds("very_tight") == (100, 324, 3200, 12800)
    assert ac.step_of("warrior_cleave", 24) == 0
    assert ac.step_of("warrior_cleave", 81) == 2
    assert ac.step_of("reckoning", 3200) == 3  # мифическая - кривая вчетверо туже


# --- Модификаторы бойца --------------------------------------------------------------


def test_steps_add_up_and_fork_is_chosen() -> None:
    effects = {"ability:warrior_cleave": 1, "step:warrior_cleave": 3, "fork:warrior_cleave": 2}
    mods = ac.combat_modifiers(effects, None)
    assert mods["skill_bonus:warrior_cleave"] == pytest.approx(0.15)
    assert mods["skill_crit:warrior_cleave"] == pytest.approx(0.10)
    assert "skill_fresh:warrior_cleave" in mods and "skill_splash:warrior_cleave" not in mods
    assert "skill_twice:warrior_cleave" not in mods  # пробуждения ещё нет


def test_awakening_is_half_in_pvp() -> None:
    effects = {"ability:warrior_cleave": 1, "step:warrior_cleave": 4}
    assert ac.combat_modifiers(effects, None)["skill_twice:warrior_cleave"] == pytest.approx(1.0)
    assert ac.combat_modifiers(effects, None, pvp=True)["skill_twice:warrior_cleave"] == pytest.approx(0.5)


def test_passive_of_subclass_is_added() -> None:
    mods = ac.combat_modifiers({}, "dark_mystic")
    assert mods["ally_heal_power"] == pytest.approx(0.25)
    assert ac.combat_modifiers({}, None) == {}


def test_tuned_moves_numbers_of_any_skill() -> None:
    actor = combatant(1, side=0)
    actor.buff_modifiers.update({"skill_cd:shadow_blade_execute": 1, "skill_bonus:shadow_blade_execute": 0.2})
    tuned = skill_catalog.tuned(actor, "shadow_blade_execute")
    base = skill_catalog.ALL_SKILL_DEFS["shadow_blade_execute"]
    assert tuned.cd == base.cd - 1 and tuned.multiplier == pytest.approx(base.multiplier + 0.2)
    assert skill_catalog.tuned(combatant(2, side=0), "shadow_blade_execute") is base


# --- Бой -----------------------------------------------------------------------------


@pytest.mark.real_abilities
def test_skill_without_its_rune_becomes_an_attack() -> None:
    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=500)
    _equip(me, "warrior_cleave")
    resolve_tick(_session(me, foe), {1: _skill("shadow_blade_execute", 2)}, NoCritRng())
    assert not me.is_on_cooldown("shadow_blade_execute")
    resolve_tick(_session(me, foe), {1: _skill("warrior_cleave", 2)}, NoCritRng())
    assert me.is_on_cooldown("warrior_cleave")


@pytest.mark.real_abilities
def test_silence_turns_skills_into_attacks() -> None:
    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=500)
    _equip(me, "warrior_cleave")
    me.apply_effect(EffectKind.SILENCE, 1.0, 2, foe.id)
    resolve_tick(_session(me, foe), {1: _skill("warrior_cleave", 2)}, NoCritRng())
    assert not me.is_on_cooldown("warrior_cleave")


def _damage(mods: dict, skill_id: str = "warrior_cleave") -> int:
    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=500)
    me.buff_modifiers.update(mods)
    before = foe.current_hp
    resolve_tick(_session(me, foe), {1: _skill(skill_id, 2)}, NoCritRng())
    return before - foe.current_hp


def test_mastery_power_makes_the_skill_stronger() -> None:
    assert _damage({"rune:warrior_cleave": 0.2}) > _damage({})


def test_step_execute_and_splash() -> None:
    me = combatant(1, side=0)
    foes = [combatant(2, side=1, vitality=500), combatant(3, side=1, vitality=500)]
    me.buff_modifiers["skill_splash:warrior_cleave"] = 0.5
    state = _session(me, *foes)
    resolve_tick(state, {1: _skill("warrior_cleave", 2)}, NoCritRng())
    assert foes[1].current_hp < foes[1].max_hp, "задевает второго"


def test_step_shield_and_reset_on_kill() -> None:
    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=1)
    me.buff_modifiers.update({"skill_shield:shadow_blade_execute": 0.1,
                              "skill_reset_kill:shadow_blade_execute": 1.0})
    foe.current_hp = 1
    resolve_tick(_session(me, foe), {1: _skill("shadow_blade_execute", 2)}, NoCritRng())
    assert any(e.kind == EffectKind.SHIELD_POOL for e in me.effects)
    assert not me.is_on_cooldown("shadow_blade_execute"), "добил - перезарядка сброшена"


# --- Новые навыки --------------------------------------------------------------------


def test_bitter_wound_cuts_healing() -> None:
    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=500)
    resolve_tick(_session(me, foe), {1: _skill("bitter_wound", 2)}, NoCritRng())
    assert foe.heal_reduction() == pytest.approx(0.5)
    from game.combat import shared_rules

    assert shared_rules.recovered(foe, 100) == 50


def test_shatter_breaks_shield_and_hits_harder() -> None:
    plain = _damage({}, "shatter")
    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=500)
    foe.apply_effect(EffectKind.SHIELD_POOL, 5, 3, foe.id)
    before = foe.current_hp
    resolve_tick(_session(me, foe), {1: _skill("shatter", 2)}, NoCritRng())
    assert not any(e.kind == EffectKind.SHIELD_POOL and e.value > 0 for e in foe.effects)
    assert before - foe.current_hp > plain


def test_mute_silences_on_success() -> None:
    class Always(NoCritRng):
        def random(self) -> float:
            return 0.99  # мимо сопротивления (rng < resist)

    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=500, will=0)
    resolve_tick(_session(me, foe, mode=CombatMode.PVE), {1: _skill("mute", 2)}, Always())
    assert foe.has_effect(EffectKind.SILENCE)


def test_counter_strike_reflects() -> None:
    me, foe = combatant(1, side=0, vitality=500), combatant(2, side=1, vitality=500)
    resolve_tick(_session(me, foe), {1: _skill("counter_strike"), 2: DeclaredAction(
        type=ActionType.ATTACK, target_id=1)}, NoCritRng())
    assert foe.current_hp < foe.max_hp


def test_breather_shortens_other_cooldowns() -> None:
    me, foe = combatant(1, side=0), combatant(2, side=1)
    me.cooldowns["warrior_cleave"] = 3
    resolve_tick(_session(me, foe), {1: _skill("breather")}, NoCritRng())
    assert me.cooldowns["warrior_cleave"] < 3
    assert me.is_on_cooldown("breather")


def test_cover_ally_takes_part_of_the_damage() -> None:
    guard, friend = combatant(1, side=0, vitality=200), combatant(3, side=0, vitality=200)
    foe = combatant(2, side=1, strength=60)
    friend.current_hp = friend.max_hp // 2
    state = _session(guard, friend, foe)
    resolve_tick(state, {1: _skill("cover_ally"), 3: DeclaredAction(type=ActionType.DEFEND),
                         2: DeclaredAction(type=ActionType.ATTACK, target_id=3)}, NoCritRng())
    assert friend.has_effect(EffectKind.COVERED)
    resolve_tick(state, {1: DeclaredAction(type=ActionType.DEFEND), 3: DeclaredAction(type=ActionType.DEFEND),
                         2: DeclaredAction(type=ActionType.ATTACK, target_id=3)}, NoCritRng())
    assert guard.current_hp < guard.max_hp, "часть удара по союзнику досталась прикрывшему"


def test_close_ranks_shields_the_whole_side() -> None:
    me, friend, foe = combatant(1, side=0), combatant(3, side=0), combatant(2, side=1)
    friend.current_hp = friend.max_hp // 5
    resolve_tick(_session(me, friend, foe), {1: _skill("close_ranks")}, NoCritRng())
    assert all(any(e.kind == EffectKind.SHIELD_POOL for e in c.effects) for c in (me, friend))


def test_reckoning_grows_with_damage_taken() -> None:
    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=500)
    weak = _damage({}, "reckoning")
    me.taken_total = 10_000
    before = foe.current_hp
    resolve_tick(_session(me, foe), {1: _skill("reckoning", 2)}, NoCritRng())
    assert before - foe.current_hp > weak
    assert me.taken_total == 0, "счётчик обнулён"


def test_cleanse_water_removes_a_bad_effect_and_blocks_control_this_turn() -> None:
    class Lands(NoCritRng):
        def random(self) -> float:
            return 0.99  # оглушение прошло бы мимо сопротивления

    me, foe = combatant(1, side=0, will=0), combatant(2, side=1)
    me.apply_effect(EffectKind.WEAKEN, 0.2, 3, foe.id)
    resolve_tick(_session(me, foe, mode=CombatMode.PVE),
                 {1: _skill("cleanse_water"), 2: _skill("warrior_stagger", 1)}, Lands())
    assert not me.has_effect(EffectKind.WEAKEN)
    assert not me.has_effect(EffectKind.FREEZE), "оглушение того же хода не прошло"


def test_strip_veil_removes_a_good_effect() -> None:
    me, foe = combatant(1, side=0), combatant(2, side=1, vitality=500)
    foe.apply_effect(EffectKind.DAMAGE_BUFF, 0.2, 3, foe.id)
    resolve_tick(_session(me, foe), {1: _skill("strip_veil", 2)}, NoCritRng())
    assert not foe.has_effect(EffectKind.DAMAGE_BUFF)


# --- Слоты и огранки -------------------------------------------------------------------


async def test_ability_slots_facets_and_fork(db_session, make_character) -> None:
    character = await make_character(level=30)
    _home(character)
    await rune_service.grant(db_session, character.id, "warrior_cleave", 1)
    await rune_service.grant(db_session, character.id, "press", 2)
    await rune_service.equip(db_session, character, rc.ABILITY, "0", "warrior_cleave")
    assert skill_catalog.skill_ids_of(character.rune_effects) == ["warrior_cleave"]
    assert [s.id for s in rune_service.skills_of(character)] == ["warrior_cleave"]
    # Огранка - первое гнездо открыто, второе - только со ступени II.
    await rune_service.equip(db_session, character, rc.SKILL, "warrior_cleave:0", "press")
    with pytest.raises(rune_service.RuneError):
        await rune_service.equip(db_session, character, rc.SKILL, "warrior_cleave:1", "press")
    # Развилка - только с третьей ступени.
    with pytest.raises(rune_service.RuneError):
        await rune_service.choose_fork(db_session, character, "warrior_cleave", 1)
    await rune_service.grant(db_session, character.id, "warrior_cleave", 800)
    await rune_service.absorb(db_session, character, "warrior_cleave", 800)
    assert character.rune_effects["step:warrior_cleave"] == 3
    assert character.rune_effects["rune:warrior_cleave"] > 0.1
    await rune_service.choose_fork(db_session, character, "warrior_cleave", 2)
    assert character.rune_effects["fork:warrior_cleave"] == 2
    # Сняли навык - огранка вернулась в сумку.
    await rune_service.unequip(db_session, character, rc.ABILITY, "0")
    assert (await rune_service.bag(db_session, character.id)).get("press") == 2
    assert skill_catalog.skill_ids_of(character.rune_effects) == []


async def test_same_skill_cannot_take_two_slots(db_session, make_character) -> None:
    character = await make_character()
    _home(character)
    await rune_service.grant(db_session, character.id, "warrior_cleave", 2)
    await rune_service.equip(db_session, character, rc.ABILITY, "0", "warrior_cleave")
    with pytest.raises(rune_service.RuneError):
        await rune_service.equip(db_session, character, rc.ABILITY, "1", "warrior_cleave")


def test_runes_drop_from_one_pool_weighted_by_rarity_only() -> None:
    """2026-11-11, владелец: долей видов нет - полный рандом по всем рунам."""
    rng = random.Random(1)
    rolled = [rc.BY_ID[rune_service.roll_rune(rng)] for _ in range(20000)]
    ready = [r for r in rc.RUNES if r.ready]
    weight = {r.id: rc.RARITY_WEIGHTS[r.rarity] for r in ready}
    share = sum(weight[r.id] for r in ready if r.kind == rc.ABILITY) / sum(weight.values())
    got = sum(1 for r in rolled if r.kind == rc.ABILITY) / len(rolled)
    assert abs(got - share) < 0.02


async def test_starter_runes_are_given_once_and_equipped(db_session, make_character) -> None:
    character = await make_character(base_class="mage")
    given = await rune_service.grant_starter(db_session, character)
    assert given == list(skill_catalog.STARTER_SKILLS["mage"])
    assert skill_catalog.skill_ids_of(character.rune_effects) == given
    assert await rune_service.grant_starter(db_session, character) == []


# --- Масштаб от характеристик (2026-11-11) ------------------------------------------


def _fighter(**stats):
    from game.combat.session import Stats, build_combatant

    s = Stats()
    for key, value in stats.items():
        setattr(s, key, value)
    return build_combatant(id=1, side=0, kind="character", name="Боец", level=40, stats=s, primary_stat="str")


def test_home_class_hits_as_before() -> None:
    """Проценты подобраны так, что «родной» класс бьёт как раньше."""
    from game.combat import formulas, stat_model
    from game.combat.skills import skill_damage_unit

    warrior = _fighter(strength=90, intellect=10)
    old = formulas.damage(warrior.tier_mult, stat_model.ACTIVE.primary_value(90, 40, True, "str"), 2.0)
    assert skill_damage_unit(warrior, "warrior_cleave") == pytest.approx(old)


def test_skill_hits_from_its_own_stats() -> None:
    """Воин с Огненной плетью бьёт от Интеллекта, а не от Силы."""
    from game.combat.skills import skill_damage_unit

    strong, clever = _fighter(strength=90, intellect=10), _fighter(strength=10, intellect=90)
    assert skill_damage_unit(strong, "warrior_cleave") > skill_damage_unit(clever, "warrior_cleave")
    assert skill_damage_unit(clever, "elementalist_fire") > skill_damage_unit(strong, "elementalist_fire")
    assert skill_damage_unit(strong, "attack") is None  # обычная атака - как прежде


def test_mastery_grows_the_stat_percent() -> None:
    from game.combat.skills import skill_damage_unit

    me = _fighter(strength=90)
    plain = skill_damage_unit(me, "warrior_cleave")
    me.buff_modifiers["rune:warrior_cleave"] = 0.1
    assert skill_damage_unit(me, "warrior_cleave") > plain
    assert ac.scaling("warrior_cleave", 1.65, 0.1)["str"] == pytest.approx(3.63)


def test_every_damage_skill_has_its_stats() -> None:
    for sid, skill in skill_catalog.ALL_SKILL_DEFS.items():
        if skill.multiplier > 0:
            assert sid in ac.SCALING_SHARES, sid
            assert sum(ac.SCALING_SHARES[sid].values()) == pytest.approx(1.0), sid


def test_card_shows_stat_percent_and_damage() -> None:
    """Карточка навыка в мини-аппе: «330% Силы (у вас 72) -> урон N»."""
    from types import SimpleNamespace

    from bot import miniapp_runes_api as api

    hero = SimpleNamespace(rune_effects={}, level=40, subclass=None, subclass_declined=False, base_class="warrior")
    weak = api._scaling_info("warrior_cleave", 0, hero, {"str": 20})
    strong = api._scaling_info("warrior_cleave", 0, hero, {"str": 72})
    assert strong["scaling"] == [{"stat": "str", "title": "Силы", "pct": 330, "have": 72}]
    assert strong["damage"] > weak["damage"]
    assert api._scaling_text(rc.BY_ID["dark_mystic_drain"], 0) == "192% Воли и 128% Интеллекта"


def test_new_facets_squint_and_finisher() -> None:
    """Огранки «Прищур» (крит навыком) и «Добивание» (по раненой цели)."""
    assert rc.BY_ID["squint"].kind == rc.SKILL and rc.BY_ID["finisher"].kind == rc.SKILL
    low = combatant(2, side=1, vitality=500)
    low.current_hp = low.max_hp // 5
    me = combatant(1, side=0)
    me.buff_modifiers["rune:finisher@warrior_cleave"] = 0.25
    from game.combat.skills import skill_step_bonus

    assert skill_step_bonus(me, low, "warrior_cleave") == pytest.approx(0.25)


# --- Перевод живых персонажей (2026-11-11, без вайпа) ------------------------------


async def test_migration_turns_old_skills_into_runes(db_session, make_character) -> None:
    import sys

    sys.path.insert(0, "tools")
    import migrate_skill_runes as mig
    from sqlalchemy import select

    from models import Wallet
    from models.character import CharacterBuffPreset
    from models.subclass_trial import CharacterUnlockedBuff

    character = await make_character(level=40, subclass="guardian")
    character.rune_skill_slots = ["guardian_block"]
    db_session.add_all([
        # огранка на слитом навыке - навык встаёт в слот первым, огранка едет с ним
        rc_slot(character.id, "guardian_stonegrip:0", "cold_count"),
        rc_slot(character.id, "guardian_block:1", "press"),
        CharacterUnlockedBuff(character_id=character.id, buff_id="guardian_guard"),
        CharacterBuffPreset(character_id=character.id, name="П", buff_ids=[], is_active=True,
                            runes=[{"kind": "hero", "slot": "0", "rune_id": "ash_skin"},
                                   {"kind": "skill", "slot": "guardian_stonegrip:0", "rune_id": "cold_count"}]),
    ])
    await db_session.flush()
    report = await mig.migrate_one(db_session, character, apply=True)
    assert report["equip"] == ["guardian_shield_bash", "guardian_block", "warrior_stagger"]
    assert report["spare"] == ["guardian_unbreakable"]
    assert skill_catalog.skill_ids_of(character.rune_effects) == report["equip"]
    bag = await rune_service.bag(db_session, character.id)
    assert bag["guardian_unbreakable"] == 1 and bag["press"] == 1
    assert bag[trial_reward("guardian_guard")] >= 1
    slots = {(r.kind, r.slot): r.rune_id for r in await rune_service.slots(db_session, character.id)}
    assert slots[(rc.SKILL, "warrior_stagger:0")] == "cold_count"
    wallet = await db_session.scalar(select(Wallet).where(Wallet.character_id == character.id))
    assert wallet.farm_currency == mig.OLD_SLOT_PRICE and character.rune_skill_slots == []
    preset = await db_session.scalar(select(CharacterBuffPreset).where(CharacterBuffPreset.character_id == character.id))
    assert {"kind": rc.SKILL, "slot": "warrior_stagger:0", "rune_id": "cold_count"} in preset.runes
    assert [e["rune_id"] for e in preset.runes if e["kind"] == rc.ABILITY] == report["equip"]
    # повторный запуск ничего не делает
    assert await mig.migrate_one(db_session, character, apply=True) is None


async def test_old_preset_layout_keeps_skills(db_session, make_character) -> None:
    """Раскладка пресета без рун-навыков (сохранена до переделки) не снимает навыки."""
    character = await make_character(base_class="mage")
    _home(character)
    await rune_service.grant_starter(db_session, character)
    await rune_service.grant(db_session, character.id, "ash_skin", 1)
    missing = await rune_service.apply_layout(db_session, character, [{"kind": "hero", "slot": "0", "rune_id": "ash_skin"}])
    assert missing == 0
    assert skill_catalog.skill_ids_of(character.rune_effects) == list(skill_catalog.STARTER_SKILLS["mage"])


def rc_slot(character_id: int, slot: str, rune_id: str):
    from models import CharacterRuneSlot

    return CharacterRuneSlot(character_id=character_id, kind=rc.SKILL, slot=slot, rune_id=rune_id)


def trial_reward(buff_id: str) -> str:
    from services import trial_service

    return trial_service.reward_rune(buff_id)
