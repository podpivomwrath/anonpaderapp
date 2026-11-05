"""Руины культа, этапы 2-4 (2026-11-05): дары, особые комнаты, уникальные
боссы, ларцы рун."""

import random

from sqlalchemy import select

from game import ruins as rules
from game import ruins_gifts as gifts_mod
from game.combat import ruins as rcombat
from game.combat.resolver import RenderedHit, TickResult
from game.combat.session import ActionType, CombatMode, CombatSessionState, DeclaredAction, Stats, build_combatant
from game.economy import ruins_config as rc
from models import CharacterLootbox, CharacterRune
from services import lootbox_service, ruins_service


# --- Дары ---------------------------------------------------------------------------


def test_offer_is_three_distinct_new_gifts() -> None:
    for seed in range(50):
        owned = ["whetstone", "thick_hide"]
        ids = gifts_mod.offer(random.Random(seed), owned)
        assert len(ids) == 3 and len(set(ids)) == 3 and not set(ids) & set(owned)
    assert all(gifts_mod.BY_ID[g].tier == gifts_mod.RARE
               for g in gifts_mod.offer(random.Random(1), [], (gifts_mod.RARE,)))


def test_gift_mods_add_up() -> None:
    mods = gifts_mod.mods([{"id": "whetstone"}, {"id": "vow_silence"}, {"id": "bad_blood"}])
    assert round(mods["damage_bonus"], 2) == 0.45
    assert mods["max_hp_bonus"] == -0.15


async def _solo(make_character, n: int = 1):
    out = []
    for _ in range(n):
        c = await make_character(level=60)
        c.pos_x, c.pos_y = rc.ENTRY_CELL
        out.append(c)
    return out


async def _run_in(db_session, make_character, kind: str, n: int = 1, event: str | None = None):
    chars = await _solo(make_character, n)
    run = await ruins_service.start(db_session, chars[0], chars, random.Random(1))
    rooms = dict(run.layout["rooms"])
    target = next(iter(rules.exits(run.layout, run.pos).values()))
    rooms[str(target)] = kind
    run.layout = {**run.layout, "rooms": rooms, "events": {str(target): event} if event else {}}
    ruins_service.move(run, target)
    return run, chars


async def test_take_gift_and_well_swaps(db_session, make_character) -> None:
    run, (a,) = await _run_in(db_session, make_character, rules.WELL)
    run.gifts = [{"id": "whetstone"}]
    result = await ruins_service.choose(db_session, run, a.id, "drop:whetstone", random.Random(3))
    assert len(result["offer"]) == 3 and run.offer["drop"] == "whetstone"
    ruins_service.take_gift(run, result["offer"][0])
    assert gifts_mod.ids(run.gifts) == [result["offer"][0]] and run.offer is None


async def test_spring_heals_and_altar_costs_blood(db_session, make_character) -> None:
    run, (a,) = await _run_in(db_session, make_character, rules.SPRING)
    (m,) = await ruins_service.members(db_session, run.id)
    top = await ruins_service.max_hp(db_session, a.id, run.gifts)
    m.hp = 1
    await ruins_service.choose(db_session, run, a.id, "drink", random.Random(1))
    assert m.hp == 1 + round(top * rc.SPRING_HEAL)
    assert not ruins_service.room_open(run), "источник одноразовый"

    run2, (b,) = await _run_in(db_session, make_character, rules.ALTAR)
    (m2,) = await ruins_service.members(db_session, run2.id)
    m2.hp = 5
    result = await ruins_service.choose(db_session, run2, b.id, "blood", random.Random(1))
    assert m2.hp == 1, "кровь вне боя не убивает"
    assert result["offer"] and all(gifts_mod.BY_ID[g].tier == gifts_mod.RARE for g in result["offer"])


async def test_crypt_raises_and_chapel_needs_relics(db_session, make_character) -> None:
    run, (a, b) = await _run_in(db_session, make_character, rules.CRYPT, 2)
    ma, mb = await ruins_service.members(db_session, run.id)
    mb.dead, mb.hp = True, 0
    await ruins_service.choose(db_session, run, a.id, "raise", random.Random(1))
    assert not mb.dead and mb.hp > 1

    run2, (c,) = await _run_in(db_session, make_character, rules.CHAPEL)
    (m,) = await ruins_service.members(db_session, run2.id)
    try:
        await ruins_service.choose(db_session, run2, c.id, "pray", random.Random(1))
        raise AssertionError("без реликвий в мешке нельзя")
    except ruins_service.RuinsError:
        pass
    m.bag = {"trophies": {"ash_dust": 5}}
    result = await ruins_service.choose(db_session, run2, c.id, "pray", random.Random(1))
    assert sum(m.bag["trophies"].values()) == 5 - rc.CHAPEL_PRICE and result["offer"]


async def test_storeroom_curse_lasts_one_floor(db_session, make_character) -> None:
    run, (a,) = await _run_in(db_session, make_character, rules.STOREROOM)
    result = await ruins_service.choose(db_session, run, a.id, "take", random.Random(1))
    assert result["curse"] and gifts_mod.BY_ID[result["curse"]].tier == gifts_mod.CURSED
    run.phase = ruins_service.CLEARED
    await ruins_service.next_floor(db_session, run, random.Random(2))
    assert not run.gifts, "проклятие кладовой - только на этаж"


async def test_cavein_blocks_until_resolved_and_detour_fights(db_session, make_character) -> None:
    run, (a,) = await _run_in(db_session, make_character, rules.CAVEIN)
    assert set(ruins_service.exits_now(run).values()) == {run.prev_pos}
    result = await ruins_service.choose(db_session, run, a.id, "detour", random.Random(1))
    assert result["fight"] == rules.FIGHT and run.phase == ruins_service.FIGHT


async def test_treasure_mimic_and_prisoner_gift(db_session, make_character) -> None:
    run, (a,) = await _run_in(db_session, make_character, rules.PRISONER)
    await ruins_service.choose(db_session, run, a.id, "free", random.Random(1))
    assert ruins_service.fight_kind(run) == rules.FIGHT
    await ruins_service.room_won(db_session, run, {a.id: 100}, {a.id: 0}, random.Random(1))
    assert run.offer and all(gifts_mod.BY_ID[g].tier == gifts_mod.RARE for g in run.offer["ids"])


async def test_trap_hits_or_dodges(db_session, make_character) -> None:
    run, chars = await _run_in(db_session, make_character, rules.TRAP, 3)
    dodged = await ruins_service.trap(db_session, run, random.Random(4))
    assert set(dodged) == {c.id for c in chars}
    assert run.pos in run.cleared


async def test_elite_win_offers_gift(db_session, make_character) -> None:
    run, (a,) = await _run_in(db_session, make_character, rules.ELITE)
    await ruins_service.room_won(db_session, run, {a.id: 100}, {a.id: 0}, random.Random(1))
    assert run.offer and len(run.offer["ids"]) == 3
    try:
        ruins_service.propose(run, a.id, "up", 1)
        raise AssertionError("пока дар не выбран - не идём")
    except ruins_service.RuinsError:
        pass


async def test_potions_vow_ambush_spare(db_session, make_character) -> None:
    run, _ = await _run_in(db_session, make_character, rules.AMBUSH)
    assert ruins_service.battle_potions_start(run, 0) == 5, "засада: зелья закрыты"
    run.extra = {}
    run.gifts = [{"id": "spare_vial"}]
    assert ruins_service.floor_potions(run) == 6
    assert ruins_service.battle_potions_start(run, 3) == 2, "осталось 3 на этаже - в бою 3"
    run.gifts = [{"id": "vow_silence"}]
    assert ruins_service.battle_potions_start(run, 0) == 5


# --- Первая победа над уникальным - ларцы рун --------------------------------------


async def test_first_unique_kill_gives_two_chests_once(db_session, make_character) -> None:
    (a,) = await _solo(make_character)
    run = await ruins_service.start(db_session, a, [a], random.Random(1))
    run.floor = 5
    run.pos = run.layout["boss"]
    found = await ruins_service.room_won(db_session, run, {a.id: 100}, {a.id: 0}, random.Random(1), bosses=1)
    assert found[a.id]["chests"] == rc.FIRST_KILL_CHESTS
    run.phase, run.pos = ruins_service.WALK, run.layout["boss"]
    found = await ruins_service.room_won(db_session, run, {a.id: 100}, {a.id: 0}, random.Random(1), bosses=1)
    assert "chests" not in found[a.id]
    chests = (await db_session.scalars(select(CharacterLootbox).where(CharacterLootbox.character_id == a.id))).all()
    assert len(chests) == 2 and all(c.kind == lootbox_service.RUNE for c in chests)


async def test_rune_chest_opens_runes(db_session, make_character) -> None:
    a = await make_character(level=60)
    await lootbox_service.grant_chest(db_session, a, 1, lootbox_service.RUNE)
    _chest, result = await lootbox_service.open_owned(db_session, a, None, random.Random(9), lootbox_service.RUNE)
    rows = (await db_session.scalars(select(CharacterRune).where(CharacterRune.character_id == a.id))).all()
    expected = {"dusty": 2, "dim": 3, "crimson": 3, "searing": 3, "tear": 3}[result.grade.id]
    assert sum(r.count for r in rows) == expected


# --- Уникальные боссы --------------------------------------------------------------


def _player(cid: int, hp: int = 1000):
    stats = Stats(strength=100, agility=100, intellect=100, vitality=100, will=100)
    c = build_combatant(id=cid, side=0, kind="character", name=f"И{cid}", level=60, stats=stats,
                        primary_stat="strength", base_class="warrior")
    c.current_hp = min(hp, c.max_hp)
    return c


def _boss_room(floor: int, party: int = 2, seed: int = 0):
    layout = rules.generate(random.Random(seed), floor)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for i in range(1, party + 1):
        state.add(_player(i))
    stage = rcombat.build_stage(22_000_000, layout, rules.BOSS, party, {}, random.Random(seed))
    stage.setup(state)
    return stage, state


def test_boss_rotation_and_combos() -> None:
    names = [rcombat.bosses_for_floor(f, random.Random(0))[0].key for f in (5, 10, 15, 20, 25, 30, 35)]
    assert names == ["gatekeeper", "counter", "candle", "herald", "brothers", "abbot", "gatekeeper"]
    assert [len(rcombat.bosses_for_floor(f, random.Random(0))) for f in (30, 35, 55, 60, 90)] == [1, 2, 2, 3, 4]
    assert isinstance(rcombat.build_stage(1, rules.generate(random.Random(0), 7), rules.BOSS, 1),
                      rcombat.RoomStage), "не кратный 5 - элитный хозяин"


def test_gatekeeper_buries_and_dig_frees() -> None:
    stage, state = _boss_room(5)
    gate = stage.bosses[0]
    out = None
    for _ in range(rc.GATE_EVERY):
        stage.ticks += 1
        out = stage._enemy_tick(state, TickResult(), random.Random(1))
    assert gate.buried and set(out.frozen) == set(gate.buried)
    buried = next(iter(gate.buried))
    digger = 1 if buried == 2 else 2
    assert stage.extra_buttons(state, digger) and not stage.extra_buttons(state, buried)
    assert stage.act(state, digger, "dig")
    res = TickResult(actions={digger: DeclaredAction(type=ActionType.SKIP, payload={"dig": True})})
    stage.ticks += 1
    stage._enemy_tick(state, res, random.Random(1))
    assert buried not in gate.buried


def test_counter_collects_debt() -> None:
    stage, state = _boss_room(10)
    boss_id = stage.bosses[0].boss_id
    before = state.combatants[1].current_hp
    for _ in range(rc.COUNTER_MARKS):
        res = TickResult(hit_renders=[RenderedHit(1, boss_id, 0, 1, "бьёт", 500, False, False, False, 9000, 8500, 9000)])
        stage._enemy_tick(state, res, random.Random(1))
    assert state.combatants[1].current_hp < before


def test_candles_heal_boss_and_go_out_with_her() -> None:
    stage, state = _boss_room(15)
    witch = stage.bosses[0]
    boss = state.combatants[witch.boss_id]
    boss.current_hp = boss.max_hp // 2
    stage._enemy_tick(state, TickResult(), random.Random(1))
    assert boss.current_hp > boss.max_hp // 2
    assert not set(witch.candles) & stage.reward_ids, "свечи - не награда"
    boss.current_hp = 0
    out = stage._enemy_tick(state, TickResult(), random.Random(1))
    assert out.cleared and not any(state.combatants[c].alive for c in witch.candles)


def test_herald_reflects_banned_strike() -> None:
    stage, state = _boss_room(20)
    herald = stage.bosses[0]
    stage._enemy_tick(state, TickResult(), random.Random(1))
    banned = herald.banned
    before = state.combatants[1].current_hp
    stage._enemy_tick(state, TickResult(actions={1: DeclaredAction(type=banned)}), random.Random(1))
    assert state.combatants[1].current_hp < before


def test_brothers_rage_when_uneven() -> None:
    stage, state = _boss_room(25)
    bro = stage.bosses[0]
    a, b = state.combatants[bro.boss_id], state.combatants[bro.second_id]
    b.current_hp = b.max_hp // 3
    stage._enemy_tick(state, TickResult(), random.Random(1))
    assert a.buff_modifiers.get("damage_bonus", 0) == rc.BROTHERS_RAGE
    b.current_hp = b.max_hp
    stage._enemy_tick(state, TickResult(), random.Random(1))
    assert a.buff_modifiers.get("damage_bonus", 0) == 0


def test_abbot_punishes_everyone() -> None:
    stage, state = _boss_room(30)
    abbot = stage.bosses[0]
    stage._enemy_tick(state, TickResult(), random.Random(1))
    abbot.vow = "skill"
    before = [state.combatants[i].current_hp for i in (1, 2)]
    stage._enemy_tick(state, TickResult(actions={1: DeclaredAction(type=ActionType.SKILL)}), random.Random(1))
    assert all(state.combatants[i].current_hp < before[k] for k, i in enumerate((1, 2)))


def test_prayer_saves_once() -> None:
    layout = rules.generate(random.Random(0), 1)
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    state.add(_player(1))
    state.add(_player(2))
    stage = rcombat.build_stage(22_000_000, layout, rules.FIGHT, 2, {"gifts": [{"id": "foreign_prayer"}]})
    stage.setup(state)
    state.combatants[1].current_hp = 0
    out = stage.after_tick(state, TickResult(deaths=[1]), random.Random(1))
    assert state.combatants[1].current_hp == 1 and 1 in stage.prayer_used and out.lines
    state.combatants[1].current_hp = 0
    stage.after_tick(state, TickResult(deaths=[1]), random.Random(1))
    assert state.combatants[1].current_hp == 0, "второй раз за этаж - нет"


def test_every_scene_has_a_photo() -> None:
    """Картинки руин (2026-11-05): у каждой комнаты, сценки, босса и вида мобов
    есть номер фото, лишних номеров нет."""
    from game import ruins as rules
    from game import ruins_rooms
    from game.combat import ruins as combat_ruins
    from game.economy import ruins_config as rc

    bosses = {cls.key for cls in combat_ruins.RuinBoss.__subclasses__()}
    assert bosses == set(rc.BOSS_PHOTO_KEYS)
    assert set(ruins_rooms.EVENTS) == set(rc.EVENT_PHOTO_KEYS)
    rooms = set(rules.CHOICE_ROOMS) - {rules.EVENT} | {rules.TRAP, rules.AMBUSH}
    assert rooms | {"mimic"} == set(rc.ROOM_PHOTO_KEYS)
    assert len(rc.MOB_PHOTO_KEYS) == len(rc.MOB_KINDS)
    need = {"вход", "пролог", "спуск", "выход", "гибель", *rc.ROOM_PHOTO_KEYS.values(),
            *rc.EVENT_PHOTO_KEYS.values(), *rc.BOSS_PHOTO_KEYS.values(), *rc.MOB_PHOTO_KEYS,
            *(f"{m}_элита" for m in rc.MOB_PHOTO_KEYS)}
    assert need == set(rc.PHOTOS)
    assert all(v.isdigit() for v in rc.PHOTOS.values())
