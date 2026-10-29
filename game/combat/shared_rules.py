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
        multiplier *= 1.0 + target.effect_total(EffectKind.VULNERABILITY)
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
