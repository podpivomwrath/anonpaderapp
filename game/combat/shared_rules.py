"""Правила боя, общие для ОБОИХ движков: тикового (game/combat/resolver.py,
PvE и групповой PvP) и дуэльного (game/combat/duel_engine.py, 1x1).

Зачем модуль. Дуэль резолвит ходы последовательно, тик - одновременно, поэтому
циклы хода у них разные и общими быть не могут. А вот ПРАВИЛА - урон яда,
поглощение щитом, память Клинка теней, окно блока Стража, эффекты конца яда,
Воодушевление на добивании - одинаковы в любом бою. Пока они жили только в
резолвере, четверть пула Отравителя и половина пула Клинка теней молча не
работали в дуэли, а яд в дуэли ещё и проходил сквозь щиты, хотя в групповом
бою щит его держит. Всё, что должно вести себя одинаково, живёт здесь и
вызывается из обоих движков.

Функции намеренно не знают про TickResult/DuelResult: строки лога они дописывают
в переданный список, а урон возвращают числом.
"""

from game.combat import balance_config as bc
from game.combat import stat_model
from game.combat.session import (
    CombatantState,
    CombatSessionState,
    BURN_TAG,
    ECHO_TAG,
    Effect,
    EffectKind,
    shield_name,
)

# --- Яд ---


def poison_tick_damage(effect: Effect, source: CombatantState | None,
                       target: CombatantState | None = None) -> int:
    """Урон одного тика ДоТа с учётом баффов ИСТОЧНИКА яда, а не жертвы:
    «Разъедающий токсин» (+% ко всему яду) и «Некроз» (+% за каждый стак).
    Без баффов множитель ровно 1.0 - число то же, что было до патча 56.
    target - жертва: её Уязвимость усиливает и яд (2026-10-25, жалоба: уязвимость
    Отравителя не работала - его урон почти весь ядом, а яд её не видел)."""
    multiplier = 1.0
    if source is not None:
        multiplier += source.buff_modifiers.get("poison_damage_bonus", 0.0)
        multiplier += source.buff_modifiers.get("poison_damage_per_stack", 0.0) * effect.stacks
        # Общий бонус урона (еда, пресет) - и к ДоТу (2026-10-29, баг-репорт:
        # блюдо на урон не усиливало яд, а у Отравителя он почти весь урон).
        multiplier += source.buff_modifiers.get("damage_bonus", 0.0)
        multiplier *= stat_model.ACTIVE.effect_power(source.stats)
    if target is not None:
        # Руна «Литая кираса» ослабляет уязвимость и для яда, как для ударов.
        multiplier *= 1.0 + target.effect_total(EffectKind.VULNERABILITY) * max(
            1.0 - target.buff_modifiers.get("rune:cast_cuirass", 0.0), 0.0)
    multiplier *= rune_dot_mult(effect, source, target)  # руны (2026-10-31)
    return max(round(effect.value * effect.stacks * multiplier), 1)


def poison_shield_pierce(source: CombatantState | None) -> float:
    """«Токсикология»: доля щита, мимо которой проходит яд."""
    return source.buff_modifiers.get("poison_shield_pierce", 0.0) if source is not None else 0.0


def absorb_by_shields(
    target: CombatantState,
    amount: int,
    lines: list[str],
    *,
    pierce: float = 0.0,
) -> int:
    """Проводит урон через однотиковый щит и через все долгие щиты (Второе
    сердце, Оберег, свиток, щиты мобов), возвращает то, что дошло до здоровья.

    pierce > 0 (яд под «Токсикологией») уменьшает ПОГЛОЩАЕМУЮ ДОЛЮ УРОНА, а не
    размер щита: пробитая часть проходит всегда, даже сквозь огромный щит.
    Доля общая на оба вида щита - игроку обещан «щит» вообще, и прятаться от
    яда за «Вторым сердцем» нельзя так же, как за однотиковым."""
    if amount <= 0:
        return amount
    budget = round(amount * (1.0 - pierce)) if pierce else amount
    if target.shield > 0 and budget > 0:
        absorbed = min(target.shield, budget)
        target.shield -= absorbed
        amount -= absorbed
        budget -= absorbed
        if absorbed:
            lines.append(f"Щит {target.name} поглощает {absorbed} урона 🛡")
    # Долгие щиты - все по очереди, первым тот, что истекает раньше
    # (2026-10-13). Раньше урон брал только первый щит в списке: сверх него
    # шёл в здоровье при живом втором щите, а опустевший щит висел первым до
    # конца срока и закрывал собой остальные.
    pool = sorted(
        (e for e in target.effects_of(EffectKind.SHIELD_POOL) if e.value > 0),
        key=lambda e: e.remaining_ticks,
    )
    for shield in pool:
        if budget <= 0:
            break
        pool_absorbed = min(int(shield.value), budget)
        shield.value -= pool_absorbed
        amount -= pool_absorbed
        budget -= pool_absorbed
        if pool_absorbed:
            lines.append(f"🛡️ {shield_name(shield)} {target.name} поглощает {pool_absorbed} урона")
    # Пустые щиты снимаем сразу: в остатке у здоровья их и так не видно.
    target.effects = [
        e for e in target.effects if not (e.kind == EffectKind.SHIELD_POOL and e.value <= 0)
    ]
    return amount


def cap_incoming(target: CombatantState, amount: int) -> int:
    """«Несокрушимый» (DAMAGE_CAP): урон за один удар не выше доли макс. HP.
    До щитов - щит гасит то, что осталось. В дуэли до 2026-10-22 не работал."""
    cap = target.effect_total(EffectKind.DAMAGE_CAP)
    if cap <= 0 or amount <= 0:
        return amount
    return min(amount, max(round(target.max_hp * cap), 1))


def settle_lifesteal(heals: list, dealt: dict[int, int]) -> None:
    """Вампиризм - от урона, который прошёл (2026-10-24, жалоба: удар по
    Стражу под «Несокрушимым» лечил от полного удара). dealt - id(удара) ->
    урон после потолка и купола (щит - тоже попадание). Удар, которого нет в
    dealt, не прошёл вовсе."""
    for heal in heals:
        if heal.of_hit is None:
            continue
        hit_dealt = dealt.get(id(heal.of_hit), 0)
        amount = max(round(hit_dealt * heal.ratio), 0)
        heal.amount = max(amount, heal.floor) if hit_dealt > 0 else 0


def block_heal_amount(target: CombatantState, amount: int) -> int:
    """«Глухая оборона» (BLOCK_STANCE + BLOCK_HEAL): лечение за каждый удар,
    пришедшийся в стойку. 0 - стойки нет или удар пустой. В дуэли до
    2026-10-22 не работало."""
    if amount <= 0 or target.effect_total(EffectKind.BLOCK_STANCE) <= 0:
        return 0
    pct = target.effect_total(EffectKind.BLOCK_HEAL)
    return round(target.max_hp * pct) if pct > 0 else 0


def block_reflect_amount(target: CombatantState, blocked: int) -> int:
    """Страж, «Отражение»: доля СРЕЗАННОГО блоком урона уходит обратно
    атакующему. Считается от заблокированного, а не от прошедшего, поэтому
    живёт отдельно от «Крови за кровь». 0 - баффа нет или блок не сработал."""
    pct = target.buff_modifiers.get("block_reflect_pct", 0.0)
    if pct <= 0 or blocked <= 0:
        return 0
    return max(round(blocked * pct), 1)


def poison_end_effects(
    session: CombatSessionState, lines: list[str], alive_before: set[int]
) -> None:
    """«Токсичный всплеск»: когда последний стак яда истекает, цель получает
    добавочный урон долей от тик-урона этого яда. «Зараза»: если отравленная
    цель погибла, яд переходит на другого противника; «Эпидемия» сохраняет при
    переходе полную силу, без неё сила падает вдвое.

    Обе механики - о КОНЦЕ жизни яда, поэтому живут в одном месте: сразу после
    тика длительностей и до подсчёта смертей. Читает combatant._expired_dots,
    который движок обязан заполнить перед фильтрацией эффектов."""
    for combatant in list(session.combatants.values()):
        for effect in list(getattr(combatant, "_expired_dots", [])):
            source = session.combatants.get(effect.source_id)
            if source is None:
                continue
            burst_pct = source.buff_modifiers.get("poison_expire_burst_pct", 0.0)
            if burst_pct > 0 and combatant.alive:
                # Доля от настоящего тика яда - с «Разъедающим токсином» и
                # «Некрозом» (2026-10-24: от голого яда выходила треть, не половина).
                amount = max(round(poison_tick_damage(effect, source, combatant) * burst_pct), 1)
                # Через щиты, как сам яд (2026-10-22).
                amount = absorb_by_shields(combatant, amount, lines, pierce=poison_shield_pierce(source))
                if amount > 0:
                    combatant.current_hp -= amount
                    lines.append(f"☠ Яд на {combatant.name} вспыхивает напоследок - {amount} урона")
                    # «Последний вздох» ловит и этот урон (2026-10-23).
                    if combatant.current_hp <= 0 and combatant.has_effect(EffectKind.LAST_BREATH):
                        combatant.effects = [e for e in combatant.effects if e.kind != EffectKind.LAST_BREATH]
                        combatant.current_hp = 1
                        lines.append(f"✨ Последний вздох удерживает {combatant.name} на грани (1 HP)")
        combatant._expired_dots = []

    for cid in alive_before:
        victim = session.combatants[cid]
        if victim.alive:
            continue
        for effect in list(victim.effects_of(EffectKind.DOT)):
            source = session.combatants.get(effect.source_id)
            if source is None or source.buff_modifiers.get("plague_spread", 0.0) <= 0:
                continue
            candidates = [c for c in session.alive_enemies_of(source) if c.id != victim.id]
            if not candidates:
                continue
            full_power = source.buff_modifiers.get("epidemic_full_power", 0.0) > 0
            value = effect.value if full_power else effect.value * 0.5
            new_target = candidates[0]
            existing = new_target.effect_from(EffectKind.DOT, effect.source_id)
            if existing is not None:
                existing.stacks = min(existing.stacks + effect.stacks, bc.POISONER_MAX_STACKS)
                existing.value = max(existing.value, value)
                existing.remaining_ticks = max(existing.remaining_ticks, effect.remaining_ticks)
            else:
                new_target.effects.append(
                    Effect(kind=EffectKind.DOT, value=value,
                           remaining_ticks=max(effect.remaining_ticks, 1),
                           source_id=effect.source_id, stacks=effect.stacks)
                )
            lines.append(f"☠ Яд перекидывается на {new_target.name}")


# --- Клинок теней и Страж: память между ходами ---


def recovery_mult(turn_number: int, max_turns: int | None) -> float:
    """Сила лечения и щитов в PvP: 1.0 в первый ход, PVP_RECOVERY_FLOOR в последний."""
    if not bc.PVP_RECOVERY_DECAY or not max_turns or max_turns <= 1:
        return 1.0
    share = min(max((max_turns - turn_number) / (max_turns - 1), 0.0), 1.0)
    return bc.PVP_RECOVERY_FLOOR + (1.0 - bc.PVP_RECOVERY_FLOOR) * share


def set_recovery(session: CombatSessionState, max_turns: int | None) -> None:
    """Открыт новый ход PvP-боя: затухание лечения и щитов для всех бойцов."""
    mult = recovery_mult(session.tick_number, max_turns)
    for c in session.combatants.values():
        c.recovery_mult = mult


def recovered(target: CombatantState, amount: int) -> int:
    """Входящее лечение после затухания в PvP (вне PvP множитель 1)."""
    mult = getattr(target, "recovery_mult", 1.0)
    return amount if mult >= 1.0 else round(amount * mult)


def begin_turn_flags(session: CombatSessionState, turn_number: int) -> None:
    """Флаги, к которым compute_hit не имеет доступа (сессии он не видит):
    есть ли живые союзники и открыт ли в этот ход «Второй шанс». Ставятся
    в начале хода, до любых ударов."""
    for c in session.combatants.values():
        c.has_allies = bool(session.alive_allies_of(c))
        c.dodged_this_tick = False
        c.crit_this_tick = False
        interval = int(c.buff_modifiers.get("second_chance_interval", 0))
        c.second_chance_active = bool(interval) and turn_number % interval == 0
    rune_gaze(session)  # «Тяжёлый взгляд»: срез в start_session, здесь - мобы, подошедшие посреди боя


def end_turn_memory(combatant: CombatantState, turn_number: int) -> None:
    """Память подкласса о прошедшем ходе. Вызывается ПОСЛЕ тика длительностей,
    но ДО reset_transient, который гасит blocked_this_tick."""
    # Страж, «Возмездие»: окно последних N ходов по срезанному блоком.
    combatant.blocked_recent.append(combatant.blocked_this_tick)
    if len(combatant.blocked_recent) > bc.GUARDIAN_RETRIBUTION_WINDOW_TURNS:
        del combatant.blocked_recent[:-bc.GUARDIAN_RETRIBUTION_WINDOW_TURNS]

    # Клинок теней, «Жажда крови»: после крита следующий удар критует
    # гарантированно, но не чаще раза в N ходов.
    bloodlust = int(combatant.buff_modifiers.get("bloodlust_cooldown", 0))
    if bloodlust and combatant.crit_this_tick and turn_number >= combatant.bloodlust_ready_tick:
        combatant.guaranteed_crit_next = True
        combatant.bloodlust_ready_tick = turn_number + bloodlust
    # «Ускользание» смотрит на уворот ПРОШЛОГО хода.
    combatant.dodged_last_tick = combatant.dodged_this_tick
    # «Танцор клинков»: удачный уворот продлевает уже висящие Метки, а не даёт
    # им истечь - иначе уворот их в этом движке никак не касается.
    if combatant.dodged_this_tick and combatant.buff_modifiers.get("blade_dancer", 0.0) > 0:
        for mark_effect in combatant.effects_of(EffectKind.MARK):
            mark_effect.remaining_ticks = max(
                mark_effect.remaining_ticks, bc.SHADOW_BLADE_MARK_DURATION
            )


def inspiration_on_deaths(
    session: CombatSessionState, lines: list[str], deaths: list[int]
) -> None:
    """Клинок теней, «Воодушевление»: добитая цель с Меткой лечит союзников её
    владельца и даёт им бонус урона. Только в бою с союзниками - в дуэли
    нет-оп, потому что союзников там нет."""
    for cid in deaths:
        victim = session.combatants[cid]
        for mark in victim.effects_of(EffectKind.MARK):
            owner = session.combatants.get(mark.source_id)
            if owner is None or owner.buff_modifiers.get("inspiration_heal_pct", 0.0) <= 0:
                continue
            allies = session.alive_allies_of(owner)
            if not allies:
                continue
            heal_pct = owner.buff_modifiers["inspiration_heal_pct"]
            dmg_bonus = owner.buff_modifiers.get("inspiration_damage_bonus", 0.0)
            for ally in allies:
                ally.current_hp = min(ally.current_hp + recovered(ally, round(ally.max_hp * heal_pct)), ally.max_hp)
                if dmg_bonus > 0:
                    ally.apply_effect(
                        EffectKind.DAMAGE_BUFF, dmg_bonus, bc.SHADOW_BLADE_INSPIRATION_TURNS, owner.id
                    )
            lines.append(f"{owner.name} воодушевляет союзников добычей")


# --- Клинок теней: Метка добычи ---


def add_mark(actor: CombatantState, target: CombatantState, stacks: int = 1) -> None:
    """+stacks Метки добычи от актёра на цели (до максимума), длительность
    обновляется до полной."""
    mark = target.effect_from(EffectKind.MARK, actor.id)
    if mark is not None:
        mark.stacks = min(mark.stacks + stacks, bc.SHADOW_BLADE_MARK_MAX_STACKS)
        mark.remaining_ticks = max(mark.remaining_ticks, bc.SHADOW_BLADE_MARK_DURATION)
    else:
        target.effects.append(
            Effect(kind=EffectKind.MARK, value=1.0, remaining_ticks=bc.SHADOW_BLADE_MARK_DURATION,
                   source_id=actor.id, stacks=min(stacks, bc.SHADOW_BLADE_MARK_MAX_STACKS))
        )


def passive_mark(actor: CombatantState | None, target: CombatantState, hit, rng, lines: list[str]) -> None:
    """Пассивка Клинка теней (2026-10-19): любой попавший удар (атака или
    навык, не ДоТ) с шансом добавляет стак к Метке добычи. Работает в обоих
    движках.

    Только к уже висящей метке: открывает её Скользящий рез. Иначе метки
    летели отовсюду и Рез стал не нужен (жалоба игрока 2026-10-19)."""
    if actor is None or getattr(actor, "subclass_id", None) != "shadow_blade":
        return
    if target.effect_from(EffectKind.MARK, actor.id) is None:
        return
    if hit.missed or hit.is_dot or hit.amount <= 0 or actor.id == target.id or not target.alive:
        return
    if rng.random() >= bc.SHADOW_BLADE_PASSIVE_MARK_CHANCE:
        return
    add_mark(actor, target)
    lines.append(f"{target.name} помечен добычей ({actor.name}) 🎯")


# --- Руны (2026-10-31) --------------------------------------------------------
# Общие для тикового боя и дуэли правила рун. Ключи «rune:...» кладёт в
# buff_modifiers preset_service.resolve_active_modifiers (в PvP уже ослаблены).
# Поля бойца читаем через getattr: старые снимки боя их не знают.

def _rune(c: CombatantState | None, key: str) -> float:
    return c.buff_modifiers.get(key, 0.0) if c is not None else 0.0


def rune_guard(combatant: CombatantState, lines: list[str], rng=None) -> None:
    """После урона: «Не сегодня» - шанс пережить смертельный удар, «Запас
    дыхания» - лечение, когда здоровья меньше 30%. Оба - раз за бой."""
    import random as _random

    rng = rng or _random
    if combatant.current_hp <= 0:
        chance = _rune(combatant, "rune:not_today")
        if chance and not getattr(combatant, "rune_saved", False) and rng.random() < chance:
            combatant.rune_saved = True
            combatant.current_hp = 1
            lines.append(f"🪨 Не сегодня: {combatant.name} остаётся на ногах с 1 HP")
        return
    heal = _rune(combatant, "rune:spare_breath")
    if heal and not getattr(combatant, "rune_breath_used", False) and combatant.current_hp < combatant.max_hp * 0.3:
        combatant.rune_breath_used = True
        amount = recovered(combatant, max(round(combatant.max_hp * heal), 1))
        combatant.current_hp = min(combatant.current_hp + amount, combatant.max_hp)
        lines.append(f"🪨 Запас дыхания: {combatant.name} +{amount} HP")


def rune_on_hit(source: CombatantState | None, target: CombatantState, hit, heals: list) -> float:
    """Удар лёг: вампиризм «Красной жажды» и «Кровяной кромки» (лечением от
    прошедшего урона, через settle_lifesteal), счётчик «Злобы». Возвращает
    долю «Колючей брони» цели для ответного урона."""
    from game.combat.skills import PendingHeal

    if hit.missed or hit.is_dot or hit.amount <= 0:
        return 0.0
    target.hits_taken = getattr(target, "hits_taken", 0) + 1
    if source is not None and source.id != target.id:
        ratio = _rune(source, "rune:red_thirst")
        skill_id = getattr(hit, "skill_id", None)
        if skill_id:
            ratio += _rune(source, f"rune:blood_edge@{skill_id}")
        if ratio > 0:
            heals.append(PendingHeal(source_id=source.id, target_id=source.id, amount=round(hit.amount * ratio),
                                     label="пьёт кровь", of_hit=hit, ratio=ratio))
    return _rune(target, "rune:thorn_plate")


def rune_dot_mult(effect: Effect, source: CombatantState | None, target: CombatantState | None) -> float:
    """Яд и горение: «Едкость» навыка, «Жар и иней» (горение) у источника,
    «Горькая кровь» у жертвы."""
    mult = 1.0
    if source is not None:
        burn = getattr(effect, "tag", None) == BURN_TAG
        skills = ("elementalist_fire",) if burn else ("poisoner_venom", "poisoner_toxic_burst")
        mult += max(_rune(source, f"rune:acrid@{s}") for s in skills)
        if burn:
            mult += _rune(source, "rune:heat_frost")
    if target is not None:
        mult *= max(1.0 - _rune(target, "rune:bitter_blood"), 0.1)
    return mult


def overflow_echo(source: CombatantState) -> float:
    """Доля лечения сверх максимума, которая уходит в щит: «Отголосок»
    Тёмного мистика (патч 56) и руна «Излишек» (2026-10-31)."""
    return source.buff_modifiers.get("heal_overflow_shield", 0.0) + _rune(source, "rune:surplus")


def overflow_shield(source: CombatantState, ally: CombatantState, overflow: int) -> int:
    """Перелечивание -> щит «Отголосок» на ally. Общее для тикового боя и
    дуэли. Возвращает, сколько щита добавилось (0 - упёрлись в потолок)."""
    amount = round(overflow * overflow_echo(source))
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
        return 0
    if current is not None:
        current.value += amount
        current.remaining_ticks = max(current.remaining_ticks, bc.DARK_MYSTIC_ECHO_DURATION)
    else:
        ally.apply_effect(EffectKind.SHIELD_POOL, amount, bc.DARK_MYSTIC_ECHO_DURATION, source.id, tag=ECHO_TAG)
    return amount


def rune_gaze(session: CombatSessionState) -> None:
    """«Тяжёлый взгляд»: у мобов клетки меньше здоровья - по самой сильной
    руне среди игроков боя, один раз на моба."""
    gaze = max((_rune(c, "rune:heavy_gaze") for c in session.combatants.values() if c.kind == "character"),
               default=0.0)
    if gaze <= 0:
        return
    for mob in session.combatants.values():
        if mob.kind != "mob" or not mob.field_mob or getattr(mob, "rune_gaze_done", False):
            continue
        mob.rune_gaze_done = True
        mob.max_hp = max(round(mob.max_hp * (1 - gaze)), 1)
        mob.current_hp = min(mob.current_hp, mob.max_hp)


def run_skill(handler, ctx, skill_id: str | None) -> None:
    """Навык с рунами: какой навык бьёт (руны навыков в compute_hit) и
    что сделать после него. Общий для тикового боя и дуэли."""
    actor = ctx.actor
    combatants = list(ctx.session.combatants.values())
    before = skill_snapshot(actor, combatants)
    heals_from = len(ctx.heals)
    cd_before = actor.cooldowns.get(skill_id, 0) if skill_id else 0
    actor.current_skill = skill_id
    try:
        handler(ctx)
    finally:
        actor.current_skill = None
    rune_cooldown(actor, skill_id, cd_before, ctx.rng)
    rune_after_skill(actor, skill_id, before, combatants, ctx, heals_from)


def rune_cooldown(actor: CombatantState, skill_id: str | None, cd_before: int, rng) -> None:
    """«Холодный счёт» и «Короткий взмах» - здесь, а не в set_cooldown:
    навыки подклассов ставят перезарядку напрямую, мимо него."""
    if not skill_id:
        return
    cd = actor.cooldowns.get(skill_id, 0)
    if cd <= cd_before:
        return  # навык перезарядку не ставил
    cold = _rune(actor, f"rune:cold_count@{skill_id}")
    if cold and rng.random() < cold:
        actor.cooldowns[skill_id] = cd_before
        return
    swing = _rune(actor, f"rune:short_swing@{skill_id}")
    if swing and cd > 1 and rng.random() < swing:
        actor.cooldowns[skill_id] = cd - 1


def skill_snapshot(actor: CombatantState, combatants) -> dict:
    """Что висело от бойца до навыка: для рун «Тягучесть» и «Подпорка»."""
    return {id(e): (e.remaining_ticks, e.value) for c in combatants for e in c.effects if e.source_id == actor.id}


def rune_after_skill(actor: CombatantState, skill_id: str | None, before: dict, combatants, ctx, heals_from: int) -> None:
    """После навыка: «Тягучесть» (эффекты навыка дольше), «Подпорка» (щиты и
    лечение навыка сильнее), «Обратная молитва» (часть лечения бьёт врага),
    «Отскок» (вторая цель в группе)."""
    if not skill_id:
        return
    mods = actor.buff_modifiers
    if not any(key.startswith("rune:") for key in mods):
        return
    rng = ctx.rng
    fresh = [e for c in combatants for e in c.effects
             if e.source_id == actor.id and (id(e) not in before or e.remaining_ticks > before[id(e)][0])]
    viscous = mods.get(f"rune:viscous@{skill_id}", 0.0)
    if viscous and fresh and rng.random() < viscous:
        for e in fresh:
            e.remaining_ticks += 1
        ctx.lines.append(f"🪨 Тягучесть: эффект «{skill_id_name(skill_id)}» продержится на ход дольше")
    prop = mods.get(f"rune:prop@{skill_id}", 0.0)
    new_heals = [h for h in ctx.heals[heals_from:] if h.source_id == actor.id]
    if prop:
        for e in fresh:
            if e.kind == EffectKind.SHIELD_POOL:
                # apply_effect перезаписывает щит целиком - усиливаем весь.
                e.value = round(e.value * (1 + prop))
        for h in new_heals:
            h.amount = round(h.amount * (1 + prop))
            h.ratio *= 1 + prop
    prayer = mods.get("rune:reverse_prayer", 0.0)
    healed = sum(max(h.amount, 0) for h in new_heals)
    if prayer and healed > 0:
        enemies = [c for c in combatants if c.side != actor.side and c.alive]
        if enemies:
            from game.combat.skills import PendingHit

            target = min(enemies, key=lambda c: c.current_hp)
            ctx.hits.append(PendingHit(source_id=actor.id, target_id=target.id,
                                       amount=max(round(healed * prayer), 1), label="обратная молитва"))
    ricochet = mods.get(f"rune:ricochet@{skill_id}", 0.0)
    if ricochet and rng.random() < ricochet:
        hit_ids = {h.target_id for h in ctx.hits if h.source_id == actor.id}
        others = [c for c in combatants if c.side != actor.side and c.alive and c.id not in hit_ids]
        if hit_ids and others:
            from game.combat.skills import compute_hit

            ctx.hits.append(compute_hit(actor, rng.choice(others), rng, label="отскок", multiplier=0.4,
                                        is_ability=True))


def skill_id_name(skill_id: str) -> str:
    from game.combat.base_skills import BASE_SKILL_DEFS

    skill = BASE_SKILL_DEFS.get(skill_id)
    if skill is None:
        from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

        skill = SUBCLASS_SKILL_DEFS.get(skill_id)
    return skill.name if skill is not None else skill_id
