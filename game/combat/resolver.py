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
from game.combat import combat_flavor, control, display, formulas, shared_rules
from game.combat.session import (
    BURN_TAG,
    ECHO_TAG,
    ActionType,
    CombatantState,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
    shield_name,
    white_max_hp,
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
    # Патч 56, «Приказ»: aggro_bonus умножает вес Стража. Только PvE/рейд -
    # ветка is_raid, в PvP этот путь выбора цели не используется вовсе.
    weights = [
        bc.GROUP_PVE_GUARDIAN_AGGRO_WEIGHT * (1.0 + e.buff_modifiers.get("aggro_bonus", 0.0))
        if e.subclass_id == "guardian" else 1.0
        for e in enemies
    ]
    return rng.choices(enemies, weights=weights, k=1)[0]


def _consume_heal_item(ctx: SkillContext, item_id: str | None) -> None:
    """Лечебное зелье (патч 16): тратит ход, как атака/навык."""
    actor = ctx.actor
    amount = ec.heal_amount(item_id, white_max_hp(actor))
    if amount is None:
        return
    ctx.heals.append(
        PendingHeal(source_id=actor.id, target_id=actor.id, amount=amount, label="пьёт зелье")
    )


def _dies_this_tick(mob: CombatantState, incoming: list, session: CombatSessionState | None = None) -> bool:
    """Умрёт ли моб от ударов этого хода - тогда он не бьёт в ответ.

    Раньше сравнивалась сырая сумма урона с HP. С лимитом урона за удар и
    щитом (патч 103) это врало в пользу игрока: Гулкий латник, у которого за
    удар уходит не больше 15%, получал «смертельный» удар, выживал - и всё
    равно пропускал ход, будто умер. Здесь урон считается так же, как его
    потом применит движок: с лимитом за удар, за вычетом щита, и моб с
    «последним вздохом» не умирает вовсе.

    2026-10-16: и с поправкой за разницу уровней (моб выше игрока получает
    меньше) - она применяется к ударам позже этой проверки. Без неё удар
    «на бумаге» добивал моба, моб выживал - и всё равно пропускал ход, а его
    замах на следующем ходу считался сбитым контролем (репорт #79).
    """
    if mob.has_effect(EffectKind.LAST_BREATH) or mob.hp_floor > 0:
        return False
    cap = mob.effect_total(EffectKind.DAMAGE_CAP)
    total = 0
    for hit in incoming:
        amount = hit.amount
        source = session.combatants.get(hit.source_id) if session is not None else None
        if source is not None and source.kind == "character" and amount > 0:
            _, taken_mult = formulas.level_diff_modifiers(mob.level, source.level, mob.field_mob)
            amount = max(round(amount * taken_mult), 1)
        if cap > 0 and amount > 0:
            amount = min(amount, max(round(mob.max_hp * cap), 1))
        total += amount
    shield = sum(e.value for e in mob.effects_of(EffectKind.SHIELD_POOL))
    return total - shield >= mob.current_hp


def _apply_last_breath_guard(combatant: CombatantState, result: "TickResult") -> None:
    """Последний вздох (патч 16): если HP<=0 и эффект активен — спасение
    на 1 HP, один раз, эффект снимается."""
    if combatant.current_hp > 0 or not combatant.has_effect(EffectKind.LAST_BREATH):
        return
    combatant.effects = [e for e in combatant.effects if e.kind != EffectKind.LAST_BREATH]
    combatant.current_hp = 1
    brain = getattr(combatant, "mob_brain", None)
    if brain is not None:
        # У мобов это не эликсир, а их способность («Не уйду», «Не умер») -
        # строка про эликсир игроков тут сбивала бы с толку.
        result.lines.append(f"✨ {combatant.name}: {brain.ability.title.lower()} - держится на 1 HP")
    else:
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
    #: пассивный тик эффекта, а не действие бойца - см. PendingHit
    is_tick: bool = False
    # Сколько урона НЕ дошло до цели: срезал блок плюс съели щит и
    # «Несокрушимый». amount - это то, что дошло, поэтому без отдельного поля
    # впитанное посчитать уже нечем: исходная величина удара к этому моменту
    # нигде не хранится. Нужно сводке рейда (bot/handlers/raid_combat.py).
    absorbed: int = 0
    #: стаков Метки добычи после уворота (см. PendingHit.marked)
    marked: int = 0
    #: сколько срезал блок (Глухая оборона и пр.) - пишется в строке удара
    blocked: int = 0
    #: сколько съел щит - тоже в строке удара (2026-10-29: в логе хода щит
    #: был не виден, только урон, который до здоровья дошёл)
    shielded: int = 0


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
    # Патч 66: {id цели: кто пытался её контролить} - включая отбитые попытки.
    # Отдельно от control_landed_by: тому важен успех, этому - сам факт удара
    # контролем по конкретной цели (окно прерывания Хирурга).
    control_attempts_on: dict[int, set[int]] = field(default_factory=dict)
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
    # Лечение мимо heal_renders - остаток щита, обращённый в здоровье
    # (Оберег, Второе сердце): (кто повесил щит, кого лечит, сколько).
    # Отдельно, чтобы не сдвигать срез строк лога выше; читает его подсчёт
    # вклада рейда (2026-10-29, баг-репорт: такое лечение не попадало в итог).
    shield_heals: list[tuple[int, int, int]] = field(default_factory=list)


def _apply_phase(
    session: CombatSessionState, hits: list, heals: list, ctx, rng,
    applied_by_hit: dict[int, int], shielded_by_hit: dict[int, int], result: "TickResult",
) -> list:
    """Применить одну фазу хода: удары и лечение суммируются в net-дельту
    по каждому участнику (внутри фазы всё одновременно). Возвращает удары
    отражения, родившиеся в этой фазе. heals дополняется лечением от блока."""
    damage_taken: dict[int, int] = {}
    heal_taken: dict[int, int] = {}
    reflect_hits: list[PendingHit] = []
    for hit in hits:
        target = session.combatants[hit.target_id]
        amount = hit.amount
        shared_rules.passive_mark(session.combatants.get(hit.source_id), target, hit, rng, ctx.lines)
        # Рейд «Безмогильное поле»: купол и стойки генерала (session.py).
        if target.incoming_hit_hook is not None and amount > 0:
            amount = max(target.incoming_hit_hook(hit, session.combatants.get(hit.source_id), amount), 0)
        # Несокрушимый (патч 39): входящий урон за удар не может превышать
        # value*maxHP, применяется ДО щитов (щит гасит то, что осталось).
        amount = shared_rules.cap_incoming(target, amount)
        # Глухая оборона (патч 39): лечит цель за каждый удар, срезанный блоком
        # (block_reduction/BLOCK_STANCE уже применены в compute_hit — здесь
        # только считаем факт "удар пришёлся по блокирующей стойке").
        block_heal = shared_rules.block_heal_amount(target, amount)
        if block_heal:
            heals.append(
                PendingHeal(
                    source_id=target.id, target_id=target.id,
                    amount=block_heal, label="Глухая оборона гасит удар",
                )
            )
        # Щиты (однотиковый + «Второе сердце») и «Токсикология» - общие с
        # дуэлью, см. game/combat/shared_rules.py.
        pierce = (
            shared_rules.poison_shield_pierce(session.combatants.get(hit.source_id))
            if hit.is_dot else 0.0
        )
        # Сколько съел щит, пишется в строке удара (render_hit, shielded) -
        # отдельные строки щитов больше не нужны.
        before_shields = amount
        amount = shared_rules.absorb_by_shields(target, amount, [], pierce=pierce)
        shielded_by_hit[id(hit)] = before_shields - amount
        # Страж, «Отражение» (патч 56) - общее с дуэлью правило.
        reflected = shared_rules.block_reflect_amount(target, hit.blocked)
        if reflected and hit.source_id != target.id:
            attacker = session.combatants.get(hit.source_id)
            if attacker is not None and attacker.alive:
                reflect_hits.append(
                    PendingHit(
                        source_id=target.id, target_id=attacker.id,
                        amount=reflected, label="отражает щитом",
                    )
                )
        # Кровь за кровь (патч 16): доля полученного урона возвращается атакующему.
        # Только за удар: яд и горение не возвращаются (2026-10-25, баг).
        reflect_pct = target.effect_total(EffectKind.BLOOD_REFLECT)
        if reflect_pct > 0 and amount > 0 and hit.source_id != target.id and not hit.is_dot:
            attacker = session.combatants.get(hit.source_id)
            if attacker is not None and attacker.alive:
                reflect_hits.append(
                    PendingHit(
                        source_id=target.id, target_id=attacker.id,
                        amount=max(round(amount * reflect_pct), 1), label=target.reflect_label,
                    )
                )
        applied_by_hit[id(hit)] = amount
        damage_taken[hit.target_id] = damage_taken.get(hit.target_id, 0) + amount
    # Ответный урон - тоже через щиты ударившего (2026-10-22, баг: «возврат
    # урона бьёт сквозь щиты»).
    for hit in reflect_hits:
        hit.amount = shared_rules.cap_incoming(session.combatants[hit.target_id], hit.amount)
        before_shields = hit.amount
        amount = shared_rules.absorb_by_shields(session.combatants[hit.target_id], hit.amount, [])
        shielded_by_hit[id(hit)] = before_shields - amount
        applied_by_hit[id(hit)] = amount
        damage_taken[hit.target_id] = damage_taken.get(hit.target_id, 0) + amount
    shared_rules.settle_lifesteal(
        heals, {hid: applied + shielded_by_hit.get(hid, 0) for hid, applied in applied_by_hit.items()},
    )
    for heal in heals:
        # Затухание лечения в PvP (shared_rules.recovered); amount правим на
        # месте - лог и вклад видят то, что дошло.
        heal.amount = shared_rules.recovered(session.combatants[heal.target_id], heal.amount)
        heal_taken[heal.target_id] = heal_taken.get(heal.target_id, 0) + heal.amount

    # Патч 56, «Отголосок» Тёмного мистика: лечение сверх максимума HP не
    # пропадает, а становится щитом следующему по низкому HP союзнику.
    for source_id in {h.source_id for h in heals}:
        source = session.combatants[source_id]
        echo = source.buff_modifiers.get("heal_overflow_shield", 0.0)
        if echo <= 0:
            continue
        for target_id in {h.target_id for h in heals if h.source_id == source_id}:
            target = session.combatants[target_id]
            overflow = (
                target.current_hp
                + heal_taken.get(target_id, 0)
                - damage_taken.get(target_id, 0)
                - target.max_hp
            )
            if overflow <= 0:
                continue
            # Сам мистик - тоже кандидат (2026-10-17): вдвоём перелечивание
            # союзника на полном HP некуда было отдать, и оно пропадало.
            group = [*session.alive_allies_of(source), *([source] if source.alive else [])]
            candidates = [c for c in group if c.id != target_id]
            if not candidates:
                continue
            ally = min(candidates, key=lambda c: c.current_hp / c.max_hp)
            amount = round(overflow * echo)
            cap = round(ally.max_hp * bc.DARK_MYSTIC_ECHO_CAP_PCT)
            # Свой щит, отдельно от Оберега (ECHO_TAG): раньше отголосок затирал
            # Оберег, а потом новый Оберег - накопленный отголосок. Новый
            # отголосок прибавляется к уже висящему.
            current = next(
                (e for e in ally.effects_of(EffectKind.SHIELD_POOL)
                 if e.source_id == source.id and getattr(e, "tag", None) == ECHO_TAG),
                None,
            )
            # Не выше потолка (2026-10-18): прибавляем только до cap.
            amount = min(amount, cap - round(current.value if current is not None else 0))
            if amount <= 0:
                continue
            if current is not None:
                current.value += amount
                current.remaining_ticks = max(current.remaining_ticks, bc.DARK_MYSTIC_ECHO_DURATION)
            else:
                ally.apply_effect(
                    EffectKind.SHIELD_POOL, amount, bc.DARK_MYSTIC_ECHO_DURATION, source.id, tag=ECHO_TAG,
                )
            ctx.lines.append(
                f"{source.name}: отголосок - {overflow} лишнего лечения ({target.name}) "
                f"становится щитом +{amount} на {ally.name}"
            )

    for cid in set(damage_taken) | set(heal_taken):
        combatant = session.combatants[cid]
        delta = heal_taken.get(cid, 0) - damage_taken.get(cid, 0)
        combatant.current_hp = min(combatant.current_hp + delta, combatant.max_hp)
        if combatant.hp_floor > 0 and combatant.current_hp < combatant.hp_floor:
            combatant.current_hp = combatant.hp_floor
        _apply_last_breath_guard(combatant, result)

    return reflect_hits


def _display_mode(session: CombatSessionState) -> str:
    return display.MODE_PVE_NUM if session.mode == CombatMode.PVE else display.MODE_PVP


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
            combat_flavor.unimplemented_skill_line(ctx.actor.name, action.skill_id)
        )


def resolve_tick(
    session: CombatSessionState,
    actions: dict[int, DeclaredAction],
    rng: random.Random,
) -> TickResult:
    result = TickResult()
    mode = _display_mode(session)
    alive_before = {c.id for c in session.combatants.values() if c.alive}
    # Эффекты, существовавшие НА НАЧАЛО хода: только они (кроме FREEZE) тикают
    # уроном/длительностью в этот ход. Свежий яд/дебаф начинает работать со
    # следующего хода; FREEZE — исключение, срабатывает и потребляется в этот ход.
    preexisting_effects = {id(e) for c in session.combatants.values() for e in c.effects}
    for combatant in session.combatants.values():
        combatant.control_attempted_by.clear()  # патч 66: память попыток - однотиковая

    # Кто заморожен НА НАЧАЛО хода (лингер многоходового контроля) — не действует
    frozen_at_start = {
        cid for cid in session.combatants
        if session.combatants[cid].has_effect(EffectKind.FREEZE)
    }

    # Патч 56: флаги, к которым compute_hit не имеет доступа (сессии он не
    # видит). Общие с дуэлью - см. game/combat/shared_rules.py.
    shared_rules.begin_turn_flags(session, session.tick_number)

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
        if action.type == ActionType.DEFEND:
            session.combatants[cid].defend_reduction = bc.DEFEND_DAMAGE_REDUCTION
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

    for combatant in session.combatants.values():
        if combatant.control_attempted_by:
            result.control_attempts_on[combatant.id] = set(combatant.control_attempted_by)

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
            # note - сценарное действие вместо хода (рейд: «несёт груз»)
            note = action.payload.get("note")
            result.lines.append(f"{combatant.name} {note}" if note else f"{combatant.name} медлит и пропускает ход")
            continue
        if action.type == ActionType.DEFEND:
            result.lines.append(combat_flavor.defend_line(combatant.name))
            continue
        _run_offensive(ctx, cid, action, session, result)

    # --- Фаза 4b: ходы мобов (замороженные контролем этого хода пропускают) ---
    # Патч 25, п.3: в PvE моб, которого хиты этого хода уже опускают до 0 HP,
    # не наносит ответный урон — мёртвый не бьёт. В PvP правила резолва не
    # меняются (взаимное уничтожение — валидный исход).
    # Удары по каждому мобу в этом ходу - его способности на них отвечают
    # (отражение, рассол, контрудар). Только до хода мобов: собственные удары
    # мобов в ответ на ответ не идут.
    incoming_by_target: dict[int, list] = {}
    for hit in ctx.hits:
        incoming_by_target.setdefault(hit.target_id, []).append(hit)
    for mob in [c for c in session.combatants.values() if c.kind == "mob" and c.alive]:
        if is_frozen(mob):
            mob.skipped_by_control_this_turn = True  # пропуск из-за контроля (стрик DR)
            # Патч 52, баг 1: см. комментарий у фазы 4a — единственное место
            # вывода «теряет ход», без исключения для лингера/свежей заморозки.
            result.lines.append(f"{mob.name} теряет ход ❄️")
            # Свойства тела (регенерация, отражение...) работают и в оглушении
            # (2026-10-20). Как и ход - только если моб этот ход переживёт.
            if mob.mob_brain is not None and mob.scripted_hit is None and not (
                session.mode == CombatMode.PVE
                and _dies_this_tick(mob, incoming_by_target.get(mob.id, []), session)
            ):
                turn = mob.mob_brain.passive(
                    mob, None, session, rng, incoming_by_target.get(mob.id, []),
                )
                ctx.hits.extend(turn.hits)
                ctx.heals.extend(turn.heals)
                ctx.lines.extend(turn.lines)
            continue
        if session.mode == CombatMode.PVE and _dies_this_tick(mob, incoming_by_target.get(mob.id, []), session):
            continue  # уже мёртв по итогам этого хода — не бьёт (патч 25, п.3)
        if mob.scripted_hit is not None:
            # Патч 53: рейд-босс с собственным сценарием хода (ротация
            # атак/фазы) — заменяет стандартное "кусает" целиком. Может
            # вернуть несколько ударов (напр. "Работа с материалом" — по
            # всем игрокам) или пустой список (ход без атаки — босс
            # "готовит инструмент").
            ctx.hits.extend(mob.scripted_hit(mob, session, rng))
            continue
        target = None
        if mob.taunted_by is not None:
            taunter = session.combatants.get(mob.taunted_by)
            if taunter is not None and taunter.alive:
                target = taunter
        if target is None:
            target = _choose_mob_target(session, mob, rng)
        if mob.mob_brain is not None:
            # Патч 103: способность моба. Сюда попадает только моб, который
            # этот ход переживёт (проверка выше), поэтому ни одна ответная
            # механика не срабатывает от добивающего удара.
            turn = mob.mob_brain.act(mob, target, session, rng, incoming_by_target.get(mob.id, []))
            ctx.hits.extend(turn.hits)
            ctx.heals.extend(turn.heals)
            ctx.lines.extend(turn.lines)
            continue
        if target is not None:
            ctx.hits.append(compute_hit(mob, target, rng, label="кусает"))

    # --- ДоТы тикают в фазу применения (только висевшие с начала хода) ---
    for combatant in session.combatants.values():
        if not combatant.alive:
            continue
        for effect in combatant.effects_of(EffectKind.DOT):
            if id(effect) not in preexisting_effects:
                continue
            source = session.combatants.get(effect.source_id)
            ctx.hits.append(
                PendingHit(
                    source_id=effect.source_id,
                    target_id=combatant.id,
                    amount=shared_rules.poison_tick_damage(effect, source, combatant),
                    # Свой ярлык у горения и яда (2026-10-29, баг-репорт: оба
                    # были «обжигает», и тик яда принимали за огонь).
                    label="горение" if effect.tag == BURN_TAG else "яд",
                    is_dot=True,
                    is_tick=True,
                )
            )

    # --- Патч 26: модификатор разницы уровней — моб выше уровнем бьёт сильнее
    # и получает меньше урона (в обратную сторону модификаторов нет). Считаем
    # по фактическим участникам каждого хита — корректно и для группового PvE.
    if session.mode == CombatMode.PVE:
        for hit in ctx.hits:
            if hit.amount <= 0 or hit.reflect_of is not None:
                continue
            source = session.combatants.get(hit.source_id)
            target = session.combatants.get(hit.target_id)
            if source is None or target is None:
                continue
            if source.kind == "mob" and target.kind == "character":
                dmg_mult, _ = formulas.level_diff_modifiers(source.level, target.level, source.field_mob)
                hit.amount = max(round(hit.amount * dmg_mult), 1)
            elif target.kind == "mob" and source.kind == "character":
                _, taken_mult = formulas.level_diff_modifiers(target.level, source.level, target.field_mob)
                hit.amount = max(round(hit.amount * taken_mult), 1)
    # Отражение моба - доля урона, который удар нанёс на самом деле (см. PendingHit.reflect_of).
    for hit in ctx.hits:
        if hit.reflect_of is not None:
            hit.amount = max(round(hit.reflect_of.amount * hit.reflect_pct), 1)

    # Патч 45, ч.1: снимок ПОСЛЕ прямых самомутаций хода (себестоимость HP у
    # Багрового пира/Круга тьмы — actor.current_hp меняется РАНЬШЕ, внутри
    # хендлера навыка, в обход damage_taken/heal_taken) — иначе лог лечения
    # ниже сравнивал бы hp_before СО СТАРТА ХОДА с итоговым HP и показывал бы
    # хилу знак себестоимости пополам с ней ("восполняет кровью: -11 HP" на
    # деле означало "заплатил 22, вылечил 11, кап отрезал остальное" — само
    # лечение было положительным и капалось верно, просто лог показывал не то).
    hp_before_apply = {c.id: c.current_hp for c in session.combatants.values()}

    # --- Применение по фазам (2026-10-19, предложение игрока) ---
    # Против мобов ход идёт по порядку: сначала удары игроков, потом удары
    # мобов и яды, а лечение доходит в конце хода вместе с ними (одной суммой,
    # поэтому по-прежнему спасает от смертельного удара). Раньше всё было
    # одной суммой, и лог врал о порядке: «Мистик лечит Стража 0 -> 25» стояло
    # выше удара волка, который его и уронил. Вариант «лечение до мобов»
    # проверяли: хил по почти полному союзнику сгорал, Архивариус 20% -> 11%,
    # обоз втроём 51% -> 35%; этот вариант баланс не меняет (сим совпал).
    # В PvP обе стороны - игроки, там ход остаётся одновременным.
    applied_by_hit: dict[int, int] = {}
    shielded_by_hit: dict[int, int] = {}
    if session.mode == CombatMode.PVE:
        def players_turn(hit) -> bool:
            src = session.combatants.get(hit.source_id)
            return src is not None and src.kind == "character" and not hit.is_tick

        phases = [
            ([h for h in ctx.hits if players_turn(h)], []),
            ([h for h in ctx.hits if not players_turn(h)], list(ctx.heals)),
        ]
    else:
        phases = [(list(ctx.hits), list(ctx.heals))]

    log_phases: list[tuple[list, list]] = []
    for index, (hits, heals) in enumerate(phases):
        if index > 0:
            # Павший в фазе игроков больше не бьёт и не получает урона: мёртвый
            # моб не отвечает, яд по трупу не тикает, лечить мёртвого нечем.
            hits = [
                h for h in hits
                if session.combatants[h.target_id].alive
                and (h.is_tick or session.combatants[h.source_id].alive)
            ]
            heals = [h for h in heals if session.combatants[h.target_id].alive]
        reflects = _apply_phase(session, hits, heals, ctx, rng, applied_by_hit, shielded_by_hit, result)
        log_phases.append((hits + reflects, heals))
    ctx.hits = [h for hits, _ in log_phases for h in hits]
    ctx.heals = [h for _, heals in log_phases for h in heals]

    # --- Строки лога: единый краткий формат везде — PvE, PvP, рейды (патч 43,
    # ч.1) — образность убрана из пошагового лога, режим влияет только на
    # точность % (display.MODE_PVE_RAID — один знак после запятой). ---
    result.lines.extend(ctx.lines)
    result.prelude_line_count = len(result.lines)  # патч 51, ч.5: граница для game/combat/battle_log.py
    running_hp = dict(hp_before_apply)
    # Порядок лога = порядок фаз: удары игроков, удары мобов, лечение.
    # battle_log берёт удары из hit_renders, а лечение из heal_renders
    # отдельно, поэтому в result.lines удары идут подряд, лечение - после.
    hit_lines: list[str] = []
    heal_lines: list[str] = []
    for hits, heals in log_phases:
        for hit in hits:
            source = session.combatants[hit.source_id]
            target = session.combatants[hit.target_id]
            h_before = running_hp[target.id]
            applied = applied_by_hit.get(id(hit), hit.amount)
            h_after = h_before - applied
            running_hp[target.id] = h_after
            hit_lines.append(
                combat_flavor.render_hit(
                    source.name, target.name,
                    label=hit.label, amount=applied, crit=hit.crit, missed=hit.missed, is_dot=hit.is_dot,
                    hp_before=h_before, hp_after=h_after, max_hp=target.max_hp, mode=mode,
                    shielded=shielded_by_hit.get(id(hit), 0),
                )
            )
            result.hit_renders.append(
                RenderedHit(
                    source_id=source.id, target_id=target.id, source_side=source.side, target_side=target.side,
                    label=hit.label, amount=applied, crit=hit.crit, missed=hit.missed, is_dot=hit.is_dot,
                    is_tick=hit.is_tick,
                    hp_before=h_before, hp_after=h_after, max_hp=target.max_hp,
                    absorbed=hit.blocked + max(hit.amount - applied, 0),
                    marked=hit.marked, blocked=hit.blocked,
                    shielded=shielded_by_hit.get(id(hit), 0),
                )
            )
        for heal in heals:
            source = session.combatants[heal.source_id]
            target = session.combatants[heal.target_id]
            h_before = running_hp[target.id]
            h_after = min(h_before + heal.amount, target.max_hp)
            # В лог идёт ФАКТИЧЕСКИ восполненное, а не запрошенное. Лечение поверх
            # полного HP не восполняет ничего, и строка «восполнено 1 HP
            # (100.0% -> 100.0%)» сама себе противоречила. Ноль не печатаем вовсе:
            # строка, в которой не изменилось ни число, ни проценты, - это шум,
            # а в рейде на пятерых такого шума приходило по пять строк за ход.
            applied = h_after - h_before
            if applied <= 0:
                continue
            running_hp[target.id] = h_after
            heal_lines.append(
                display.action_line(
                    source.name, heal.label, target.name,
                    h_before, h_after, target.max_hp, mode,
                )
            )
            result.heal_renders.append(
                RenderedHeal(
                    source_id=source.id, target_id=target.id, source_side=source.side, target_side=target.side,
                    label=heal.label, amount=applied, hp_before=h_before, hp_after=h_after, max_hp=target.max_hp,
                )
            )
    result.lines.extend(hit_lines)
    result.lines.extend(heal_lines)

    # --- Тик длительностей, КД, контроля; очистка однотиковых состояний ---
    pvp = session.mode != CombatMode.PVE  # DR-стрик считаем только в PvP
    for combatant in session.combatants.values():
        # Пепельная лихорадка (патч 16): самоурон + эскалация КАЖДЫЙ активный
        # ход, включая ход применения (эликсир — бесплатное действие).
        for effect in combatant.effects_of(EffectKind.ASHEN_FEVER):
            if not combatant.alive:
                continue
            before_hp = combatant.current_hp
            # Метнутая склянкой - и жжёт слабее, и растёт с той же силой.
            power = getattr(effect, "power", 1.0)
            self_dmg = max(round(combatant.max_hp * ec.ASHEN_FEVER_SELF_DAMAGE_PCT_MAX_HP * power), 1)
            combatant.current_hp -= self_dmg
            _apply_last_breath_guard(combatant, result)
            result.lines.append(
                f"🔥 Пепельная лихорадка жжёт {combatant.name} "
                f"{display.hp_delta_line(before_hp, combatant.current_hp, combatant.max_hp, _display_mode(session))}"
            )
            step = round(effect.value / (ec.ASHEN_FEVER_DAMAGE_BONUS_STEP * power))
            effect.value = ec.ASHEN_FEVER_DAMAGE_BONUS_STEP * power * (step + 1)

        for effect in combatant.effects:
            # Немедленные эффекты (FREEZE, эликсиры-патч16) тикают всегда;
            # прочие свежие эффекты не тикают в ход наложения
            if id(effect) in preexisting_effects or effect.kind in _IMMEDIATE_EFFECT_KINDS:
                effect.remaining_ticks -= 1

        # Щит (Второе сердце, Оберег; патч 16) не пробит за отведённые ходы - остаток лечит
        for effect in combatant.effects_of(EffectKind.SHIELD_POOL):
            if effect.remaining_ticks <= 0 and effect.value > 0 and combatant.alive:
                if getattr(effect, "tag", None) == ECHO_TAG:
                    # Щит из перелечивания не лечит снова (2026-10-18): иначе
                    # лечение -> щит -> лечение ходили по кругу.
                    effect.value = 0
                    continue
                # Без затухания PvP: щит уже срезан, когда его вешали, второй
                # срез на остатке - двойной (баг 241, 2026-10-30).
                heal = round(effect.value)
                before_hp = combatant.current_hp
                combatant.current_hp = min(combatant.current_hp + heal, combatant.max_hp)
                if combatant.current_hp == before_hp:
                    # здоровье полное - строка «+0 HP» только путает
                    effect.value = 0
                    continue
                result.lines.append(
                    f"🛡️ {shield_name(effect)} {combatant.name} обращается в исцеление "
                    f"{display.hp_delta_line(before_hp, combatant.current_hp, combatant.max_hp, _display_mode(session))}"
                )
                result.shield_heals.append((effect.source_id, combatant.id, combatant.current_hp - before_hp))
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

        # Память подкласса о ходе (Возмездие, Жажда крови, Ускользание,
        # Танцор клинков) - общая с дуэлью, см. game/combat/shared_rules.py.
        shared_rules.end_turn_memory(combatant, session.tick_number)

        # Истёкшие в этот ход ДоТы нужны «Токсичному всплеску» - после фильтра
        # эффектов до них уже не добраться.
        combatant._expired_dots = [
            e for e in combatant.effects if e.kind == EffectKind.DOT and e.remaining_ticks <= 0
        ]
        combatant.effects = [e for e in combatant.effects if e.remaining_ticks > 0]
        combatant.decay_debuffs(preexisting_effects)  # уязвимость и ослабление слабеют каждый ход (2026-10-16)
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

    # --- Патч 56, Отравитель: «Токсичный всплеск» и «Зараза»/«Эпидемия» ---
    shared_rules.poison_end_effects(session, result.lines, alive_before)

    # --- Смерти и исход ---
    result.deaths = [cid for cid in alive_before if not session.combatants[cid].alive]
    shared_rules.inspiration_on_deaths(session, result.lines, result.deaths)

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
