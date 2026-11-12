"""Правила боя, общие для резолвера (game/combat/resolver.py) и механик рейдов
и разломов. Дуэльный движок (duel_engine.py) удалён 2026-11-05: с 2026-10-29
дуэль идёт на тиковом движке. Ниже - история, зачем модуль появился.

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
        # Бонус ко всему урону за ход - яду, горению, кровотечению (2026-11-05,
        # владелец: у дотов Элементалиста не было своих усилений).
        multiplier += source.buff_modifiers.get("dot_damage_bonus", 0.0)
        multiplier += source.buff_modifiers.get("poison_damage_per_stack", 0.0) * effect.stacks
        # «Весь урон» (еда) - и к ДоТу (2026-10-29, баг-репорт: блюдо на урон
        # не усиливало яд). Прямой урон (пассивки, дары) сюда не идёт (2026-11-05).
        multiplier += source.buff_modifiers.get("damage_bonus", 0.0)
        multiplier *= stat_model.ACTIVE.effect_power(source.stats)
        # Воля (2026-11-06) - горению и прочему; яду игрока нет: Воля уже в
        # силе его яда (2026-11-11, у не-Отравителей шла дважды).
        players_poison = source.kind == "character" and getattr(effect, "tag", None) != BURN_TAG
        if not players_poison:
            multiplier *= stat_model.ACTIVE.dot_power(source.stats)
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
                    else:
                        rune_guard(combatant, lines)
        combatant._expired_dots = []

    for cid in alive_before:
        victim = session.combatants[cid]
        if victim.alive:
            continue
        for effect in list(victim.effects_of(EffectKind.DOT)):
            if getattr(effect, "tag", None) == BURN_TAG:
                continue  # «Эпидемия» перекидывает яд, не огонь
            source = session.combatants.get(effect.source_id)
            if source is None or source.buff_modifiers.get("plague_spread", 0.0) <= 0:
                continue
            candidates = [c for c in session.alive_enemies_of(source) if c.id != victim.id]
            if not candidates:
                continue
            full_power = source.buff_modifiers.get("epidemic_full_power", 0.0) > 0
            value = effect.value if full_power else effect.value * 0.5
            new_target = candidates[0]
            existing = new_target.poison_from(effect.source_id)
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


def shield_value(holder: CombatantState, source_id: int, tag: str | None) -> int:
    """Сколько поглощения в щите этого бойца с этой меткой - для строки боя:
    после всех усилений и срезов (репорт 351)."""
    return round(sum(e.value for e in holder.effects
                     if e.kind == EffectKind.SHIELD_POOL and e.source_id == source_id
                     and getattr(e, "tag", None) == tag))


def recovered(target: CombatantState, amount: int) -> int:
    """Входящее лечение после затухания в PvP (вне PvP множитель 1),
    «Горькой раны» (2026-11-10: EffectKind.HEAL_REDUCTION) и «Порчи руин»."""
    mult = getattr(target, "recovery_mult", 1.0)
    reduction = target.heal_reduction() if hasattr(target, "heal_reduction") else 0.0
    mult *= 1.0 - reduction
    # «Порча руин» (2026-11-11): чем глубже этаж, тем слабее лечение и щиты.
    mult *= 1.0 - (getattr(target, "buff_modifiers", None) or {}).get("ruins_rot", 0.0)
    return amount if mult >= 1.0 else round(amount * mult)


def bitter_backlash(target: CombatantState, healed: int) -> int:
    """Пробуждение «Горькой раны»: доля лечения цели бьёт её саму. Доля -
    в метке эффекта "bitter:<доля>"."""
    if healed <= 0:
        return 0
    for effect in target.effects_of(EffectKind.HEAL_REDUCTION):
        tag = getattr(effect, "tag", None) or ""
        if effect.remaining_ticks > 0 and tag.startswith("bitter:"):
            share = float(tag.split(":", 1)[1] or 0)
            if share > 0:
                return max(round(healed * share), 1)
    return 0


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
    wind = _rune(combatant, "rune:second_wind")
    if wind and not getattr(combatant, "rune_wind_used", False) and combatant.current_hp < combatant.max_hp * wind:
        # «Свежие силы» (2026-11-05): раз за бой все перезарядки - в ноль.
        combatant.rune_wind_used = True
        if any(v > 0 for v in combatant.cooldowns.values()):
            combatant.cooldowns = {k: 0 for k in combatant.cooldowns}
            lines.append(f"🪨 Свежие силы: у {combatant.name} снова готовы все навыки")
    heal = _rune(combatant, "rune:spare_breath")
    if heal and not getattr(combatant, "rune_breath_used", False) and combatant.current_hp < combatant.max_hp * 0.3:
        combatant.rune_breath_used = True
        amount = recovered(combatant, max(round(combatant.max_hp * heal), 1))
        combatant.current_hp = min(combatant.current_hp + amount, combatant.max_hp)
        lines.append(f"🪨 Запас дыхания: {combatant.name} +{amount} HP")


def rune_will(target: CombatantState, rng) -> bool:
    """«Каменная воля» (2026-11-05): первый контроль в бою - шанс стряхнуть.
    Попытка одна: прошёл первый контроль - дальше руна молчит."""
    chance = _rune(target, "rune:stone_will")
    if not chance or getattr(target, "rune_will_used", False):
        return False
    target.rune_will_used = True
    return rng.random() < chance


def rune_last_word(session: CombatSessionState, alive_before: set[int], lines: list[str]) -> None:
    """«Последнее слово» (2026-11-05): павший в этот ход бьёт всех живых
    врагов на долю своего максимума здоровья. Через щиты, раз за бой; от его
    удара павшие словом не отвечают - цепочки нет."""
    fallen = [c for cid, c in session.combatants.items()
              if cid in alive_before and not c.alive and not getattr(c, "rune_last_word_done", False)]
    for dead in fallen:
        share = _rune(dead, "rune:last_word")
        if share <= 0:
            continue
        dead.rune_last_word_done = True
        amount = max(round(dead.max_hp * share), 1)
        enemies = [c for c in session.combatants.values() if c.side != dead.side and c.alive]
        if not enemies:
            continue
        lines.append(f"🪨 Последнее слово: {dead.name} падает и бьёт всех врагов на {amount}")
        # Павшие от слова в список выше не попали - их слово уже не прозвучит.
        for enemy in enemies:
            dealt = absorb_by_shields(enemy, cap_incoming(enemy, amount), [])
            enemy.current_hp = max(enemy.current_hp - dealt, enemy.hp_floor, 0)
            rune_guard(enemy, lines)


def rune_after_deaths(session: CombatSessionState, deaths: list[int], hits: list, lines: list[str], rng) -> None:
    """После смертей хода (2026-11-05): «За своих» - живым союзникам павшего
    +1 к счёту; «Без передышки» - добил навыком, шанс сбросить его перезарядку."""
    if not deaths:
        return
    for cid in deaths:
        dead = session.combatants[cid]
        if dead.kind != "character":
            continue
        for ally in session.combatants.values():
            if ally.side == dead.side and ally.alive and ally.id != cid:
                ally.allies_fallen = getattr(ally, "allies_fallen", 0) + 1
    done: set[tuple] = set()
    for hit in hits:
        skill_id = getattr(hit, "skill_id", None)
        if not skill_id or hit.target_id not in deaths or hit.missed:
            continue
        source = session.combatants.get(hit.source_id)
        if source is None or not source.alive or (source.id, skill_id) in done:
            continue
        from game.combat import ability_rules

        heal_kill = ability_rules.heal_on_kill(source, skill_id)
        if heal_kill and (source.id, skill_id, "heal") not in done and source.max_hp > 0:
            done.add((source.id, skill_id, "heal"))
            # через recovered: в PvP и под «Порчей руин» тоже слабее (репорт 352)
            gain = recovered(source, round(source.max_hp * heal_kill))
            source.current_hp = min(source.max_hp, source.current_hp + gain)
            lines.append(f"🟣 Добивание навыком «{skill_id_name(skill_id)}»: {source.name} лечится на {gain}")
        chance = _rune(source, f"rune:no_rest@{skill_id}") + ability_rules.reset_kill_chance(source, skill_id)
        if not chance or source.cooldowns.get(skill_id, 0) <= 0:
            continue
        done.add((source.id, skill_id))
        if rng.random() < chance:
            source.cooldowns[skill_id] = 0
            lines.append(f"🪨 Без передышки: навык «{skill_id_name(skill_id)}» у {source.name} снова готов")


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
            from game.combat import ability_rules

            ratio += ability_rules.lifesteal(source, skill_id)  # ступень руны-навыка
        if ratio > 0:
            heals.append(PendingHeal(source_id=source.id, target_id=source.id, amount=round(hit.amount * ratio),
                                     label="пьёт кровь", of_hit=hit, ratio=ratio))
    return _rune(target, "rune:thorn_plate")


def rune_dot_mult(effect: Effect, source: CombatantState | None, target: CombatantState | None) -> float:
    """Яд и горение: «Едкость» навыка, «Жар и иней» (горение) у источника,
    стойкость к периодическому урону у жертвы (руна «Горькая кровь», вещи, перстень -
    preset_service сводит их в resist_dot)."""
    mult = 1.0
    if source is not None:
        burn = getattr(effect, "tag", None) == BURN_TAG
        mult += _rune(source, "rune:acrid@" + ("elementalist_fire" if burn else "poisoner_venom"))
        # Руна-навык (2026-11-10): сила навыка, что повесил яд. Горение -
        # доля удара Плети, сила руны в нём уже есть (2026-11-11).
        if not burn:
            mult += _rune(source, "rune:poisoner_venom")
        synergy = source.buff_modifiers.get("burn_poison_synergy", 0.0)
        if synergy and target is not None:
            mine = [e for e in target.effects_of(EffectKind.DOT) if e.source_id == source.id]
            if any(getattr(e, "tag", None) == BURN_TAG for e in mine) and any(
                    getattr(e, "tag", None) != BURN_TAG for e in mine):
                mult += synergy  # пробуждение Огненной плети: яд и горение вместе
        if burn:
            mult += _rune(source, "rune:heat_frost")
    if target is not None:
        mult *= max(1.0 - _rune(target, "resist_dot"), 0.1)
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
    hits_from = len(ctx.hits)
    cd_before = actor.cooldowns.get(skill_id, 0) if skill_id else 0
    actor.current_skill = skill_id
    actor.cd_free = None
    from game.combat import session as session_mod

    session_mod.SHIELD_BOOST = _shield_boost(actor, skill_id)
    try:
        handler(ctx)
    finally:
        actor.current_skill = None
        session_mod.SHIELD_BOOST = None
    cd_free_line(actor, skill_id, ctx.lines)
    rune_cooldown(actor, skill_id, cd_before, ctx.rng, ctx.lines)
    rune_after_skill(actor, skill_id, before, combatants, ctx, heals_from)
    from game.combat import ability_rules

    ability_rules.after_skill(actor, skill_id, ctx, hits_from)  # ступени руны-навыка (2026-11-10)
    rune_once_more(handler, ctx, skill_id)


def cd_free_line(actor: CombatantState, skill_id: str | None, lines: list[str]) -> None:
    """Навык не ушёл на перезарядку (шанс из баффов и даров, «Перегрузка») -
    строка в лог, иначе видно только по панели (репорт 343)."""
    why, actor.cd_free = actor.cd_free, None
    if not why or not skill_id:
        return
    head = "⚡ Перегрузка" if why == "overload" else "🌀 Без перезарядки"
    lines.append(f"{head}: навык «{skill_id_name(skill_id)}» у {actor.name} снова готов")


def rune_once_more(handler, ctx, skill_id: str | None) -> None:
    """«Ещё раз» (2026-11-05): шанс, что навык сработает второй раз вполсилы
    (compute_hit режет урон по actor.rune_half). Перезарядка и цена навыка
    здоровьем - от первого раза: второй прогон бесплатный."""
    actor = ctx.actor
    chance = _rune(actor, f"rune:once_more@{skill_id}") if skill_id else 0.0
    if skill_id:
        from game.combat import ability_rules

        chance += ability_rules.twice_chance(actor, skill_id)  # ступень руны-навыка
    if not chance or ctx.rng.random() >= chance:
        return
    if not any(c.alive and c.side != actor.side for c in ctx.session.combatants.values()):
        return
    cooldowns, hp = dict(actor.cooldowns), actor.current_hp
    ctx.lines.append(f"🪨 Ещё раз: «{skill_id_name(skill_id)}» у {actor.name} срабатывает снова, вполсилы")
    actor.current_skill, actor.rune_half = skill_id, True
    try:
        handler(ctx)
    finally:
        actor.current_skill, actor.rune_half = None, False
    actor.cooldowns = cooldowns
    if actor.current_hp < hp:
        actor.current_hp = hp


def rune_cooldown(actor: CombatantState, skill_id: str | None, cd_before: int, rng,
                  lines: list[str] | None = None) -> None:
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
        if lines is not None:
            lines.append(f"🪨 Холодный счёт: «{skill_id_name(skill_id)}» у {actor.name} без перезарядки")
        return
    swing = _rune(actor, f"rune:short_swing@{skill_id}")
    if swing and cd > 1 and rng.random() < swing:
        actor.cooldowns[skill_id] = cd - 1
        if lines is not None:
            lines.append(f"🪨 Короткий взмах: перезарядка «{skill_id_name(skill_id)}» у {actor.name} на ход короче")


def _shield_boost(actor: CombatantState, skill_id: str | None):
    """Усиление щитов навыка в момент, когда щит вешается (session.SHIELD_BOOST):
    пассивки (щиты Стража крепче, щиты Тёмного мистика на союзников сильнее),
    «Подпорка» и сила руны-навыка от мастерства."""
    from game.combat import ability_rules

    shield = ability_rules.shield_power(actor)
    ally = ability_rules.ally_heal_power(actor)
    mods = actor.buff_modifiers
    prop = (mods.get(f"rune:prop@{skill_id}", 0.0) + mods.get(f"rune:{skill_id}", 0.0)) if skill_id else 0.0
    if not (shield or ally or prop):
        return None

    def boost(source_id: int, holder, value: float) -> float:
        if source_id != actor.id:
            return value
        mult = 1.0 + shield + (ally if holder.id != actor.id else 0.0)
        return round(round(value * mult) * (1 + prop))

    return boost


def _passive_recovery(actor: CombatantState, ctx, heals_from: int) -> None:
    """Пассивка Тёмного мистика (2026-11-10): лечение союзников сильнее.
    Щиты усиливаются, когда вешаются (_shield_boost)."""
    from game.combat import ability_rules

    ally = ability_rules.ally_heal_power(actor)
    if ally:
        for h in ctx.heals[heals_from:]:
            if h.source_id == actor.id and h.target_id != actor.id:
                h.amount = round(h.amount * (1 + ally))
                h.ratio *= 1 + ally


def skill_snapshot(actor: CombatantState, combatants) -> dict:
    """Что висело от бойца до навыка: для рун «Тягучесть» и «Подпорка»."""
    return {id(e): (e.remaining_ticks, e.value) for c in combatants for e in c.effects if e.source_id == actor.id}


def prayer_hit(actor: CombatantState, healed: int, combatants):
    """«Обратная молитва»: доля лечения навыка бьёт самого раненого врага.
    Лечение навыка в ход применения (rune_after_skill) и лечение Глухой
    обороны за удар по стойке (резолвер, репорт 359). None - руны нет."""
    prayer = (actor.buff_modifiers or {}).get("rune:reverse_prayer", 0.0)
    if not prayer or healed <= 0:
        return None
    enemies = [c for c in combatants if c.side != actor.side and c.alive]
    if not enemies:
        return None
    from game.combat.skills import PendingHit

    target = min(enemies, key=lambda c: c.current_hp)
    return PendingHit(source_id=actor.id, target_id=target.id, amount=max(round(healed * prayer), 1),
                      label="обратная молитва", reactive=True)


def rune_after_skill(actor: CombatantState, skill_id: str | None, before: dict, combatants, ctx, heals_from: int) -> None:
    """После навыка: «Тягучесть» (эффекты навыка дольше), «Подпорка» (щиты и
    лечение навыка сильнее), «Обратная молитва» (часть лечения бьёт врага),
    «Отскок» (вторая цель в группе)."""
    if not skill_id:
        return
    mods = actor.buff_modifiers
    fresh = [e for c in combatants for e in c.effects
             if e.source_id == actor.id and (id(e) not in before or e.remaining_ticks > before[id(e)][0])]
    _passive_recovery(actor, ctx, heals_from)
    if not any(key.startswith("rune:") for key in mods):
        return
    rng = ctx.rng
    viscous = mods.get(f"rune:viscous@{skill_id}", 0.0)
    if viscous and fresh and rng.random() < viscous:
        for e in fresh:
            e.remaining_ticks += 1
        ctx.lines.append(f"🪨 Тягучесть: эффект «{skill_id_name(skill_id)}» продержится на ход дольше")
    # «Подпорка» и сила руны-навыка от мастерства (2026-11-10) - на лечение;
    # щиты - в момент, когда вешаются (_shield_boost).
    prop = mods.get(f"rune:prop@{skill_id}", 0.0) + mods.get(f"rune:{skill_id}", 0.0)
    new_heals = [h for h in ctx.heals[heals_from:] if h.source_id == actor.id]
    if prop:
        for h in new_heals:
            h.amount = round(h.amount * (1 + prop))
            h.ratio *= 1 + prop
    hit = prayer_hit(actor, sum(max(h.amount, 0) for h in new_heals), combatants)
    if hit is not None:
        ctx.hits.append(hit)
    ricochet = mods.get(f"rune:ricochet@{skill_id}", 0.0)
    if ricochet and rng.random() < ricochet:
        hit_ids = {h.target_id for h in ctx.hits if h.source_id == actor.id}
        others = [c for c in combatants if c.side != actor.side and c.alive and c.id not in hit_ids]
        if hit_ids and others:
            from game.combat.skills import compute_hit

            ctx.hits.append(compute_hit(actor, rng.choice(others), rng, label="отскок", multiplier=0.4,
                                        is_ability=True))


def skill_id_name(skill_id: str) -> str:
    from game.combat import skill_catalog

    skill = skill_catalog.skill_def(skill_id)
    return skill.name if skill is not None else skill_id
