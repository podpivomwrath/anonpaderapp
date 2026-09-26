"""Реестр боевых умений и расчёт удара.

Умения делятся на две фазы тика:
  - защитные (DEFENSIVE) — применяются ПЕРВЫМИ и защищают уже в этот тик;
  - атакующие (OFFENSIVE) — считаются по состоянию после защитной фазы,
    применяются одновременно в фазу применения.

Подклассы регистрируют свои умения декораторами при импорте модуля
(см. game/classes/__init__.py).
"""

import random
from dataclasses import dataclass, field
from typing import Callable

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.session import (
    CombatantState,
    Effect,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
)


@dataclass
class PendingHit:
    source_id: int
    target_id: int
    amount: int
    crit: bool = False
    label: str = "бьёт"
    missed: bool = False  # цель полностью уклонилась (Дымовая завеса)
    # is_dot — МЕХАНИКА: урон идёт мимо уворота, крита и митигации, но упирается
    # в щит. is_tick — ОТОБРАЖЕНИЕ: это пассивный тик эффекта, а не действие
    # бойца. Токсический выброс — is_dot без is_tick: по правилам он яд, но в
    # логе это ход игрока. Пока флаг был один, выброс печатался в разделе
    # ПРОТИВНИКА строкой «теряет N HP от эффекта», а сторона игрока в этот ход
    # показывала «Без изменений».
    is_dot: bool = False
    is_tick: bool = False
    blocked: int = 0      # патч 56: сколько урона срезал блок цели («Отражение» Стража)


@dataclass
class PendingHeal:
    source_id: int
    target_id: int
    amount: int
    label: str = "исцеляет"


@dataclass
class SkillContext:
    session: CombatSessionState
    actor: CombatantState
    action: DeclaredAction
    rng: random.Random
    hits: list[PendingHit] = field(default_factory=list)
    heals: list[PendingHeal] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def resolve_target(self) -> CombatantState | None:
        """Цель действия: указанная живая, иначе случайный живой враг."""
        target_id = self.action.target_id
        if target_id is not None:
            target = self.session.combatants.get(target_id)
            if target is not None and target.alive:
                return target
        enemies = self.session.alive_enemies_of(self.actor)
        return self.rng.choice(enemies) if enemies else None


SkillHandler = Callable[[SkillContext], None]

DEFENSIVE_SKILLS: dict[str, SkillHandler] = {}
OFFENSIVE_SKILLS: dict[str, SkillHandler] = {}

# Патч 46, ч.1: id элементальных умений Элементалиста → тег стихии, для
# «Стихийного потока» (см. register_element_use). Дублирует
# game.combat.battle_report.ELEMENT_SKILLS (тот — для трекера испытаний,
# этот — для боевого эффекта; независимые системы, держим раздельно).
ELEMENT_SKILL_TAGS = {
    "elementalist_fire": "fire",
    "elementalist_ice": "ice",
    "elementalist_lightning": "lightning",
}


def set_cooldown(actor: CombatantState, skill_id: str, cd: int, rng: random.Random) -> None:
    """Кулдаун навыка — с учётом микробаффов Элементалиста «Экономия» (шанс
    не уйти на КД) и «Перегрузка» (раз в N ходов следующий навык не уходит
    на КД). Для всех остальных актёров buff_modifiers не содержит этих
    ключей — поведение не отличается от прямого actor.cooldowns[skill_id] = cd."""
    chance = actor.buff_modifiers.get("no_cooldown_chance", 0.0)
    if chance > 0 and rng.random() < chance:
        return
    if actor.overload_ready:
        actor.overload_ready = False
        return
    actor.cooldowns[skill_id] = cd


def register_element_use(actor: CombatantState, skill_id: str) -> None:
    """«Стихийный поток» (патч 46, ч.1): 3 разные стихии подряд — следующее
    действие усилено на elemental_flow_bonus. Нет-оп без этого ключа в
    buff_modifiers (актёр не слотнул бафф) или для неэлементального умения."""
    bonus = actor.buff_modifiers.get("elemental_flow_bonus", 0.0)
    if bonus <= 0:
        return
    element = ELEMENT_SKILL_TAGS.get(skill_id)
    if element is None:
        return
    actor.recent_elements = (actor.recent_elements + [element])[-3:]
    if len(actor.recent_elements) == 3 and len(set(actor.recent_elements)) == 3:
        actor.apply_effect(EffectKind.ELEMENTAL_FLOW, bonus, 1, actor.id)
        actor.recent_elements = []


def element_damage_multiplier(actor: CombatantState, element: str | None) -> float:
    """Патч 49, ч.2: Элементалист — «Пламенная/Ледяная мощь/Мощь бури» (бонус
    урона своей стихии) и «Всеобщая стихия» (бонус всем стихийным навыкам) НЕ
    складываются на одном навыке — берётся больший (иначе связка из всех
    четырёх даёт +53% разом, что и было явно запрещено патчем)."""
    all_bonus = actor.buff_modifiers.get("all_elements_damage_bonus", 0.0)
    specific_bonus = actor.buff_modifiers.get(f"{element}_damage_bonus", 0.0) if element else 0.0
    return 1.0 + max(all_bonus, specific_bonus)


def tick_overload(actor: CombatantState) -> None:
    """Перегрузка (патч 46, ч.1): раз в OVERLOAD_INTERVAL_TURNS ходов —
    следующий навык не уходит на КД. Вызывать раз за ход актёра, вместе с
    tick_cooldowns (резолвер/дуэль). Нет-оп без overload_active в buff_modifiers."""
    if actor.buff_modifiers.get("overload_active", 0.0) <= 0:
        return
    actor.overload_turn_counter += 1
    if actor.overload_turn_counter >= bc.ELEMENTALIST_OVERLOAD_INTERVAL_TURNS:
        actor.overload_turn_counter = 0
        actor.overload_ready = True


def defensive_skill(skill_id: str) -> Callable[[SkillHandler], SkillHandler]:
    def wrap(fn: SkillHandler) -> SkillHandler:
        DEFENSIVE_SKILLS[skill_id] = fn
        return fn

    return wrap


def offensive_skill(skill_id: str) -> Callable[[SkillHandler], SkillHandler]:
    def wrap(fn: SkillHandler) -> SkillHandler:
        OFFENSIVE_SKILLS[skill_id] = fn
        return fn

    return wrap


# --- Расчёт удара (общий для tick_engine и duel_engine) ---


def outgoing_multiplier(actor: CombatantState, target: CombatantState) -> float:
    """Модификаторы исходящего урона: Ослабление, Боевой клич, PvP-провокация,
    damage_bonus активного пресета (патч 14, ч.3 — напр. Тяжёлая рука/Кровавая ярость),
    Пепельная лихорадка (патч 16 — эскалирующий бонус, value обновляется по ходам)."""
    mult = 1.0 - min(actor.effect_total(EffectKind.WEAKEN), 0.9)
    mult *= 1.0 + actor.effect_total(EffectKind.DAMAGE_BUFF)  # Боевой клич +30%
    mult *= 1.0 + actor.buff_modifiers.get("damage_bonus", 0.0)
    mult *= 1.0 + actor.effect_total(EffectKind.ASHEN_FEVER)
    mult *= 1.0 + actor.effect_total(EffectKind.ELEMENTAL_FLOW)  # Стихийный поток (патч 46, ч.1)
    # Кровавый рыцарь, «Безрассудность»/«Общий пир» (патч 47, ч.2) — отдельные
    # ключи от damage_bonus: слияние stat_modifiers пресета — dict.update, два
    # баффа на один ключ перезаписали бы друг друга, а не сложились.
    mult *= 1.0 + actor.buff_modifiers.get("reckless_damage_bonus", 0.0)
    mult *= 1.0 + actor.buff_modifiers.get("group_damage_bonus", 0.0)
    mult *= 1.0 + retribution_bonus(actor)  # Страж, «Возмездие» (патч 56)
    # Клинок теней, «Одиночество охотника» (патч 56): бонус только когда
    # Клинок дерётся один. Флаг ставит резолвер - здесь нет доступа к сессии.
    if actor.buff_modifiers.get("solo_damage_bonus", 0.0) > 0 and not actor.has_allies:
        mult *= 1.0 + actor.buff_modifiers["solo_damage_bonus"]
    for effect in actor.effects_of(EffectKind.PROVOKE_PVP):
        if target.id != effect.source_id:
            mult *= 1.0 - effect.value
    return max(mult, 0.0)


def retribution_bonus(actor: CombatantState) -> float:
    """Страж, «Возмездие» (патч 56): за каждые 10% maxHP, срезанные блоком за
    последние GUARDIAN_RETRIBUTION_WINDOW_TURNS ходов, урон следующей атаки
    растёт на per_10pct, но не выше cap. Без баффа - ровно 0.0."""
    per_10pct = actor.buff_modifiers.get("retribution_damage_per_10pct", 0.0)
    if per_10pct <= 0 or actor.max_hp <= 0:
        return 0.0
    blocked = sum(actor.blocked_recent)
    if blocked <= 0:
        return 0.0
    tenths = (blocked / actor.max_hp) / 0.10
    cap = actor.buff_modifiers.get("retribution_cap", bc.GUARDIAN_RETRIBUTION_CAP)
    return min(tenths * per_10pct, cap)


def effective_mitigation(target: CombatantState) -> float:
    """Митигация с учётом штрафа (групповой щит стража отдаёт часть защиты)."""
    base = formulas.mitigation(target.stats.vitality)
    return base * (1.0 - target.mitigation_penalty)


def compute_hit(
    actor: CombatantState,
    target: CombatantState,
    rng: random.Random,
    label: str = "бьёт",
    multiplier: float = 1.0,
    force_crit: bool = False,
    is_ability: bool = False,
    crit_multiplier: float | None = None,
    ignore_dodge: bool = False,
) -> PendingHit:
    """Расчёт удара. multiplier — множитель урона навыка (Атака = 1.0);
    force_crit — гарантированный крит (Теневой рывок); is_ability (патч 34,
    ч.1) — True для любого навыка/способности (уворот от них — четверть
    уворота от обычных атак), False для базовой атаки/укуса моба.

    Уклонение цели: базовый стат-уворот от AGI (formulas.dodge_chance/
    ability_dodge_chance) + внешние источники (Дымовая завеса и т.п.,
    EffectKind.DODGE — эликсиры/микробаффы) складываются АДДИТИВНО, общий
    потолок DODGE_HARD_CAP (не DODGE_STAT_CAP — тот лимитирует только вклад
    самого стата)."""
    stat_dodge = (
        formulas.ability_dodge_chance(target.stats.agility) if is_ability
        else formulas.dodge_chance(target.stats.agility)
    )
    # Патч 56, Клинок теней: «Тень» (пассивный уворот), «Ускользание» (после
    # удачного уворота по нему сложнее попасть в следующий ход), «Второй шанс»
    # (раз в N ходов удар гарантированно мимо; флаг ставит резолвер).
    extra_dodge = target.buff_modifiers.get("dodge_bonus", 0.0)
    if target.dodged_last_tick:
        extra_dodge += target.buff_modifiers.get("slip_away_bonus", 0.0)
    total_dodge = min(
        stat_dodge + target.effect_total(EffectKind.DODGE) + extra_dodge, bc.DODGE_HARD_CAP
    )
    # Патч 103, «Знает, где ты»: против такого бойца уворот цели не работает
    # вовсе - ни стат, ни эффекты, ни «Второй шанс» Клинка теней.
    if ignore_dodge:
        total_dodge = 0.0
    dodges = (not ignore_dodge and target.second_chance_active) or (
        total_dodge > 0 and rng.random() < total_dodge
    )
    if dodges:
        target.second_chance_active = False
        target.dodged_this_tick = True
        # «Голод клинка»: каждый удачный уворот добавляет стак Метки добычи
        # атакующему-жертве. Без баффа - нет-оп.
        if target.buff_modifiers.get("mark_on_dodge", 0.0) > 0:
            mark = actor.effect_from(EffectKind.MARK, target.id)
            if mark is not None:
                mark.stacks = min(mark.stacks + 1, bc.SHADOW_BLADE_MARK_MAX_STACKS)
                mark.remaining_ticks = max(mark.remaining_ticks, bc.SHADOW_BLADE_MARK_DURATION)
            else:
                actor.effects.append(
                    Effect(kind=EffectKind.MARK, value=1.0,
                           remaining_ticks=bc.SHADOW_BLADE_MARK_DURATION,
                           source_id=target.id, stacks=1)
                )
        return PendingHit(
            source_id=actor.id, target_id=target.id, amount=0, label=label, missed=True
        )

    base = formulas.damage(
        actor.tier_mult,
        actor.stats.by_key(actor.primary_stat),
        formulas.k_dmg_for(actor.primary_stat),
    ) * multiplier
    # Патч 56, Клинок теней: «Смертельная точность» (+шанс крита), «Передача
    # метки» (союзники чаще критуют по помеченной цели), «Жажда крови»
    # (следующий удар после крита критует гарантированно).
    crit_chance = formulas.crit_chance(actor.stats.agility)
    crit_chance += actor.buff_modifiers.get("crit_chance_bonus", 0.0)
    if target.has_effect(EffectKind.MARK):
        for mark in target.effects_of(EffectKind.MARK):
            crit_chance += actor.buff_modifiers.get("mark_ally_crit_bonus", 0.0) if mark.source_id != actor.id else 0.0
    crit = True if (force_crit or actor.guaranteed_crit_next) else rng.random() < crit_chance
    if actor.guaranteed_crit_next:
        actor.guaranteed_crit_next = False
    if crit:
        actor.crit_this_tick = True
        base *= crit_multiplier if crit_multiplier is not None else bc.CRIT_MULTIPLIER
        # Кровавый рыцарь, «Стойкий к боли» (патч 47, ч.2): свой крит-урон не
        # трогает, только входящий по себе.
        base *= 1.0 - target.buff_modifiers.get("crit_damage_taken_reduction", 0.0)
    base *= outgoing_multiplier(actor, target)
    base *= 1.0 + target.effect_total(EffectKind.VULNERABILITY)
    base *= 1.0 - effective_mitigation(target)
    # Кровавый рыцарь, «Кровавый доспех»/«Второе дыхание» (патч 47, ч.2) —
    # безусловное и низко-HP-условное снижение входящего урона.
    base *= 1.0 - target.buff_modifiers.get("incoming_damage_reduction", 0.0)
    # Патч 56: порог низкого HP - ПАРАМЕТР БАФФА, а не общая константа. У
    # Кровавого рыцаря он 40% (патч 47), у «Стойкости» Стража 30%; раньше
    # здесь был жёстко зашит порог Кровавого рыцаря на оба подкласса.
    low_hp_threshold = target.buff_modifiers.get(
        "low_hp_damage_reduction_threshold", bc.BLOOD_KNIGHT_SECOND_WIND_HP_THRESHOLD
    )
    if target.current_hp < target.max_hp * low_hp_threshold:
        base *= 1.0 - target.buff_modifiers.get("low_hp_damage_reduction", 0.0)
    # Глухая оборона (патч 39) — многоходовый блок, не суммируется с однотиковым
    # block_reduction (напр. Живительный блок пресета), берём максимум.
    before_block = base
    base *= 1.0 - max(target.block_reduction, target.effect_total(EffectKind.BLOCK_STANCE))
    # Патч 56 (Страж): срезанное блоком нужно «Отражению» (вернуть долю
    # атакующему в этот же ход, см. resolver) и «Возмездию» (накопление за окно).
    blocked_amount = max(round(before_block - base), 0)
    target.blocked_this_tick += blocked_amount
    # Осколочная кровь (патч 16): фикс. бонус урона за удар, НЕ от статов —
    # добавляется ПОСЛЕ всех множителей, не масштабируется крит/митигацией.
    base += actor.effect_total(EffectKind.FLAT_DAMAGE_BONUS)
    return PendingHit(
        blocked=blocked_amount,
        source_id=actor.id,
        target_id=target.id,
        amount=max(round(base), 1),
        crit=crit,
        label=label,
    )


@offensive_skill("attack")
def basic_attack(ctx: SkillContext) -> None:
    """Базовая атака — доступна всем."""
    target = ctx.resolve_target()
    if target is None:
        return
    ctx.hits.append(compute_hit(ctx.actor, target, ctx.rng))
    # Патч 56, Клинок теней, «Пометка добычи+»: обычная атака с шансом вешает
    # стак Метки добычи. У остальных подклассов ключа нет - нет-оп.
    actor = ctx.actor
    chance = actor.buff_modifiers.get("mark_on_attack_chance", 0.0)
    if chance > 0 and ctx.rng.random() < chance:
        mark = target.effect_from(EffectKind.MARK, actor.id)
        if mark is not None:
            mark.stacks = min(mark.stacks + 1, bc.SHADOW_BLADE_MARK_MAX_STACKS)
            mark.remaining_ticks = max(mark.remaining_ticks, bc.SHADOW_BLADE_MARK_DURATION)
        else:
            target.effects.append(
                Effect(kind=EffectKind.MARK, value=1.0,
                       remaining_ticks=bc.SHADOW_BLADE_MARK_DURATION,
                       source_id=actor.id, stacks=1)
            )
        ctx.lines.append(f"{target.name} помечен добычей ({actor.name}) 🎯")
