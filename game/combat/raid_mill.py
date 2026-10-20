"""Рейд «Жернова Паломников», этапы 2-3 (бой).

Этап 2, обоз. Паломники идут волнами, позади катятся жернова - их не
пробить, они только напоминают, куда опаздывать нельзя. Груз несут по
очереди подклассы группы: «📦 Нести груз» сразу занимает ход носильщика.
Не несли mc.DROP_AFTER ходов - груз падает: минус мешок и «Тяжесть» всем.
Мешки кончились - обоз пропал, гибнет вся группа. Донесли mc.CARGO_STEPS
раз - этап взят.

Этап 3, Мельник Отлучённых:
- «Замри»: помеченный следующим ходом может только защищаться или ждать,
  иначе жернова дробят ему ноги.
- «Помол»: раз в mc.GRIND_EVERY ходов - по тому, кто за это время нанёс
  Мельнику больше всех урона; каждый следующий помол того же игрока сильнее.
- «Цепь жерновов» (2026-10-20): один игрок прикован к Мельнику. Половина
  урона по Мельнику уходит в прикованного, половина лечения и щитов на
  прикованном - Мельнику. Цепь - отдельный противник; не разбили за
  mc.CHAIN_TURNS ходов - стягивается и ранит прикованного.
- «Отлучение»: один подкласс состава на ход без навыков.
- «Каравай»: взявший лечится, но следующий удар Мельника - в него, сильнее.
- Финал: ниже mc.FINAL_HP ход вдвое короче.

Чистая логика поверх session/resolver, как raid_archive.py.
"""

import random

from game.classes.base import REGISTRY
from game.combat.raid_archive import _skills_of
from game.combat.raid_bosses import _boss_combatant
from game.combat.raid_field import StageTick, _idle, _players, _strike, _target_of
from game.combat.resolver import TickResult
from game.combat.session import ActionType, CombatantState, CombatSessionState, EffectKind
from game.combat.skills import PendingHit, compute_hit
from game.economy import raid_mill_config as mc

BOSS_NAME = "Мельник Отлучённых"
MILLSTONES_NAME = "Жернова"
CHAIN_NAME = "Цепь жерновов"

CARRY_NOTE = "несёт груз 📦"
#: Не в свою очередь (или груз уже взят) - ход потрачен, груз стоит.
WRONG_CARRY_NOTE = "хватается за груз не в свою очередь - груз не сдвинулся"


def subclass_title(subclass_id: str | None) -> str:
    cls = REGISTRY.get(subclass_id) if subclass_id else None
    return cls.title if cls is not None else (subclass_id or "без подкласса")


def carry_order(subclasses: list[str | None]) -> list[str | None]:
    """Очередь носильщиков: подклассы в порядке входа, без повторов."""
    order: list[str | None] = []
    for sid in subclasses:
        if sid not in order:
            order.append(sid)
    return order


def _hurt(player: CombatantState, amount: int, out: StageTick) -> None:
    """Сценарный урон мимо резолвера; гибель - в out.deaths."""
    if amount <= 0 or not player.alive:
        return
    player.current_hp = max(0, player.current_hp - amount)
    if player.current_hp <= 0:
        out.deaths.append(player.id)
        out.lines.append(f"☠ {player.name} погибает")


def _shields(player: CombatantState) -> dict[int, float]:
    return {id(e): e.value for e in player.effects_of(EffectKind.SHIELD_POOL)}


def _taken(result: TickResult, cid: int) -> int:
    return sum(
        h.amount for h in result.hit_renders
        if h.target_id == cid and not h.missed and h.amount > 0
    )


# --- Этап 2: обоз -----------------------------------------------------------------


class CargoStage:
    def __init__(self, start_id: int, participants: int, order: list[str | None]) -> None:
        self._next_id = start_id
        self.participants = max(1, participants)
        self.order = order or [None]
        self.turn = 0
        self.progress = 0
        self.idle = 0
        self.sacks = mc.SACKS_START
        self.ticks = 0
        self.carried = False
        self.pilgrim_ids: list[int] = []
        self.first_ids: set[int] = set()
        self.millstones_id: int | None = None

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    @property
    def reward_ids(self) -> set[int]:
        return set(self.first_ids)

    def _pilgrim(self) -> CombatantState:
        pilgrim = _boss_combatant(self._new_id(), "Паломник", mc.PILGRIM_HP, mc.PILGRIM_STAT_MULT)
        pilgrim.scripted_hit = _strike("бьёт посохом", mc.PILGRIM_STRIKE_MULT)
        self.pilgrim_ids.append(pilgrim.id)
        return pilgrim

    def setup(self, session: CombatSessionState) -> list[str]:
        for _ in range(self.participants + mc.PILGRIM_EXTRA_START):
            pilgrim = self._pilgrim()
            self.first_ids.add(pilgrim.id)
            session.add(pilgrim)
        # Жернова стоят на доске, чтобы этап не кончился смертью последнего
        # паломника: цель этапа - донести груз, а не перебить всех.
        stones = _boss_combatant(self._new_id(), MILLSTONES_NAME, 1, 1.0)
        stones.scripted_hit = _idle
        stones.hp_floor = 1
        stones.control_immune_always = True
        stones.incoming_hit_hook = lambda hit, source, amount: 0
        self.millstones_id = stones.id
        session.add(stones)
        return [self.status_line(session)]

    # --- Очередь носильщиков ---

    def carrier(self, session: CombatSessionState) -> str | None:
        """Чей подкласс несёт сейчас. Павших пропускаем: очередь идёт дальше."""
        alive = {p.subclass_id for p in _players(session)}
        for shift in range(len(self.order)):
            sid = self.order[(self.turn + shift) % len(self.order)]
            if sid in alive:
                self.turn = (self.turn + shift) % len(self.order)
                return sid
        return None

    def can_carry(self, session: CombatSessionState, cid: int) -> bool:
        player = session.combatants.get(cid)
        if player is None or not player.alive or self.carried:
            return False
        return player.subclass_id == self.carrier(session)

    def claim(self) -> None:
        self.carried = True

    def status_line(self, session: CombatSessionState) -> str:
        carrier = self.carrier(session)
        who = subclass_title(carrier) if carrier is not None or self.order == [None] else "-"
        return (
            f"📦 Груз: {self.progress}/{mc.CARGO_STEPS} · 🌾 мешков: {self.sacks} · "
            f"несёт: {who}"
        )

    def after_tick(self, session: CombatSessionState, result: TickResult, rng: random.Random) -> StageTick:
        self.ticks += 1
        out = StageTick()
        carried = any(a.payload.get("carry") for a in result.actions.values())
        self.carried = False
        if carried:
            self.progress += 1
            self.idle = 0
            self.turn = (self.turn + 1) % len(self.order)
            if self.progress >= mc.CARGO_STEPS:
                out.cleared = True
                out.lines.append("📦 Груз дошёл. Жернова остались позади.")
                return out
        else:
            self.idle += 1
            if self.idle >= mc.DROP_AFTER:
                self.idle = 0
                self._drop(session, out)
                if self.sacks <= 0:
                    return out
        self._spawn(session)
        out.lines.append(self.status_line(session))
        return out

    def _drop(self, session: CombatSessionState, out: StageTick) -> None:
        self.sacks -= 1
        if self.sacks <= 0:
            out.lines.append("🌾 Последний мешок рвётся о камни. Обоз пуст, жёрнов догоняет вас.")
            for player in _players(session):
                _hurt(player, player.current_hp, out)
            return
        pct = round(mc.HEAVY_WEAKEN * 100)
        out.lines.append(
            f"🌾 Груз падает: минус мешок. Тяжесть - урон группы -{pct}% на {mc.HEAVY_TURNS} хода."
        )
        for player in _players(session):
            player.apply_effect(EffectKind.WEAKEN, mc.HEAVY_WEAKEN, mc.HEAVY_TURNS, -5, decays=False)

    def _spawn(self, session: CombatSessionState) -> None:
        if self.ticks % mc.PILGRIM_SPAWN_EVERY:
            return
        alive = sum(1 for cid in self.pilgrim_ids if session.combatants[cid].alive)
        if alive < self.participants + mc.PILGRIM_EXTRA_CAP:
            session.add(self._pilgrim())


# --- Этап 3: Мельник --------------------------------------------------------------


class MillerAI:
    def __init__(self, stage: "MillerStage") -> None:
        self.stage = stage

    def __call__(self, boss: CombatantState, session: CombatSessionState, rng: random.Random) -> list[PendingHit]:
        fed = session.combatants.get(self.stage.fed_id) if self.stage.fed_id is not None else None
        self.stage.fed_id = None
        if fed is not None and fed.alive:
            return [compute_hit(boss, fed, rng, label="Удар по сытому", multiplier=mc.BREAD_STRIKE_MULT)]
        target = _target_of(boss, session, rng)
        if target is None:
            return []
        return [compute_hit(boss, target, rng, label="Удар жерновом", multiplier=mc.STRIKE_MULT)]


class MillerStage:
    def __init__(self, start_id: int) -> None:
        self._next_id = start_id
        self.boss_id: int | None = None
        self.ticks = 0
        self.hinted: set[str] = set()
        # «Замри»
        self.hold_id: int | None = None
        # «Помол»
        self.window_damage: dict[int, int] = {}
        self.ground: dict[int, int] = {}
        # «Цепь»
        self.chain_id: int | None = None
        self.chained_id: int | None = None
        self.chain_left = 0
        #: Щиты прикованного на конец прошлого хода: {id(эффекта): остаток}.
        #: По нему видно, какой щит повесили за ход, - половина уходит Мельнику.
        self.chain_shields: dict[int, float] = {}
        # «Каравай»
        self.bread_open = False
        self.fed_id: int | None = None
        self.final = False

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    @property
    def reward_ids(self) -> set[int]:
        return {self.boss_id} if self.boss_id is not None else set()

    def setup(self, session: CombatSessionState) -> list[str]:
        boss = _boss_combatant(self._new_id(), BOSS_NAME, mc.BOSS_HP, mc.BOSS_STAT_MULT)
        boss.scripted_hit = MillerAI(self)
        boss.control_immune_always = True
        self.boss_id = boss.id
        session.add(boss)
        return []

    def _hint(self, key: str, line: str, out: StageTick) -> None:
        if key not in self.hinted:
            self.hinted.add(key)
            out.lines.append(line)

    def take_bread(self, session: CombatSessionState, cid: int) -> str | None:
        """Каравай взят. None - его уже нет или игрок не может взять."""
        player = session.combatants.get(cid)
        if not self.bread_open or player is None or not player.alive:
            return None
        self.bread_open = False
        self.fed_id = cid
        before = player.current_hp
        player.current_hp = min(player.max_hp, player.current_hp + round(player.max_hp * mc.BREAD_HEAL_PCT))
        return (
            f"🍞 {player.name} берёт каравай: +{player.current_hp - before} HP. "
            "Следующий удар Мельника - по сытому."
        )

    def after_tick(self, session: CombatSessionState, result: TickResult, rng: random.Random) -> StageTick:
        self.ticks += 1
        out = StageTick()
        boss = session.combatants[self.boss_id]
        if not boss.alive:
            return out
        self._check_hold(session, result, out)
        self._count_damage(result)
        self._tick_chain(session, result, out)
        if self.bread_open:
            self.bread_open = False
            out.lines.append("🍞 Каравай крошится в муку - никто не взял.")

        if self.ticks % mc.GRIND_EVERY == 0:
            self._grind(session, out)
        elif self.ticks % mc.GRIND_EVERY == mc.GRIND_EVERY - 1:
            out.lines.append("⚠️ Жернова поворачиваются к тому, кто бьёт яростнее всех.")
            self._hint("grind", f"Помол бьёт того, кто за {mc.GRIND_EVERY} хода нанёс Мельнику больше всех урона.", out)

        if self.ticks % mc.FREEZE_EVERY == 0:
            self._mark_hold(session, rng, out)
        if self.ticks % mc.CHAIN_EVERY == mc.CHAIN_OFFSET and self.chain_id is None:
            self._spawn_chain(session, rng, out)
        if self.ticks % mc.EXCOMMUNICATE_EVERY == mc.EXCOMMUNICATE_OFFSET:
            self._excommunicate(session, rng, out)
        if self.ticks > 1 and self.ticks % mc.BREAD_EVERY == mc.BREAD_OFFSET:
            self.bread_open = True
            out.lines.append("🍞 На жернов ложится каравай. Взять его может только один.")
            self._hint("bread", "Взявший лечится, но следующий удар Мельника - по нему и вдвое сильнее.", out)

        if not self.final and boss.current_hp <= boss.max_hp * mc.FINAL_HP:
            self.final = True
            session.turn_seconds = mc.FINAL_TURN_SECONDS
            out.lines.append(f"⚙️ Жернова ускоряются: на ход теперь {round(mc.FINAL_TURN_SECONDS)} секунд.")
        return out

    # --- Замри ---

    def _mark_hold(self, session, rng, out: StageTick) -> None:
        players = _players(session)
        if not players:
            return
        target = rng.choice(players)
        self.hold_id = target.id
        out.lines.append(f"⚠️ Мельник указывает на {target.name}: «Замри!»")
        self._hint("hold", "Следующим ходом помеченному можно только «🛡️ Защититься» или ждать.", out)

    def _check_hold(self, session, result: TickResult, out: StageTick) -> None:
        cid, self.hold_id = self.hold_id, None
        player = session.combatants.get(cid) if cid is not None else None
        if player is None or not player.alive:
            return
        action = result.actions.get(cid)
        if action is None or action.type in (ActionType.SKIP, ActionType.DEFEND):
            out.lines.append(f"{player.name} замирает - жёрнов проходит мимо.")
            return
        out.lines.append(f"⚙️ {player.name} шевельнулся - жернова дробят ему ноги.")
        _hurt(player, round(player.max_hp * mc.FREEZE_CRUSH_PCT), out)
        if player.alive:
            player.apply_effect(EffectKind.FREEZE, 1.0, 1, self.boss_id)
            out.frozen.append(cid)

    # --- Помол ---

    def _count_damage(self, result: TickResult) -> None:
        for h in result.hit_renders:
            if h.target_id == self.boss_id and not h.missed and h.amount > 0 and h.source_side == 0:
                self.window_damage[h.source_id] = self.window_damage.get(h.source_id, 0) + h.amount

    def _grind(self, session, out: StageTick) -> None:
        window, self.window_damage = self.window_damage, {}
        alive = {p.id: p for p in _players(session)}
        candidates = [(dmg, cid) for cid, dmg in window.items() if cid in alive and dmg > 0]
        if not candidates:
            out.lines.append("⚙️ Помол вхолостую - жернова не нашли, кого молоть.")
            return
        _, cid = max(candidates)
        victim = alive[cid]
        times = self.ground.get(cid, 0)
        self.ground[cid] = times + 1
        amount = round(victim.max_hp * mc.GRIND_BASE_PCT * (1 + mc.GRIND_GROWTH * times))
        out.lines.append(f"⚙️ Помол: {victim.name} - {amount} урона" + (f" (уже {times + 1}-й раз)" if times else ""))
        _hurt(victim, amount, out)

    # --- Цепь ---

    def _spawn_chain(self, session, rng, out: StageTick) -> None:
        players = _players(session)
        if not players:
            return
        victim = rng.choice(players)
        chain = _boss_combatant(self._new_id(), CHAIN_NAME, mc.CHAIN_HP, 1.0)
        chain.scripted_hit = _idle
        chain.control_immune_always = True
        session.add(chain)
        self.chain_id = chain.id
        self.chained_id = victim.id
        self.chain_left = mc.CHAIN_TURNS
        self.chain_shields = _shields(victim)
        out.lines.append(
            f"⛓ Цепь жерновов приковывает {victim.name} к Мельнику: половина урона по Мельнику "
            f"уходит в {victim.name}, половина лечения и щитов на нём - Мельнику."
        )
        self._hint(
            "chain",
            f"Пока цепь цела, каждый удар по Мельнику ранит прикованного. Бейте цепь всей группой "
            f"(🎯 Выбор цели): за {mc.CHAIN_TURNS} хода не разобьёте - она стянется.",
            out,
        )

    def _tick_chain(self, session, result: TickResult, out: StageTick) -> None:
        if self.chain_id is None or self.chained_id is None:
            return
        chain = session.combatants.get(self.chain_id)
        boss = session.combatants[self.boss_id]
        player = session.combatants.get(self.chained_id)
        if chain is None or not chain.alive or player is None or not player.alive:
            if chain is not None and not chain.alive:
                out.lines.append("⛓ Цепь разбита.")
            self._drop_chain(chain)
            return
        # Урон по Мельнику: половина возвращается ему и бьёт прикованного.
        shared = round(_taken(result, boss.id) * mc.CHAIN_SHARE)
        if shared > 0:
            boss.current_hp = min(boss.max_hp, boss.current_hp + shared)
            out.lines.append(f"⛓ Цепь: {shared} урона с Мельника уходит в {player.name}")
            _hurt(player, shared, out)
        # Лечение и щиты прикованного: половина - Мельнику.
        healed = sum(h.amount for h in result.heal_renders if h.target_id == player.id)
        drained = min(round(healed * mc.CHAIN_SHARE), max(player.current_hp - 1, 0))
        if player.alive and drained > 0:
            player.current_hp -= drained
        shield_cut = 0
        before = self.chain_shields
        for effect in player.effects_of(EffectKind.SHIELD_POOL):
            gained = effect.value - before.get(id(effect), 0.0)
            if gained > 0:
                cut = gained * mc.CHAIN_SHARE
                effect.value -= cut
                shield_cut += round(cut)
        self.chain_shields = _shields(player)
        to_boss = drained + shield_cut
        if to_boss > 0:
            boss.current_hp = min(boss.max_hp, boss.current_hp + to_boss)
            out.lines.append(f"⛓ Цепь: Мельник забирает {to_boss} лечения и щитов {player.name}")
        self.chain_left -= 1
        if self.chain_left <= 0:
            out.lines.append("⛓ Цепь стягивается.")
            if player.alive:
                _hurt(player, round(player.max_hp * mc.CHAIN_SNAP_PCT), out)
            self._drop_chain(chain)

    def _drop_chain(self, chain: CombatantState | None) -> None:
        if chain is not None:
            chain.current_hp = 0
        self.chain_id = None
        self.chained_id = None
        self.chain_left = 0
        self.chain_shields = {}

    # --- Отлучение ---

    def _excommunicate(self, session, rng, out: StageTick) -> None:
        players = _players(session)
        subclasses = sorted({p.subclass_id for p in players if p.subclass_id})
        if not subclasses:
            return
        chosen = rng.choice(subclasses)
        for player in players:
            if player.subclass_id != chosen:
                continue
            for skill_id in list(player.cooldowns) + _skills_of(player):
                player.cooldowns[skill_id] = max(player.cooldowns.get(skill_id, 0), 1)
        out.lines.append(f"⛪ Мельник отлучает: {subclass_title(chosen)}. На ход - без навыков.")
