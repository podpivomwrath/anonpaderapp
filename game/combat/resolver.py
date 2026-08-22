"""Одновременный резолв хода (PvE и групповой PvP).

Порядок фаз внутри хода (progression-patch-4, §5):
  1. защитные/баф-умения;
  2. контроль-умения — вешают оглушение/заморозку В ЭТОТ ЖЕ ход;
  3. проверка «кто способен действовать» (замороженные пропускают ход);
  4. атакующие действия способных + ходы мобов (по снимку после защиты);
  5. одновременное применение урона/хила;
  6. тик длительностей эффектов, КД, стрика/иммунитета контроля; смерти, исход.

Контроль, наложенный в этот ход, действует немедленно: мобы и цели-игроки,
получившие FREEZE, не действуют. FREEZE тикает в тот же ход (потребляется).
"""

import random
from dataclasses import dataclass, field

import game.classes  # noqa: F401  — регистрация умений подклассов
import game.combat.base_skills as base_skills  # регистрация базовых навыков + метаданные
import game.combat.subclass_skills as subclass_skills  # регистрация навыков подклассов + метаданные
from game.combat import balance_config as bc
from game.combat import combat_flavor, control, display, formulas
from game.combat.session import (
    ActionType,
    CombatantState,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)
from game.combat.skills import (
    DEFENSIVE_SKILLS,
    OFFENSIVE_SKILLS,
    PendingHeal,
    PendingHit,
    SkillContext,
    compute_hit,
    tick_overload,
)
from game.economy import elixir_config as ec

# Эффекты боевых эликсиров (патч 16) — "бесплатное действие": накладываются
# МИМО объявления хода, поэтому обязаны срабатывать/тикать НЕМЕДЛЕННО (как
# FREEZE), а не с хода после наложения — иначе "N ходов" на деле длилось бы
# N+1. DODGE НЕ входит — его переиспользует Дымовая завеса (обычный навык
# с обычной семантикой отложенного тика), трогать нельзя.
_IMMEDIATE_EFFECT_KINDS = {
    EffectKind.FREEZE,
    EffectKind.ASHEN_FEVER,
    EffectKind.LAST_BREATH,
    EffectKind.BLOOD_REFLECT,
    EffectKind.CONTROL_IMMUNE,
    EffectKind.SHIELD_POOL,
    EffectKind.FLAT_DAMAGE_BONUS,
}


def _choose_mob_target(session: CombatSessionState, mob: CombatantState, rng: random.Random) -> CombatantState | None:
    """Провокация (taunted_by) форсит жёстко — проверяется вызывающим до
    обращения сюда. Иначе — случайный живой враг; в групповом PvE (is_raid)
    Страж с повышенной пассивной агрессией притягивает удары чаще
    (GROUP_PVE_GUARDIAN_AGGRO_WEIGHT), обычный PvE/PvP — равновероятно."""
    enemies = session.alive_enemies_of(mob)
    if not enemies:
        return None
    if not session.is_raid:
        return rng.choice(enemies)
    weights = [
        bc.GROUP_PVE_GUARDIAN_AGGRO_WEIGHT if e.subclass_id == "guardian" else 1.0
        for e in enemies
    ]
    return rng.choices(enemies, weights=weights, k=1)[0]


def _consume_heal_item(ctx: SkillContext, item_id: str | None) -> None:
    """Лечебное зелье (патч 16): тратит ход, как атака/навык."""
    pct = ec.HEAL_PCT.get(item_id) if item_id else None
    if pct is None:
        return
    actor = ctx.actor
    amount = round(actor.max_hp * pct)
    ctx.heals.append(
        PendingHeal(source_id=actor.id, target_id=actor.id, amount=amount, label="пьёт зелье")
    )


def _apply_last_breath_guard(combatant: CombatantState, result: "TickResult") -> None:
    """Последний вздох (патч 16): если HP<=0 и эффект активен — спасение
    на 1 HP, один раз, эффект снимается."""
    if combatant.current_hp > 0 or not combatant.has_effect(EffectKind.LAST_BREATH):
        return
    combatant.effects = [e for e in combatant.effects if e.kind != EffectKind.LAST_BREATH]
    combatant.current_hp = 1
    result.lines.append(f"✨ Последний вздох удерживает {combatant.name} на грани (1 HP)")


@dataclass
class RenderedHit:
    """Патч 51, ч.5: структурный снимок урона/лечения для нового формата
    боевого лога (game/combat/battle_log.py) — тот же удар, что уже попал в
    result.lines как готовая строка, но с исходными полями (сторона, hp
    до/после), достаточными чтобы собрать раздел «своя сторона»/«противник»
    без парсинга текста."""

    source_id: int
    target_id: int
    source_side: int
    target_side: int
    label: str
    amount: int
    crit: bool
    missed: bool
    is_dot: bool
    hp_before: int
    hp_after: int
    max_hp: int


@dataclass
class RenderedHeal:
    source_id: int
    target_id: int
    source_side: int
    target_side: int
    label: str
    amount: int
    hp_before: int
    hp_after: int
    max_hp: int


@dataclass
class TickResult:
    lines: list[str] = field(default_factory=list)
    deaths: list[int] = field(default_factory=list)
    finished: bool = False
    winner_side: int | None = None
    draw: bool = False
    # Патч 30: различает ничью "оба легли" (draw_reason=None) от принудительной
    # ничьи по лимиту ходов (только PVP_GROUP — см. TickEngine.max_turns) —
    # у них разный лорный текст в bot/handlers/pvp.py.
    draw_reason: str | None = None
    # Патч 12 (классовые испытания): структурные данные хода для
    # services/trial_service.py — не для отображения, только для трекинга.
    hits: list[PendingHit] = field(default_factory=list)
    actions: dict[int, DeclaredAction] = field(default_factory=dict)  # только "character"
    control_landed_by: set[int] = field(default_factory=set)  # cid, успешно наложившие контроль в этот ход
    # Патч 51, ч.5: структурные версии hit/heal-строк лога — см. RenderedHit/
    # RenderedHeal выше. lines[len(prelude_line_count):...] по-прежнему несёт
    # готовый текст (обратная совместимость и уже существующие тесты), эти
    # два списка — ДОПОЛНИТЕЛЬНЫЙ параллельный канал для нового рендера.
    hit_renders: list[RenderedHit] = field(default_factory=list)
    heal_renders: list[RenderedHeal] = field(default_factory=list)
    # Число строк в result.lines ДО hit/heal-рендеров этого хода (control/баф
    # эффекты фазы 1-2, ctx.lines) — граница для game/combat/battle_log.py:
    # lines[:prelude_line_count] и lines[prelude_line_count+len(hit_renders)+
    # len(heal_renders):] — "прочие" строки (не hit/heal), идут в свой раздел
    # по эвристике имени комбатанта; средний срез дублирует hit_renders/
    # heal_renders текстом и рендером не используется напрямую.
    prelude_line_count: int = 0


def _display_mode(session: CombatSessionState) -> str:
    return display.MODE_PVE_RAID if session.is_raid else display.MODE_PVP


def _run_offensive(ctx: SkillContext, cid: int, action: DeclaredAction, session, result) -> None:
    ctx.actor = session.combatants[cid]
    ctx.action = action
    if action.type == ActionType.ATTACK:
        OFFENSIVE_SKILLS["attack"](ctx)
    elif action.type == ActionType.ITEM:
        _consume_heal_item(ctx, action.item_id)
    elif action.type == ActionType.SKILL and action.skill_id in OFFENSIVE_SKILLS:
        OFFENSIVE_SKILLS[action.skill_id](ctx)
    elif action.type == ActionType.SKILL and action.skill_id not in DEFENSIVE_SKILLS:
        result.lines.append(
            f"{ctx.actor.name}: умение «{action.skill_id}» ещё не реализовано (TODO: content)"
        )


def resolve_tick(
    session: CombatSessionState,
    actions: dict[int, DeclaredAction],
    rng: random.Random,
) -> TickResult:
    result = TickResult()
    mode = _display_mode(session)
    alive_before = {c.id for c in session.combatants.values() if c.alive}
    hp_before = {c.id: c.current_hp for c in session.combatants.values()}
    # Эффекты, существовавшие НА НАЧАЛО хода: только они (кроме FREEZE) тикают
    # уроном/длительностью в этот ход. Свежий яд/дебаф начинает работать со
    # следующего хода; FREEZE — исключение, срабатывает и потребляется в этот ход.
    preexisting_effects = {id(e) for c in session.combatants.values() for e in c.effects}

    # Кто заморожен НА НАЧАЛО хода (лингер многоходового контроля) — не действует
    frozen_at_start = {
        cid for cid in session.combatants
        if session.combatants[cid].has_effect(EffectKind.FREEZE)
    }

    normalized: dict[int, DeclaredAction] = {}
    for cid in session.expected_declarers():
        normalized[cid] = actions.get(cid) or DeclaredAction(type=ActionType.SKIP)

    ctx = SkillContext(
        session=session,
        actor=next(iter(session.combatants.values())),
        action=DeclaredAction(),
        rng=rng,
    )

    # --- Фаза 1: защитные/баф-умения (только не замороженных на старте) ---
    for cid, action in normalized.items():
        if cid in frozen_at_start:
            continue
        if action.type == ActionType.SKILL and action.skill_id in DEFENSIVE_SKILLS:
            ctx.actor = session.combatants[cid]
            ctx.action = action
            DEFENSIVE_SKILLS[action.skill_id](ctx)

    # --- Фаза 2: контроль-умения — вешают FREEZE в этот же ход ---
    control_actors: set[int] = set()
    for cid, action in normalized.items():
        if cid in frozen_at_start:
            continue
        if action.type == ActionType.SKILL and (
            base_skills.is_control_skill(action.skill_id)
            or subclass_skills.is_control_skill(action.skill_id)
        ):
            _run_offensive(ctx, cid, action, session, result)
            control_actors.add(cid)

    # Успешно наложенный контроль (патч 12): новый FREEZE-эффект от одного из
    # control_actors, которого не было на начало хода (см. preexisting_effects).
    if control_actors:
        for combatant in session.combatants.values():
            for effect in combatant.effects:
                if (
                    effect.kind == EffectKind.FREEZE
                    and id(effect) not in preexisting_effects
                    and effect.source_id in control_actors
                ):
                    result.control_landed_by.add(effect.source_id)

    # --- Фаза 3: кто способен действовать (заморожен на старте ИЛИ получил контроль) ---
    def is_frozen(c: CombatantState) -> bool:
        return c.has_effect(EffectKind.FREEZE)

    # --- Фаза 4a: атакующие действия игроков (кроме уже сходивших контролем) ---
    for cid, action in normalized.items():
        if cid in control_actors:
            continue
        combatant = session.combatants[cid]
        if cid in frozen_at_start or is_frozen(combatant):
            # пропуск ИЗ-ЗА контроля — засчитывается в стрик DR (control-patch-8)
            combatant.skipped_by_control_this_turn = True
            # Патч 52, баг 1: единственное место, где печатается «теряет ход» —
            # здесь, где резолвер УЖЕ определил, что боец не может действовать.
            # Раньше это же сообщение дублировал combat_flavor.control_line в
            # обработчике наложения контроля (base_skills.py/subclass_skills.py/
            # poisoner.py) — из-за проверки "только для лингера" (frozen_at_start)
            # дубль казался устранённым для СВЕЖЕЙ заморозки, но проявлялся при
            # ПОВТОРНОМ наложении контроля на УЖЕ замороженную цель (обновление
            # длительности): control_line печатал строку в фазе 2, а эта ветка —
            # ещё раз, т.к. цель была frozen_at_start. Теперь control_line вообще
            # не печатает «теряет ход» — только эта строка, ровно один раз.
            result.lines.append(f"{combatant.name} теряет ход ❄️")
            continue
        if action.type == ActionType.SKIP:
            result.lines.append(f"{combatant.name} медлит и пропускает ход")
            continue
        _run_offensive(ctx, cid, action, session, result)

    # --- Фаза 4b: ходы мобов (замороженные контролем этого хода пропускают) ---
    # Патч 25, п.3: в PvE моб, которого хиты этого хода уже опускают до 0 HP,
    # не наносит ответный урон — мёртвый не бьёт. В PvP правила резолва не
    # меняются (взаимное уничтожение — валидный исход).
    pending_damage: dict[int, int] = {}
    if session.mode == CombatMode.PVE:
        for hit in ctx.hits:
            pending_damage[hit.target_id] = pending_damage.get(hit.target_id, 0) + hit.amount
    for mob in [c for c in session.combatants.values() if c.kind == "mob" and c.alive]:
        if is_frozen(mob):
            mob.skipped_by_control_this_turn = True  # пропуск из-за контроля (стрик DR)
            # Патч 52, баг 1: см. комментарий у фазы 4a — единственное место
            # вывода «теряет ход», без исключения для лингера/свежей заморозки.
            result.lines.append(f"{mob.name} теряет ход ❄️")
            continue
        if session.mode == CombatMode.PVE and pending_damage.get(mob.id, 0) >= mob.current_hp:
            continue  # уже мёртв по итогам этого хода — не бьёт (патч 25, п.3)
        target = None
        if mob.taunted_by is not None:
            taunter = session.combatants.get(mob.taunted_by)
            if taunter is not None and taunter.alive:
                target = taunter
        if target is None:
            target = _choose_mob_target(session, mob, rng)
        if target is not None:
            ctx.hits.append(compute_hit(mob, target, rng, label="кусает"))

    # --- ДоТы тикают в фазу применения (только висевшие с начала хода) ---
    for combatant in session.combatants.values():
        if not combatant.alive:
            continue
        for effect in combatant.effects_of(EffectKind.DOT):
            if id(effect) not in preexisting_effects:
                continue
            ctx.hits.append(
                PendingHit(
                    source_id=effect.source_id,
                    target_id=combatant.id,
                    amount=max(round(effect.value * effect.stacks), 1),
                    label="обжигает (ДоТ)",
                    is_dot=True,
                )
            )

    # --- Патч 26: модификатор разницы уровней — моб выше уровнем бьёт сильнее
    # и получает меньше урона (в обратную сторону модификаторов нет). Считаем
    # по фактическим участникам каждого хита — корректно и для группового PvE.
    if session.mode == CombatMode.PVE:
        for hit in ctx.hits:
            if hit.amount <= 0:
                continue
            source = session.combatants.get(hit.source_id)
            target = session.combatants.get(hit.target_id)
            if source is None or target is None:
                continue
            if source.kind == "mob" and target.kind == "character":
                dmg_mult, _ = formulas.level_diff_modifiers(source.level, target.level)
                hit.amount = max(round(hit.amount * dmg_mult), 1)
            elif target.kind == "mob" and source.kind == "character":
                _, taken_mult = formulas.level_diff_modifiers(target.level, source.level)
                hit.amount = max(round(hit.amount * taken_mult), 1)

    # Патч 45, ч.1: снимок ПОСЛЕ прямых самомутаций хода (себестоимость HP у
    # Багрового пира/Круга тьмы — actor.current_hp меняется РАНЬШЕ, внутри
    # хендлера навыка, в обход damage_taken/heal_taken) — иначе лог лечения
    # ниже сравнивал бы hp_before СО СТАРТА ХОДА с итоговым HP и показывал бы
    # хилу знак себестоимости пополам с ней ("восполняет кровью: -11 HP" на
    # деле означало "заплатил 22, вылечил 11, кап отрезал остальное" — само
    # лечение было положительным и капалось верно, просто лог показывал не то).
    hp_before_apply = {c.id: c.current_hp for c in session.combatants.values()}

    # --- Одновременное применение: net-дельта по каждому участнику ---
    damage_taken: dict[int, int] = {}
    heal_taken: dict[int, int] = {}
    reflect_hits: list[PendingHit] = []
    # Патч 32, баг 2/3: фактически поглощённый урон КАЖДОГО хита (после щита/
    # пула) — по id(hit), для прогрессивного hp_before/hp_after в логе ниже.
    # Раньше лог всех хитов по одной цели в этот ход показывал ОДИН и тот же
    # (общий hp_before хода → итоговый current_hp) переход — второй удар
    # «Двойного укола» выглядел так, будто не наносил урона, хотя фактически
    # урон суммировался в damage_taken корректно.
    applied_by_hit: dict[int, int] = {}
    for hit in ctx.hits:
        target = session.combatants[hit.target_id]
        amount = hit.amount
        # Несокрушимый (патч 39): входящий урон за удар не может превышать
        # value*maxHP, применяется ДО щитов (щит гасит то, что осталось).
        damage_cap = target.effect_total(EffectKind.DAMAGE_CAP)
        if damage_cap > 0 and amount > 0:
            amount = min(amount, max(round(target.max_hp * damage_cap), 1))
        # Глухая оборона (патч 39): лечит цель за каждый удар, срезанный блоком
        # (block_reduction/BLOCK_STANCE уже применены в compute_hit — здесь
        # только считаем факт "удар пришёлся по блокирующей стойке").
        block_stance = target.effect_total(EffectKind.BLOCK_STANCE)
        if block_stance > 0 and amount > 0:
            block_heal_pct = target.effect_total(EffectKind.BLOCK_HEAL)
            if block_heal_pct > 0:
                ctx.heals.append(
                    PendingHeal(
                        source_id=target.id, target_id=target.id,
                        amount=round(target.max_hp * block_heal_pct), label="исцеляется от блока",
                    )
                )
        if target.shield > 0:
            absorbed = min(target.shield, amount)
            target.shield -= absorbed
            amount -= absorbed
            if absorbed:
                result.lines.append(f"Щит {target.name} поглощает {absorbed} урона 🛡")
        # Второе сердце (патч 16): персистентный щит на несколько ходов,
        # отдельный от однотикового target.shield (групповой щит стража).
        shield_pool = target.effects_of(EffectKind.SHIELD_POOL)
        if shield_pool and amount > 0:
            pool = shield_pool[0]
            pool_absorbed = min(int(pool.value), amount)
            pool.value -= pool_absorbed
            amount -= pool_absorbed
            if pool_absorbed:
                result.lines.append(f"🛡️ Второе сердце {target.name} поглощает {pool_absorbed} урона")
        # Кровь за кровь (патч 16): доля полученного урона возвращается атакующему
        reflect_pct = target.effect_total(EffectKind.BLOOD_REFLECT)
        if reflect_pct > 0 and amount > 0 and hit.source_id != target.id:
            attacker = session.combatants.get(hit.source_id)
            if attacker is not None and attacker.alive:
                reflect_hits.append(
                    PendingHit(
                        source_id=target.id, target_id=attacker.id,
                        amount=max(round(amount * reflect_pct), 1), label="шипы",
                    )
                )
        applied_by_hit[id(hit)] = amount
        damage_taken[hit.target_id] = damage_taken.get(hit.target_id, 0) + amount
    ctx.hits.extend(reflect_hits)
    for hit in reflect_hits:
        applied_by_hit[id(hit)] = hit.amount
        damage_taken[hit.target_id] = damage_taken.get(hit.target_id, 0) + hit.amount
    for heal in ctx.heals:
        heal_taken[heal.target_id] = heal_taken.get(heal.target_id, 0) + heal.amount

    for cid in set(damage_taken) | set(heal_taken):
        combatant = session.combatants[cid]
        delta = heal_taken.get(cid, 0) - damage_taken.get(cid, 0)
        combatant.current_hp = min(combatant.current_hp + delta, combatant.max_hp)
        _apply_last_breath_guard(combatant, result)

    # --- Строки лога: единый краткий формат везде — PvE, PvP, рейды (патч 43,
    # ч.1) — образность убрана из пошагового лога, режим влияет только на
    # точность % (display.MODE_PVE_RAID — один знак после запятой). ---
    result.lines.extend(ctx.lines)
    result.prelude_line_count = len(result.lines)  # патч 51, ч.5: граница для game/combat/battle_log.py
    running_hp = dict(hp_before_apply)
    for hit in ctx.hits:
        source = session.combatants[hit.source_id]
        target = session.combatants[hit.target_id]
        h_before = running_hp[target.id]
        applied = applied_by_hit.get(id(hit), hit.amount)
        h_after = h_before - applied
        running_hp[target.id] = h_after
        result.lines.append(
            combat_flavor.render_hit(
                source.name, target.name,
                label=hit.label, amount=applied, crit=hit.crit, missed=hit.missed, is_dot=hit.is_dot,
                hp_before=h_before, hp_after=h_after, max_hp=target.max_hp, mode=mode,
            )
        )
        result.hit_renders.append(
            RenderedHit(
                source_id=source.id, target_id=target.id, source_side=source.side, target_side=target.side,
                label=hit.label, amount=applied, crit=hit.crit, missed=hit.missed, is_dot=hit.is_dot,
                hp_before=h_before, hp_after=h_after, max_hp=target.max_hp,
            )
        )
    for heal in ctx.heals:
        source = session.combatants[heal.source_id]
        target = session.combatants[heal.target_id]
        h_before = running_hp[target.id]
        h_after = min(h_before + heal.amount, target.max_hp)
        running_hp[target.id] = h_after
        result.lines.append(
            display.action_line(
                source.name, heal.label, target.name,
                h_before, h_after, target.max_hp, mode,
            )
        )
        result.heal_renders.append(
            RenderedHeal(
                source_id=source.id, target_id=target.id, source_side=source.side, target_side=target.side,
                label=heal.label, amount=heal.amount, hp_before=h_before, hp_after=h_after, max_hp=target.max_hp,
            )
        )

    # --- Тик длительностей, КД, контроля; очистка однотиковых состояний ---
    pvp = session.mode != CombatMode.PVE  # DR-стрик считаем только в PvP
    for combatant in session.combatants.values():
        # Пепельная лихорадка (патч 16): самоурон + эскалация КАЖДЫЙ активный
        # ход, включая ход применения (эликсир — бесплатное действие).
        for effect in combatant.effects_of(EffectKind.ASHEN_FEVER):
            if not combatant.alive:
                continue
            before_hp = combatant.current_hp
            self_dmg = max(round(combatant.max_hp * ec.ASHEN_FEVER_SELF_DAMAGE_PCT_MAX_HP), 1)
            combatant.current_hp -= self_dmg
            _apply_last_breath_guard(combatant, result)
            result.lines.append(
                f"🔥 Пепельная лихорадка жжёт {combatant.name} "
                f"{display.hp_delta_line(before_hp, combatant.current_hp, combatant.max_hp)}"
            )
            step = round(effect.value / ec.ASHEN_FEVER_DAMAGE_BONUS_STEP)
            effect.value = ec.ASHEN_FEVER_DAMAGE_BONUS_STEP * (step + 1)

        for effect in combatant.effects:
            # Немедленные эффекты (FREEZE, эликсиры-патч16) тикают всегда;
            # прочие свежие эффекты не тикают в ход наложения
            if id(effect) in preexisting_effects or effect.kind in _IMMEDIATE_EFFECT_KINDS:
                effect.remaining_ticks -= 1

        # Второе сердце (патч 16): щит не пробит за отведённые ходы — остаток лечит
        for effect in combatant.effects_of(EffectKind.SHIELD_POOL):
            if effect.remaining_ticks <= 0 and effect.value > 0 and combatant.alive:
                heal = round(effect.value)
                before_hp = combatant.current_hp
                combatant.current_hp = min(combatant.current_hp + heal, combatant.max_hp)
                result.lines.append(
                    f"🛡️ Второе сердце {combatant.name} обращается в исцеление "
                    f"{display.hp_delta_line(before_hp, combatant.current_hp, combatant.max_hp)}"
                )
                effect.value = 0

        # Элементалист, «Тепловой шок» (патч 49, ч.2): именно в момент, когда
        # Горение (ДоТ) истекает на этой цели, сопротивление контролю цели
        # снижается на 1 ход. Проверяем ДО фильтрации — remaining_ticks уже
        # продекрементирован выше для немедленных/старых эффектов.
        for effect in combatant.effects_of(EffectKind.DOT):
            if effect.remaining_ticks > 0:
                continue
            source = session.combatants.get(effect.source_id)
            if source is None:
                continue
            heat_shock_bonus = source.buff_modifiers.get("burn_expire_resist_down", 0.0)
            if heat_shock_bonus > 0:
                combatant.apply_effect(EffectKind.CONTROL_RESIST_DOWN, heat_shock_bonus, 1, source.id)

        combatant.effects = [e for e in combatant.effects if e.remaining_ticks > 0]
        combatant.tick_cooldowns()
        tick_overload(combatant)
        control.tick_control(combatant, pvp)
        combatant.reset_transient()

    # Патч 12: снимок хитов/действий этого хода для трекера испытаний
    # (только персонажи — мобьи действия трекеру не интересны).
    result.hits = list(ctx.hits)
    result.actions = {
        cid: action for cid, action in normalized.items()
        if session.combatants[cid].kind == "character"
    }

    # --- Смерти и исход ---
    result.deaths = [cid for cid in alive_before if not session.combatants[cid].alive]
    for cid in result.deaths:
        result.lines.append(f"☠ {session.combatants[cid].name} погибает")

    sides = session.sides_alive()
    if len(sides) == 0:
        result.finished = True
        result.draw = True
        result.lines.append("Ничья: обе стороны пали одновременно")
    elif len(sides) == 1:
        result.finished = True
        result.winner_side = sides.pop()
    return result
