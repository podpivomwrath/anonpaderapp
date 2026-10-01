"""Рейд «Безмогильное поле» - три этапа одного длинного боя.

1. Туман. Скелеты и знаменосцы; фигура вдали недосягаема, каждый павший
   знаменосец её приближает.
2. Тот, кто зовёт. Сам бьёт слабо, зато его навыки ставят на поле объекты:
   они не атакуют, но каждый - задача для группы (спасти схваченного,
   заглушить колокол, пробить купол разными руками, разорвать цепь, разбить
   надгробие).
3. Генерал. Тот же противник берёт алебарду. Стойки объявляются за ход, у
   каждой свой правильный ответ; ниже половины HP он иногда обманывает.

Чистая логика поверх session/resolver - без БД и VK, как raid_bosses.py.
Оркестрация (рассылка, награды, смена этапов) - bot/handlers/raid_field_flow.py.
Механика держится на двух полях CombatantState: hp_floor (призыватель не
умирает, а превращается) и incoming_hit_hook (купол, стойки).
"""

import random
from dataclasses import dataclass, field

from game.combat import combat_flavor
from game.combat.raid_bosses import BOSS_LEVEL, _boss_combatant
from game.combat.resolver import TickResult, _choose_mob_target
from game.combat.session import CombatantState, CombatSessionState, EffectKind, Stats, build_combatant
from game.combat.skills import PendingHit, compute_hit
from game.economy import raid_field_config as fc

SUMMONER_NAME = "Тот, кто зовёт"
GENERAL_NAME = "Генерал Тавр"


@dataclass
class StageTick:
    """Итог одного хода для оркестрации."""

    lines: list[str] = field(default_factory=list)
    #: игроки, погибшие сценарно (HP обнулён мимо резолвера) - нужно для
    #: проверки вайпа: движок про такие смерти не знает.
    deaths: list[int] = field(default_factory=list)
    #: этап пройден не через смерть всех противников (знамёна пали,
    #: призыватель взял алебарду) - оркестрация закрывает сессию сама.
    cleared: bool = False
    #: скованные на следующий ход - за них оркестрация объявит пропуск, иначе
    #: группа ждала бы таймера хода.
    frozen: list[int] = field(default_factory=list)


def _players(session: CombatSessionState) -> list[CombatantState]:
    return [c for c in session.combatants.values() if c.kind == "character" and c.alive]


def _target_of(boss: CombatantState, session: CombatSessionState, rng: random.Random) -> CombatantState | None:
    """Провокация Стража в силе и для сценарных боссов."""
    if boss.taunted_by is not None:
        taunter = session.combatants.get(boss.taunted_by)
        if taunter is not None and taunter.alive:
            return taunter
    return _choose_mob_target(session, boss, rng)


def _strike(label: str, mult: float):
    """Обычный удар моба со своей подписью вместо «кусает»."""

    def hit(mob: CombatantState, session: CombatSessionState, rng: random.Random) -> list[PendingHit]:
        target = _target_of(mob, session, rng)
        if target is None:
            return []
        return [compute_hit(mob, target, rng, label=label, multiplier=mult)]

    return hit


def _idle(mob: CombatantState, session: CombatSessionState, rng: random.Random) -> list[PendingHit]:
    return []


def _kill(c: CombatantState) -> None:
    c.current_hp = 0


# --- Этап 1: туман ------------------------------------------------------------


class FogStage:
    """Знаменосцы - цель этапа, скелеты - помеха. Скелеты лута не дают
    (оркестрация награждает только за id из reward_ids), иначе бесконечный
    подъём мертвецов стал бы фермой."""

    def __init__(self, start_id: int) -> None:
        self._next_id = start_id
        self.bearer_ids: list[int] = []
        self.skeleton_ids: list[int] = []
        self.ticks = 0

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    @property
    def reward_ids(self) -> set[int]:
        return set(self.bearer_ids)

    def _skeleton(self) -> CombatantState:
        skeleton = _boss_combatant(self._new_id(), "Скелет", fc.SKELETON_HP, fc.SKELETON_STAT_MULT)
        skeleton.scripted_hit = _strike("рубит", 1.0)
        self.skeleton_ids.append(skeleton.id)
        return skeleton

    def setup(self, session: CombatSessionState) -> list[str]:
        for _ in range(fc.BEARER_COUNT):
            bearer = _boss_combatant(self._new_id(), "Знаменосец", fc.BEARER_HP, fc.BEARER_STAT_MULT)
            bearer.scripted_hit = _strike("бьёт древком", 1.0)
            self.bearer_ids.append(bearer.id)
            session.add(bearer)
        for _ in range(fc.SKELETONS_AT_START):
            session.add(self._skeleton())
        return [distance_line(self.distance(session))]

    def distance(self, session: CombatSessionState) -> int:
        return sum(1 for cid in self.bearer_ids if session.combatants[cid].alive)

    def after_tick(self, session: CombatSessionState, result: TickResult) -> StageTick:
        self.ticks += 1
        out = StageTick()
        fallen = [cid for cid in result.deaths if cid in self.bearer_ids]
        left = self.distance(session)
        if fallen and left > 0:
            out.lines.append(f"Знаменосец падает. Туман редеет - шагов до фигуры: {left}.")
        if left == 0:
            for cid in self.skeleton_ids:
                _kill(session.combatants[cid])
            out.lines.append("Последнее знамя ложится в грязь. Скелеты оседают следом.")
            out.cleared = True
            return out
        alive_skeletons = sum(1 for cid in self.skeleton_ids if session.combatants[cid].alive)
        if self.ticks % fc.SKELETON_RAISE_EVERY == 0 and alive_skeletons < fc.SKELETON_ALIVE_CAP:
            raised = min(fc.SKELETON_RAISE_COUNT, fc.SKELETON_ALIVE_CAP - alive_skeletons)
            for _ in range(raised):
                session.add(self._skeleton())
            out.lines.append("📯 Фигура в тумане поднимает руку. Из земли встаёт скелет.")
        out.lines.append(distance_line(left))
        return out


def distance_line(steps: int) -> str:
    return f"📯 {SUMMONER_NAME} - в тумане, вне досягаемости. Шагов до него: {steps}."


# --- Этап 2: Тот, кто зовёт ---------------------------------------------------

HANDS, BELL, MOUND, CHAIN, GRAVE = "hands", "bell", "mound", "chain", "grave"
#: Навыки, которым нужны хотя бы двое живых: в одиночку схваченного некому
#: спасать, а цепь не с кем связать.
_NEEDS_TWO = {HANDS, CHAIN}


@dataclass
class FieldObject:
    kind: str
    combatant_id: int
    victim_id: int | None = None
    partner_id: int | None = None   # второй конец цепи
    turns_left: int = 0
    required: int = 0               # курган: сколько разных бойцов
    hitters: set[int] = field(default_factory=set)
    tick_seen: set[int] = field(default_factory=set)


class SummonerAI:
    """Ход призывателя внутри резолва: слабый удар, раз в несколько ходов
    проклятие по всем. Удар из открытой могилы тоже идёт отсюда - через
    обычный расчёт удара, поэтому щиты, блок и лечение на цели работают."""

    def __init__(self) -> None:
        self.turn = 0
        self.grave_strike_on: int | None = None

    def __call__(self, boss: CombatantState, session: CombatSessionState, rng: random.Random) -> list[PendingHit]:
        self.turn += 1
        if self.grave_strike_on is not None:
            victim = session.combatants.get(self.grave_strike_on)
            self.grave_strike_on = None
            if victim is not None and victim.alive:
                return [compute_hit(boss, victim, rng, label="Чужая могила",
                                    multiplier=fc.GRAVE_STRIKE_MULT, is_ability=True)]
        if self.turn % fc.SUMMONER_CURSE_EVERY == 0:
            hits = []
            for target in session.alive_enemies_of(boss):
                hits.append(compute_hit(boss, target, rng, label="Проклятие тлена",
                                        multiplier=fc.SUMMONER_CURSE_MULT, is_ability=True))
                target.apply_effect(EffectKind.WEAKEN, fc.SUMMONER_CURSE_WEAKEN,
                                    fc.SUMMONER_CURSE_WEAKEN_TURNS, boss.id)
            return hits
        target = _target_of(boss, session, rng)
        if target is None:
            return []
        return [compute_hit(boss, target, rng, label="Шёпот тлена",
                            multiplier=fc.SUMMONER_WHISPER_MULT, is_ability=True)]


def _object_combatant(cid: int, name: str, hp: int) -> CombatantState:
    """Объект поля: не ходит, не уворачивается, не держит удар бронёй -
    задача не в том, чтобы его продавить, а в том, чтобы успеть."""
    obj = build_combatant(
        id=cid, side=1, kind="mob", name=name, level=BOSS_LEVEL,
        stats=Stats(strength=1, agility=1, intellect=1, vitality=1, will=1), primary_stat="str",
    )
    obj.max_hp = obj.current_hp = max(hp, 1)
    obj.scripted_hit = _idle
    obj.control_immune_always = True
    return obj


class SummonerStage:
    def __init__(self, start_id: int, participants: int) -> None:
        self._next_id = start_id
        self.participants = max(participants, 1)
        self.summoner_id: int | None = None
        self.ai = SummonerAI()
        self.objects: list[FieldObject] = []
        self.ticks = 0
        self.last_cast: str | None = None
        #: сколько объектов стояло на поле, когда он взял алебарду
        self.leftover = 0

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    @property
    def reward_ids(self) -> set[int]:
        return {self.summoner_id} if self.summoner_id is not None else set()

    def setup(self, session: CombatSessionState) -> list[str]:
        summoner = _boss_combatant(self._new_id(), SUMMONER_NAME, fc.SUMMONER_HP, fc.SUMMONER_STAT_MULT, "int")
        summoner.scripted_hit = self.ai
        summoner.control_immune_always = True
        summoner.hp_floor = 1
        summoner.incoming_hit_hook = self._summoner_hook
        self.summoner_id = summoner.id
        session.add(summoner)
        self._session = session
        return []

    # --- фильтры урона ---

    def _alive_object(self, session: CombatSessionState, kind: str) -> FieldObject | None:
        for obj in self.objects:
            if obj.kind == kind and session.combatants[obj.combatant_id].alive:
                return obj
        return None

    def _session_ref(self) -> CombatSessionState | None:
        return getattr(self, "_session", None)

    def _summoner_hook(self, hit: PendingHit, source: CombatantState | None, amount: int) -> int:
        session = self._session_ref()
        if session is not None and self._alive_object(session, MOUND) is not None:
            return 0  # под курганом
        return amount

    def _mound_hook(self, obj: FieldObject):
        def hook(hit: PendingHit, source: CombatantState | None, amount: int) -> int:
            if source is None or source.kind != "character":
                return 0
            if source.id in obj.hitters or source.id in obj.tick_seen:
                return 0
            obj.tick_seen.add(source.id)
            return fc.MOUND_SEGMENT_HP
        return hook

    # --- ход ---

    def after_tick(self, session: CombatSessionState, result: TickResult, rng: random.Random) -> StageTick:
        self._session = session
        self.ticks += 1
        out = StageTick()
        summoner = session.combatants[self.summoner_id]
        # Отравитель может дожать HP уже после фазы применения - пол там не
        # действует. Призыватель всё равно не умирает: он встаёт генералом.
        if summoner.current_hp < summoner.hp_floor:
            summoner.current_hp = summoner.hp_floor
        if self.summoner_id in result.deaths:
            result.deaths.remove(self.summoner_id)
            death_line = f"☠ {summoner.name} погибает"
            if death_line in result.lines:
                result.lines.remove(death_line)

        # Проверка ДО колокола и прочих объектов: колокол не должен вытащить
        # его из превращения, а руки - успеть утащить кого-то, когда бой
        # этого этапа уже окончен.
        if summoner.current_hp <= summoner.hp_floor:
            self.leftover = sum(1 for o in self.objects if session.combatants[o.combatant_id].alive)
            for obj in self.objects:
                _kill(session.combatants[obj.combatant_id])
                if obj.kind == HANDS and obj.victim_id is not None:
                    victim = session.combatants.get(obj.victim_id)
                    if victim is not None:
                        victim.effects = [e for e in victim.effects if e.kind != EffectKind.FREEZE]
            out.cleared = True
            return out

        self._tick_mound(session, out)
        self._tick_chain(session, result, out)
        self._tick_bell(session, summoner, out)
        self._tick_hands(session, out)
        self._tick_grave(session, out)

        every = (
            fc.SKILL_EVERY_LATE
            if summoner.current_hp <= summoner.max_hp * fc.SKILL_LATE_HP_FRACTION
            else fc.SKILL_EVERY
        )
        alive_objects = sum(1 for o in self.objects if session.combatants[o.combatant_id].alive)
        if self.ticks % every == 0 and alive_objects < fc.OBJECTS_ALIVE_CAP:
            self._cast(session, rng, out)

        out.frozen = [
            o.victim_id for o in self.objects
            if o.kind == HANDS and session.combatants[o.combatant_id].alive and o.victim_id is not None
        ]
        return out

    def _tick_mound(self, session: CombatSessionState, out: StageTick) -> None:
        obj = next((o for o in self.objects if o.kind == MOUND and o.tick_seen), None)
        for o in self.objects:
            if o.kind != MOUND:
                continue
            o.hitters |= o.tick_seen
            o.tick_seen.clear()
        if obj is None:
            return
        if session.combatants[obj.combatant_id].alive:
            out.lines.append(f"⛰ Курган трескается ({len(obj.hitters)}/{obj.required}).")
        else:
            out.lines.append(f"⛰ Курган осыпается. {SUMMONER_NAME} снова открыт.")

    def _tick_chain(self, session: CombatSessionState, result: TickResult, out: StageTick) -> None:
        for obj in self.objects:
            if obj.kind != CHAIN or obj.turns_left < 0:
                continue
            chain = session.combatants[obj.combatant_id]
            a = session.combatants.get(obj.victim_id)
            b = session.combatants.get(obj.partner_id)
            if not chain.alive or a is None or b is None or not a.alive or not b.alive:
                if chain.alive:
                    _kill(chain)
                obj.turns_left = -1  # отработана
                out.lines.append("⛓ Цепь черепов лопается.")
                continue
            # Урон, дошедший до одного конца, второй получает таким же числом.
            # Только удары противника: свой же урон по себе (кровавые навыки)
            # цепь не передаёт, иначе мистик убивал бы напарника лечением.
            got = {a.id: 0, b.id: 0}
            for hit in result.hit_renders:
                if hit.target_id in got and hit.source_side == 1 and not hit.missed and hit.amount > 0:
                    got[hit.target_id] += hit.amount
            for receiver, amount in ((b, got[a.id]), (a, got[b.id])):
                if amount <= 0 or not receiver.alive:
                    continue
                receiver.current_hp -= amount
                out.lines.append(f"⛓ Цепь передаёт урон: {receiver.name} -{amount} HP.")
                if receiver.current_hp <= 0:
                    receiver.current_hp = 0
                    out.deaths.append(receiver.id)
                    out.lines.append(f"☠ {receiver.name} погибает")

    def _tick_bell(self, session: CombatSessionState, summoner: CombatantState, out: StageTick) -> None:
        if self._alive_object(session, BELL) is None or summoner.current_hp <= summoner.hp_floor:
            return
        before = summoner.current_hp
        summoner.current_hp = min(summoner.max_hp, before + round(summoner.max_hp * fc.BELL_HEAL_FRACTION))
        healed = summoner.current_hp - before
        if healed > 0:
            out.lines.append(f"🔔 Колокол звонит. {SUMMONER_NAME} затягивает раны: +{healed} HP.")

    def _tick_hands(self, session: CombatSessionState, out: StageTick) -> None:
        for obj in self.objects:
            if obj.kind != HANDS or obj.turns_left < 0:
                continue
            hands = session.combatants[obj.combatant_id]
            victim = session.combatants.get(obj.victim_id)
            if victim is None or not victim.alive:
                _kill(hands)
                obj.turns_left = -1
                continue
            if not hands.alive:
                obj.turns_left = -1
                victim.effects = [
                    e for e in victim.effects
                    if not (e.kind == EffectKind.FREEZE and e.source_id == hands.id)
                ]
                out.lines.append(f"🦴 Руки рассыпаются. {victim.name} снова может двигаться.")
                continue
            obj.turns_left -= 1
            if obj.turns_left <= 0:
                victim.current_hp = 0
                _kill(hands)
                obj.turns_left = -1
                out.deaths.append(victim.id)
                out.lines.append(f"🦴 Руки утаскивают под землю: {victim.name}.")
                continue
            victim.apply_effect(EffectKind.FREEZE, 1.0, 1, hands.id)
            out.lines.append(f"⚠️ Руки тянут вниз: {victim.name}. Остался последний ход.")

    def _tick_grave(self, session: CombatSessionState, out: StageTick) -> None:
        for obj in self.objects:
            if obj.kind != GRAVE or obj.turns_left < 0:
                continue
            grave = session.combatants[obj.combatant_id]
            victim = session.combatants.get(obj.victim_id)
            if victim is None or not victim.alive:
                _kill(grave)
                obj.turns_left = -1
                continue
            if not grave.alive:
                obj.turns_left = -1
                out.lines.append("🪦 Надгробие разбито. Имени на нём больше не прочесть.")
                continue
            obj.turns_left -= 1
            if obj.turns_left <= 0:
                _kill(grave)
                obj.turns_left = -1
                self.ai.grave_strike_on = victim.id
                out.lines.append(f"⚠️ Могила открывается: {victim.name}. Следующий ход - удар в неё.")
            else:
                out.lines.append(f"🪦 Могила ждёт: {victim.name}. Ходов: {obj.turns_left}.")

    def _cast(self, session: CombatSessionState, rng: random.Random, out: StageTick) -> None:
        players = _players(session)
        if not players:
            return
        busy = {o.victim_id for o in self.objects if session.combatants[o.combatant_id].alive}
        busy |= {o.partner_id for o in self.objects if session.combatants[o.combatant_id].alive}
        free = [p for p in players if p.id not in busy]
        options = []
        for kind in (HANDS, BELL, MOUND, CHAIN, GRAVE):
            if self._alive_object(session, kind) is not None:
                continue
            if kind in _NEEDS_TWO and len(players) < 2:
                continue
            if kind in (HANDS, GRAVE) and not free:
                continue
            if kind == CHAIN and len(free) < 2:
                continue
            options.append(kind)
        if len(options) > 1 and self.last_cast in options:
            options.remove(self.last_cast)
        if not options:
            return
        kind = rng.choice(options)
        self.last_cast = kind
        hp_scale = self.participants
        if kind == HANDS:
            victim = rng.choice(free)
            hands = _object_combatant(self._new_id(), f"🦴 Руки из-под земли ({victim.name})",
                                      fc.HANDS_HP_PER_PLAYER * hp_scale)
            session.add(hands)
            victim.apply_effect(EffectKind.FREEZE, 1.0, 1, hands.id)
            self.objects.append(FieldObject(HANDS, hands.id, victim_id=victim.id, turns_left=fc.HANDS_TURNS))
            out.lines.append(
                f"⚠️ Из земли лезут костяные руки и смыкаются: {victim.name}. "
                f"Не разбить за {fc.HANDS_TURNS} хода - утянут под землю."
            )
        elif kind == BELL:
            bell = _object_combatant(self._new_id(), "🔔 Погребальный колокол", fc.BELL_HP_PER_PLAYER * hp_scale)
            session.add(bell)
            self.objects.append(FieldObject(BELL, bell.id))
            out.lines.append(f"⚠️ Из земли поднимается колокол. Пока он звонит, {SUMMONER_NAME} затягивает раны.")
        elif kind == MOUND:
            required = min(fc.MOUND_HITS_REQUIRED, len(players))
            mound = _object_combatant(self._new_id(), "⛰ Курган", fc.MOUND_SEGMENT_HP * required)
            obj = FieldObject(MOUND, mound.id, required=required)
            mound.incoming_hit_hook = self._mound_hook(obj)
            session.add(mound)
            self.objects.append(obj)
            who = "одного удара" if required == 1 else f"ударов {required} разных бойцов"
            out.lines.append(
                f"⚠️ Земля встаёт куполом над Тем, кто зовёт. Удары по нему гаснут. "
                f"Курган рухнет от {who}."
            )
        elif kind == CHAIN:
            a, b = rng.sample(free, 2)
            chain = _object_combatant(self._new_id(), "⛓ Цепь черепов", fc.CHAIN_HP_PER_PLAYER * hp_scale)
            session.add(chain)
            self.objects.append(FieldObject(CHAIN, chain.id, victim_id=a.id, partner_id=b.id))
            out.lines.append(f"⚠️ Цепь черепов связывает: {a.name} и {b.name}. Урон одному достаётся обоим.")
        else:
            victim = rng.choice(free)
            grave = _object_combatant(self._new_id(), f"🪦 Надгробие ({victim.name})",
                                      fc.GRAVE_HP_PER_PLAYER * hp_scale)
            session.add(grave)
            self.objects.append(FieldObject(GRAVE, grave.id, victim_id=victim.id, turns_left=fc.GRAVE_TURNS))
            out.lines.append(
                f"⚠️ Из земли встаёт надгробие. На нём имя: {victim.name}. "
                f"Через {fc.GRAVE_TURNS} хода могила откроется."
            )


# --- Этап 3: Генерал ----------------------------------------------------------

STRIKE, GUARD, LUNGE, REAP, IRON, CHALLENGE, COUNT = (
    "strike", "guard", "lunge", "reap", "iron", "challenge", "count",
)
STANCES = (GUARD, LUNGE, REAP, IRON, CHALLENGE, COUNT)

_POSE = {
    GUARD: "⚠️ Генерал ставит древко поперёк груди и замирает.",
    LUNGE: "⚠️ Острие алебарды смотрит на одного: {target}.",
    REAP: "⚠️ Генерал отводит алебарду далеко за спину.",
    IRON: "⚠️ Генерал опускает забрало.",
    CHALLENGE: "⚠️ Генерал указывает алебардой: {target}.",
    COUNT: "⚠️ Генерал опускает алебарду и начинает считать вслух.",
}
# Подсказка - только при первом показе стойки за заход. Дальше группа
# читает позу сама: в этом и смысл этапа.
_HINT = {
    GUARD: "Кто ударит его в этот ход, получит свой удар обратно.",
    LUNGE: "Следующий удар придётся в одного, и он будет тяжёлым.",
    REAP: "Взмах заденет всех.",
    IRON: "Простые удары отскочат от лат. Навыки найдут щели.",
    CHALLENGE: f"{fc.CHALLENGE_TURNS} хода это поединок: ранить его сможет только вызванный.",
    COUNT: "Если ударят больше чем {allowed}, он ответит каждому.",
}
# Обманная стойка: показана одна, сделана другая. Выдаёт её одна
# странная деталь - внимательный заметит.
_FEINTS = {
    GUARD: (REAP, "Но вес у него на задней ноге."),
    IRON: (GUARD, "Но алебарду он держит не для удара."),
    LUNGE: (REAP, "Но смотрит он поверх голов."),
    REAP: (LUNGE, "Но взгляд не отрывается от одного: {target}."),
}


class GeneralAI:
    """Состояние стоек. resolver зовёт __call__ каждый ход - здесь только
    удары; объявление следующей стойки и последствия делает GeneralStage."""

    def __init__(self) -> None:
        self.active: str = STRIKE           # что он делает в ближайший ход
        self.target_id: int | None = None   # выпад/вызов
        self.challenge_left = 0

    def __call__(self, boss: CombatantState, session: CombatSessionState, rng: random.Random) -> list[PendingHit]:
        stance = self.active
        if stance in (GUARD, COUNT):
            return []
        if stance == REAP:
            return [
                compute_hit(boss, t, rng, label="Жнец", multiplier=fc.REAP_MULT, is_ability=True)
                for t in session.alive_enemies_of(boss)
            ]
        if stance in (LUNGE, CHALLENGE):
            target = session.combatants.get(self.target_id) if self.target_id is not None else None
            if stance == LUNGE and boss.taunted_by is not None:
                target = _target_of(boss, session, rng)  # Провокация перехватывает выпад
            if target is None or not target.alive:
                target = _target_of(boss, session, rng)
            if target is None:
                return []
            label, mult = ("Выпад", fc.LUNGE_MULT) if stance == LUNGE else ("Поединок", fc.CHALLENGE_MULT)
            return [compute_hit(boss, target, rng, label=label, multiplier=mult, is_ability=True)]
        target = _target_of(boss, session, rng)
        if target is None:
            return []
        mult = fc.IRON_STRIKE_MULT if stance == IRON else fc.GENERAL_STRIKE_MULT
        return [compute_hit(boss, target, rng, label="Удар алебардой", multiplier=mult)]

    def hook(self, hit: PendingHit, source: CombatantState | None, amount: int) -> int:
        if self.active == IRON:
            if hit.is_dot:
                return amount
            if combat_flavor.is_basic_attack_label(hit.label):
                return 0
            return round(amount * fc.IRON_SKILL_MULT)
        if self.active == CHALLENGE and source is not None and source.id != self.target_id:
            return 0
        return amount


class GeneralStage:
    def __init__(self, start_id: int, leftover_objects: int = 0) -> None:
        self._next_id = start_id
        self.general_id: int | None = None
        self.ai = GeneralAI()
        self.leftover = leftover_objects
        self.ticks = 0
        self.shown: set[str] = set()
        self.last_stance: str | None = None
        self.banner = False
        self.banner_turns = 0
        #: показанная стойка - для обманки: группа видит одно, ai.active другое
        self.announced: str | None = None
        self.count_allowed = 1

    @property
    def reward_ids(self) -> set[int]:
        return {self.general_id} if self.general_id is not None else set()

    def setup(self, session: CombatSessionState) -> list[str]:
        self._next_id += 1
        general = _boss_combatant(self._next_id, GENERAL_NAME, fc.GENERAL_HP, fc.GENERAL_STAT_MULT)
        general.scripted_hit = self.ai
        general.control_immune_always = True
        general.incoming_hit_hook = self.ai.hook
        self.general_id = general.id
        session.add(general)
        lines = []
        if self.leftover > 0:
            general.apply_effect(
                EffectKind.DAMAGE_BUFF, fc.OBJECT_LEFTOVER_DAMAGE_BONUS * self.leftover, 10**6, -1,
            )
            lines.append(
                f"Он забирает своих обратно: {self.leftover} - и бьёт сильнее "
                f"на {round(fc.OBJECT_LEFTOVER_DAMAGE_BONUS * self.leftover * 100)}%."
            )
        return lines

    def after_tick(
        self, session: CombatSessionState, result: TickResult, rng: random.Random,
        damage_by_player: dict[int, int],
    ) -> StageTick:
        self.ticks += 1
        out = StageTick()
        general = session.combatants[self.general_id]
        executed = self.ai.active
        if not general.alive:
            return out

        if executed == COUNT:
            self._count_retaliation(session, result, general, out)
        elif executed == IRON:
            if any(
                h.target_id == general.id and combat_flavor.is_basic_attack_label(h.label)
                for h in result.hit_renders
            ):
                out.lines.append("Простые удары звенят о латы.")

        self._tick_banner(general, out)

        if executed == CHALLENGE:
            self.ai.challenge_left -= 1
            if self.ai.challenge_left > 0:
                return out  # поединок ещё ход
        if executed == STRIKE:
            self._announce(session, general, rng, damage_by_player, out)
        else:
            self.ai.active = STRIKE
            self.ai.target_id = None
            self.announced = None
        return out

    def _count_retaliation(
        self, session: CombatSessionState, result: TickResult, general: CombatantState, out: StageTick,
    ) -> None:
        attackers = {
            h.source_id for h in result.hit_renders
            if h.target_id == general.id and h.source_side == 0 and not h.is_tick
        }
        allowed = self.count_allowed
        if len(attackers) <= allowed:
            out.lines.append(f"Генерал досчитал до {len(attackers)} и опустил голову.")
            return
        out.lines.append(f"Генерал досчитал до {len(attackers)}. Отвечает каждому.")
        for cid in sorted(attackers):
            player = session.combatants.get(cid)
            if player is None or not player.alive:
                continue
            damage = max(round(player.max_hp * fc.COUNT_RETALIATION_FRACTION), 1)
            player.current_hp -= damage
            out.lines.append(f"Генерал → ответ по {player.name} - {damage} урона")
            if player.current_hp <= 0:
                player.current_hp = 0
                out.deaths.append(cid)
                out.lines.append(f"☠ {player.name} погибает")

    @staticmethod
    def _count_allowed(session: CombatSessionState) -> int:
        """Пятерым можно бить троим, троим - одному. Порог фиксируется в
        момент объявления: группа планирует ход по тому, что ей сказали."""
        return max(1, len(_players(session)) - 2)

    def _tick_banner(self, general: CombatantState, out: StageTick) -> None:
        if not self.banner and general.current_hp <= general.max_hp * fc.BANNER_HP_FRACTION:
            self.banner = True
            out.lines.append("Генерал втыкает в землю знамя. Под ним он с каждым ходом бьёт сильнее.")
        if self.banner:
            self.banner_turns += 1
            general.apply_effect(
                EffectKind.DAMAGE_BUFF, fc.BANNER_DAMAGE_STEP * self.banner_turns, 10**6, general.id,
            )

    def _announce(
        self, session: CombatSessionState, general: CombatantState, rng: random.Random,
        damage_by_player: dict[int, int], out: StageTick,
    ) -> None:
        players = _players(session)
        if not players:
            return
        options = [s for s in STANCES if s != self.last_stance]
        if len(players) < fc.COUNT_MIN_PLAYERS and COUNT in options:
            options.remove(COUNT)
        shown = rng.choice(options)
        actual = shown
        tell = ""
        if (
            shown in _FEINTS
            and general.current_hp <= general.max_hp * fc.FEINT_HP_FRACTION
            and rng.random() < fc.FEINT_CHANCE
        ):
            actual, tell = _FEINTS[shown]

        # Цель нужна и показанной, и настоящей стойке: при обманке «Жнец →
        # Выпад» взгляд выдаёт именно того, в кого придётся удар.
        if CHALLENGE in (shown, actual):
            target = max(players, key=lambda p: (damage_by_player.get(p.id, 0), -p.id))
        else:
            target = rng.choice(players)

        self.last_stance = shown
        self.announced = shown
        self.count_allowed = self._count_allowed(session)
        self.ai.active = actual
        self.ai.target_id = target.id
        if actual == CHALLENGE:
            self.ai.challenge_left = fc.CHALLENGE_TURNS
        if actual == GUARD:
            general.apply_effect(EffectKind.BLOOD_REFLECT, fc.GUARD_REFLECT, 1, general.id)

        line = _POSE[shown].format(target=target.name)
        if tell:
            line = f"{line} {tell.format(target=target.name)}"
        out.lines.append(line)
        if shown not in self.shown:
            self.shown.add(shown)
            out.lines.append(_HINT[shown].format(allowed=self.count_allowed))
