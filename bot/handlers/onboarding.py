"""Сюжетный онбординг: Хранитель Списков ведёт создание персонажа.

FSM (vkbottle BaseStateGroup): NICKNAME_INPUT → CLASS_SELECT → CLASS_CONFIRM →
REGION_SELECT → REGION_CONFIRM → DONE. Сцена пробуждения показывается по /start
без кнопки — сразу ожидание никнейма.

Истинный прогресс — в БД (characters.creation_state); CreationRestoreMiddleware
восстанавливает состояние диспенсера после рестарта. Шаги *_CONFIRM при
восстановлении откатываются к *_SELECT (выбранная кнопка жила в памяти).

Внутри CLASS_CONFIRM/REGION_CONFIRM два подшага, различаются кнопками:
описание пути → «Выбрать этот путь» → «— Уверен? Кровь запомнит.» → «Да, это
мой путь». Отдельное состояние не требуется — тексты кнопок уникальны.
"""

from vkbottle import BaseMiddleware, BaseStateGroup
from vkbottle.bot import BotLabeler, Message

from bot import onboarding_texts as texts
from bot.keyboards.onboarding import (
    begin_keyboard,
    classes_keyboard,
    empty_keyboard,
    path_confirm_keyboard,
    path_view_keyboard,
    region_confirm_keyboard,
    region_view_keyboard,
    regions_keyboard,
)
from bot.keyboards.world import city_menu_keyboard
from services import onboarding_service as svc
from services.db import get_session_factory

# Мир (город/карта) подключается ПОСЛЕ создания персонажа — импорт handler-модуля,
# а не сервиса, т.к. нужен show_location для полного контекста (город/клетка/в
# пути/мёртв). Однонаправленно: world.py onboarding.py не импортирует.
from bot.handlers import world as world_handlers

labeler = BotLabeler()

_dispenser = None  # bot.state_dispenser, устанавливается в setup()

KEEPER = texts.KEEPER


class CreationState(BaseStateGroup):
    NICKNAME_INPUT = svc.STATE_NICKNAME
    CLASS_SELECT = svc.STATE_CLASS_SELECT
    CLASS_CONFIRM = svc.STATE_CLASS_CONFIRM
    REGION_SELECT = svc.STATE_REGION_SELECT
    REGION_CONFIRM = svc.STATE_REGION_CONFIRM


# DB-состояние → состояние диспенсера при восстановлении (confirm → select;
# lore_intro — легаси старого флоу, теперь это ввод никнейма)
RESTORE_STATES = {
    svc.STATE_LORE: CreationState.NICKNAME_INPUT,
    svc.STATE_NICKNAME: CreationState.NICKNAME_INPUT,
    svc.STATE_CLASS_SELECT: CreationState.CLASS_SELECT,
    svc.STATE_CLASS_CONFIRM: CreationState.CLASS_SELECT,
    svc.STATE_REGION_SELECT: CreationState.REGION_SELECT,
    svc.STATE_REGION_CONFIRM: CreationState.REGION_SELECT,
}


def setup(bot) -> None:
    """Вызывается из main.create_bot: привязка диспенсера и middleware."""
    global _dispenser
    _dispenser = bot.state_dispenser
    bot.labeler.message_view.register_middleware(CreationRestoreMiddleware)


class CreationRestoreMiddleware(BaseMiddleware[Message]):
    """После рестарта бота возвращает игрока на его шаг создания из БД."""

    async def pre(self) -> None:
        if _dispenser is None:
            return
        if await _dispenser.get(self.event.peer_id) is not None:
            return
        async with get_session_factory()() as db:
            character = await svc.get_character(db, self.event.from_id)
            state_str = character.creation_state if character else None
        if state_str in RESTORE_STATES:
            await _dispenser.set(self.event.peer_id, RESTORE_STATES[state_str])


async def _resume(message: Message, state_str: str) -> None:
    """Продолжение с сохранённого шага (в т.ч. по повторному /start)."""
    state = RESTORE_STATES[state_str]
    await _dispenser.set(message.peer_id, state)
    if state == CreationState.NICKNAME_INPUT:
        await message.answer(
            KEEPER["scene_awakening"],
            attachment=texts.scene_attachment("scene_awakening"),
            keyboard=empty_keyboard(),
        )
    elif state == CreationState.CLASS_SELECT:
        await message.answer(KEEPER["class_relisten"], keyboard=classes_keyboard())
    else:
        await message.answer(KEEPER["region_relisten"], keyboard=regions_keyboard())


# --- /start ---


@labeler.message(text=["/start", "start", "Начать", "начать"])
async def handle_start(message: Message) -> None:
    async with get_session_factory()() as db:
        user = await svc.get_or_create_user(db, message.from_id)
        character = await svc.get_character(db, message.from_id)
        if character is None:
            await svc.begin_creation(db, user)
            await db.commit()
            await _dispenser.set(message.peer_id, CreationState.NICKNAME_INPUT)
            await message.answer(
                KEEPER["scene_awakening"],
                attachment=texts.scene_attachment("scene_awakening"),
                keyboard=empty_keyboard(),
            )
            return
        if character.creation_state is None:
            await db.commit()
            await message.answer(f"С возвращением, {character.name}!")
            await world_handlers.show_location(message, db, character)
            return
        await db.commit()
        state_str = character.creation_state
    await _resume(message, state_str)


# --- Сцена 1-2: пробуждение и никнейм ---


@labeler.message(state=CreationState.NICKNAME_INPUT)
async def nickname_input(message: Message) -> None:
    nickname = (message.text or "").strip()
    async with get_session_factory()() as db:
        character = await svc.get_character(db, message.from_id)
        error = await svc.try_set_nickname(db, character, nickname)
        await db.commit()
    if error is not None:
        await message.answer(texts.NICKNAME_ERRORS[error])
        return
    await _dispenser.set(message.peer_id, CreationState.CLASS_SELECT)
    await message.answer(
        KEEPER["scene_blood_test"].format(nickname=nickname),
        attachment=texts.scene_attachment("scene_blood_test"),
        keyboard=classes_keyboard(),
    )


# --- Сцена 3: проверка крови (класс) ---


@labeler.message(state=CreationState.CLASS_SELECT, text=list(texts.CLASS_BUTTONS))
async def class_view(message: Message) -> None:
    class_id = texts.CLASS_BUTTONS[message.text]
    async with get_session_factory()() as db:
        character = await svc.get_character(db, message.from_id)
        await svc.set_state(db, character, svc.STATE_CLASS_CONFIRM)
        await db.commit()
    await _dispenser.set(
        message.peer_id, CreationState.CLASS_CONFIRM, pending_class=class_id
    )
    await message.answer(
        KEEPER["class_paths"][class_id], keyboard=path_view_keyboard()
    )


@labeler.message(state=CreationState.CLASS_SELECT)
async def class_select_fallback(message: Message) -> None:
    await message.answer(KEEPER["class_relisten"], keyboard=classes_keyboard())


@labeler.message(state=CreationState.CLASS_CONFIRM, text=[texts.BTN_CHOOSE_PATH])
async def class_choose_path(message: Message) -> None:
    if not (message.state_peer and message.state_peer.payload.get("pending_class")):
        await _back_to_class_select(message)
        return
    await message.answer(
        KEEPER["class_confirm_question"], keyboard=path_confirm_keyboard()
    )


@labeler.message(state=CreationState.CLASS_CONFIRM, text=[texts.BTN_CONFIRM_PATH])
async def class_confirm(message: Message) -> None:
    payload = message.state_peer.payload if message.state_peer else {}
    class_id = payload.get("pending_class")
    if class_id is None:  # выбор потерян (рестарт) — назад к узорам
        await _back_to_class_select(message)
        return
    async with get_session_factory()() as db:
        character = await svc.get_character(db, message.from_id)
        await svc.apply_class(db, character, class_id)
        await db.commit()
    await _dispenser.set(message.peer_id, CreationState.REGION_SELECT)
    await message.answer(KEEPER["class_confirmed"])
    await message.answer(
        KEEPER["scene_four_roads"],
        attachment=texts.scene_attachment("scene_four_roads"),
        keyboard=regions_keyboard(),
    )


@labeler.message(
    state=CreationState.CLASS_CONFIRM, text=[texts.BTN_OTHER_PATHS, texts.BTN_THINK_MORE]
)
async def class_back(message: Message) -> None:
    await _back_to_class_select(message)


@labeler.message(state=CreationState.CLASS_CONFIRM)
async def class_confirm_fallback(message: Message) -> None:
    await message.answer(KEEPER["class_confirm_question"], keyboard=path_confirm_keyboard())


async def _back_to_class_select(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await svc.get_character(db, message.from_id)
        await svc.set_state(db, character, svc.STATE_CLASS_SELECT)
        await db.commit()
    await _dispenser.set(message.peer_id, CreationState.CLASS_SELECT)
    await message.answer(KEEPER["class_relisten"], keyboard=classes_keyboard())


# --- Сцена 4: четыре дороги (регион) ---


@labeler.message(state=CreationState.REGION_SELECT, text=list(texts.REGION_BUTTONS))
async def region_view(message: Message) -> None:
    region_id = texts.REGION_BUTTONS[message.text]
    async with get_session_factory()() as db:
        character = await svc.get_character(db, message.from_id)
        await svc.set_state(db, character, svc.STATE_REGION_CONFIRM)
        await db.commit()
    await _dispenser.set(
        message.peer_id, CreationState.REGION_CONFIRM, pending_region=region_id
    )
    await message.answer(
        KEEPER["regions"][region_id],
        attachment=texts.region_attachment(region_id),
        keyboard=region_view_keyboard(),
    )


@labeler.message(state=CreationState.REGION_SELECT)
async def region_select_fallback(message: Message) -> None:
    await message.answer(KEEPER["region_relisten"], keyboard=regions_keyboard())


@labeler.message(state=CreationState.REGION_CONFIRM, text=[texts.BTN_GO_REGION])
async def region_go(message: Message) -> None:
    if not (message.state_peer and message.state_peer.payload.get("pending_region")):
        await _back_to_region_select(message)
        return
    await message.answer(
        KEEPER["region_confirm_question"], keyboard=region_confirm_keyboard()
    )


@labeler.message(state=CreationState.REGION_CONFIRM, text=[texts.BTN_YES, "да"])
async def region_confirm(message: Message) -> None:
    payload = message.state_peer.payload if message.state_peer else {}
    region_id = payload.get("pending_region")
    if region_id is None:
        await _back_to_region_select(message)
        return
    async with get_session_factory()() as db:
        character = await svc.get_character(db, message.from_id)
        stats = await svc.complete_creation(db, character, region_id)
        final = texts.final_message(character.name, character.base_class, region_id, stats)
        await db.commit()
    try:
        await _dispenser.delete(message.peer_id)
    except (KeyError, LookupError):
        pass
    await message.answer(final, keyboard=begin_keyboard())


@labeler.message(
    state=CreationState.REGION_CONFIRM, text=[texts.BTN_OTHER_ROADS, texts.BTN_THINK_MORE]
)
async def region_back(message: Message) -> None:
    await _back_to_region_select(message)


@labeler.message(state=CreationState.REGION_CONFIRM)
async def region_confirm_fallback(message: Message) -> None:
    await message.answer(
        KEEPER["region_confirm_question"], keyboard=region_confirm_keyboard()
    )


async def _back_to_region_select(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await svc.get_character(db, message.from_id)
        await svc.set_state(db, character, svc.STATE_REGION_SELECT)
        await db.commit()
    await _dispenser.set(message.peer_id, CreationState.REGION_SELECT)
    await message.answer(KEEPER["region_relisten"], keyboard=regions_keyboard())


# --- Сцена 5: «Ступить на путь →» (вне FSM — создание уже завершено) ---


@labeler.message(text=[texts.BTN_BEGIN])
async def begin_journey(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await svc.get_character(db, message.from_id)
        if character is None or character.region is None:
            return
        await message.answer(
            f"Ты в городе: {texts.REGION_TITLES[character.region]}",
            keyboard=city_menu_keyboard(character),
        )
