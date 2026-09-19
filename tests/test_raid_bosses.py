"""Патч 53: чистая логика рейд-боссов «Кукольный театр» — построение
участников, порядок убийства Вельдов, скриптованный ИИ Хирурга."""

import random


from game.combat import raid_bosses as rb
from game.combat.session import CombatMode, CombatSessionState, EffectKind, Stats, build_combatant
from game.economy import raid_config as rc


class DeterministicRng(random.Random):
    """random() всегда 0.0 (никогда не резист/не уворот/не промах),
    choice — первый элемент."""

    def random(self) -> float:
        return 0.0

    def choice(self, seq):
        return seq[0]


def make_player(id: int, side: int = 0, **stat_overrides) -> "object":
    stats = Stats(strength=50, agility=50, intellect=50, vitality=50, will=50)
    for key, value in stat_overrides.items():
        setattr(stats, key, value)
    return build_combatant(
        id=id, side=side, kind="character", name=f"Игрок{id}", level=60,
        stats=stats, primary_stat="str",
    )


def make_session(*combatants) -> CombatSessionState:
    state = CombatSessionState(session_id=1, mode=CombatMode.PVE, is_raid=True)
    for c in combatants:
        state.add(c)
    return state


# --- Построение участников ---


def test_build_stage1_mobs_count_and_hp():
    mobs = rb.build_stage1_mobs(start_id=100)
    assert len(mobs) == rc.STAGE1_MOB_COUNT == 3
    assert all(m.max_hp == rc.STAGE1_MOB_HP == 8_000 for m in mobs)
    assert all(m.current_hp == m.max_hp for m in mobs)
    assert {m.id for m in mobs} == {100, 101, 102}


def test_build_veld_mobs_hp_and_names():
    velds = rb.build_veld_mobs(start_id=200)
    assert velds[rc.VELD_OSWALD].max_hp == 14_000
    assert velds[rc.VELD_IRMA].max_hp == 9_000
    assert velds[rc.VELD_LITTA].max_hp == 6_000
    assert velds[rc.VELD_OSWALD].id == 200
    assert velds[rc.VELD_IRMA].id == 201
    assert velds[rc.VELD_LITTA].id == 202
    assert velds[rc.VELD_OSWALD].name == "Освальд Вельд"


def test_build_surgeon_hp():
    boss = rb.build_surgeon(id=300)
    assert boss.max_hp == rc.SURGEON_HP == 45_000
    assert boss.name == "Хирург"


# --- Порядок убийства Вельдов ---


def test_veld_order_correct_no_violation():
    velds = rb.build_veld_mobs(start_id=200)
    combatants = {c.id: c for c in velds.values()}
    ids_by_veld = {vid: c.id for vid, c in velds.items()}
    killed: list[str] = []

    result = rb.check_veld_kill_order(
        combatants, ids_by_veld, [rc.VELD_OSWALD], killed, violations_so_far=0,
    )
    assert result.violations == 0
    assert result.lines == []
    assert killed == [rc.VELD_OSWALD]
    # Ирма/Литта не тронуты
    assert combatants[ids_by_veld[rc.VELD_IRMA]].max_hp == 9_000
    assert combatants[ids_by_veld[rc.VELD_LITTA]].max_hp == 6_000


def test_veld_order_first_violation_doubles_remaining():
    velds = rb.build_veld_mobs(start_id=200)
    combatants = {c.id: c for c in velds.values()}
    ids_by_veld = {vid: c.id for vid, c in velds.items()}
    killed: list[str] = []

    # Убили Ирму первой (неправильно — должен быть Освальд)
    result = rb.check_veld_kill_order(
        combatants, ids_by_veld, [rc.VELD_IRMA], killed, violations_so_far=0,
    )
    assert result.violations == 1
    assert len(result.lines) == 1

    oswald = combatants[ids_by_veld[rc.VELD_OSWALD]]
    litta = combatants[ids_by_veld[rc.VELD_LITTA]]
    assert oswald.max_hp == 14_000 * 2
    assert oswald.current_hp == 14_000 * 2
    assert litta.max_hp == 6_000 * 2


def test_veld_order_second_violation_compounds_to_times_ten():
    velds = rb.build_veld_mobs(start_id=200)
    combatants = {c.id: c for c in velds.values()}
    ids_by_veld = {vid: c.id for vid, c in velds.items()}
    killed: list[str] = []

    # Ирма первой (violation 1) -> Освальд/Литта x2
    r1 = rb.check_veld_kill_order(combatants, ids_by_veld, [rc.VELD_IRMA], killed, 0)
    # Затем Освальд (тоже неправильно — ожидался Освальд ПЕРВЫМ, но раз он не
    # был первым, его смерть теперь второй по счёту — тоже не по rc.VELD_ORDER[1])
    r2 = rb.check_veld_kill_order(combatants, ids_by_veld, [rc.VELD_OSWALD], killed, r1.violations)
    assert r2.violations == 2

    litta = combatants[ids_by_veld[rc.VELD_LITTA]]
    # x2 (первая ошибка) затем x5 поверх текущего состояния = x10 от базы
    assert litta.max_hp == 6_000 * 2 * 5
    assert litta.current_hp == 6_000 * 2 * 5


def test_veld_order_full_kill_no_extra_violation_on_last():
    """Третья (последняя) кукла гибнет неизбежно последней — это не третье
    нарушение (при 3 куклах их физически не может быть больше двух)."""
    velds = rb.build_veld_mobs(start_id=200)
    combatants = {c.id: c for c in velds.values()}
    ids_by_veld = {vid: c.id for vid, c in velds.items()}
    killed: list[str] = []

    r1 = rb.check_veld_kill_order(combatants, ids_by_veld, [rc.VELD_OSWALD], killed, 0)
    r2 = rb.check_veld_kill_order(combatants, ids_by_veld, [rc.VELD_IRMA], killed, r1.violations)
    r3 = rb.check_veld_kill_order(combatants, ids_by_veld, [rc.VELD_LITTA], killed, r2.violations)
    assert r1.violations == 0
    assert r2.violations == 0
    assert r3.violations == 0
    assert r3.lines == []


# --- Хирург: скриптованный ИИ ---


def test_surgeon_first_tick_does_not_attack():
    ai = rb.SurgeonAI()
    boss = rb.build_surgeon(id=1)
    player = make_player(2)
    session = make_session(boss, player)
    hits = ai(boss, session, DeterministicRng())
    assert hits == []
    assert ai.preparing is False


def test_surgeon_awaiting_interrupt_suppresses_attack():
    ai = rb.SurgeonAI()
    ai.preparing = False
    ai.open_interrupt_window()
    boss = rb.build_surgeon(id=1)
    player = make_player(2)
    session = make_session(boss, player)
    hits = ai(boss, session, DeterministicRng())
    assert hits == []


def test_surgeon_phase3_bezdeystvie_suppresses_attack():
    ai = rb.SurgeonAI()
    ai.preparing = False
    ai.enter_phase3()
    boss = rb.build_surgeon(id=1)
    player = make_player(2)
    session = make_session(boss, player)
    hits = ai(boss, session, DeterministicRng())
    assert hits == []
    assert ai.phase3_turns_left == rc.SURGEON_PHASE3_TURNS


def test_surgeon_rotation_order_and_effects():
    ai = rb.SurgeonAI()
    ai.preparing = False
    boss = rb.build_surgeon(id=1)
    p1 = make_player(2)
    p2 = make_player(3)
    session = make_session(boss, p1, p2)
    rng = DeterministicRng()

    # 1. Резекция — одна цель
    hits1 = ai(boss, session, rng)
    assert len(hits1) == 1
    assert hits1[0].label == "Резекция"

    # 2. Замена частей — одна цель + Ослабление
    hits2 = ai(boss, session, rng)
    assert len(hits2) == 1
    assert hits2[0].label == "Замена частей"
    target = session.combatants[hits2[0].target_id]
    assert target.has_effect(EffectKind.WEAKEN)

    # 3. Работа с материалом — бьёт ВСЕХ живых игроков
    hits3 = ai(boss, session, rng)
    assert {h.target_id for h in hits3} == {p1.id, p2.id}
    assert all(h.label == "Работа с материалом" for h in hits3)

    # 4. Подтяжка нитей — одна цель, лечит Хирурга
    boss_hp_before = boss.current_hp
    hits4 = ai(boss, session, rng)
    assert len(hits4) == 1
    assert hits4[0].label == "Подтяжка нитей"
    assert boss.current_hp >= boss_hp_before  # самоисцеление применилось немедленно

    # 5. Цикл повторяется — снова Резекция
    hits5 = ai(boss, session, rng)
    assert hits5[0].label == "Резекция"


def test_surgeon_no_targets_returns_empty():
    ai = rb.SurgeonAI()
    ai.preparing = False
    boss = rb.build_surgeon(id=1)
    session = make_session(boss)  # ни одного игрока
    assert ai(boss, session, DeterministicRng()) == []


# --- Патч 66: Хирург не поддаётся контролю, но контроль сбивает его навык ---


class NoResistRng(random.Random):
    """random() почти 1.0 - ни один процентный бросок НЕ срабатывает.

    Для резиста Воли это "не сопротивился": проверка там rng.random() < resist,
    так что DeterministicRng (0.0) дал бы ровно обратное - вечный резист.
    """

    def random(self) -> float:
        return 0.999


def _control_tick(boss, player, skill_id: str):
    """Один ход: игрок бьёт по боссу контроль-навыком, резист не срабатывает."""
    from game.combat import resolver
    from game.combat.session import ActionType, DeclaredAction

    session = make_session(boss, player)
    return resolver.resolve_tick(
        session,
        {player.id: DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=boss.id)},
        NoResistRng(),
    )


def test_surgeon_is_never_controlled():
    """Резист Воли упирается в 75% - у Хирурга контроль не проходит вовсе.

    NoResistRng не даёт сработать ни одному резисту: если бы Хирург держался
    только на Воле, контроль бы лёг.
    """
    boss = rb.build_surgeon(id=1)
    assert boss.control_immune_always is True
    player = make_player(2)
    result = _control_tick(boss, player, "mage_ice_bonds")
    # FREEZE потребляется в тот же ход (см. game/combat/control.py), поэтому
    # факт наложения проверяем по control_landed_by, а не по остаточному эффекту.
    assert player.id not in result.control_landed_by


def test_control_attempt_on_surgeon_is_recorded_even_though_it_fails():
    """Окно прерывания живёт именно на этом: попытка засчитана, эффекта нет."""
    boss = rb.build_surgeon(id=1)
    player = make_player(2)
    result = _control_tick(boss, player, "mage_ice_bonds")
    assert result.control_attempts_on.get(boss.id) == {player.id}
    assert not result.control_landed_by  # ничего не легло - сбивается навык, не Хирург


def test_ordinary_boss_still_yields_to_control():
    """Иммунитет - свойство Хирурга, а не всех рейд-боссов."""
    veld = rb.build_veld_mobs(start_id=1)[rc.VELD_OSWALD]
    assert veld.control_immune_always is False
    player = make_player(50)
    result = _control_tick(veld, player, "mage_ice_bonds")
    assert result.control_landed_by == {player.id}


def test_control_attempts_do_not_leak_between_ticks():
    from game.combat import resolver
    from game.combat.session import ActionType, DeclaredAction

    boss = rb.build_surgeon(id=1)
    player = make_player(2)
    session = make_session(boss, player)
    attack = {player.id: DeclaredAction(type=ActionType.SKILL, skill_id="mage_ice_bonds", target_id=boss.id)}
    resolver.resolve_tick(session, attack, NoResistRng())
    quiet = resolver.resolve_tick(session, {}, NoResistRng())
    assert boss.id not in quiet.control_attempts_on


# --- Патч 67: автоцель 2 этапа не должна совпадать с нужной ---


def test_veld_kill_order_is_not_hp_order_by_accident():
    """Фиксирует исходные данные загадки: очередь задана VELD_ORDER, и сейчас
    она совпадает и с порядком HP, и с порядком представления в лоре. Если
    это когда-нибудь поменяют, тест автоцели ниже надо перечитать."""
    assert rc.VELD_ORDER == (rc.VELD_OSWALD, rc.VELD_IRMA, rc.VELD_LITTA)
    by_hp = sorted(rc.VELD_ORDER, key=lambda v: -rc.VELD_HP[v])
    assert list(rc.VELD_ORDER) == by_hp


def test_stage2_autotarget_is_not_the_one_to_kill_first():
    """Раньше автоцель вставала в Освальда - он же и нужен первым, так что
    этап проходился нажатием «Ударить» без единой смены цели."""
    from bot.handlers import raid_combat as raid

    velds = rb.build_veld_mobs(start_id=20_100_000)
    battle = raid.RaidBattle(
        group_id=None, participants={}, member_inputs=[], rng=DeterministicRng(),
        stage=2, mob_ids={c.id for c in velds.values()},
        veld_combatant_ids={vid: c.id for vid, c in velds.items()},
    )
    target = raid._default_target_id(battle)
    assert target is not None
    assert target != velds[rc.VELD_ORDER[0]].id
    assert target == velds[rc.VELD_ORDER[-1]].id


def test_stage1_autotarget_is_stable():
    """На 1 этапе куклы одинаковые - важно лишь, что цель у всех одна и та же
    (обход set давал бы её по везению с хешами)."""
    from bot.handlers import raid_combat as raid

    mobs = rb.build_stage1_mobs(start_id=20_000_000)
    battle = raid.RaidBattle(
        group_id=None, participants={}, member_inputs=[], rng=DeterministicRng(),
        stage=1, mob_ids={m.id for m in mobs},
    )
    assert raid._default_target_id(battle) == min(m.id for m in mobs)
