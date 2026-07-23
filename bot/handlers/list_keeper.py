"""Хранитель Списков вне онбординга (патч 12): выбор подкласса на 30 уровне
за золото ("Раскол пути") + список классовых испытаний после выбора.

FSM (vkbottle BaseStateGroup), персистентный шаг — characters.subclass_select_state
(тот же паттерн, что и creation_state в onboarding.py): переживает рестарт бота.
CONFIRM-подшаг при восстановлении откатывается к SELECT (выбор пути жил только
в памяти диспенсера).
"""

from vkbottle import BaseMiddleware, BaseStateGroup
from vkbottle.bot import BotLabeler, Message

from bot.keyboards.list_keeper import (
    BTN_CHOOSE_PATH,
    BTN_CONFIRM_PATH,
    BTN_LEAVE,
    BTN_OTHER_PATH,
    BTN_PAY,
    BTN_THINK_MORE,
    offer_keyboard,
    path_confirm_keyboard,
    path_view_keyboard,
    paths_keyboard,
)
from bot.keyboards.world import BTN_KEEPER, city_menu_keyboard
from game.classes.base import REGISTRY
from game.content_loader import load_npc_texts
from services import onboarding_service as onboarding_svc
from services import subclass_service, trial_service
from services.db import get_session_factory
from services.wallet_service import NotEnoughCurrency

labeler = BotLabeler()

_bot_api = None
_dispenser = None  # bot.state_dispenser, устанавливается в setup()

KEEPER = load_npc_texts("list_keeper")["subclass_select"]

STATE_OFFER = "subclass_offer"
STATE_PATH_SELECT = "subclass_path_select"
STATE_PATH_CONFIRM = "subclass_path_confirm"

# Все титулы подклассов сразу (across 3 базовых класса) — конкретный игрок
# видит только два своих, остальные тексты кнопок для него просто не появятся.
ALL_SUBCLASS_TITLES: dict[str, str] = {s.title: s.id for s in REGISTRY.values()}


class SubclassSelectState(BaseStateGroup):
    OFFER = STATE_OFFER
    PATH_SELECT = STATE_PATH_SELECT
    PATH_CONFIRM = STATE_PATH_CONFIRM


RESTORE_STATES = {
    STATE_OFFER: SubclassSelectState.OFFER,
    STATE_PATH_SELECT: SubclassSelectState.PATH_SELECT,
    STATE_PATH_CONFIRM: SubclassSelectState.PATH_SELECT,
}


def setup(bot) -> None:
    global _bot_api, _dispenser
    _bot_api = bot.api
    _dispenser = bot.state_dispenser
    bot.labeler.message_view.register_middleware(SubclassRestoreMiddleware)


class SubclassRestoreMiddleware(BaseMiddleware[Message]):
    """После рестарта бота возвращает игрока на его шаг «Раскола пути» из БД."""

    async def pre(self) -> None:
        if _dispenser is None:
            return
        if await _dispenser.get(self.event.peer_id) is not None:
            return
        async with get_session_factory()() as db:
            character = await onboarding_svc.get_character(db, self.event.from_id)
            state_str = character.subclass_select_state if character else None
        if state_str in RESTORE_STATES:
            await _dispenser.set(self.event.peer_id, RESTORE_STATES[state_str])


async def _set_select_state(db, character, state: str | None) -> None:
    character.subclass_select_state = state
    await db.flush()


async def _send_trials(peer_id: int, character) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None:
            return
        states = await trial_service.get_trial_states(db, character)

    remaining = [s for s in states if not s.unlocked]
    opened = [s for s in states if s.unlocked]
    if not remaining:
        text = KEEPER["trials_all_done"]
    else:
        lines = [KEEPER["trials_header"], ""]
        for s in remaining:
            lines.append(
                KEEPER["trial_entry_locked"].format(
                    buff_name=s.buff_name, progress=s.progress, target=s.target, text=s.trial.text,
                )
            )
        if opened:
            lines.append("")
            lines.append("Открыто:")
            for s in opened:
                lines.append(KEEPER["trial_entry_open"].format(buff_name=s.buff_name))
        text = "\n".join(lines)
    await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, keyboard=city_menu_keyboard(character))


@labeler.message(text=[BTN_KEEPER])
async def open_keeper(message: Message) -> None:
    peer_id = message.peer_id
    has_subclass = False
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if character.subclass is not None:
            has_subclass = True
        elif not subclass_service.can_offer(character):
            await message.answer(KEEPER["too_low_level"])
            return
        else:
            await _set_select_state(db, character, STATE_OFFER)
            await db.commit()
            await _dispenser.set(peer_id, SubclassSelectState.OFFER)
            await message.answer(
                KEEPER["offer"].format(nickname=character.name), keyboard=offer_keyboard()
            )
            return

    if has_subclass:
        await _send_trials(peer_id, character)


@labeler.message(state=SubclassSelectState.OFFER, text=[BTN_PAY])
async def offer_pay(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None or character.subclass is not None:
            return
        try:
            await subclass_service.pay_unlock(db, character)
        except NotEnoughCurrency:
            await message.answer(KEEPER["not_enough_gold"], keyboard=offer_keyboard())
            return
        await _set_select_state(db, character, STATE_PATH_SELECT)
        await db.commit()
        base_class = character.base_class

    titles = [s.title for s in subclass_service.paths_for(base_class)]
    await _dispenser.set(peer_id, SubclassSelectState.PATH_SELECT)
    await message.answer(KEEPER["path_intro"], keyboard=paths_keyboard(titles))


@labeler.message(state=SubclassSelectState.OFFER, text=[BTN_LEAVE])
async def offer_leave(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        await _set_select_state(db, character, None)
        await db.commit()
    await _dispenser.delete(message.peer_id)
    await message.answer("Хорошо. Возвращайся, когда будешь готов.", keyboard=city_menu_keyboard(character))


@labeler.message(state=SubclassSelectState.OFFER)
async def offer_fallback(message: Message) -> None:
    await message.answer(KEEPER["offer"].format(nickname=""), keyboard=offer_keyboard())


@labeler.message(state=SubclassSelectState.PATH_SELECT, text=list(ALL_SUBCLASS_TITLES))
async def path_view(message: Message) -> None:
    peer_id = message.peer_id
    subclass_id = ALL_SUBCLASS_TITLES[message.text]
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.subclass is not None:
            return
        valid_ids = {s.id for s in subclass_service.paths_for(character.base_class)}
        if subclass_id not in valid_ids:
            return  # чужой путь (не для базового класса игрока) — молча игнорируем
        base_class = character.base_class

    await _dispenser.set(
        peer_id, SubclassSelectState.PATH_CONFIRM, pending_subclass=subclass_id
    )
    await message.answer(
        KEEPER["path_descriptions"][subclass_id], keyboard=path_view_keyboard()
    )


@labeler.message(state=SubclassSelectState.PATH_SELECT)
async def path_select_fallback(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        titles = [s.title for s in subclass_service.paths_for(character.base_class)]
    await message.answer(KEEPER["path_intro"], keyboard=paths_keyboard(titles))


@labeler.message(state=SubclassSelectState.PATH_CONFIRM, text=[BTN_CHOOSE_PATH])
async def path_choose(message: Message) -> None:
    if not (message.state_peer and message.state_peer.payload.get("pending_subclass")):
        await _back_to_path_select(message)
        return
    await message.answer(KEEPER["path_confirm_question"], keyboard=path_confirm_keyboard())


@labeler.message(state=SubclassSelectState.PATH_CONFIRM, text=[BTN_CONFIRM_PATH])
async def path_confirm(message: Message) -> None:
    payload = message.state_peer.payload if message.state_peer else {}
    subclass_id = payload.get("pending_subclass")
    if subclass_id is None:
        await _back_to_path_select(message)
        return

    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.subclass is not None:
            return
        subclass_service.apply_subclass(character, subclass_id)
        await _set_select_state(db, character, None)
        await db.commit()
        title = next(s.title for s in REGISTRY.values() if s.id == subclass_id)

    await _dispenser.delete(peer_id)
    await message.answer(KEEPER["confirmed"].format(subclass=title))
    await _send_trials(peer_id, character)


@labeler.message(
    state=SubclassSelectState.PATH_CONFIRM, text=[BTN_OTHER_PATH, BTN_THINK_MORE]
)
async def path_back(message: Message) -> None:
    await _back_to_path_select(message)


@labeler.message(state=SubclassSelectState.PATH_CONFIRM)
async def path_confirm_fallback(message: Message) -> None:
    await message.answer(KEEPER["path_confirm_question"], keyboard=path_confirm_keyboard())


async def _back_to_path_select(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        await _set_select_state(db, character, STATE_PATH_SELECT)
        await db.commit()
        titles = [s.title for s in subclass_service.paths_for(character.base_class)]
    await _dispenser.set(message.peer_id, SubclassSelectState.PATH_SELECT)
    await message.answer(KEEPER["path_relisten"], keyboard=paths_keyboard(titles))
