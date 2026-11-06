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
    assert round(mods["direct_damage_bonus"], 2) == 0.45
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


async def test_closed_potions_name_the_real_reason(db_session, make_character) -> None:
    """Репорт 2026-11-06: в засаде сумка писала «лимит 5 за бой исчерпан»,
    и игрок искал у себя проклятие. Причина - своя строка в окне зелий."""
    from game.combat import consumable_limit

    run, _ = await _run_in(db_session, make_character, rules.AMBUSH)
    note = ruins_service.potions_closed_text(run, 0)
    assert note and "ЗАСАДА" in note and "‼️" in note
    run.extra = {}
    assert ruins_service.potions_closed_text(run, 2) is None, "зелья есть - причины нет"
    assert "этаж" in ruins_service.potions_closed_text(run, 5)
    run.gifts = [{"id": "vow_silence"}]
    assert "Обет" in ruins_service.potions_closed_text(run, 0)

    class _C:
        consumables_used = consumable_limit.LIMIT
        potions_closed_text = note

    assert note in consumable_limit.items_header(_C())
    _C.potions_closed_text = None
    assert consumable_limit.EXHAUSTED_TEXT in consumable_limit.items_header(_C())


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


def test_gatekeeper_solo_skips_one_turn_per_burial() -> None:
    """2026-11-05 (Дедушка_Ау): одиночку засыпало, а выбирался он только
    после второго пропуска - и сразу под новый завал, ходил 1 раз из 3.
    Теперь: засыпало - один пропущенный ход - свободен."""
    stage, state = _boss_room(5, party=1)
    frozen_ticks = []
    for tick in range(1, 4 * rc.GATE_EVERY + 1):
        stage.ticks = tick
        out = stage._enemy_tick(state, TickResult(), random.Random(1))
        state.combatants[1].current_hp = state.combatants[1].max_hp  # не дать погибнуть
        if 1 in out.frozen:
            frozen_ticks.append(tick + 1)  # пропускается следующий ход
    assert frozen_ticks == [t + 1 for t in range(rc.GATE_EVERY, 4 * rc.GATE_EVERY + 1, rc.GATE_EVERY)]


def test_counter_collects_debt() -> None:
    stage, state = _boss_room(10)
    boss_id = stage.bosses[0].boss_id
    before = state.combatants[1].current_hp
    for _ in range(rc.COUNTER_MARKS):
        res = TickResult(hit_renders=[RenderedHit(1, boss_id, 0, 1, "бьёт", 500, False, False, False, 9000, 8500, 9000)])
        out = stage._enemy_tick(state, res, random.Random(1))
    assert state.combatants[1].current_hp < before
    # Репорт 322 (2026-11-06): сколько взыскал - в логе.
    assert any("взыскивает долг" in x and x.rstrip().endswith("урона") for x in out.lines), out.lines


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
    """Возвращает только удар по врагу объявленным видом. 2026-11-06, баг:
    бил и за Глухую оборону - защитный навык тоже считался «навыком»."""
    from game.combat.session import ActionType

    stage, state = _boss_room(20)
    herald = stage.bosses[0]
    boss_id = herald.boss_id

    def strike(cid):
        return RenderedHit(cid, boss_id, 0, 1, "бьёт", 100, False, False, False, 9000, 8900, 9000)

    for banned, action in ((ActionType.ATTACK, DeclaredAction(type=ActionType.ATTACK)),
                           (ActionType.SKILL, DeclaredAction(type=ActionType.SKILL, skill_id="warrior_stagger"))):
        herald.banned = banned
        before = state.combatants[1].current_hp
        res = TickResult(actions={1: action}, hit_renders=[strike(1)])
        stage._enemy_tick(state, res, random.Random(1))
        assert state.combatants[1].current_hp < before, banned
        state.combatants[1].current_hp = state.combatants[1].max_hp
    herald.banned = ActionType.SKILL
    before = state.combatants[1].current_hp
    guard = DeclaredAction(type=ActionType.SKILL, skill_id="guardian_block")
    stage._enemy_tick(state, TickResult(actions={1: guard}), random.Random(1))
    assert state.combatants[1].current_hp == before, "защитный навык без удара - не в счёт"


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


def test_raven_letter_once_before_mentor_intro() -> None:
    """Ворон с письмом (2026-11-05): с 60 уровня, один раз и только пока
    наставник ещё не дал задание о руинах."""
    from types import SimpleNamespace

    from services import story_service

    hero = SimpleNamespace(level=59, ui_flags={})
    assert not story_service.ruins_raven_due(hero)
    hero.level = 60
    assert story_service.ruins_raven_due(hero)
    story_service.mark_ruins_raven(hero)
    assert not story_service.ruins_raven_due(hero)
    took = SimpleNamespace(level=60, ui_flags={"ruins_intro": True})
    assert not story_service.ruins_raven_due(took)


def test_room_keyboard_passes_vk_limits(monkeypatch) -> None:
    """2026-11-05: ссылка на мини-апп стояла третьей в ряду с мешком и
    группой - VK (ошибка 911) отклонял каждое сообщение руин. Ряд со ссылкой -
    не больше 2 кнопок, рядов не больше 5, в каждом состоянии комнаты."""
    import json
    import random
    from types import SimpleNamespace

    from bot.handlers import ruins as handler
    from config import get_settings
    from game import ruins as rules
    from services import ruins_service

    monkeypatch.setattr(get_settings(), "vk_miniapp_url", "https://vk.com/app1")
    seen_link = False
    for seed in range(40):
        layout = rules.generate(random.Random(seed), 1)
        for pos in rules.rooms_of(layout):
            for leader, pending, phase, offer, vote, gifts in (
                (1, None, ruins_service.WALK, None, None, []),
                (2, None, ruins_service.WALK, None, None, []),
                (1, {"dir": "up", "to": pos, "ok": []}, ruins_service.WALK, None, None, []),
                (1, None, ruins_service.CLEARED, None, {"target": 3, "yes": [], "no": []}, []),
                (1, None, ruins_service.WALK, {"ids": ["rusty_nail", "stone_skin", "blood_debt"]}, None, []),
                (1, None, ruins_service.WALK, None, {"target": 3, "yes": [], "no": []},
                 [{"id": g} for g in ("rusty_nail", "stone_skin", "blood_debt", "miner_pick")]),
            ):
                run = SimpleNamespace(leader_id=leader, offer=offer, phase=phase, pending=pending, layout=layout,
                                      pos=pos, prev_pos=None, cleared=[], visited=[pos], gifts=gifts, vote=vote, extra={})
                rows = json.loads(handler._room_keyboard(run, 1))["buttons"]
                assert len(rows) <= 5
                for row in rows:
                    if any(b["action"]["type"] == "open_link" for b in row):
                        seen_link = True
                        assert len(row) <= 2
                    assert len(row) <= 5
    assert seen_link


def test_no_model_reads_right_after_rollback() -> None:
    """2026-11-05: «Пожертвовать» без реликвий ломало игру - отказ собирал
    клавиатуру из забега ПОСЛЕ db.rollback(), поля были просрочены, и чтение
    шло в базу вне сессии (greenlet_spawn). Игрок видел «кнопка устарела»."""
    import re
    from pathlib import Path

    lines = Path("bot/handlers/ruins.py").read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if "await db.rollback()" not in line:
            continue
        indent = len(line) - len(line.lstrip())
        for nxt in lines[i + 1:i + 4]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) < indent:
                break
            assert not re.search(r"\b(run|character|member)\.", nxt), f"строка {i + 1}: {nxt.strip()}"


def test_no_waiting_message_without_allies(monkeypatch) -> None:
    """2026-11-05 (Пётр Филиппов): одиночке в руинах пришло «Ожидание
    остальных». Сообщение - только если есть живой союзник без хода."""
    from types import SimpleNamespace

    from bot.handlers import raid_combat

    alive = SimpleNamespace(alive=True)
    dead = SimpleNamespace(alive=False)
    solo = SimpleNamespace(participants={1: object()})
    monkeypatch.setattr(raid_combat, "_live_state", lambda bid, b: {1: alive, 2: alive, 3: dead})
    monkeypatch.setitem(raid_combat._declared_this_tick, -999, {1})
    assert not raid_combat._others_pending(-999, solo, 1)
    duo = SimpleNamespace(participants={1: object(), 2: object()})
    assert raid_combat._others_pending(-999, duo, 1)
    raid_combat._declared_this_tick[-999].add(2)
    assert not raid_combat._others_pending(-999, duo, 1)
    with_dead = SimpleNamespace(participants={1: object(), 3: object()})
    assert not raid_combat._others_pending(-999, with_dead, 1)


def test_ruins_mobs_use_the_exploration_level_curve() -> None:
    """2026-11-05, владелец: разница уровней в руинах - точно как в
    исследовании (LVL_DIFF_FIELD_*), но «Тяжёлый взгляд» мобов руин не режет."""
    from game.combat import formulas, shared_rules

    for floor, room in ((1, rules.FIGHT), (7, rules.ELITE), (5, rules.BOSS)):
        stage, state = _boss_room(floor) if room == rules.BOSS else (None, None)
        if stage is None:
            layout = rules.generate(random.Random(0), floor)
            state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
            state.add(_player(1))
            stage = rcombat.build_stage(22_000_000, layout, room, 1, {}, random.Random(0))
            stage.setup(state)
        mobs = [c for c in state.combatants.values() if c.kind == "mob"]
        assert mobs and all(m.field_curve and not m.field_mob for m in mobs), (floor, room)
        mob = mobs[0]
        assert formulas.level_diff_modifiers(mob.level, 60, mob.field_curve) == \
            formulas.level_diff_modifiers(mob.level, 60, True)
        hp = mob.max_hp
        state.combatants[1].buff_modifiers["rune:heavy_gaze"] = 0.06
        shared_rules.rune_gaze(state)
        assert mob.max_hp == hp


def test_candle_wax_boosts_burn_and_poison() -> None:
    """2026-11-05, владелец: бонус к урону ядом - бонус ко всему урону за ход,
    горение Элементалиста тоже."""
    from game import ruins_gifts
    from game.combat import shared_rules
    from game.combat.session import BURN_TAG, Effect, EffectKind

    src, tgt = _player(1), _player(2)
    src.buff_modifiers.update(ruins_gifts.mods([{"id": "candle_wax"}]))
    for tag in (BURN_TAG, None):
        effect = Effect(kind=EffectKind.DOT, value=100, remaining_ticks=3, source_id=1, stacks=1, tag=tag)
        plain = shared_rules.poison_tick_damage(effect, _player(3), tgt)
        assert shared_rules.poison_tick_damage(effect, src, tgt) == round(plain * 1.25), tag


def test_party_over_three_makes_enemies_tougher() -> None:
    """2026-11-06, владелец: мобов от трёх игроков всегда 5, поэтому за 4-го
    и 5-го - здоровье и урон противников. Уникальным боссам - только урон:
    здоровье у них и так растёт с группой."""
    from game.combat.session import CombatMode, CombatSessionState

    def mobs(room: str, party: int, floor: int = 1):
        layout = rules.generate(random.Random(0), floor)
        state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
        for i in range(1, party + 1):
            state.add(_player(i))
        stage = rcombat.build_stage(22_000_000, layout, room, party, {}, random.Random(0))
        stage.setup(state)
        return [c for c in state.combatants.values() if c.kind == "mob"]

    base, four, five = (mobs(rules.FIGHT, n)[0] for n in (3, 4, 5))
    assert len(mobs(rules.FIGHT, 5)) == len(mobs(rules.FIGHT, 3))
    assert four.max_hp > base.max_hp and five.max_hp > four.max_hp
    assert sum(base.stats.__dict__.values()) < sum(five.stats.__dict__.values())
    b3, b5 = mobs(rules.BOSS, 3, floor=5)[0], mobs(rules.BOSS, 5, floor=5)[0]
    hp_ratio = b5.max_hp / b3.max_hp
    expected = (1 + rc.UNIQUE_HP_PER_PLAYER * 4) / (1 + rc.UNIQUE_HP_PER_PLAYER * 2)
    assert abs(hp_ratio - expected) < 0.05, "здоровье уникального босса - только своей формулой, без двойного"
