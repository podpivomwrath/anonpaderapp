"""Рейд «Кукольный театр» (патч 53) — три этапа поверх ОБЩЕГО с групповым PvE
tick_engine (свой экземпляр TickEngine, см. main.py — session_id-пространство
не пересекается ни с чем другим, т.к. движок отдельный). Один battle_id живёт
ВСЮ попытку рейда (все три этапа) — только участники/мобы/раунд меняются,
_peer_battle не перестраивается между этапами.

Оркестрация механик боссов (порядок Вельдов, окна прерывания/фазы Хирурга) —
здесь; чистая логика самих механик — game/combat/raid_bosses.py."""

import asyncio
import random
from dataclasses import dataclass, field

from loguru import logger
from vkbottle.bot import BotLabeler, Message

from bot import background, short_log
from bot.keyboards import combat_modes
from bot.keyboards.combat_items import page_of
from bot import dailies_texts, editable_message, group_texts, raid_key_texts, raid_texts as rt
from bot import raid_archive_texts as at
from bot import raid_field_texts as ft
from bot import raid_mill_texts as mt
from bot import raid_trail_texts as tt
from bot.handlers import respawn as respawn_handlers
from bot.handlers import stats_window
from bot.handlers.group_combat import MemberCombatInput
from bot.keyboards import raid as kb
from bot.battle_keyboard import answer_battle_gone
from bot.keyboards.items import no_keyboard
from bot.keyboards.world import movement_keyboard
from game.combat import balance_config as bc
from game.combat import battle_log, display, elixir_effects, raid_archive, raid_bosses, raid_field, raid_mill
from game.combat import raid_trail as trail_combat
from game.combat import rift as rift_combat
from game.combat.resolver import TickResult
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
    Stats,
    build_combatant,
)
from game.combat.skills import DEFENSIVE_SKILLS
from game.combat.tick_engine import TickEngine
from game.combat import consumable_limit
from game.economy import elixir_config as ec
from game.economy import raid_config as rc
from game.economy import raid_archive_config as ac
from game.economy import raid_field_config as fc
from game.economy import raid_mill_config as mc
from game.economy import raid_trail_config as tc
from game.economy import rift_config as rfc
from models import Character
from services import (
    daily_service,
    elixir_service,
    encounter_service,
    item_service,
    mount_service,
    pvp_shield,
    quest_service,
    raid_combat_service,
    subclass_service,
    trial_service,
    trophy_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»

_engine: TickEngine | None = None
_bot_api = None

_next_battle_id = -1


@dataclass
class Participant:
    character_id: int
    peer_id: int
    name: str
    base_class: str
    subclass_id: str | None


@dataclass
class RaidContribution:
    """Вклад одного участника за ВЕСЬ рейд, все три этапа.

    Копится по ходам, а не считается в конце: TickResult живёт один ход, и к
    финалу восстановить его уже нечем. Один battle_id держит весь рейд, так
    что переживает смену этапа вместе с остальным состоянием боя.
    """

    damage: int = 0     # дошло до противников (промахи и поглощённое не в счёт)
    healed: int = 0     # фактически восполнено союзникам, включая себя
    absorbed: int = 0   # весь урон, пришедший в игрока: дошедший + срезанный блоком и щитами


@dataclass
class RaidBattle:
    group_id: int | None
    participants: dict[int, Participant]
    member_inputs: list[MemberCombatInput]
    rng: random.Random
    run_id: int | None = None
    stage: int = 1
    mob_ids: set[int] = field(default_factory=set)
    #: Скованы механикой рейда в этот ход: пропуск за них объявлен сам, но
    #: кнопки боя у них остаются (2026-10-22, жалоба: «оглушение отключает
    #: клавиатуру»). Нажатие отвечает HELD_TEXT. Снимается с началом хода.
    frozen_now: set[int] = field(default_factory=set)
    last_combatants: dict[int, object] = field(default_factory=dict)
    # --- Этап 2: Вельды ---
    veld_combatant_ids: dict[str, int] = field(default_factory=dict)
    veld_killed_order: list[str] = field(default_factory=list)
    veld_violations: int = 0
    # --- Этап 3: Хирург ---
    surgeon_ai: "raid_bosses.SurgeonAI | None" = None
    surgeon_id: int | None = None
    surgeon_phase3_hp_at_start: int | None = None
    surgeon_phase3_failed: bool = False
    #: Шприцы (2026-10-29): ходов без шприца, набранный цвет, что действует и сколько ещё.
    syringe_clock: int = 0
    syringe_drawn: str | None = None
    syringe_active: str | None = None
    syringe_left: int = 0
    # Награды этапов ждут конца захода (2026-10-18, решение владельца): раньше
    # брали ключ, проходили лёгкий этап, получали опыт и нарочно погибали.
    # Выдаются только при победе; вайп - ничего. Элемент - StageReward.
    pending_rewards: list = field(default_factory=list)
    contribution: dict[int, RaidContribution] = field(default_factory=dict)
    #: когда пал каждый боец - таймер воскрешения идёт с этого момента, а
    #: не с конца захода (2026-10-29, баг-репорт: пал в начале, ждал весь рейд)
    died_at: dict[int, float] = field(default_factory=dict)
    # --- Рейд «Безмогильное поле» (game/combat/raid_field.py) ---
    raid_id: str = rc.RAID_PUPPET_THEATRE_ID
    field_stage: object | None = None   # FogStage / SummonerStage / GeneralStage
    field_leftover: int = 0             # объекты, живые к моменту алебарды
    #: ход, с которого продолжается нумерация: три этапа поля читаются как
    #: один бой, и счётчик хода не должен сбрасываться на единицу.
    tick_offset: int = 0
    #: ходов на текущем этапе - на RAID_STAGE_TURN_LIMIT босс бьёт ультимативно
    stage_ticks: int = 0
    #: строки, которые этап выкладывает на доску до первого хода
    opening_lines: list[str] = field(default_factory=list)

    # --- Рейд «Безликий архив»: этапы 1-2 без боя (bot/handlers/raid_archive.py) ---
    leader_id: int | None = None

    # --- Разломы (services/rift_service.py): тип, уровень, клетка ---
    rift_id: int | None = None
    rift_kind: str | None = None
    rift_level: int = 0
    rift_ring: int = 1
    #: кровавый заход (в группе 60-й) - противники сильнее
    rift_blood: bool = False
    #: клетка, куда участники возвращаются после боя (у рейдов - Монолит)
    home: tuple[int, int] = rc.MONOLITH_COORDS

    @property
    def is_rift(self) -> bool:
        return self.rift_id is not None

    @property
    def final_stage(self) -> int:
        return rift_combat.stage_count(self.rift_kind) if self.is_rift else 3

    @property
    def is_field(self) -> bool:
        return self.raid_id == fc.RAID_FIELD_ID

    @property
    def is_archive(self) -> bool:
        return self.raid_id == ac.RAID_ARCHIVE_ID

    @property
    def is_mill(self) -> bool:
        return self.raid_id == mc.RAID_MILL_ID

    @property
    def is_trail(self) -> bool:
        return self.raid_id == tc.RAID_TRAIL_ID

    @property
    def is_theatre(self) -> bool:
        return self.raid_id == rc.RAID_PUPPET_THEATRE_ID


_battles: dict[int, RaidBattle] = {}


def rift_progress(rift_id: int) -> tuple[int, int] | None:
    """(этап, всего этапов) идущего захода разлома; None - боя в памяти нет."""
    for battle in _battles.values():
        if battle.rift_id == rift_id:
            return battle.stage, battle.final_stage
    return None
_peer_battle: dict[int, int] = {}
_declared_this_tick: dict[int, set[int]] = {}
#: Объявленные в этом ходу действия: {battle_id: {cid: действие}}. Смена цели
#: после объявления переобъявляет удар по новой цели (2026-10-31, репорт 271:
#: «бил жернова, ударило мельника» - цель вшивалась в момент нажатия).
_declared_actions: dict[int, dict[int, DeclaredAction]] = {}
HELD_TEXT = "Ты скован и этот ход пропускаешь. Кнопки заработают на следующем."
_chosen_target: dict[int, int] = {}
_character_in_raid: set[int] = set()


def setup(engine: TickEngine, bot_api) -> None:
    global _engine, _bot_api
    _engine = engine
    _bot_api = bot_api


def has_active_raid(character_id: int) -> bool:
    return character_id in _character_in_raid


def has_active_battle(peer_id: int) -> bool:
    return peer_id in _peer_battle


def rebuild_keyboard(peer_id: int) -> str | None:
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id)
    if battle is None:
        return None
    if battle.is_archive and battle.stage < 3:
        from bot.handlers import raid_archive  # цикл импортов

        return raid_archive.keyboard_for(peer_id)
    if battle.is_mill and battle.stage < 2:
        from bot.handlers import raid_procession  # цикл импортов

        return raid_procession.keyboard_for(peer_id)
    if battle.is_trail and battle.stage < 3:
        from bot.handlers import raid_trail  # цикл импортов

        return raid_trail.keyboard_for(peer_id)
    state = _engine.sessions.get(battle_id) if _engine else None
    cid = _character_id_for_peer(battle, peer_id)
    c = state.combatants.get(cid) if state else None
    if c is None or not c.alive or (
        cid in _declared_this_tick.get(battle_id, set()) and cid not in battle.frozen_now
    ):
        return kb.raid_waiting_keyboard()
    p = battle.participants[cid]
    return _combat_keyboard(battle, p, c)


def _combat_keyboard(battle: RaidBattle, p: Participant, combatant) -> str:
    """Боевая клавиатура рейда + кнопки этапа (груз обоза, каравай Мельника)."""
    extra = []
    stage = battle.field_stage
    if isinstance(stage, raid_mill.CargoStage):
        # Видят все: не в свою очередь - попытка проваливается (решение владельца).
        extra.append((mt.BTN_CARRY, {"type": "raid_carry"}))
    elif isinstance(stage, raid_mill.MillerStage) and stage.bread_open:
        extra.append((mt.BTN_BREAD, {"type": "raid_bread"}))
    grid = _arena_grid(battle, stage, p.character_id) if isinstance(stage, trail_combat.NamelessStage) else None
    return kb.raid_combat_keyboard(p.base_class, combatant.cooldowns, subclass_id=p.subclass_id, extra=extra,
                                   grid=grid)


def _arena_grid(battle: RaidBattle, stage, cid: int) -> list[list[tuple[str, dict, str]]]:
    """Арена Безымянного 3×3 сверху боевой клавиатуры: цвет - что на клетке."""
    numbers = {c: n for n, c in enumerate(sorted(battle.participants), start=1)}
    danger = stage.danger(cid)
    rows = []
    for r in range(tc.ARENA):
        row = []
        for c in range(tc.ARENA):
            cell = r * tc.ARENA + c
            others = [numbers[o] for o, pos in stage.pos.items() if pos == cell and o != cid]
            if stage.pos.get(cid) == cell:
                # Под тобой отпечаток - клетка красная (2026-10-25: зелёная
                # своя клетка прятала опасность, а один отпечаток всегда под кем-то).
                label, color = "📍", "negative" if cell in danger else "positive"
            elif cell in danger:
                label, color = (str(min(others)) if others else "👣"), "negative"
            elif others:
                label, color = str(min(others)), "secondary"
            else:
                label, color = "·", "primary"
            row.append((label, {"type": "raid_step", "c": cell}, color))
        rows.append(row)
    return rows


# --- Построение боевых участников (свежие каждый этап — как и групповой PvE) ---


def _build_player_combatants(state: CombatSessionState, member_inputs: list[MemberCombatInput]) -> None:
    for m in member_inputs:
        bonus = m.gear_bonus
        stats = Stats(
            strength=m.stats.strength + bonus.get("str", 0),
            agility=m.stats.agility + bonus.get("agi", 0),
            intellect=m.stats.intellect + bonus.get("int", 0),
            vitality=m.stats.vitality + bonus.get("vit", 0),
            will=m.stats.will + bonus.get("wil", 0),
        )
        primary = bc.PRIMARY_STAT_BY_CLASS[m.character.base_class]
        combatant = build_combatant(
            id=m.character.id, side=0, kind="character", name=m.character.name,
            level=m.character.level, stats=stats, primary_stat=primary,
            subclass_id=m.character.subclass, buff_modifiers=m.buff_modifiers,
            base_class=m.character.base_class, gear_vit=bonus.get("vit", 0),
        )
        # Между этапами HP восстанавливается ПОЛНОСТЬЮ, включая погибших на
        # предыдущем этапе (текст патча) — новый CombatantState стартует с
        # полным HP всегда, не с current_hp предыдущего боя.
        combatant.current_hp = combatant.max_hp
        state.add(combatant)


def _start_stage_session(battle_id: int, battle: RaidBattle) -> CombatSessionState:
    battle.stage_ticks = 0
    state = CombatSessionState(session_id=battle_id, mode=CombatMode.PVE, is_raid=True)
    _build_player_combatants(state, battle.member_inputs)

    if battle.is_field or battle.is_archive or battle.is_rift or battle.is_mill or battle.is_trail:
        _build_field_stage(battle, state)
    elif battle.stage == 1:
        mobs = raid_bosses.build_stage1_mobs(start_id=20_000_000)
        for m in mobs:
            state.add(m)
        battle.mob_ids = {m.id for m in mobs}
    elif battle.stage == 2:
        velds = raid_bosses.build_veld_mobs(start_id=20_100_000)
        for m in velds.values():
            state.add(m)
        battle.mob_ids = {m.id for m in velds.values()}
        battle.veld_combatant_ids = {vid: c.id for vid, c in velds.items()}
        battle.veld_killed_order = []
        battle.veld_violations = 0
    else:
        surgeon = raid_bosses.build_surgeon(id=20_200_000)
        ai = raid_bosses.SurgeonAI()
        surgeon.scripted_hit = ai
        state.add(surgeon)
        battle.mob_ids = {surgeon.id}
        battle.surgeon_ai = ai
        battle.surgeon_id = surgeon.id
        battle.surgeon_phase3_hp_at_start = None
        battle.surgeon_phase3_failed = False

    default_target = _default_target_id(battle)
    if default_target is not None:
        for p in list(battle.participants.values()):
            _chosen_target[p.character_id] = default_target
    return state


def _build_field_stage(battle: RaidBattle, state: CombatSessionState) -> None:
    """Этап «Безмогильного поля». id противников - свой диапазон на этап,
    как у театра: объекты и скелеты нумеруются дальше от него. У архива
    боевой только третий этап - Архивариус."""
    if battle.is_rift:
        stage = rift_combat.build_stage(
            battle.rift_kind, battle.stage, 21_000_000 + battle.stage * 100_000, battle.rift_level, battle.rift_ring,
            blood=getattr(battle, "rift_blood", False),
        )
    elif battle.is_archive:
        stage = raid_archive.ArchiveStage(start_id=20_600_000)
    elif battle.is_mill and battle.stage == 2:
        order = raid_mill.carry_order([p.subclass_id for p in battle.participants.values()])
        stage = raid_mill.CargoStage(start_id=20_700_000, participants=len(battle.participants), order=order)
    elif battle.is_mill:
        stage = raid_mill.MillerStage(start_id=20_800_000)
    elif battle.is_trail:
        stage = trail_combat.NamelessStage(start_id=20_900_000)
    elif battle.stage == 1:
        stage = raid_field.FogStage(start_id=20_300_000)
    elif battle.stage == 2:
        stage = raid_field.SummonerStage(start_id=20_400_000, participants=len(battle.participants))
    else:
        stage = raid_field.GeneralStage(start_id=20_500_000, leftover_objects=battle.field_leftover)
    battle.opening_lines = stage.setup(state)
    battle.field_stage = stage
    # Награда и цель по умолчанию - только за «настоящих» противников этапа:
    # скелеты и объекты поля лута не дают, иначе бесконечный подъём
    # мертвецов стал бы фермой.
    battle.mob_ids = set(stage.reward_ids)
    state.tick_number = battle.tick_offset


def _default_target_id(battle: RaidBattle) -> int | None:
    """Цель, которая стоит у всех на первом ходу этапа.

    На 2 этапе это НАМЕРЕННО тот Вельд, которого надо убить ПОСЛЕДНИМ. Раньше
    сюда попадал Освальд - он же первый в rc.VELD_ORDER, он же первый по HP,
    он же первый в лоре. Загадка про порядок решалась сама собой: достаточно
    было жать «Ударить», ни разу не сменив цель. Теперь автобой ведёт ровно в
    противоположный конец очереди, и цель приходится выбирать руками.

    На 1 и 3 этапах выбирать не из чего (три одинаковые куклы / один Хирург),
    поэтому просто первый по id - sorted, а не обход set, чтобы у всех
    участников цель совпадала гарантированно, а не по везению с хешами.
    """
    if battle.stage == 2 and battle.veld_combatant_ids:
        last_in_order = rc.VELD_ORDER[-1]
        target = battle.veld_combatant_ids.get(last_in_order)
        if target is not None:
            return target
    enemies = sorted(battle.mob_ids)
    return enemies[0] if enemies else None


_STAGE_APPEAR_TEXT = {1: rt.STAGE1_APPEAR_TEXT, 2: rt.STAGE2_APPEAR_TEXT, 3: rt.STAGE3_APPEAR_TEXT}
_STAGE_LOOT_MULT = {1: rc.STAGE1_LOOT_MULT, 2: rc.STAGE2_LOOT_MULT, 3: rc.STAGE3_LOOT_MULT}
_STAGE_LOOT_FLOOR = {1: "uncommon", 2: "rare", 3: "epic"}

_FIELD_APPEAR_TEXT = {1: ft.STAGE1_APPEAR_TEXT, 2: ft.STAGE2_APPEAR_TEXT, 3: ft.STAGE3_APPEAR_TEXT}
_FIELD_LOOT_MULT = {1: fc.STAGE1_LOOT_MULT, 2: fc.STAGE2_LOOT_MULT, 3: fc.STAGE3_LOOT_MULT}


_ARCHIVE_LOOT_MULT = {1: ac.STAGE1_LOOT_MULT, 2: ac.STAGE2_LOOT_MULT, 3: ac.STAGE3_LOOT_MULT}
_MILL_LOOT_MULT = {1: mc.STAGE1_LOOT_MULT, 2: mc.STAGE2_LOOT_MULT, 3: mc.STAGE3_LOOT_MULT}
_TRAIL_LOOT_MULT = {1: tc.STAGE1_LOOT_MULT, 2: tc.STAGE2_LOOT_MULT, 3: tc.STAGE3_LOOT_MULT}


def _texts(battle: RaidBattle):
    """Модуль текстов рейда: пролог, эпилог, поражение, картинки."""
    if battle.is_rift:
        from bot.rift_texts import RiftTexts

        return RiftTexts(battle.rift_kind, blood=getattr(battle, "rift_blood", False))
    if battle.is_field:
        return ft
    if battle.is_archive:
        return at
    if battle.is_mill:
        return mt
    if battle.is_trail:
        return tt
    return rt


def _appear_text(battle: RaidBattle) -> str:
    if battle.is_rift:
        return _texts(battle).appear_text(battle.stage)
    if battle.is_archive:
        return at.STAGE3_APPEAR_TEXT
    if battle.is_mill:
        return mt.STAGE2_APPEAR_TEXT if battle.stage == 2 else mt.STAGE3_APPEAR_TEXT
    if battle.is_trail:
        return tt.STAGE3_APPEAR_TEXT
    return (_FIELD_APPEAR_TEXT if battle.is_field else _STAGE_APPEAR_TEXT)[battle.stage]


def _stage_attachment(battle: RaidBattle) -> str | None:
    return _texts(battle).stage_attachment(battle.stage)


def _xp_mobs(battle: RaidBattle) -> float:
    """Опыт этапа в «обычных мобах» каждому живому, без дележа. Разлом
    (2026-10-13): этап с волной - x2 за каждого моба, босс - x10. Рейд
    (2026-10-17): rc.RAID_STAGE_XP_MOBS по этапу."""
    if not battle.is_rift:
        return rc.RAID_STAGE_XP_MOBS[battle.stage]
    stage = battle.field_stage
    if stage is None or battle.stage == battle.final_stage or getattr(stage, "is_boss", False):
        return rfc.BOSS_XP_MOBS
    return rfc.WAVE_XP_PER_MOB * max(1, len(getattr(stage, "reward_ids", ()) or ()))


def _loot_mult(battle: RaidBattle) -> int:
    if battle.is_rift:
        # Босс - последний множитель, сколько бы этапов ни было до него.
        if battle.stage == battle.final_stage:
            return rfc.STAGE_LOOT_MULT[-1]
        return rfc.STAGE_LOOT_MULT[battle.stage - 1]
    if battle.is_archive:
        return _ARCHIVE_LOOT_MULT[battle.stage]
    if battle.is_mill:
        return _MILL_LOOT_MULT[battle.stage]
    if battle.is_trail:
        return _TRAIL_LOOT_MULT[battle.stage]
    return (_FIELD_LOOT_MULT if battle.is_field else _STAGE_LOOT_MULT)[battle.stage]


def _trial_level(battle: RaidBattle) -> int:
    if battle.is_archive:
        return ac.TRIAL_LEVEL
    if battle.is_mill:
        return mc.TRIAL_LEVEL
    if battle.is_trail:
        return tc.TRIAL_LEVEL
    return fc.TRIAL_LEVEL if battle.is_field else rc.SURGEON_TRIAL_LEVEL


def _unique_id(battle: RaidBattle) -> str:
    if battle.is_archive:
        return ac.RAID_UNIQUE_ITEM_ID
    if battle.is_mill:
        return mc.RAID_UNIQUE_ITEM_ID
    if battle.is_trail:
        return tc.RAID_UNIQUE_ITEM_ID
    return fc.RAID_UNIQUE_ITEM_ID if battle.is_field else rc.RAID_UNIQUE_ITEM_ID


async def start_raid(
    group_id: int | None, member_inputs: list[MemberCombatInput], rng: random.Random, *,
    run_id: int | None = None, raid_id: str = rc.RAID_PUPPET_THEATRE_ID, leader_id: int | None = None,
    rift=None,
) -> None:
    """rift - строка разлома (models.Rift) с уже выставленным level: бой
    разлома идёт тем же путём, что и рейды 60 уровня."""
    global _next_battle_id
    battle_id = _next_battle_id
    _next_battle_id -= 1

    participants = {
        m.character.id: Participant(
            character_id=m.character.id, peer_id=m.peer_id, name=m.character.name,
            base_class=m.character.base_class, subclass_id=m.character.subclass,
        )
        for m in member_inputs
    }
    battle = RaidBattle(
        group_id=group_id, participants=participants, member_inputs=member_inputs, rng=rng,
        run_id=run_id, raid_id=raid_id, leader_id=leader_id,
    )
    if rift is not None:
        battle.raid_id = f"rift:{rift.kind}"
        battle.rift_id, battle.rift_kind = rift.id, rift.kind
        battle.rift_level, battle.rift_ring = rift.level, rift.ring
        from services import rift_service  # цикл импортов

        battle.rift_blood = rift_service.is_blood(rift)
        battle.home = (rift.x, rift.y)
    _battles[battle_id] = battle
    for cid, p in participants.items():
        _peer_battle[p.peer_id] = battle_id
        _character_in_raid.add(cid)

    texts = _texts(battle)
    if battle.is_archive:
        # Первые два этапа архива - головоломки и загадки, не бой: ими
        # ведёт свой модуль, а бой начнётся с begin_combat_stage.
        from bot.handlers import raid_archive  # цикл импортов

        for p in participants.values():
            await _bot_api.messages.send(
                peer_id=p.peer_id, message=texts.PROLOGUE_TEXT,
                attachment=texts.prologue_attachment(), random_id=0,
            )
        await raid_archive.start(battle_id, battle)
        return
    if battle.is_mill:
        # Первый этап - шествие, не бой: бой начнётся с begin_combat_stage.
        from bot.handlers import raid_procession  # цикл импортов

        for p in participants.values():
            await _bot_api.messages.send(
                peer_id=p.peer_id, message=texts.PROLOGUE_TEXT,
                attachment=texts.prologue_attachment(), random_id=0,
            )
        await raid_procession.start(battle_id, battle)
        return
    if battle.is_trail:
        # Первый этап - лабиринт, не бой: бой с Безымянным - третьим этапом.
        from bot.handlers import raid_trail  # цикл импортов

        for p in participants.values():
            await _bot_api.messages.send(
                peer_id=p.peer_id, message=texts.PROLOGUE_TEXT,
                attachment=texts.prologue_attachment(), random_id=0,
            )
        await raid_trail.start(battle_id, battle)
        return

    state = _start_stage_session(battle_id, battle)
    _engine.start_session(state)

    for p in participants.values():
        await _bot_api.messages.send(
            peer_id=p.peer_id, message=texts.PROLOGUE_TEXT,
            attachment=texts.prologue_attachment(), random_id=0,
        )
        await _bot_api.messages.send(
            peer_id=p.peer_id, message=_appear_text(battle),
            attachment=_stage_attachment(battle), random_id=0,
        )
    await _broadcast_board(battle_id, battle, None, boss_lines=_take_opening_lines(battle))


async def begin_combat_stage(
    battle_id: int, stage: int = 3, lame: dict[int, int] | None = None,
    hp_share: dict[int, float] | None = None,
) -> None:
    """Небоевые этапы позади: архив - бой с Архивариусом (3), жернова -
    обоз (2). lame - хромота шествия: каждый стак - минус здоровье на старте.
    hp_share - с какой долей здоровья начинает бой (Тропа: не успевшие к
    воротам)."""
    battle = _battles.get(battle_id)
    if battle is None:
        return
    battle.stage = stage
    state = _start_stage_session(battle_id, battle)
    for cid, stacks in (lame or {}).items():
        c = state.combatants.get(cid)
        if c is not None and stacks > 0:
            c.current_hp = max(1, c.current_hp - round(c.max_hp * mc.LAME_HP_PCT * stacks))
            battle.opening_lines.append(f"🩼 {c.name} хромает: -{round(mc.LAME_HP_PCT * stacks * 100)}% здоровья")
    for cid, share in (hp_share or {}).items():
        c = state.combatants.get(cid)
        if c is not None:
            c.current_hp = max(1, round(c.max_hp * share))
    _engine.start_session(state)
    for p in list(battle.participants.values()):
        await _bot_api.messages.send(
            peer_id=p.peer_id, message=_appear_text(battle),
            attachment=_stage_attachment(battle), random_id=0,
        )
    await _broadcast_board(battle_id, battle, None, boss_lines=_take_opening_lines(battle))


async def award_stage(battle_id: int, skip: set[int] | frozenset = frozenset()) -> dict[int, str]:
    """Архив: награда за пройденный небоевой этап - всем участникам, кроме
    skip (Тропа: не успевшие к воротам)."""
    battle = _battles.get(battle_id)
    if battle is None:
        return {}
    return await _stage_rewards(battle, [cid for cid in battle.participants if cid not in skip])


def _take_opening_lines(battle: RaidBattle) -> list[str] | None:
    lines, battle.opening_lines = battle.opening_lines, []
    return lines or None


def abort_run(run_id: int) -> None:
    for battle_id, battle in list(_battles.items()):
        if battle.run_id != run_id:
            continue
        _engine.abort_session(battle_id)
        if battle.is_archive:
            from bot.handlers import raid_archive  # цикл импортов

            raid_archive.abort(battle_id)
        if battle.is_mill:
            from bot.handlers import raid_procession  # цикл импортов

            raid_procession.abort(battle_id)
        if battle.is_trail:
            from bot.handlers import raid_trail  # цикл импортов

            raid_trail.abort(battle_id)
        _battles.pop(battle_id, None)
        _declared_this_tick.pop(battle_id, None)
        _declared_actions.pop(battle_id, None)
        from bot import trial_tracking  # бой прерван - незаконченный этап не считается

        trial_tracking.drop(battle_id)
        for p in list(battle.participants.values()):
            _peer_battle.pop(p.peer_id, None)
            _chosen_target.pop(p.character_id, None)
            _character_in_raid.discard(p.character_id)


def _live_state(battle_id: int, battle: RaidBattle) -> dict:
    state = _engine.sessions.get(battle_id)
    if state is not None:
        battle.last_combatants = dict(state.combatants)
    return battle.last_combatants


def _character_id_for_peer(battle: RaidBattle, peer_id: int) -> int | None:
    for cid, p in list(battle.participants.items()):
        if p.peer_id == peer_id:
            return cid
    return None


def _enemies_of(battle_id: int, battle: RaidBattle, cid: int) -> list[int]:
    combatants = _live_state(battle_id, battle)
    me = combatants.get(cid)
    if me is None:
        return []
    return [c.id for c in combatants.values() if c.side != me.side and c.alive]


def _resolve_chosen_target(battle_id: int, battle: RaidBattle, cid: int) -> int | None:
    combatants = _live_state(battle_id, battle)
    target_id = _chosen_target.get(cid)
    target = combatants.get(target_id) if target_id is not None else None
    if target is not None and target.alive:
        return target_id
    enemies = _enemies_of(battle_id, battle, cid)
    fallback = enemies[0] if enemies else None
    if fallback is not None:
        _chosen_target[cid] = fallback
    return fallback


def _target_line(battle_id: int, battle: RaidBattle, cid: int) -> str:
    # Цель пала - сразу следующая, и её видно (2026-10-17).
    _resolve_chosen_target(battle_id, battle, cid)
    combatants = _live_state(battle_id, battle)
    target_id = _chosen_target.get(cid)
    target = combatants.get(target_id) if target_id is not None else None
    if target is None or not target.alive:
        return ""
    hp_pct = round(100 * target.current_hp / target.max_hp) if target.max_hp else 0
    return f"🎯 Цель: {target.name} ({hp_pct}% HP)"


def _render_board(
    state: CombatSessionState, result: TickResult | None = None, boss_lines: list[str] | None = None,
) -> str:
    return battle_log.render_tick(state, result or TickResult(), viewer_side=0, enemy_lines=boss_lines)


async def _broadcast_board(
    battle_id: int, battle: RaidBattle, result: TickResult | None, notices: dict[int, str] | None = None,
    boss_lines: list[str] | None = None,
) -> None:
    """boss_lines - сценарные реплики босса (порядок Вельдов, фазы Хирурга).

    Уходят В ДОСКУ, в раздел противника (battle_log.render_tick ждёт их
    параметром enemy_lines - ради них он и написан): это ДЕЙСТВИЯ врага в
    этот ход, и читаться они должны перед ударами, которые объясняют.
    Персональные notices (опыт, дроп) - наоборот, над доской: к ходу боя
    они отношения не имеют.
    """
    state = _engine.sessions.get(battle_id)
    text = _render_board(state, result, boss_lines) if state is not None else ""
    short = (
        battle_log.render_short(state, result or TickResult(), enemy_lines=boss_lines) if state is not None else ""
    )
    notices = notices or {}
    skipping = _declared_this_tick.get(battle_id, set())
    for cid, p in list(battle.participants.items()):
        combatant = _live_state(battle_id, battle).get(cid)
        # Скованный (руки на поле) ход не выбирает - за него уже объявлен
        # пропуск, кнопки боя ему ни к чему.
        keyboard = (
            _combat_keyboard(battle, p, combatant)
            if combatant is not None and combatant.alive and (cid not in skipping or cid in battle.frozen_now)
            else kb.raid_waiting_keyboard()
        )
        personal = text
        short_personal = short or text
        notice = notices.get(cid)
        if notice:
            personal = f"{notice}\n\n{personal}"
            short_personal = f"{notice}\n\n{short_personal}"
        target_line = _target_line(battle_id, battle, cid)
        if target_line and combatant is not None and combatant.alive:
            personal = f"{personal}\n{target_line}"
            short_personal = f"{short_personal}\n{target_line}"
        raid_state = _engine.sessions.get(battle_id)
        own = battle_log.class_line(raid_state.combatants, cid) if raid_state is not None else None
        if own:
            personal = f"{personal}\n{own}"
        # Личное, а не общее: патч 71 по ошибке заменил здесь personal на text,
        # и с тех пор опыт, дроп, ключ, испытание и строка цели до игрока
        # не доходили вовсе.
        await short_log.send(_bot_api, p.peer_id, short_personal, personal, keyboard)


# --- Действия боя (атака/навык) ---


# Патч 54: раньше правило было `text=["⚔️ Ударить"]` — дословно подпись
# группового PvE, чей лейблер зарегистрирован РАНЬШЕ (bot/handlers/__init__.py),
# поэтому нажатие перехватывал group_attack, не находил группового боя и молча
# выходил: обычная атака в рейде не работала вовсе. Теперь диспетчеризация по
# уникальному payload, а подпись — из общего реестра (bot/keyboards/combat_modes.py).
@labeler.message(payload_contains={"type": "raid_attack"})
async def raid_attack(message: Message) -> None:
    await _raid_action(message, DeclaredAction(type=ActionType.ATTACK))


@labeler.message(payload_contains={"type": combat_modes.RAID.defend_payload})
async def raid_defend(message: Message) -> None:
    await _raid_action(message, DeclaredAction(type=ActionType.DEFEND))


@labeler.message(payload_contains={"type": "raid_skill"})
async def raid_skill(message: Message) -> None:
    payload = message.get_payload_json() or {}
    skill_id = payload.get("id")
    if not isinstance(skill_id, str):
        return
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    if combatant is not None and combatant.is_on_cooldown(skill_id):
        cd = combatant.cooldowns.get(skill_id, 0)
        p = battle.participants.get(cid)
        keyboard = _combat_keyboard(battle, p, combatant) if p else None
        await message.answer(f"⏳ Навык ещё не готов (КД {cd}).", keyboard=keyboard)
        return
    await _raid_action(message, DeclaredAction(type=ActionType.SKILL, skill_id=skill_id))


async def _raid_action(message: Message, action: DeclaredAction) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    if cid in battle.frozen_now:
        await message.answer(HELD_TEXT)
        return

    is_defensive = action.type == ActionType.DEFEND or (
        action.type == ActionType.SKILL and action.skill_id in DEFENSIVE_SKILLS
    )
    if not is_defensive:
        target = _resolve_chosen_target(battle_id, battle, cid)
        if target is None:
            return
        action = action.model_copy(update={"target_id": target})

    _declared_this_tick.setdefault(battle_id, set()).add(cid)
    _declared_actions.setdefault(battle_id, {})[cid] = action
    try:
        await _engine.declare_action(battle_id, cid, action)
    except (KeyError, ValueError):
        _declared_this_tick.get(battle_id, set()).discard(cid)
        _declared_actions.get(battle_id, {}).pop(cid, None)
        return
    if cid in _declared_this_tick.get(battle_id, set()):
        p = battle.participants.get(cid)
        if p is not None:
            await _bot_api.messages.send(
                peer_id=p.peer_id, message="✅ Действие принято. Ожидание остальных...",
                random_id=0, keyboard=kb.raid_waiting_keyboard(),
            )


@labeler.message(payload_contains={"type": "raid_carry"})
async def raid_carry(message: Message) -> None:
    """Обоз: «Нести груз» сразу занимает ход. Не в свою очередь - ход
    потрачен впустую (решение владельца 2026-10-19)."""
    battle_id = _peer_battle.get(message.peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        await answer_battle_gone(message)
        return
    stage = battle.field_stage
    state = _engine.sessions.get(battle_id)
    cid = _character_id_for_peer(battle, message.peer_id)
    if not isinstance(stage, raid_mill.CargoStage) or state is None or cid is None:
        return
    if cid in battle.frozen_now:
        await message.answer(HELD_TEXT)
        return
    if cid in _declared_this_tick.get(battle_id, set()):
        return
    if stage.can_carry(state, cid):
        stage.claim()
        action = DeclaredAction(type=ActionType.SKIP, payload={"note": raid_mill.CARRY_NOTE, "carry": True})
    else:
        action = DeclaredAction(type=ActionType.SKIP, payload={"note": raid_mill.WRONG_CARRY_NOTE})
    await _raid_action(message, action)
    if action.payload.get("carry") and cid not in _declared_this_tick.get(battle_id, set()):
        stage.carried = False  # ход не принят движком - груз свободен


@labeler.message(payload_contains={"type": "raid_step"})
async def raid_step(message: Message) -> None:
    """Безымянный: шаг по арене - занимает ход."""
    battle_id = _peer_battle.get(message.peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        await answer_battle_gone(message)
        return
    stage = battle.field_stage
    cid = _character_id_for_peer(battle, message.peer_id)
    cell = (message.get_payload_json() or {}).get("c")
    if not isinstance(stage, trail_combat.NamelessStage) or cid is None or not isinstance(cell, int):
        return
    if cid in battle.frozen_now:
        await message.answer(HELD_TEXT)
        return
    if cid in _declared_this_tick.get(battle_id, set()):
        return
    if not stage.can_step(cid, cell):
        state = _engine.sessions.get(battle_id)
        combatant = state.combatants.get(cid) if state else None
        if combatant is not None:
            await message.answer("Шагнуть можно только на соседнюю плиту.",
                                 keyboard=_combat_keyboard(battle, battle.participants[cid], combatant))
        return
    await _raid_action(message, DeclaredAction(type=ActionType.SKIP, payload={"note": tt.STEP_NOTE, "step": cell}))


@labeler.message(payload_contains={"type": "raid_bread"})
async def raid_bread(message: Message) -> None:
    """Мельник: каравай - без траты хода, достаётся первому."""
    battle_id = _peer_battle.get(message.peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        await answer_battle_gone(message)
        return
    stage = battle.field_stage
    state = _engine.sessions.get(battle_id)
    cid = _character_id_for_peer(battle, message.peer_id)
    if not isinstance(stage, raid_mill.MillerStage) or state is None or cid is None:
        return
    line = stage.take_bread(state, cid)
    if line is None:
        await message.answer("🍞 Каравай уже взяли.")
        return
    p = battle.participants[cid]
    combatant = state.combatants.get(cid)
    await _tell_others(battle, cid, line)
    keyboard = (
        kb.raid_waiting_keyboard()
        if cid in _declared_this_tick.get(battle_id, set()) and cid not in battle.frozen_now
        else _combat_keyboard(battle, p, combatant)
    )
    await _bot_api.messages.send(peer_id=p.peer_id, message=line, random_id=0, keyboard=keyboard)


# --- Выбор цели (бесплатное действие, как в массовом PvP/групповом PvE) ---


@labeler.message(payload_contains={"type": "raid_open_target"})
async def raid_open_target(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    mob_ids = _enemies_of(battle_id, battle, cid)
    if not mob_ids:
        return
    combatants = _live_state(battle_id, battle)
    current_id = _chosen_target.get(cid)
    lines = ["🎯 Выбор цели", ""]
    for i, mob_id in enumerate(mob_ids, start=1):
        mob = combatants[mob_id]
        hp_pct = round(100 * mob.current_hp / mob.max_hp) if mob.max_hp else 0
        lines.append(f"{i}. {mob.name} · {hp_pct}% HP")
    lines.append("")
    current = combatants.get(current_id) if current_id is not None else None
    lines.append(f"Текущая цель: {current.name if current is not None else '-'}")
    # Открытие окна - всегда новым сообщением внизу: иначе правилось бы
    # окно из прошлого боя, давно уехавшее вверх, и нажатие казалось мёртвым.
    editable_message.clear("raid_target", peer_id)
    await editable_message.send_or_edit(
        _bot_api, "raid_target", peer_id, "\n".join(lines), kb.raid_target_keyboard(mob_ids),
    )


@labeler.message(payload_contains={"type": "raid_target_pick"})
async def raid_pick_target(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    target_id = payload.get("target")
    if not isinstance(target_id, int):
        return
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatants = _live_state(battle_id, battle)
    me = combatants.get(cid)
    target = combatants.get(target_id)
    if me is None or target is None or target.side == me.side or not target.alive:
        return
    _chosen_target[cid] = target_id
    p = battle.participants.get(cid)
    if p is None:
        return
    declared = _declared_actions.get(battle_id, {}).get(cid)
    if declared is not None and declared.target_id is not None and declared.target_id != target_id:
        # Ход уже объявлен - удар уходит по новой цели, а не по старой.
        declared = declared.model_copy(update={"target_id": target_id})
        _declared_actions[battle_id][cid] = declared
        try:
            await _engine.declare_action(battle_id, cid, declared)
        except (KeyError, ValueError):
            pass
    if cid in _declared_this_tick.get(battle_id, set()):
        await editable_message.send_or_edit(
            _bot_api, "raid_target", peer_id, f"🎯 Новая цель: {target.name}. Удар этого хода - по ней.", no_keyboard(),
        )
        return
    await editable_message.send_or_edit(_bot_api, "raid_target", peer_id, f"🎯 Новая цель: {target.name}.", no_keyboard())
    board = f"🎯 Цель: {target.name}.\n\n{_render_board(_engine.sessions.get(battle_id))}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=board, random_id=0,
        keyboard=_combat_keyboard(battle, p, me),
    )


@labeler.message(payload_contains={"type": "raid_target_back"})
async def raid_target_back(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    p = battle.participants.get(cid)
    if combatant is None or p is None:
        return
    await editable_message.send_or_edit(_bot_api, "raid_target", peer_id, "Возврат в бой.", no_keyboard())
    await _bot_api.messages.send(
        peer_id=peer_id, message=_render_board(_engine.sessions.get(battle_id)), random_id=0,
        keyboard=_combat_keyboard(battle, p, combatant),
    )


# --- Предметы в бою ---


@labeler.message(payload_contains={"type": "raid_items_page"})
@labeler.message(payload_contains={"type": "raid_open_items"})
async def raid_open_items(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    combatant = _live_state(battle_id, battle).get(cid)
    p = battle.participants.get(cid)
    if combatant is None or p is None:
        return
    battle_kb = _combat_keyboard(battle, p, combatant)
    if combatant.has_effect(EffectKind.FREEZE):
        await message.answer("Скован, не до зелий сейчас. ❄️", keyboard=battle_kb)
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        stock = await elixir_service.get_stock(db, character.id)

    if not stock:
        await message.answer("🎒 В сумке пусто.", keyboard=battle_kb)
        return

    limit_reached = combatant.combat_elixirs_used >= ec.ELIXIR_PER_BATTLE_LIMIT
    visible = consumable_limit.visible_stock(combatant, stock, limit_reached)
    text = consumable_limit.items_header(combatant)
    if limit_reached and any(d.category != "heal" for d, _ in stock):
        text += "\n\nБольше твоё тело не выдержит за один бой - боевые эликсиры недоступны."
    # Открытие окна - всегда новым сообщением внизу: иначе правилось бы
    # окно из прошлого боя, давно уехавшее вверх, и нажатие казалось мёртвым.
    page = page_of(message)
    if page is None:
        editable_message.clear("raid_item", peer_id)
    await editable_message.send_or_edit(
        _bot_api, "raid_item", peer_id, text, kb.raid_items_keyboard(visible, page or 0),
    )


@labeler.message(payload_contains={"type": "raid_use_item"})
async def raid_use_item(message: Message) -> None:
    peer_id = message.peer_id
    battle_id = _peer_battle.get(peer_id)
    battle = _battles.get(battle_id) if battle_id is not None else None
    if battle is None:
        # Молчать здесь нельзя: клавиатура боя осталась у игрока на экране,
        # а самого боя в памяти уже нет. См. battle_keyboard.answer_battle_gone.
        await answer_battle_gone(message)
        return
    cid = _character_id_for_peer(battle, peer_id)
    if cid is None:
        return
    payload = message.get_payload_json() or {}
    elixir_id = payload.get("id")
    elixir = elixir_service.elixir_def(elixir_id) if isinstance(elixir_id, str) else None
    if elixir is None:
        return

    combatant = _live_state(battle_id, battle).get(cid)
    p = battle.participants.get(cid)
    if combatant is None or p is None:
        return
    battle_kb = _combat_keyboard(battle, p, combatant)
    if combatant.has_effect(EffectKind.FREEZE):
        await message.answer("Скован, не до зелий сейчас. ❄️", keyboard=battle_kb)
        return
    if consumable_limit.left(combatant) <= 0:
        await message.answer(consumable_limit.EXHAUSTED_TEXT, keyboard=battle_kb)
        return
    if elixir.category == "heal" and consumable_limit.heal_taken(combatant):
        await message.answer(consumable_limit.HEAL_TAKEN_TEXT, keyboard=battle_kb)
        return
    if elixir.category != "heal" and combatant.combat_elixirs_used >= ec.ELIXIR_PER_BATTLE_LIMIT:
        await message.answer("Больше твоё тело не выдержит за один бой.", keyboard=battle_kb)
        return

    # Метательная склянка (2026-10-23): спросить, пить самому или на группу.
    from bot import flask_throw
    from game.economy import craft_gear_config as gear_cfg

    mode = payload.get("mode")
    live = _live_state(battle_id, battle)
    allies = sum(1 for c in live.values() if c.alive and c.side == combatant.side and c.id != cid)
    if await flask_throw.ask(_bot_api, "raid_item", peer_id, cid, "raid_use_item", elixir, mode, allies):
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        consumed = await elixir_service.consume(db, character.id, elixir_id)
        await db.commit()
    if not consumed:
        await message.answer("Этого зелья больше нет в сумке.", keyboard=battle_kb)
        return
    consumable_limit.spend(combatant)
    throw = mode == "throw" and flask_throw.can_throw(elixir) and await flask_throw.spend(cid)

    await editable_message.send_or_edit(
        _bot_api, "raid_item", peer_id, f"Использовано: {elixir.emoji} {elixir.name}.", no_keyboard()
    )

    if throw:
        line = elixir_effects.throw_flask(combatant, elixir_id, live, gear_cfg.FLASK_POWER)
        if elixir.category == "heal":
            consumable_limit.mark_heal(combatant)
        else:
            combatant.combat_elixirs_used += 1
        await _tell_others(battle, cid, f"{p.name}: {line}")
    # Лечебное зелье - тоже без траты хода (2026-10-14).
    elif elixir.category == "heal":
        before = combatant.current_hp
        line = elixir_effects.drink_heal(combatant, elixir_id)
        consumable_limit.mark_heal(combatant)
        await _tell_others(battle, cid, elixir_effects.heal_seen(combatant, p.name, combatant.current_hp - before))
    else:
        line = elixir_effects.apply_combat_elixir(combatant, elixir_id, _live_state(battle_id, battle))
        combatant.combat_elixirs_used += 1
        if elixir.category != "scroll":
            await _tell_others(battle, cid, elixir_effects.elixir_seen(p.name, elixir))
    if elixir.category == "scroll":
        await _tell_others(battle, cid, f"{p.name}: {line}")
    text = f"{line} Твой ход.\n\n{_render_board(_engine.sessions.get(battle_id))}"
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0,
        keyboard=_combat_keyboard(battle, p, combatant),
    )


async def _tell_others(battle, cid: int, text: str) -> None:
    """Свиток действует на всю сторону (или на всех врагов) - видеть это
    должны все в бою, а не только прочитавший."""
    for other_id, other in list(battle.participants.items()):
        if other_id == cid:
            continue
        try:
            await _bot_api.messages.send(peer_id=other.peer_id, message=text, random_id=0)
        except Exception:
            logger.warning("Свиток: не доставлено {}", other.peer_id)


# Нарезка (2026-10-22): этот блок живёт в bot.handlers.raid_results.
# Старые адреса (raid_combat.X в других модулях и тестах) работают через ссылку.
from bot.handlers.raid_results import (  # noqa: E402,F401
    PENDING_REWARD_LINE,
    RIFT_RAISED_HP_PCT,
    SAFE_EXIT_LINE,
    StageReward,
    _advance_or_finish,
    _auto_skip,
    _cleanup_and_return,
    _field_after_tick,
    _finish_victory,
    _finish_wipe,
    _grant_blood_chests,
    _grant_pending_rewards,
    _grant_rift_legendaries,
    _grant_stage_clear_bonus,
    _grant_stage_reward,
    _kill_random_survivor,
    _record_contribution,
    _rift_gold,
    _send_location_summary,
    _stage_rewards,
    on_raid_battle_finished,
    on_raid_tick_resolved,
    wipe,
)
