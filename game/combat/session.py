"""Runtime-состояние боя (в памяти движка; БД хранит только персистентный снимок).

CombatantState/CombatSessionState — рабочие объекты tick_engine и duel_engine.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Callable

from pydantic import BaseModel, Field

from game.combat import balance_config as bc
from game.combat import formulas

if TYPE_CHECKING:
    from game.combat.skills import PendingHit


class CombatMode(StrEnum):
    PVE = "pve"              # соло/группа против мобов: без таймера, ждём всех живых игроков
    PVP_GROUP = "pvp_group"  # групповой PvP: таймер 1 мин + досрочный резолв
    DUEL = "duel"            # 1×1, последовательные ходы (duel_engine)


class ActionType(StrEnum):
    ATTACK = "attack"
    SKILL = "skill"
    ITEM = "item"  # патч 16: лечебное зелье — тратит ход, как атака/навык
    SKIP = "skip"
    # 2026-10-19: «Защититься» - добровольный пропуск хода за -10% входящего
    # урона до следующего своего хода (bc.DEFEND_DAMAGE_REDUCTION).
    DEFEND = "defend"


class EffectKind(StrEnum):
    DOT = "dot"                    # периодический урон (value = урон за ход)
    VULNERABILITY = "vulnerability"  # входящий урон * (1 + value)
    WEAKEN = "weaken"              # исходящий урон * (1 - value)
    FREEZE = "freeze"              # пропуск действия в ход (оглушение/заморозка)
    PROVOKE_PVP = "provoke_pvp"    # PvP-провокация: урон по целям != source * (1 - value)
    MARK = "mark"                  # стаки «Метки добычи» Клинка теней
    DAMAGE_BUFF = "damage_buff"    # исходящий урон * (1 + value) — Боевой клич
    DODGE = "dodge"                # шанс полного уклонения от входящего удара — Дымовая завеса
    # --- Боевые эликсиры (патч 16) ---
    ASHEN_FEVER = "ashen_fever"          # эскалирующий исходящий урон + самоурон 5%/ход
    LAST_BREATH = "last_breath"          # спасение от смертельного урона (1 раз)
    BLOOD_REFLECT = "blood_reflect"      # value — доля полученного урона, отражаемая атакующему
    CONTROL_IMMUNE = "control_immune"    # иммунитет к контролю (оба режима боя)
    SHIELD_POOL = "shield_pool"          # персистентный щит (value — остаток поглощения)
    FLAT_DAMAGE_BONUS = "flat_damage_bonus"  # фикс. бонус урона за удар (не от статов)
    # --- Патч 39: навыки подклассов ---
    DAMAGE_CAP = "damage_cap"      # входящий урон за удар не может превышать value*maxHP (Несокрушимый)
    BLOOD_SEAL = "blood_seal"      # цель отмечена: лайфстил источника с неё удвоен (Кровавая печать)
    BLOCK_HEAL = "block_heal"      # value — доля maxHP, лечащая актёра за каждый СРЕЗАННЫЙ блоком удар
    BLOCK_STANCE = "block_stance"  # многоходовый блок (Глухая оборона) — снижение урона, в отличие
                                    # от однотикового block_reduction держится effect_duration ходов
    # --- Патч 46, ч.1: Элементалист, «Стихийный поток» ---
    ELEMENTAL_FLOW = "elemental_flow"  # исходящий урон * (1 + value), 1 ход — 3 разные стихии подряд
    # --- Патч 49, ч.2: Элементалист, «Тепловой шок»/«Ледяное поле» ---
    CONTROL_RESIST_DOWN = "control_resist_down"  # value — доля, вычитаемая из сопротивления контролю цели
    # Патч 58: цель НЕДАВНО была под контролем. Заморозка живёт один ход и
    # гасится в тот же тик, поэтому «ударить по замороженному» физически не
    # успевало сработать - связка держалась на прибавке длительности, а после
    # нерфа контроля в PvP развалилась совсем. Метка живёт своим окном и
    # разводит «как долго цель стоит» и «успеешь ли ты добить по холоду».
    CHILLED = "chilled"


class DeclaredAction(BaseModel):
    """Действие, объявленное в окно тика / ход дуэли."""

    type: ActionType = ActionType.SKIP
    target_id: int | None = None
    skill_id: str | None = None
    item_id: str | None = None  # патч 16: id лечебного зелья при type=ITEM
    payload: dict = Field(default_factory=dict)


@dataclass
class Stats:
    strength: int = bc.STARTING_STAT
    agility: int = bc.STARTING_STAT
    intellect: int = bc.STARTING_STAT
    vitality: int = bc.STARTING_STAT
    will: int = bc.STARTING_STAT

    def by_key(self, key: str) -> int:
        return {
            "str": self.strength,
            "agi": self.agility,
            "int": self.intellect,
            "vit": self.vitality,
            "wil": self.will,
        }[key]


#: Метка Горения на DOT-эффекте. Горение, яд и DoT'ы мобов - один и тот же
#: EffectKind.DOT, отличаются только источником; Схождению стихий нужно именно
#: Горение (от любого игрока), а не любой периодический урон.
BURN_TAG = "burn"

#: Метки щитов SHIELD_POOL (2026-10-13): эликсир, Оберег мистика и щиты
#: мобов - один EffectKind, и лог называл «Вторым сердцем» любой из них.
#: Без метки (мобы, страница архива, снимки старых боёв) - просто «Щит».
SECOND_HEART_TAG = "second_heart"
WARD_TAG = "ward"
SCROLL_WARD_TAG = "scroll_ward"
#: Щит «Отголоска» мистика - отдельный от Оберега (2026-10-17): в одном
#: эффекте новый Оберег затирал накопленный отголосок.
ECHO_TAG = "echo"
SHIELD_NAMES = {
    SECOND_HEART_TAG: "Второе сердце", WARD_TAG: "Оберег", SCROLL_WARD_TAG: "Свиток оберега",
    ECHO_TAG: "Отголосок",
}


def shield_name(effect) -> str:
    return SHIELD_NAMES.get(getattr(effect, "tag", None), "Щит")


@dataclass
class Effect:
    kind: EffectKind
    value: float
    remaining_ticks: int
    source_id: int
    stacks: int = 1
    tag: str | None = None
    #: Не затухает (2026-10-17): дебафф способности моба или босса - он
    #: работает ровно как написано в описании. Затухание - против дебаффов
    #: игроков, которые складывались в +70% (см. CombatantState.decay_debuffs).
    fixed: bool = False


@dataclass
class CombatantState:
    id: int
    side: int              # 0/1; в PvE игроки — 0, мобы — 1
    kind: str              # "character" | "mob"
    name: str
    level: int
    stats: Stats
    primary_stat: str      # "str" | "agi" | "int"
    tier: str
    max_hp: int
    current_hp: int
    subclass_id: str | None = None
    base_class: str | None = None  # у персонажа - для пассивок базового класса
    #: Выносливость от экипировки (2026-10-13): зелья лечат от «белого»
    #: здоровья, без неё - см. white_max_hp.
    gear_vit: int = 0
    # Мерж stat_modifiers всех баффов активного пресета (патч 14, ч.3) — читается
    # умениями подкласса по имени ключа (full_block_chance, damage_bonus, ...).
    buff_modifiers: dict[str, float] = field(default_factory=dict)

    # Однотиковые защитные состояния (сбрасываются после резолва тика /
    # в дуэли — в начале собственного хода)
    shield: int = 0                 # пул поглощения
    block_reduction: float = 0.0    # доля срезаемого входящего урона
    defend_reduction: float = 0.0   # «Защититься»: множитель поверх всех снижений, не блок
    mitigation_penalty: float = 0.0  # штраф к митигации (групповой щит стража)
    taunted_by: int | None = None   # PvE-форс цели для моба
    taunt_left: int = 0             # сколько ещё тиков держится taunted_by

    effects: list[Effect] = field(default_factory=list)
    # Кулдауны навыков в ходах боя {skill_id: осталось}; сбрасываются между
    # боями естественно (новый CombatantState на каждую встречу).
    cooldowns: dict[str, int] = field(default_factory=dict)

    # --- Защита от чейн-контроля (diminishing returns, progression-patch-4/8) ---
    # Стрик считает ходы, ПРОПУЩЕННЫЕ из-за контроля подряд (не число наложений):
    # долгая заморозка тоже накручивает стрик каждым пропущенным ходом.
    control_streak: int = 0            # подряд пропущенных из-за контроля ходов
    control_immune_turns: int = 0      # осталось ходов иммунитета к контролю
    skipped_by_control_this_turn: bool = False  # transient: пропустил ход из-за контроля
    # Сколько раз контроль УЖЕ лёг на эту цель за последнее время (PvP). Второй
    # контроль проверяется удвоенной Волей, третий не проходит вовсе.
    control_hits: int = 0
    control_hits_reset_in: int = 0   # ходов до обнуления счётчика
    # Патч 66: существо, у которого контроль не проходит НИКОГДА. Резист Воли
    # упирается в CONTROL_RESIST_CAP (0.75), то есть волей 100% не набрать -
    # а Хирургу по задумке контроль не страшен вообще. Флаг, а не эффект с
    # огромной длительностью: эффект тикает, показывается в логе и снимается
    # диспеллом, тогда как это свойство самого существа.
    control_immune_always: bool = False
    # Кто ПЫТАЛСЯ наложить контроль в этот ход - независимо от того, лёг он
    # или нет. Резолвер чистит в начале хода. Нужно окну прерывания Хирурга:
    # там засчитывается сама попытка, иначе абсолютный иммунитет выше сделал
    # бы окно непроходимым.
    control_attempted_by: set[int] = field(default_factory=set)

    # --- Боевые эликсиры (патч 16): лимит 2 за бой, считается на весь бой ---
    combat_elixirs_used: int = 0
    # Все расходники за бой (зелья + эликсиры), лимит CONSUMABLES_PER_BATTLE.
    consumables_used: int = 0

    #: Затухание дебаффов (2026-10-16), {вид: доля}: с какой силой ляжет новый
    #: дебафф этого вида (bc.DECAYING_DEBUFFS - уязвимость, ослабление). Пока
    #: дебафф держится на цели, каждый ход и он, и эта доля падают на
    #: bc.DEBUFF_DECAY_PER_TURN; доля сбрасывается, когда дебаффа не осталось.
    #: Цепочкой печатей от нескольких игроков +70% больше не удержать.
    debuff_fatigue: dict[str, float] = field(default_factory=dict)

    # --- Патч 46, ч.1: Элементалист, «Перегрузка»/«Стихийный поток» ---
    # Перегрузка: ходов накоплено с последнего срабатывания / готов ли пропуск КД
    # следующего навыка. Считается только если у актёра есть overload_active
    # в buff_modifiers (см. game/combat/skills.py::set_cooldown).
    overload_turn_counter: int = 0
    overload_ready: bool = False
    # Стихийный поток: последние (до 3) применённые элементальные умения подряд
    recent_elements: list[str] = field(default_factory=list)

    # Патч 56 (Страж): сколько урона СРЕЗАНО блоком. blocked_this_tick -
    # однотиковое (нужно «Отражению»: вернуть долю атакующему в этот же ход),
    # blocked_recent - скользящее окно последних ходов для «Возмездия».
    blocked_this_tick: int = 0
    blocked_recent: list[int] = field(default_factory=list)

    # Патч 56 (Клинок теней): память о прошлом ходе для «Ускользания»
    # (уклонился - по нему сложнее попасть), «Жажды крови» (после крита
    # следующая атака критует) и «Второго шанса» (раз в N ходов промах).
    dodged_last_tick: bool = False
    dodged_this_tick: bool = False
    crit_this_tick: bool = False
    guaranteed_crit_next: bool = False
    bloodlust_ready_tick: int = 0
    second_chance_active: bool = False
    # Есть ли живые союзники: ставит резолвер в начале хода. Нужен там, где
    # до сессии не дотянуться (compute_hit), и отделяет соло-бонусы от групповых.
    has_allies: bool = False
    # Патч 56 (Тёмный мистик): предыдущий навык потратил собственное HP,
    # значит «Тёмное вознаграждение» усилит следующий Кровавый пакт.
    dark_reward_ready: bool = False

    # Патч 53: скриптованный ход рейд-босса — если задан, резолвер (фаза 4b)
    # вызывает ЕГО вместо стандартного "кусает" compute_hit(mob, target).
    # None у ВСЕХ обычных мобов/персонажей — поведение резолвера не меняется
    # ни для одного существующего боя (PvE/PvP), это ЧИСТОЕ расширение.
    # Не персистится нигде — как и весь CombatantState, живёт только в
    # памяти на время конкретного рейд-боя (game/combat/raid_bosses.py).
    scripted_hit: "Callable[[CombatantState, CombatSessionState, object], list[PendingHit]] | None" = None
    # Патч 103: способность обычного моба (game/combat/mob_abilities.py).
    # Резолвер зовёт её ход вместо стандартного «кусает». None - у игроков и
    # у рейд-боссов, которые ходят через scripted_hit.
    mob_brain: object | None = None
    # Рейд «Безмогильное поле»: ниже этого HP существо не опускается -
    # призыватель второго этапа не умирает, а встаёт с алебардой (смену
    # этапа делает оркестрация, bot/handlers/raid_field_flow.py). 0 - как у
    # всех обычных бойцов, поведение резолвера не меняется.
    hp_floor: int = 0
    # Рейд «Безмогильное поле»: фильтр входящего удара - (удар, атакующий,
    # урон) -> новый урон. Купол над призывателем гасит урон, стойки
    # генерала меняют его по типу удара. Вызывается в фазе применения, до
    # лимитов и щитов. None у всех остальных - чистое расширение.
    incoming_hit_hook: "Callable[[object, CombatantState | None, int], int] | None" = None
    # Подпись отражённого удара (EffectKind.BLOOD_REFLECT) в логе: у эликсира
    # это шипы, у стойки генерала - «Заслон».
    reflect_label: str = "шипы"

    @property
    def alive(self) -> bool:
        return self.current_hp > 0

    @property
    def tier_mult(self) -> float:
        return formulas.tier_multiplier(self.tier)

    def effect_total(self, kind: EffectKind) -> float:
        return sum(e.value * e.stacks for e in self.effects if e.kind == kind)

    def has_effect(self, kind: EffectKind) -> bool:
        return any(e.kind == kind for e in self.effects)

    def effects_of(self, kind: EffectKind) -> list[Effect]:
        return [e for e in self.effects if e.kind == kind]

    def effect_from(self, kind: EffectKind, source_id: int) -> Effect | None:
        return next((e for e in self.effects if e.kind == kind and e.source_id == source_id), None)

    def has_burning(self) -> bool:
        """Горит ли цель (Горение от любого источника)."""
        # getattr: соло-бои переживают перезапуск pickle-снимком, и эффект из
        # снимка, сделанного кодом до появления tag, этого поля не имеет.
        return any(e.kind == EffectKind.DOT and getattr(e, "tag", None) == BURN_TAG for e in self.effects)

    def apply_effect(
        self, kind: EffectKind, value: float, duration: int, source_id: int, tag: str | None = None,
        decays: bool = True,
    ) -> None:
        """Наложить временный эффект. Non-stacking: повторное применение того же
        вида от того же источника ОБНОВЛЯЕТ значение и длительность, не суммирует.
        tag - метка вида эффекта (см. BURN_TAG). decays=False - дебафф моба или
        босса: без затухания (Effect.fixed)."""
        if kind in bc.DECAYING_DEBUFFS and value > 0 and decays:
            # getattr: соло-бой из pickle-снимка до появления поля.
            value *= getattr(self, "debuff_fatigue", {}).get(kind.value, 1.0)
        for effect in self.effects:
            # Щиты с разными метками не сливаются: мистик со своим Оберегом
            # выпил «Второе сердце» - это два щита, а не один перезаписанный.
            if kind == EffectKind.SHIELD_POOL and getattr(effect, "tag", None) != tag:
                continue
            if effect.kind == kind and effect.source_id == source_id:
                # Горение (2026-10-18): слабое перекинувшееся пламя не гасит
                # полноценный поджог того же элементалиста - остаётся сильное.
                if tag == BURN_TAG and getattr(effect, "tag", None) == BURN_TAG:
                    value = max(value, effect.value)
                effect.value = value
                effect.remaining_ticks = max(effect.remaining_ticks, duration)
                if tag is not None:
                    effect.tag = tag
                effect.fixed = not decays
                return
        self.effects.append(
            Effect(kind=kind, value=value, remaining_ticks=duration, source_id=source_id, tag=tag,
                   fixed=not decays)
        )

    def decay_debuffs(self, preexisting: set[int] | None = None) -> None:
        """Конец хода, после снятия истёкших эффектов: дебафф из
        bc.DECAYING_DEBUFFS держится - он и следующий такой же слабеют на
        bc.DEBUFF_DECAY_PER_TURN; не держится - следующий ляжет в полную
        силу. preexisting - id эффектов, что были на начало хода (резолвер):
        наложенный в этот ход начинает слабеть со следующего, как и его
        длительность. Отрицательные значения (защитная черта моба) не трогаются."""
        fatigue = getattr(self, "debuff_fatigue", None)
        if fatigue is None:
            fatigue = self.debuff_fatigue = {}
        keep = 1.0 - bc.DEBUFF_DECAY_PER_TURN
        for kind in bc.DECAYING_DEBUFFS:
            held = [
                e for e in self.effects
                if e.kind == kind and e.value > 0 and not getattr(e, "fixed", False)
            ]
            if not held:
                fatigue.pop(kind, None)
                continue
            old = [e for e in held if preexisting is None or id(e) in preexisting]
            if not old:
                continue
            for effect in old:
                effect.value *= keep
            fatigue[kind] = fatigue.get(kind, 1.0) * keep

    def is_on_cooldown(self, skill_id: str) -> bool:
        return self.cooldowns.get(skill_id, 0) > 0

    def tick_cooldowns(self) -> None:
        for skill_id in list(self.cooldowns):
            self.cooldowns[skill_id] -= 1
            if self.cooldowns[skill_id] <= 0:
                del self.cooldowns[skill_id]

    def reset_transient(self) -> None:
        self.blocked_this_tick = 0
        self.shield = 0
        self.block_reduction = 0.0
        self.defend_reduction = 0.0
        self.mitigation_penalty = 0.0
        # Провокация держится taunt_left тиков (2026-10-14: раньше слетала
        # после первого же тика, хотя навык обещает 2 хода).
        self.taunt_left = max(0, self.taunt_left - 1)
        if self.taunt_left == 0:
            self.taunted_by = None


def build_combatant(
    id: int,
    side: int,
    kind: str,
    name: str,
    level: int,
    stats: Stats,
    primary_stat: str,
    subclass_id: str | None = None,
    tier: str | None = None,
    buff_modifiers: dict[str, float] | None = None,
    base_class: str | None = None,
    gear_vit: int = 0,
) -> CombatantState:
    """Собирает участника, считая HP/тир по формулам v2. base_class - у
    персонажа: до подкласса даёт пассивку класса - здоровье воина здесь, крит
    разбойника в compute_hit (по combatant.base_class), см. bc.BASE_CLASS_*.
    gear_vit - сколько выносливости в stats от экипировки (для зелий)."""
    tier = tier or formulas.tier_for_level(level)
    max_hp = round(formulas.hp(level, stats.vitality, formulas.tier_multiplier(tier)))
    if kind == "character":
        max_hp = round(max_hp * formulas.class_hp_mult(base_class, subclass_id))
    return CombatantState(
        id=id,
        side=side,
        kind=kind,
        name=name,
        level=level,
        stats=stats,
        primary_stat=primary_stat,
        tier=tier,
        max_hp=max_hp,
        current_hp=max_hp,
        subclass_id=subclass_id,
        base_class=base_class,
        buff_modifiers=buff_modifiers or {},
        gear_vit=gear_vit,
    )


def white_max_hp(c: CombatantState) -> int:
    """Максимум здоровья без выносливости экипировки - от него лечат зелья
    (2026-10-13, решение владельца). Здоровье линейно по выносливости, и
    класс с тиром его только умножают - поэтому пропорцией от max_hp."""
    gear = getattr(c, "gear_vit", 0) or 0
    if gear <= 0 or c.max_hp <= 0:
        return c.max_hp
    tm = formulas.tier_multiplier(c.tier)
    full = formulas.hp(c.level, c.stats.vitality, tm)
    bare = formulas.hp(c.level, max(0, c.stats.vitality - gear), tm)
    return max(1, round(c.max_hp * bare / full)) if full > 0 else c.max_hp


@dataclass
class CombatSessionState:
    session_id: int
    mode: CombatMode
    combatants: dict[int, CombatantState] = field(default_factory=dict)
    tick_number: int = 0
    is_raid: bool = False  # влияет на точность % в логе (п.11)
    #: своё окно хода вместо общего (финал Мельника: жернова ускоряются)
    turn_seconds: float | None = None

    def add(self, combatant: CombatantState) -> None:
        self.combatants[combatant.id] = combatant

    def alive_on_side(self, side: int) -> list[CombatantState]:
        return [c for c in self.combatants.values() if c.side == side and c.alive]

    def alive_enemies_of(self, combatant: CombatantState) -> list[CombatantState]:
        return [
            c for c in self.combatants.values() if c.side != combatant.side and c.alive
        ]

    def alive_allies_of(self, combatant: CombatantState) -> list[CombatantState]:
        return [
            c
            for c in self.combatants.values()
            if c.side == combatant.side and c.alive and c.id != combatant.id
        ]

    def expected_declarers(self) -> set[int]:
        """Кто должен объявить действие в тик: живые игроки (мобы — AI)."""
        return {
            c.id
            for c in self.combatants.values()
            if c.alive and c.kind == "character"
        }

    def sides_alive(self) -> set[int]:
        return {c.side for c in self.combatants.values() if c.alive}
