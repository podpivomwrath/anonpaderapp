"""Групповые события исследования: рассылка, выборы, таймер, итог.

Каждый участник видит сцену в своём диалоге и выбирает своей кнопкой. Выбор
окончательный. Итог - когда выбрали все или вышел таймер (кто не успел,
выбрал вариант по умолчанию, см. group_events.default_choice). Итог всем
одинаковый (кто что выбрал), плюс у каждого своя строка награды.

Гнездо и осада идут в несколько раундов: после итога раунда те, кто
продолжает, получают следующий; закончившие - сводку клетки.

Висящее событие - в памяти процесса, как у соло-событий: рестарт бота его
теряет, кнопки просто перестают отвечать. Логика исходов -
game/world/group_events.py, награды - services/scene_event_service.py.
"""

import asyncio
import itertools
import random
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot.activity import ActivityBusy
from bot.handlers import scene_events as scene_event_handlers
from bot.keyboards.world import waiting_keyboard
from bot.vk_media import photo_attachment
from game.world import group_events as ge
from models import Character, CharacterStats
from services import death_service, scene_event_service, wallet_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
_rng = random.Random()
_tokens = itertools.count(1)


@dataclass
class Member:
    character_id: int
    peer_id: int
    name: str


@dataclass
class GroupScene:
    token: int
    group_id: int
    event_id: str
    members: dict[int, Member]
    leader_id: int | None
    region: str
    dist: int
    cell: tuple[int, int]
    victim_id: int | None = None
    state: dict = field(default_factory=dict)
    choices: dict[int, str | None] = field(default_factory=dict)
    resolving: bool = False
    task: asyncio.Task | None = None

    @property
    def event(self) -> ge.GroupEvent:
        return ge.event_by_id(self.event_id)

    def options(self, cid: int) -> list[tuple[str, str]]:
        return ge.choices_of(self.event, cid, self.victim_id, self.state, len(self.members))

    def deciders(self) -> list[int]:
        """Кому есть что выбирать в этом раунде."""
        return [cid for cid in self.members if self.options(cid)]


_scenes: dict[int, GroupScene] = {}


def has_group_event(group_id: int) -> bool:
    return group_id in _scenes


def _api():
    from bot.handlers import world as world_handlers  # цикл импортов

    return world_handlers._bot_api


async def _send(peer_id: int, text: str, keyboard: str | None = None, attachment: str | None = None) -> None:
    try:
        await _api().messages.send(
            peer_id=peer_id, message=text, random_id=0, keyboard=keyboard, attachment=attachment,
        )
    except Exception:
        logger.exception("Групповое событие: не удалось написать {}", peer_id)


def _keyboard(scene: GroupScene, cid: int) -> str:
    options = scene.options(cid)
    if not options:
        return waiting_keyboard()
    kb = Keyboard(one_time=False)
    for value, label in options:
        kb.add(
            Text(scene_event_handlers._label(label), payload={"type": "gscene", "t": scene.token, "v": value}),
            color=KeyboardButtonColor.PRIMARY,
        )
        kb.row()
    if kb.buttons and not kb.buttons[-1]:
        kb.buttons.pop()
    return kb.get_json()


async def maybe_start(db, group_id: int, leader_id: int | None, cohort: list[Character],
                      region: str, dist: int, ring: int, rng: random.Random) -> bool:
    """Бросок «событие вместо боя». True - событие началось, бой не нужен."""
    if has_group_event(group_id) or rng.random() >= ge.GROUP_EVENT_CHANCE:
        return False
    event = ge.pick_event(rng, ring, region, len(cohort))
    if event is None:
        return False
    members = {}
    for c in cohort:
        peer_id = await onboarding_svc.vk_id_for_character(db, c.id)
        if peer_id is not None:
            members[c.id] = Member(c.id, peer_id, c.name)
    if len(members) < event.min_members:
        return False
    await db.commit()
    await start(group_id, event, members, leader_id, region, dist, (cohort[0].pos_x, cohort[0].pos_y))
    return True


async def start(group_id: int, event: ge.GroupEvent, members: dict[int, Member], leader_id: int | None,
                region: str, dist: int, cell: tuple[int, int]) -> None:
    scene = GroupScene(
        token=next(_tokens), group_id=group_id, event_id=event.id, members=members,
        leader_id=leader_id, region=region, dist=dist, cell=cell,
        state=ge.initial_state(event, list(members)),
    )
    if event.mechanic == "rescue":
        scene.victim_id = _rng.choice(sorted(members))
    _scenes[group_id] = scene

    attachment = photo_attachment(event.image) if event.image else None
    victim = members.get(scene.victim_id) if scene.victim_id is not None else None
    for cid, m in members.items():
        parts = [event.title, event.text]
        if event.mechanic == "siege":
            parts.append(ge.round_prompt(event, scene.state))
        if victim is not None:
            parts.append(event.victim_text if cid == victim.character_id else f"В трясине: {victim.name}.")
        parts.append(f"⏱ {ge.DECISION_SECONDS} сек. Решают все.")
        await _send(m.peer_id, "\n\n".join(parts), _keyboard(scene, cid), attachment)
    _arm_timer(scene)


def _arm_timer(scene: GroupScene) -> None:
    scene.task = asyncio.get_running_loop().create_task(_timer(scene.group_id, scene.token))


async def _timer(group_id: int, token: int) -> None:
    try:
        await asyncio.sleep(ge.DECISION_SECONDS)
    except asyncio.CancelledError:
        return
    scene = _scenes.get(group_id)
    if scene is None or scene.token != token:
        return
    scene.task = None
    await _resolve(scene)


@labeler.message(payload_contains={"type": "gscene"})
async def on_choice(message: Message) -> None:
    payload = message.get_payload_json() or {}
    token, value = payload.get("t"), payload.get("v")
    scene = next((s for s in _scenes.values() if s.token == token), None)
    if scene is None or scene.resolving:
        await message.answer("Это решение уже принято.", keyboard=waiting_keyboard())
        return
    cid = next((c for c, m in scene.members.items() if m.peer_id == message.peer_id), None)
    if cid is None:
        return
    options = dict(scene.options(cid))
    if value not in options:
        return
    if cid in scene.choices:
        await message.answer("Ты уже выбрал. Ждём остальных.", keyboard=waiting_keyboard())
        return
    scene.choices[cid] = value
    deciders = scene.deciders()
    done = sum(1 for c in deciders if c in scene.choices)
    await message.answer(
        f"Выбор принят: {options[value]}. Ждём остальных ({done}/{len(deciders)}).",
        keyboard=waiting_keyboard(),
    )
    if done >= len(deciders):
        if scene.task is not None:
            scene.task.cancel()
            scene.task = None
        await _resolve(scene)


async def _resolve(scene: GroupScene) -> None:
    if scene.resolving:
        return
    scene.resolving = True
    continues = False
    try:
        continues = await _finish(scene)
    except Exception:
        logger.exception("Групповое событие {} упало на итоге", scene.event_id)
        for m in scene.members.values():
            await _send(m.peer_id, "Что-то пошло не так - событие прервалось.", waiting_keyboard())
            await scene_event_handlers._epilogue(m.peer_id, [], None)
    finally:
        if continues:
            scene.resolving = False
        elif _scenes.get(scene.group_id) is scene:
            _scenes.pop(scene.group_id, None)


async def _finish(scene: GroupScene) -> bool:
    """Итог раунда. True - событие продолжается следующим раундом."""
    event = scene.event
    default = ge.default_choice(event)
    deciders = set(scene.deciders())
    choices = {cid: scene.choices.get(cid, default if cid in deciders else None) for cid in scene.members}
    names = {cid: m.name for cid, m in scene.members.items()}

    personal: dict[int, list[str]] = {cid: [] for cid in scene.members}
    applied_by: dict[int, object] = {}
    fighters: list[int] = []
    async with get_session_factory()() as db:
        loaded = {}
        for cid in scene.members:
            character = await db.get(Character, cid)
            if character is None or death_service.is_dead(character):
                continue
            stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == cid))
            loaded[cid] = (character, stats)

        if event.mechanic == "pot":
            # Ставка, которую уже нечем оплатить, - не ставка: это видно
            # всем в итоге, а котёл не платит за то, чего не получил.
            stakes = {s.id: s for s in event.stakes}
            for cid, value in list(choices.items()):
                stake = stakes.get(value)
                if stake is None or stake.gold <= 0:
                    continue
                if cid not in loaded:
                    choices[cid] = ge.NO_STAKE
                    continue
                wallet = await wallet_service.get_wallet(db, cid)
                if wallet.farm_currency < scene_event_service.gold_amount(loaded[cid][0], stake.gold):
                    choices[cid] = ge.NO_STAKE
                    personal[cid].append("Денег на эту ставку уже нет - котёл тебя не взял.")

        outcome = ge.resolve(event, names, choices, _rng, scene.leader_id, scene.victim_id, scene.state)

        for cid, units in outcome.charges.items():
            if cid not in loaded:
                continue
            try:
                await wallet_service.charge(db, cid, "farm", scene_event_service.gold_amount(loaded[cid][0], units))
            except wallet_service.NotEnoughCurrency:
                # Успел потратить, пока решали: ставка сгорает без выплаты.
                outcome.results.pop(cid, None)
                personal[cid].append("Денег на ставку уже не хватило.")

        for cid, (character, stats) in loaded.items():
            result = outcome.results.get(cid)
            if result is not None:
                result = ge.scale(result) if outcome.scaled else result
                applied = await scene_event_service.apply_result(db, character, stats, result, _rng)
                if not outcome.next_round or cid not in outcome.active:
                    await scene_event_service.finish_event(db, character, applied)
                personal[cid] += applied.lines
                applied_by[cid] = applied
            if (character.pos_x, character.pos_y) == scene.cell:
                fighters.append(cid)
        await db.commit()

    summary = "\n".join(outcome.summary)
    for cid, m in scene.members.items():
        text = "\n\n".join(part for part in (event.title, summary, "\n".join(personal[cid])) if part)
        await _send(m.peer_id, text, waiting_keyboard())
        await scene_event_handlers._notify(m.peer_id, applied_by.get(cid))

    if outcome.next_round:
        done = [cid for cid in scene.members if cid not in outcome.active]
        for cid in done:
            await scene_event_handlers._epilogue(scene.members[cid].peer_id, [], None)
        scene.members = {cid: m for cid, m in scene.members.items() if cid in outcome.active}
        scene.state = outcome.state
        scene.choices = {}
        scene.token = next(_tokens)
        prompt = ge.round_prompt(event, scene.state)
        for cid, m in scene.members.items():
            await _send(m.peer_id, f"{prompt}\n\n⏱ {ge.DECISION_SECONDS} сек.", _keyboard(scene, cid))
        _arm_timer(scene)
        return True

    if outcome.combat and await _start_ambush(scene, fighters):
        return False
    for m in scene.members.values():
        await scene_event_handlers._epilogue(m.peer_id, [], None)
    return False


async def _start_ambush(scene: GroupScene, fighter_ids: list[int]) -> bool:
    """Засада: групповой бой для тех, кто ещё стоит на клетке события."""
    from bot.handlers import group_combat as group_combat_handlers

    if not fighter_ids:
        return False
    try:
        async with get_session_factory()() as db:
            fighters = [await db.get(Character, cid) for cid in fighter_ids]
            fighters = [c for c in fighters if c is not None]
            await group_combat_handlers.start_ready_group(
                db, scene.group_id, fighters, scene.region, scene.dist, _rng,
            )
    except ActivityBusy:
        return False
    # Кто ушёл с клетки, в бой не попал - ему просто сводка локации.
    for cid, m in scene.members.items():
        if cid not in fighter_ids:
            await scene_event_handlers._epilogue(m.peer_id, [], None)
    return True
