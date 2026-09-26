"""Способности мобов (патч 103): чем моб отличается от остальных в бою.

До этого моб в бою умел одно: «если не заморожен - кусает». Мобы с одной
главной характеристикой играли одинаково. Теперь у каждого своя способность
по его же описанию (content/mobs/*.json, поле ability): у Солевара «ударишь
сильно - лопнет и обдаст рассолом», и он это делает.

Как это встроено в бой
----------------------
Статичные механики (уворот, лимит урона за удар, щит, иммунитет к контролю,
«не уйду») - это обычные эффекты движка, вешаются один раз при появлении
моба (prepare). Всё остальное делает MobBrain.act, который резолвер зовёт
ВМЕСТО стандартного «кусает» - через тот же путь, что рейдового Хирурга.

Главное правило: ОТ ДОБИВАЮЩЕГО УДАРА НИЧЕГО НЕ СРАБАТЫВАЕТ. Резолвер не
даёт ходить мобу, который умрёт в этом ходу (патч 25). Поэтому все ответные
механики - отражение, рассол Солевара, контрудар Королевы - считаются
здесь, внутри хода моба, а не общим эффектом «Кровь за кровь»: тот бьёт в
ответ даже умирая. Игрок, добивший моба, ответа не получает никогда.

Второе правило: у мобов нет контроля. Оглушение отбирает у игрока ход, и
владелец игры убрал его сознательно - это только деморализует. Сильные
удары вместо этого идут С ЗАМАХОМ: моб за ход предупреждает, и игрок может
ответить блоком, лечением или сбить замах своим контролем.

Третье: промах не накладывает ничего (то же правило, что у игроков, патч 68).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from game.combat.session import CombatantState, CombatSessionState, EffectKind
from game.combat.skills import PendingHeal, PendingHit, compute_hit
from game.content_loader import MobAbilityDef, MobTraitDef

#: «Весь бой» для эффектов, которые не должны кончаться.
FOREVER = 999

#: Все механики. Тест сверяет с ним контент, чтобы опечатка в kind не
#: превратилась в моба без способности - молча.
KINDS = frozenset({
    # при появлении
    "armor_start", "dodge", "damage_cap", "shield_start", "control_immune", "last_breath",
    # в ход моба
    "regen", "lifesteal", "on_hit", "execute", "rage_below", "banner", "first_turn_weaken",
    "first_hit_crit", "windup", "extra_hit", "repeat_every", "choir", "dive", "self_burn",
    "shield_below", "stacking_weaken", "growing", "ignore_dodge",
    # ответ на удары по мобу (только если моб пережил ход)
    "brine_spray", "reflect", "counter_on_dodge",
})

#: Эффекты, которые моб может повесить на игрока. FREEZE тут нет намеренно:
#: контроля у мобов нет (см. шапку). Тест это закрепляет.
PLAYER_EFFECTS = {
    "dot": EffectKind.DOT,
    "weaken": EffectKind.WEAKEN,
    "vulnerability": EffectKind.VULNERABILITY,
}


@dataclass
class MobTurn:
    hits: list[PendingHit] = field(default_factory=list)
    heals: list[PendingHeal] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def _landed(hit: PendingHit) -> bool:
    return not hit.missed and hit.amount > 0


def _hp_share(combatant: CombatantState) -> float:
    return combatant.current_hp / combatant.max_hp if combatant.max_hp else 0.0


def prepare(mob: CombatantState, ability: MobAbilityDef | None) -> None:
    """Вешает статичные механики и мозг. Зовётся один раз при появлении моба."""
    if ability is None:
        return
    for trait in ability.traits:
        kind = trait.kind
        if kind == "armor_start":
            # Отрицательная уязвимость = снижение входящего урона.
            mob.apply_effect(EffectKind.VULNERABILITY, -trait.value, trait.duration, mob.id)
        elif kind == "dodge":
            mob.apply_effect(EffectKind.DODGE, trait.value, FOREVER, mob.id)
        elif kind == "damage_cap":
            mob.apply_effect(EffectKind.DAMAGE_CAP, trait.value, FOREVER, mob.id)
        elif kind == "shield_start":
            # Щит на весь бой: у SHIELD_POOL по истечении остаток лечит, и
            # игрок увидел бы строку про «Второе сердце» - эликсир игроков.
            mob.apply_effect(EffectKind.SHIELD_POOL, round(mob.max_hp * trait.value), FOREVER, mob.id)
        elif kind == "control_immune":
            mob.apply_effect(EffectKind.CONTROL_IMMUNE, 1.0, FOREVER, mob.id)
        elif kind == "last_breath":
            mob.apply_effect(EffectKind.LAST_BREATH, 1.0, FOREVER, mob.id)
    mob.mob_brain = MobBrain(ability)


class MobBrain:
    """Ход моба со способностью. Хранит память между ходами: сколько раз
    ходил, поднят ли штандарт, идёт ли замах, нырнул ли в камень."""

    def __init__(self, ability: MobAbilityDef) -> None:
        self.ability = ability
        self.traits: dict[str, list[MobTraitDef]] = {}
        for trait in ability.traits:
            self.traits.setdefault(trait.kind, []).append(trait)
        self.turns = 0
        self.windup_tick: int | None = None
        self.diving = False
        self.shield_used = False
        self.enraged = False

    def has(self, kind: str) -> bool:
        return kind in self.traits

    def one(self, kind: str) -> MobTraitDef:
        return self.traits[kind][0]

    # --- ход ----------------------------------------------------------------

    def act(
        self,
        mob: CombatantState,
        target: CombatantState | None,
        session: CombatSessionState,
        rng: random.Random,
        incoming: list[PendingHit],
    ) -> MobTurn:
        """Ход моба. Сюда резолвер попадает, только если моб этот ход
        переживёт, - поэтому ответы на удары здесь не могут сработать от
        добивающего удара."""
        self.turns += 1
        turn = MobTurn()
        title = self.ability.title

        self._answer_incoming(mob, session, rng, incoming, turn)
        self._self_upkeep(mob, target, session, turn)

        if target is None or not target.alive:
            return turn

        # Особые ходы, которые заменяют обычный удар.
        if self.has("banner") and self.turns == 1:
            trait = self.one("banner")
            mob.apply_effect(EffectKind.DAMAGE_BUFF, trait.value, FOREVER, mob.id)
            turn.lines.append(f"{mob.name} поднимает штандарт: дальше бьёт сильнее")
            return turn

        if self.has("windup"):
            trait = self.one("windup")
            if self.windup_tick is not None:
                released_now = session.tick_number == self.windup_tick + 1
                self.windup_tick = None
                if released_now:
                    self._strike(mob, target, rng, turn, trait.mult, label="бьёт с замаха", windup=trait)
                    return turn
                # Между замахом и ударом моб пропустил ход - его сбили
                # контролем. Сбитый замах не переносится на потом.
                turn.lines.append(f"{mob.name}: замах сбит")
            elif self.turns % trait.period == 0:
                self.windup_tick = session.tick_number
                turn.lines.append(f"⚠️ {mob.name} замахивается - следующий удар будет сильным")
                return turn

        if self.has("dive"):
            trait = self.one("dive")
            if self.diving:
                self.diving = False
                self._strike(mob, target, rng, turn, trait.mult, label="выныривает и бьёт")
                return turn
            if self.turns % trait.period == 0:
                self.diving = True
                # Уворот упрётся в общий потолок движка - неуязвимым моб не
                # станет, по нему просто трудно попасть один ход.
                mob.apply_effect(EffectKind.DODGE, trait.value, 1, mob.id)
                turn.lines.append(f"{mob.name} уходит в камень - по нему трудно попасть")
                return turn

        # Обычный удар - с множителями способности.
        mult = self._multiplier(mob, target, session)
        self._strike(mob, target, rng, turn, mult, label="кусает")

        # Дополнительные удары.
        if self.has("extra_hit"):
            trait = self.one("extra_hit")
            low_enough = trait.threshold <= 0 or _hp_share(mob) < trait.threshold
            if low_enough and self.turns % trait.period == 0:
                self._strike(mob, target, rng, turn, trait.mult, label="бьёт ещё раз")
        if self.has("repeat_every") and self.turns % self.one("repeat_every").period == 0:
            self._strike(mob, target, rng, turn, mult, label="повторяет удар")
        if self.has("choir"):
            trait = self.one("choir")
            others = [e for e in session.alive_enemies_of(mob) if e.id != target.id]
            for other in others:
                self._strike(mob, other, rng, turn, trait.value, label="бьёт по всем")
        if self.has("first_turn_weaken") and self.turns == 1:
            trait = self.one("first_turn_weaken")
            target.apply_effect(EffectKind.WEAKEN, trait.value, trait.duration, mob.id)
            turn.lines.append(f"{mob.name}: {title.lower()} - ты медлишь")
        return turn

    # --- части хода -----------------------------------------------------------

    def _multiplier(
        self, mob: CombatantState, target: CombatantState, session: CombatSessionState,
    ) -> float:
        mult = 1.0
        if self.has("rage_below") and _hp_share(mob) < self.one("rage_below").threshold:
            mult *= self.one("rage_below").mult
        if self.has("execute") and _hp_share(target) < self.one("execute").threshold:
            mult *= self.one("execute").mult
        if self.has("growing"):
            trait = self.one("growing")
            mult *= 1.0 + min(trait.step * (self.turns - 1), trait.cap)
        if self.has("self_burn") and _hp_share(mob) < self.one("self_burn").threshold:
            mult *= self.one("self_burn").mult
        if self.enraged:
            mult *= self.one("shield_below").mult
        solo = len(session.alive_enemies_of(mob)) <= 1
        if self.has("choir") and solo and self.turns % self.one("choir").period == 0:
            # В одиночку «По очереди» бьёт сильнее через ход; в группе вместо
            # этого бьёт по всем (см. act).
            mult *= self.one("choir").mult
        return mult

    def _strike(
        self,
        mob: CombatantState,
        target: CombatantState,
        rng: random.Random,
        turn: MobTurn,
        mult: float,
        label: str,
        windup: MobTraitDef | None = None,
    ) -> PendingHit:
        first = self.turns == 1 and not turn.hits
        hit = compute_hit(
            mob, target, rng, label=label, multiplier=mult,
            force_crit=self.has("first_hit_crit") and first,
            ignore_dodge=self.has("ignore_dodge"),
        )
        turn.hits.append(hit)
        if not _landed(hit):
            return hit  # промах не накладывает ничего (патч 68)
        for trait in self.traits.get("on_hit", []):
            if trait.chance >= 1.0 or rng.random() < trait.chance:
                self._afflict(mob, target, trait, hit, turn)
        if windup is not None and windup.effect:
            self._afflict(mob, target, windup, hit, turn)
        if self.has("lifesteal"):
            amount = max(round(hit.amount * self.one("lifesteal").value), 1)
            turn.heals.append(PendingHeal(
                source_id=mob.id, target_id=mob.id, amount=amount,
                label="пьёт кровь",
            ))
        return hit

    def _afflict(
        self, mob: CombatantState, target: CombatantState, trait: MobTraitDef,
        hit: PendingHit, turn: MobTurn,
    ) -> None:
        kind = PLAYER_EFFECTS[trait.effect]
        if kind == EffectKind.DOT:
            # Яд считается от удара, который его наложил: так он растёт вместе
            # с мобом по кольцам без отдельной таблицы чисел.
            per_tick = max(round(hit.amount * trait.value), 1)
            target.apply_effect(kind, per_tick, trait.duration, mob.id)
            turn.lines.append(f"{mob.name}: {self.ability.title.lower()} - {per_tick} урона за ход")
        elif kind == EffectKind.WEAKEN:
            target.apply_effect(kind, trait.value, trait.duration, mob.id)
            turn.lines.append(f"{mob.name} ослабляет тебя на {trait.value:.0%}")
        else:
            target.apply_effect(kind, trait.value, trait.duration, mob.id)
            turn.lines.append(f"{mob.name}: ты получаешь на {trait.value:.0%} больше урона")

    def _self_upkeep(
        self, mob: CombatantState, target: CombatantState | None,
        session: CombatSessionState, turn: MobTurn,
    ) -> None:
        if self.has("regen"):
            amount = max(round(mob.max_hp * self.one("regen").value), 1)
            turn.heals.append(PendingHeal(
                source_id=mob.id, target_id=mob.id, amount=amount, label="зарастает",
            ))
        if self.has("shield_below") and not self.shield_used:
            trait = self.one("shield_below")
            if _hp_share(mob) < trait.threshold:
                self.shield_used = True
                self.enraged = trait.mult > 1.0
                mob.apply_effect(
                    EffectKind.SHIELD_POOL, round(mob.max_hp * trait.value), FOREVER, mob.id
                )
                turn.lines.append(f"{mob.name}: {self.ability.title.lower()} - закрывается щитом")
        if self.has("self_burn"):
            trait = self.one("self_burn")
            if _hp_share(mob) < trait.threshold:
                turn.hits.append(PendingHit(
                    source_id=mob.id, target_id=mob.id,
                    amount=max(round(mob.max_hp * trait.value), 1),
                    label="горит сам", is_dot=True, is_tick=True,
                ))
        if self.has("stacking_weaken") and target is not None and target.alive:
            trait = self.one("stacking_weaken")
            current = target.effect_from(EffectKind.WEAKEN, mob.id)
            value = min((current.value if current else 0.0) + trait.step, trait.cap)
            target.apply_effect(EffectKind.WEAKEN, value, 2, mob.id)

    def _answer_incoming(
        self, mob: CombatantState, session: CombatSessionState, rng: random.Random,
        incoming: list[PendingHit], turn: MobTurn,
    ) -> None:
        """Ответ на удары по мобу в этом ходу. Моб его пережил - иначе
        резолвер сюда бы не пустил (см. шапку модуля)."""
        for hit in incoming:
            attacker = session.combatants.get(hit.source_id)
            if attacker is None or not attacker.alive or attacker.side == mob.side:
                continue
            if hit.is_dot:
                continue  # яд - не удар, на него не отвечают
            if hit.missed:
                if self.has("counter_on_dodge"):
                    self._strike(mob, attacker, rng, turn, self.one("counter_on_dodge").mult,
                                 label="бьёт в ответ")
                continue
            if hit.amount <= 0:
                continue
            if self.has("reflect"):
                turn.hits.append(PendingHit(
                    source_id=mob.id, target_id=attacker.id,
                    amount=max(round(hit.amount * self.one("reflect").value), 1),
                    label="возвращает урон",
                ))
            if self.has("brine_spray"):
                trait = self.one("brine_spray")
                if hit.amount >= mob.max_hp * trait.threshold:
                    per_tick = max(round(hit.amount * trait.value / trait.duration), 1)
                    attacker.apply_effect(EffectKind.DOT, per_tick, trait.duration, mob.id)
                    turn.lines.append(f"{mob.name} лопается и обдаёт {attacker.name} рассолом")
