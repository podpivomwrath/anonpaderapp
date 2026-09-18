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
from game.combat.session import CombatantState, CombatSessionState, Effect, EffectKind


# --- Яд ---


def poison_tick_damage(effect: Effect, source: CombatantState | None) -> int:
    """Урон одного тика ДоТа с учётом баффов ИСТОЧНИКА яда, а не жертвы:
    «Разъедающий токсин» (+% ко всему яду) и «Некроз» (+% за каждый стак).
    Без баффов множитель ровно 1.0 - число то же, что было до патча 56."""
    multiplier = 1.0
    if source is not None:
        multiplier += source.buff_modifiers.get("poison_damage_bonus", 0.0)
        multiplier += source.buff_modifiers.get("poison_damage_per_stack", 0.0) * effect.stacks
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
    """Проводит урон через однотиковый щит и через «Второе сердце», возвращает
    то, что дошло до здоровья.

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
    pool = target.effects_of(EffectKind.SHIELD_POOL)
    if pool and budget > 0:
        first = pool[0]
        pool_absorbed = min(int(first.value), budget)
        first.value -= pool_absorbed
        amount -= pool_absorbed
        budget -= pool_absorbed
        if pool_absorbed:
            lines.append(f"🛡️ Второе сердце {target.name} поглощает {pool_absorbed} урона")
    return amount


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
                amount = max(round(effect.value * effect.stacks * burst_pct), 1)
                combatant.current_hp -= amount
                lines.append(f"☠ Яд на {combatant.name} вспыхивает напоследок - {amount} урона")
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
                ally.current_hp = min(ally.current_hp + round(ally.max_hp * heal_pct), ally.max_hp)
                if dmg_bonus > 0:
                    ally.apply_effect(
                        EffectKind.DAMAGE_BUFF, dmg_bonus, bc.SHADOW_BLADE_INSPIRATION_TURNS, owner.id
                    )
            lines.append(f"{owner.name} воодушевляет союзников добычей")
