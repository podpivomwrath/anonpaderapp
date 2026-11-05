"""Руины культа: бой комнаты. Интерфейс этапа тот же, что у разломов и поля
(setup -> строки, after_tick -> StageTick, reward_ids); оркестрация -
bot/handlers/raid_combat.py, переход по комнатам - bot/handlers/ruins.py.

Противники - обычные мобы IV кольца уровня этажа (rift.build_mob), усиленные
множителями ruins_config. Элита и хозяин этажа - один усиленный моб плюс
свита из обычных (решение владельца: элита без свиты слишком проста). На
этажах, кратных 5, - уникальные боссы (RuinBoss ниже), после 30 этажа по
нескольку в одном зале, здоровье не режется: стена задумана.

Дары культа (game/ruins_gifts.py) действуют здесь: модификаторы бойца уже в
buff_modifiers, а то, что зависит от хода и комнаты, - в _apply_gifts и
_gift_tick.
"""

from __future__ import annotations

import random

from game import ruins as rules
from game import ruins_gifts as gifts_mod
from game.combat.raid_field import StageTick, _idle, _players, stage_hurt
from game.combat.resolver import TickResult
from game.combat.rift import build_mob
from game.combat.session import ActionType, CombatantState, CombatSessionState
from game.economy import ruins_config as rc


class _RuinsStage:
    """Общее: id, уровень этажа, дары."""

    is_boss = False
    ruins = True

    def __init__(self, start_id: int, layout: dict, room: str, party: int, ctx: dict | None = None) -> None:
        self._next_id = start_id
        self.floor = int(layout.get("floor", 1))
        self.level = rc.mob_level(self.floor)
        self.room = room
        self.party = max(1, party)
        self.layout = layout
        self.ctx = ctx or {}
        self.gifts = self.ctx.get("gifts") or []
        self.name, self.elite_name, self.primary, self.label = rules.mob_kind(layout)
        self.ids: list[int] = []
        self.ticks = 0
        #: кого в этом бою спасла «Чужая молитва» - оркестрация пишет в забег
        self.prayer_used: list[int] = list(self.ctx.get("prayer_used") or [])
        self._timed: list[tuple[int, str, float]] = []  # (до хода, ключ, сколько) - снять после

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _toughness(self) -> float:
        return 1.15 if gifts_mod.has(self.gifts, "heavy_bag") else 1.0

    def _mob(self, name: str, hp: float, dmg: float, primary: str | None = None, label: str | None = None):
        mob = build_mob(self._new_id(), name, self.level, rc.MOB_RING, hp * self._toughness(), dmg,
                        primary or self.primary, label or self.label)
        # Разница уровней - как у мобов исследования (2026-11-05, владелец).
        mob.steep_level_curve = True
        return mob

    def _add(self, session: CombatSessionState, mob: CombatantState, reward: bool = True) -> CombatantState:
        if reward:
            self.ids.append(mob.id)
        session.add(mob)
        return mob

    # --- дары ---------------------------------------------------------------

    def _bump(self, session: CombatSessionState, key: str, value: float, until_tick: int | None = None) -> None:
        for p in _players(session):
            p.buff_modifiers[key] = p.buff_modifiers.get(key, 0.0) + value
        if until_tick is not None:
            self._timed.append((until_tick, key, value))

    def _apply_gifts(self, session: CombatSessionState) -> list[str]:
        lines = []
        if gifts_mod.has(self.gifts, "rusty_nail"):
            self._bump(session, "crit_chance_bonus", 1.0, until_tick=1)
        if gifts_mod.has(self.gifts, "stone_skin"):
            self._bump(session, "incoming_damage_reduction", 0.5, until_tick=2)
        if gifts_mod.has(self.gifts, "blood_debt"):
            self._bump(session, "damage_bonus", min(0.30, 0.02 * int(self.ctx.get("kills", 0))))
        if gifts_mod.has(self.gifts, "miner_pick"):
            big = self.room in (rules.ELITE, rules.BOSS)
            self._bump(session, "damage_bonus", 0.30 if big else -0.15)
        if gifts_mod.has(self.gifts, "foreign_name"):
            for p in _players(session):
                p.current_hp = max(1, p.current_hp - round(p.max_hp * 0.10))
            lines.append("🩸 Чужое имя берёт своё: -10% здоровья всем")
        return lines

    def _gift_tick(self, session: CombatSessionState, result: TickResult, out: StageTick) -> None:
        for until, key, value in list(self._timed):
            if self.ticks >= until:
                for p in session.combatants.values():
                    if p.kind == "character":
                        p.buff_modifiers[key] = p.buff_modifiers.get(key, 0.0) - value
                self._timed.remove((until, key, value))
        if gifts_mod.has(self.gifts, "foreign_prayer"):
            dead_now = set(result.deaths) | set(out.deaths)
            alive_left = any(p.alive for p in _players(session))
            for cid in dead_now:
                c = session.combatants.get(cid)
                if c is None or c.kind != "character" or cid in self.prayer_used or not alive_left:
                    continue
                c.current_hp = 1
                self.prayer_used.append(cid)
                if cid in out.deaths:
                    out.deaths.remove(cid)
                out.lines.append(f"🙏 Чужая молитва удерживает {c.name}: 1 HP")

    # --- интерфейс этапа ------------------------------------------------------

    def setup(self, session: CombatSessionState) -> list[str]:
        lines = self._setup_enemies(session)
        return lines + self._apply_gifts(session)

    def _setup_enemies(self, session: CombatSessionState) -> list[str]:
        raise NotImplementedError

    @property
    def reward_ids(self) -> set[int]:
        return set(self.ids)

    def after_tick(self, session: CombatSessionState, result: TickResult, rng: random.Random) -> StageTick:
        self.ticks += 1
        out = self._enemy_tick(session, result, rng)
        self._gift_tick(session, result, out)
        return out

    def _enemy_tick(self, session, result, rng) -> StageTick:
        return StageTick()

    def extra_buttons(self, session: CombatSessionState, cid: int) -> list[tuple[str, dict]]:
        return []

    def act(self, session: CombatSessionState, cid: int, action: str) -> str | None:
        """Особое действие этапа (кнопка extra_buttons). Вернёт заметку хода
        или None - нельзя."""
        return None


class RoomStage(_RuinsStage):
    """Обычный бой, элита со свитой, хозяин этажа со свитой, засада, мимик."""

    def __init__(self, start_id, layout, room, party, ctx=None) -> None:
        super().__init__(start_id, layout, room, party, ctx)
        self.is_boss = room == rules.BOSS

    def _setup_enemies(self, session: CombatSessionState) -> list[str]:
        count = rc.mob_count(self.party)
        if self.room == rules.BOSS:
            self._add(session, self._mob(f"{self.elite_name}, хозяин этажа", rc.BOSS_HP, rc.BOSS_DMG))
            count -= 1
        elif self.room == rules.ELITE:
            self._add(session, self._mob(self.elite_name, rc.ELITE_HP, rc.ELITE_DMG))
            count -= 1
        elif self.room == rules.TREASURE:
            self._add(session, self._mob("Сундук с зубами", rc.ELITE_HP, rc.ELITE_DMG, "agi", "кусает"))
            count -= 1
        for _ in range(count):
            self._add(session, self._mob(self.name, rc.MOB_HP, rc.MOB_DMG))
        return []


# --- Уникальные боссы (этажи, кратные 5) ----------------------------------------


class RuinBoss:
    """Механика одного босса. Не этап сам по себе: этапом служит BossRoom,
    которая держит одного или нескольких (после 30 этажа)."""

    key = ""
    name = ""
    hp = 1.0
    dmg = 1.0
    primary = "str"
    label = "бьёт"

    def __init__(self, room: "BossRoom") -> None:
        self.room = room
        self.boss_id: int | None = None

    def spawn(self, session: CombatSessionState) -> list[str]:
        party = self.room.party
        hp = rc.UNIQUE_HP * self.hp * (1 + rc.UNIQUE_HP_PER_PLAYER * (party - 1))
        boss = self.room._add(session, self.room._mob(self.name, hp, rc.UNIQUE_DMG * self.dmg, self.primary,
                                                     self.label))
        self.boss_id = boss.id
        return self.opening()

    def opening(self) -> list[str]:
        return []

    def boss(self, session: CombatSessionState) -> CombatantState | None:
        return session.combatants.get(self.boss_id)

    def alive(self, session: CombatSessionState) -> bool:
        b = self.boss(session)
        return b is not None and b.alive

    def tick(self, session: CombatSessionState, result: TickResult, rng: random.Random, out: StageTick) -> None:
        pass

    def extra_buttons(self, session, cid) -> list[tuple[str, dict]]:
        return []

    def act(self, session, cid, action) -> str | None:
        return None


class Gatekeeper(RuinBoss):
    """Привратник завала: раз в несколько ходов засыпает игрока камнями -
    тот вне боя, пока другой не потратит ход на «Разгрести». Одиночку
    отпускает сам через пару ходов."""

    key, name, hp, dmg, label = "gatekeeper", "Привратник завала", 1.1, 1.0, "бьёт глыбой"

    def __init__(self, room) -> None:
        super().__init__(room)
        self.buried: dict[int, int] = {}  # id -> ход, когда засыпан

    def opening(self) -> list[str]:
        return [f"🪨 Привратник обрушивает своды. Засыпанного откапывают ходом «{rc.BTN_DIG}»."]

    def tick(self, session, result, rng, out) -> None:
        if not self.alive(session):
            self.buried.clear()
            return
        for cid, action in result.actions.items():
            if action.type == ActionType.SKIP and action.payload.get("dig") and self.buried:
                freed = min(self.buried, key=self.buried.get)
                self.buried.pop(freed, None)
                c = session.combatants.get(freed)
                out.lines.append(f"⛏ {session.combatants[cid].name} откапывает {c.name if c else 'своего'}")
        alive = _players(session)
        for cid in list(self.buried):
            c = session.combatants.get(cid)
            if c is None or not c.alive:
                self.buried.pop(cid, None)
            elif len(alive) == 1 and self.room.ticks - self.buried[cid] >= rc.GATE_SOLO_FREE:
                self.buried.pop(cid, None)
                out.lines.append(f"⛏ {c.name} сам выбирается из-под камней")
        if self.room.ticks % rc.GATE_EVERY == 0:
            free = [p for p in alive if p.id not in self.buried]
            if free and (len(alive) == 1 or len(free) > 1):
                victim = rng.choice(free)
                self.buried[victim.id] = self.room.ticks
                hurt = stage_hurt(victim, round(victim.max_hp * rc.GATE_HIT), out)
                out.lines.append(f"🪨 Свод рушится на {victim.name} - {hurt} урона, его засыпало")
        out.frozen.extend(cid for cid in self.buried if cid not in out.frozen)

    def extra_buttons(self, session, cid) -> list[tuple[str, dict]]:
        if self.buried and cid not in self.buried:
            return [(rc.BTN_DIG, {"type": "ruins_act", "a": "dig"})]
        return []

    def act(self, session, cid, action) -> str | None:
        if action == "dig" and self.buried and cid not in self.buried:
            return "разгребает камни"
        return None


class Counter(RuinBoss):
    """Счетовод: кто за ход нанёс больше всех урона, получает метку долга;
    третья метка - взыскание. Урон надо раскладывать по группе."""

    key, name, hp, dmg, label = "counter", "Счетовод культа", 1.0, 0.9, "бьёт счётами"

    def __init__(self, room) -> None:
        super().__init__(room)
        self.marks: dict[int, int] = {}

    def opening(self) -> list[str]:
        return ["📒 Счетовод записывает, кто бьёт сильнее всех. Три записи - и он взыщет долг."]

    def tick(self, session, result, rng, out) -> None:
        if not self.alive(session):
            return
        dealt: dict[int, int] = {}
        for h in result.hit_renders:
            if h.source_side == 0 and h.target_side == 1 and not h.missed:
                dealt[h.source_id] = dealt.get(h.source_id, 0) + h.amount
        if not dealt:
            return
        top = max(dealt, key=dealt.get)
        c = session.combatants.get(top)
        if c is None or not c.alive:
            return
        self.marks[top] = self.marks.get(top, 0) + 1
        if self.marks[top] >= rc.COUNTER_MARKS:
            self.marks[top] = 0
            stage_hurt(c, round(c.max_hp * rc.COUNTER_HIT), out)
            out.lines.append(f"📒 Счетовод взыскивает долг с {c.name}")
        else:
            out.lines.append(f"📒 Долг {c.name}: {self.marks[top]} из {rc.COUNTER_MARKS}")


class Candlewoman(RuinBoss):
    """Свечница: пока горят свечи, она лечится. Свечи - отдельные цели, их
    тушат ударом вместо удара по ней. Время от времени зажигает новую."""

    key, name, hp, dmg, label = "candle", "Свечница", 0.9, 1.0, "плещет воском"

    def __init__(self, room) -> None:
        super().__init__(room)
        self.candles: list[int] = []

    def _candle(self, session) -> None:
        hp = rc.CANDLE_HP * (1 + rc.UNIQUE_HP_PER_PLAYER * (self.room.party - 1))
        mob = self.room._mob("Свеча", hp, 0.0)
        mob.scripted_hit = _idle
        self.room._add(session, mob, reward=False)
        self.candles.append(mob.id)

    def spawn(self, session) -> list[str]:
        lines = super().spawn(session)
        for _ in range(rc.CANDLES_START):
            self._candle(session)
        return lines

    def opening(self) -> list[str]:
        return ["🕯 Вокруг Свечницы горят свечи. Пока горят - она залечивает раны. Тушите их ударом."]

    def tick(self, session, result, rng, out) -> None:
        lit = [cid for cid in self.candles if session.combatants.get(cid) and session.combatants[cid].alive]
        boss = self.boss(session)
        if boss is None or not boss.alive:
            for cid in lit:
                session.combatants[cid].current_hp = 0
            out.cleared = bool(lit)
            return
        if lit:
            heal = round(boss.max_hp * rc.CANDLE_HEAL * len(lit))
            boss.current_hp = min(boss.max_hp, boss.current_hp + heal)
            out.lines.append(f"🕯 Свечи горят ({len(lit)}) - Свечница затягивает раны: +{heal}")
        if self.room.ticks % rc.CANDLE_RELIGHT == 0 and len(lit) < rc.CANDLES_MAX:
            self._candle(session)
            out.lines.append("🕯 Свечница зажигает новую свечу")


class Herald(RuinBoss):
    """Глашатай: заранее объявляет, какой удар отразит на следующем ходу -
    обычный или навык. Ударивший объявленным получает урон обратно."""

    key, name, hp, dmg, label = "herald", "Глашатай", 1.0, 1.0, "бьёт жезлом"
    KINDS = {ActionType.ATTACK: "обычный удар", ActionType.SKILL: "навык"}

    def __init__(self, room) -> None:
        super().__init__(room)
        self.banned: ActionType | None = None

    def opening(self) -> list[str]:
        return ["📯 Глашатай каждый ход кричит, какой удар отразит на следующем. Его слова - в логе хода."]

    def tick(self, session, result, rng, out) -> None:
        if not self.alive(session):
            return
        if self.banned is not None:
            for cid, action in result.actions.items():
                c = session.combatants.get(cid)
                if action.type == self.banned and c is not None and c.alive:
                    stage_hurt(c, round(c.max_hp * rc.HERALD_HIT), out)
                    out.lines.append(f"📯 {c.name} ударил запретным - удар вернулся")
        self.banned = rng.choice(list(self.KINDS))
        out.lines.append(f"📯 Глашатай: «Следующий {self.KINDS[self.banned]} вернётся тому, кто ударит!»")


class Brothers(RuinBoss):
    """Братья-копатели: два тела. Если их здоровье разошлось больше чем на
    BROTHERS_GAP, здоровый звереет. Бить надо ровно."""

    key, name, hp, dmg, label = "brothers", "Старший копатель", 0.6, 0.9, "бьёт лопатой"

    def __init__(self, room) -> None:
        super().__init__(room)
        self.second_id: int | None = None
        self.raged: set[int] = set()

    def spawn(self, session) -> list[str]:
        lines = super().spawn(session)
        party = self.room.party
        hp = rc.UNIQUE_HP * self.hp * (1 + rc.UNIQUE_HP_PER_PLAYER * (party - 1))
        second = self.room._add(session, self.room._mob("Младший копатель", hp, rc.UNIQUE_DMG * self.dmg,
                                                        "str", "бьёт киркой"))
        self.second_id = second.id
        return lines

    def opening(self) -> list[str]:
        return ["⛏ Братья дерутся спина к спине. Отстанет один по здоровью - второй звереет."]

    def alive(self, session) -> bool:
        return any(session.combatants.get(i) and session.combatants[i].alive for i in (self.boss_id, self.second_id))

    def tick(self, session, result, rng, out) -> None:
        a, b = session.combatants.get(self.boss_id), session.combatants.get(self.second_id)
        if a is None or b is None:
            return
        share = {c.id: (c.current_hp / c.max_hp if c.max_hp else 0) for c in (a, b) if c.alive}
        for c in (a, b):
            angry = (c.alive and len(share) == 2
                     and share[c.id] - min(share.values()) > rc.BROTHERS_GAP)
            if angry and c.id not in self.raged:
                c.buff_modifiers["damage_bonus"] = c.buff_modifiers.get("damage_bonus", 0.0) + rc.BROTHERS_RAGE
                self.raged.add(c.id)
                out.lines.append(f"⛏ {c.name} звереет: брат отстал")
            elif not angry and c.id in self.raged:
                c.buff_modifiers["damage_bonus"] = c.buff_modifiers.get("damage_bonus", 0.0) - rc.BROTHERS_RAGE
                self.raged.discard(c.id)
                if c.alive:
                    out.lines.append(f"⛏ {c.name} успокаивается")


class Abbot(RuinBoss):
    """Настоятель: каждый ход объявляет обет на следующий - не бить
    навыками, не защищаться, не пить зелий. Нарушил кто-то один - урон
    всей группе."""

    key, name, hp, dmg, label = "abbot", "Настоятель", 1.2, 1.0, "бьёт кадилом"
    VOWS = {"skill": "не бить навыками", "defend": "не защищаться", "potion": "не пить зелий"}

    def __init__(self, room) -> None:
        super().__init__(room)
        self.vow: str | None = None
        self.potions: dict[int, int] = {}

    def opening(self) -> list[str]:
        return ["📿 Настоятель каждый ход объявляет обет. Нарушит один - больно будет всем."]

    def _broken(self, session, result) -> list[str]:
        names = []
        for cid, action in result.actions.items():
            c = session.combatants.get(cid)
            if c is None:
                continue
            if self.vow == "skill" and action.type == ActionType.SKILL:
                names.append(c.name)
            elif self.vow == "defend" and action.type == ActionType.DEFEND:
                names.append(c.name)
        if self.vow == "potion":
            for p in session.combatants.values():
                if p.kind == "character" and getattr(p, "consumables_used", 0) > self.potions.get(p.id, 0):
                    names.append(p.name)
        return names

    def tick(self, session, result, rng, out) -> None:
        if not self.alive(session):
            return
        if self.vow is not None:
            broken = self._broken(session, result)
            if broken:
                out.lines.append(f"📿 Обет нарушен ({', '.join(sorted(set(broken)))}) - кара всем")
                for p in _players(session):
                    stage_hurt(p, round(p.max_hp * rc.ABBOT_HIT), out)
        self.potions = {p.id: getattr(p, "consumables_used", 0) for p in session.combatants.values()
                        if p.kind == "character"}
        self.vow = rng.choice(list(self.VOWS))
        out.lines.append(f"📿 Обет на следующий ход: {self.VOWS[self.vow]}")


BOSSES: tuple[type[RuinBoss], ...] = (Gatekeeper, Counter, Candlewoman, Herald, Brothers, Abbot)


def bosses_for_floor(floor: int, rng: random.Random) -> list[type[RuinBoss]]:
    """Этаж 5 - первый босс, 10 - второй... по кругу. После 30 этажа в зале
    несколько: 35-55 - двое, 60-85 - трое, дальше +1 каждые 30 этажей."""
    main = BOSSES[(floor // 5 - 1) % len(BOSSES)]
    count = 1 if floor <= 30 else 1 + floor // 30
    others = [b for b in BOSSES if b is not main]
    rng.shuffle(others)
    return [main] + others[: max(0, min(count, len(BOSSES)) - 1)]


class BossRoom(_RuinsStage):
    """Зал уникального босса (или нескольких)."""

    is_boss = True

    def __init__(self, start_id, layout, room, party, ctx=None, rng: random.Random | None = None) -> None:
        super().__init__(start_id, layout, room, party, ctx)
        rng = rng or random.Random()
        self.bosses = [cls(self) for cls in bosses_for_floor(self.floor, rng)]

    @property
    def names(self) -> list[str]:
        out = []
        for b in self.bosses:
            out.append("Братья-копатели" if isinstance(b, Brothers) else b.name)
        return out

    def _setup_enemies(self, session) -> list[str]:
        lines = []
        for b in self.bosses:
            lines += b.spawn(session)
        return lines

    def _enemy_tick(self, session, result, rng) -> StageTick:
        out = StageTick()
        for b in self.bosses:
            b.tick(session, result, rng, out)
        return out

    def extra_buttons(self, session, cid) -> list[tuple[str, dict]]:
        out = []
        for b in self.bosses:
            out += b.extra_buttons(session, cid)
        return out

    def act(self, session, cid, action) -> str | None:
        for b in self.bosses:
            note = b.act(session, cid, action)
            if note is not None:
                return note
        return None


def build_stage(start_id: int, layout: dict, room: str, party: int, ctx: dict | None = None,
                rng: random.Random | None = None) -> _RuinsStage:
    floor = int(layout.get("floor", 1))
    if room == rules.BOSS and floor % 5 == 0:
        return BossRoom(start_id, layout, room, party, ctx, rng)
    return RoomStage(start_id, layout, room, party, ctx)
