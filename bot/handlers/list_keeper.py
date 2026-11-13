"""Хранитель Списков вне онбординга (патч 12): выбор подкласса на 30 уровне
за золото ("Раскол пути") + список классовых испытаний после выбора.

FSM (vkbottle BaseStateGroup), персистентный шаг — characters.subclass_select_state
(тот же паттерн, что и creation_state в onboarding.py): переживает рестарт бота.
CONFIRM-подшаг при восстановлении откатывается к SELECT (выбор пути жил только
в памяти диспенсера).
"""

from sqlalchemy import select
from vkbottle import BaseMiddleware, BaseStateGroup
from vkbottle.bot import BotLabeler, Message

from bot.keyboards.list_keeper import (
    BTN_CANCEL_PATH,
    BTN_CHOOSE_PATH,
    BTN_CONFIRM_PATH,
    BTN_DECLINE,
    BTN_DECLINE_CONFIRM,
    BTN_KEEPER_LEAVE,
    BTN_LEAVE,
    BTN_OTHER_PATH,
    BTN_PAY,
    BTN_PAY_OLD,
    BTN_REMAKE,
    BTN_REMAKE_CANCEL,
    BTN_REMAKE_CLASS,
    BTN_REMAKE_CONFIRM,
    BTN_REMAKE_STATS,
    BTN_REMAKE_SUBCLASS,
    BTN_THINK_MORE,
    base_class_keyboard,
    decline_confirm_keyboard,
    offer_keyboard,
    path_confirm_keyboard,
    path_view_keyboard,
    paths_keyboard,
    remake_confirm_keyboard,
    remake_keyboard,
    trials_keyboard,
)
from bot.keyboards.world import BTN_KEEPER, tavern_keyboard
from bot.vk_media import photo_attachment
from bot.onboarding_texts import CLASS_BUTTONS
from bot.world_texts import FOREIGN_NPC_REJECTION, mentor_name
from bot import text_match
from game.classes.base import REGISTRY
from game.combat import balance_config as bc
from game.combat import display
from game.content_loader import load_npc_texts
from game.world import grid
from models import CharacterStats
from services import onboarding_service as onboarding_svc
from services import (
    respec_service,
    screen_service,
    story_service,
    subclass_service,
    trial_service,
    wallet_service,
)
from services.db import get_session_factory
from services.wallet_service import NotEnoughCurrency

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»

_bot_api = None
_dispenser = None  # bot.state_dispenser, устанавливается в setup()

_KEEPER_NPC = load_npc_texts("list_keeper")
KEEPER = _KEEPER_NPC["subclass_select"]
KEEPER_ATTACHMENT = photo_attachment(_KEEPER_NPC["image"]) if _KEEPER_NPC.get("image") else None


def path_attachment(subclass_id: str) -> str | None:
    """Иллюстрация пути - там, где игрок читает про него целиком и ещё может
    передумать. Пустой id означает, что картинки пока нет: сообщение уйдёт
    без вложения, как уходило до сих пор."""
    photo_id = KEEPER.get("path_images", {}).get(subclass_id)
    return photo_attachment(photo_id) if photo_id else None

STATE_OFFER = "subclass_offer"
STATE_PATH_SELECT = "subclass_path_select"
#: Повторный выбор пути после смены класса/подкласса (временно бесплатно).
FREE_REPICK_LINE = "Вы уже платили за путь. После смены класса новый выбирается без платы."
PAID_KEPT_LINE = "Плата за путь сохранится: при следующем разговоре Хранитель сразу предложит выбор."
STATE_PATH_CONFIRM = "subclass_path_confirm"
#: Заплатил и ушёл с выбора пути кнопкой «Отменить» (2026-11-13). Не в
#: RESTORE_STATES: иначе после рестарта игрока снова заперло бы в выборе.
#: Хранитель по нему сразу ведёт к выбору, без второй платы (баг 246).
STATE_PATH_PAID = "subclass_path_paid"
#: С 2026-11-13 (владелец) 20 000 списываются только на «Да, это мой путь».
#: Раньше - на входе в выбор, и записанные тогда PATH_SELECT / PATH_CONFIRM
#: в базе значат «уже заплатил»: новый поток эти строки в базу не пишет.
PAID_STATES = (STATE_PATH_SELECT, STATE_PATH_CONFIRM, STATE_PATH_PAID)


def _paid(character) -> bool:
    return character.subclass_select_state in PAID_STATES


def _can_decline(character) -> bool:
    """Отказ от пути - пока за него не заплачено: после оплаты он сжёг бы золото."""
    return subclass_service.free_repick(character) or not _paid(character)


def _price_line(character) -> str:
    if _paid(character) or subclass_service.free_repick(character):
        return ""
    cost = f"{bc.SUBCLASS_UNLOCK_COST:,}".replace(",", " ")
    return f"\n\nПосле подтверждения спишется {cost} золота."
# Отказ от подкласса (2026-10-20): подтверждение живёт в памяти, после
# рестарта игрок вернётся на прежний шаг (предложение или выбор пути).
STATE_DECLINE_CONFIRM = "subclass_decline_confirm"
# Переделка персонажа (альфа-тест). В characters.subclass_select_state НЕ
# сохраняется: сцена короткая, и после рестарта бота безопаснее начать её
# заново, чем восстановить игрока посреди необратимого действия.
STATE_REMAKE_MENU = "remake_menu"
STATE_REMAKE_CLASS = "remake_class_select"
STATE_REMAKE_CONFIRM = "remake_confirm"

# Все титулы подклассов сразу (across 3 базовых класса) — конкретный игрок
# видит только два своих, остальные тексты кнопок для него просто не появятся.
ALL_SUBCLASS_TITLES: dict[str, str] = {s.title: s.id for s in REGISTRY.values()}


class SubclassSelectState(BaseStateGroup):
    OFFER = STATE_OFFER
    PATH_SELECT = STATE_PATH_SELECT
    REMAKE_MENU = STATE_REMAKE_MENU
    REMAKE_CLASS = STATE_REMAKE_CLASS
    REMAKE_CONFIRM = STATE_REMAKE_CONFIRM
    PATH_CONFIRM = STATE_PATH_CONFIRM
    DECLINE_CONFIRM = STATE_DECLINE_CONFIRM


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
        # Патч 39: Хранитель Списков живёт в Таверне — назад из его окна
        # возвращает туда, не сразу на площадь.
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()

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
    await _bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0,
        keyboard=trials_keyboard(), attachment=KEEPER_ATTACHMENT,
    )


@labeler.message(text=[BTN_KEEPER])
async def open_keeper(message: Message) -> None:
    peer_id = message.peer_id
    has_subclass = False
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is not None and region != character.region:
            await message.answer(FOREIGN_NPC_REJECTION)  # патч 26: чужой город
            return
        if character.subclass is not None:
            has_subclass = True
        elif subclass_service.declined(character):
            has_subclass = True  # испытания пути - как у подкласса
        elif not subclass_service.can_offer(character):
            await message.answer(KEEPER["too_low_level"])
            return
        elif subclass_service.free_repick(character) or _paid(character):
            # После смены класса/подкласса - сразу к выбору пути, без платы.
            # Уже заплатил, но путь не выбрал (ушёл, рестарт) - тоже сюда:
            # раньше Хранитель снова просил 20 000 (баг 246, 2026-10-30).
            titles = [s.title for s in subclass_service.paths_for(character.base_class)]
            await _dispenser.set(peer_id, SubclassSelectState.PATH_SELECT)
            repick = subclass_service.free_repick(character)
            line = FREE_REPICK_LINE if repick else "Плата уже внесена, осталось выбрать путь."
            await message.answer(
                f"{line}\n\n{KEEPER['path_intro']}", keyboard=paths_keyboard(titles, decline=repick),
                attachment=KEEPER_ATTACHMENT,
            )
            return
        else:
            await _set_select_state(db, character, STATE_OFFER)
            await db.commit()
            await _dispenser.set(peer_id, SubclassSelectState.OFFER)
            await message.answer(
                KEEPER["offer"].format(nickname=character.name), keyboard=offer_keyboard(),
                attachment=KEEPER_ATTACHMENT,
            )
            return

    if has_subclass:
        await _send_trials(peer_id, character)


@labeler.message(state=SubclassSelectState.OFFER, text=[BTN_PAY, BTN_PAY_OLD])
async def offer_pay(message: Message) -> None:
    """К выбору пути. Золото только проверяется: списывается оно на «Да, это
    мой путь» (2026-11-13, владелец), чтобы уйти с выбора можно было даром."""
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None or character.subclass is not None:
            return
        gold = (await wallet_service.get_wallet(db, character.id)).farm_currency
        if not subclass_service.free_repick(character) and gold < bc.SUBCLASS_UNLOCK_COST:
            await message.answer(KEEPER["not_enough_gold"], keyboard=offer_keyboard())
            return
        titles = [s.title for s in subclass_service.paths_for(character.base_class)]
        decline = _can_decline(character)

    await _dispenser.set(peer_id, SubclassSelectState.PATH_SELECT)
    await message.answer(KEEPER["path_intro"], keyboard=paths_keyboard(titles, decline=decline))


@labeler.message(state=SubclassSelectState.OFFER, text=[BTN_LEAVE])
async def offer_leave(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        await _set_select_state(db, character, None)
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
    await _dispenser.delete(message.peer_id)
    await message.answer(
        "- Хорошо. Возвращайся, когда будешь готов.",
        keyboard=tavern_keyboard(character),
    )


@labeler.message(state=SubclassSelectState.OFFER, text=[BTN_DECLINE])
@labeler.message(state=SubclassSelectState.PATH_SELECT, text=[BTN_DECLINE])
async def decline_ask(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.subclass is not None or subclass_service.declined(character):
            return
        # После оплаты отказ сжёг бы 20 000: в выборе пути кнопка есть только
        # у бесплатного повтора после смены класса.
        if not _can_decline(character):
            return
    await _dispenser.set(message.peer_id, SubclassSelectState.DECLINE_CONFIRM)
    await message.answer(KEEPER["decline_question"], keyboard=decline_confirm_keyboard())


@labeler.message(state=SubclassSelectState.DECLINE_CONFIRM, text=[BTN_DECLINE_CONFIRM])
async def decline_confirm(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.subclass is not None or subclass_service.declined(character):
            await _dispenser.delete(message.peer_id)
            return
        subclass_service.decline(character)
        await _set_select_state(db, character, None)
        stats = await db.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        # Для сюжета отказ - тот же выбор пути: пауза на 30 уровне снимается.
        story_reward_text = await story_service.advance_past_subclass_gate(db, character, stats)
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
    await _dispenser.delete(message.peer_id)
    text = KEEPER["declined"]
    if story_reward_text:
        text += f"\n\n{story_reward_text}"
    await message.answer(text, keyboard=tavern_keyboard(character))
    if story_reward_text:
        await message.answer(f"📜 {mentor_name(character.region)} ждёт вас в городе.")


@labeler.message(state=SubclassSelectState.DECLINE_CONFIRM)
async def decline_back(message: Message) -> None:
    """«Подумаю ещё» и всё прочее - назад, на тот шаг, откуда пришли."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        on_paths = _paid(character) or subclass_service.free_repick(character)
        titles = [s.title for s in subclass_service.paths_for(character.base_class)]
        decline = _can_decline(character)
    if on_paths:
        await _dispenser.set(message.peer_id, SubclassSelectState.PATH_SELECT)
        await message.answer(KEEPER["path_intro"], keyboard=paths_keyboard(titles, decline=decline))
        return
    await _dispenser.set(message.peer_id, SubclassSelectState.OFFER)
    await message.answer(KEEPER["offer"].format(nickname=character.name), keyboard=offer_keyboard())


@labeler.message(state=SubclassSelectState.OFFER)
async def offer_fallback(message: Message) -> None:
    await message.answer(KEEPER["offer"].format(nickname=""), keyboard=offer_keyboard())


@labeler.message(state=SubclassSelectState.PATH_SELECT, text=list(ALL_SUBCLASS_TITLES))
async def path_view(message: Message) -> None:
    peer_id = message.peer_id
    subclass_id = text_match.lookup(ALL_SUBCLASS_TITLES, message.text)
    if subclass_id is None:
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.subclass is not None:
            return
        valid_ids = {s.id for s in subclass_service.paths_for(character.base_class)}
        if subclass_id not in valid_ids:
            return  # чужой путь (не для базового класса игрока) — молча игнорируем

    await _dispenser.set(
        peer_id, SubclassSelectState.PATH_CONFIRM, pending_subclass=subclass_id
    )
    await message.answer(
        KEEPER["path_descriptions"][subclass_id], keyboard=path_view_keyboard(),
        attachment=path_attachment(subclass_id),
    )


@labeler.message(state=SubclassSelectState.PATH_SELECT, text=[BTN_CANCEL_PATH])
async def path_cancel(message: Message) -> None:
    """Уйти, не выбрав путь. Плата не пропадает: Хранитель при следующем
    разговоре сразу откроет выбор."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.subclass is not None:
            await _dispenser.delete(message.peer_id)
            return
        # Заплатившие по старому порядку (до 2026-11-13) - плата помнится этой
        # строкой. Остальные ещё ничего не платили: просто уходят.
        kept = _paid(character) and not subclass_service.free_repick(character)
        await _set_select_state(db, character, STATE_PATH_PAID if kept else None)
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
    await _dispenser.delete(message.peer_id)
    text = KEEPER["path_cancelled"]
    if kept:
        text += "\n\n" + PAID_KEPT_LINE
    await message.answer(text, keyboard=tavern_keyboard(character))


@labeler.message(state=SubclassSelectState.PATH_SELECT)
async def path_select_fallback(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        titles = [s.title for s in subclass_service.paths_for(character.base_class)]
        decline = _can_decline(character)
    await message.answer(KEEPER["path_intro"], keyboard=paths_keyboard(titles, decline=decline))


async def _confirm_question(message: Message) -> str:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        price = _price_line(character) if character is not None else ""
    return KEEPER["path_confirm_question"] + price


@labeler.message(state=SubclassSelectState.PATH_CONFIRM, text=[BTN_CHOOSE_PATH])
async def path_choose(message: Message) -> None:
    if not (message.state_peer and message.state_peer.payload.get("pending_subclass")):
        await _back_to_path_select(message)
        return
    await message.answer(await _confirm_question(message), keyboard=path_confirm_keyboard())


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
        # Плата - здесь, в момент смены (2026-11-13, владелец). Заплатившие
        # по старому порядку и бесплатный повтор второй раз не платят.
        paid = 0
        if not _paid(character):
            try:
                paid = await subclass_service.pay_unlock(db, character)
            except NotEnoughCurrency:
                await _set_select_state(db, character, None)
                await screen_service.set_screen(db, character, "tavern")
                await db.commit()
                await _dispenser.delete(peer_id)
                await message.answer(KEEPER["not_enough_gold"], keyboard=tavern_keyboard(character))
                return
        subclass_service.apply_subclass(character, subclass_id)
        # Пассивка сменилась - эффекты рун заново (руны остаются на местах).
        from services import rune_service

        await rune_service.recompute(db, character)
        await _set_select_state(db, character, None)
        # патч 18: если сюжет стоял на паузе на subclass_gate-квесте — продвигаем
        stats = await db.scalar(
            select(CharacterStats).where(CharacterStats.character_id == character.id)
        )
        story_reward_text = await story_service.advance_past_subclass_gate(db, character, stats)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        title = next(s.title for s in REGISTRY.values() if s.id == subclass_id)

    await _dispenser.delete(peer_id)
    text = KEEPER["confirmed"].format(subclass=title)
    if paid:
        text = f"{display.gold_delta_line(-paid, total)}\n\n{text}"
    if story_reward_text:
        text += f"\n\n{story_reward_text}"
    await message.answer(text)
    if story_reward_text:
        # патч 21, п.1: сюжет продвинулся (акт 4 открыт) — игрок сейчас у
        # Хранителя, не у наставника, поэтому пингуем сами
        await message.answer(f"📜 {mentor_name(character.region)} ждёт вас в городе.")
    await _send_trials(peer_id, character)


@labeler.message(
    state=SubclassSelectState.PATH_CONFIRM, text=[BTN_OTHER_PATH, BTN_THINK_MORE]
)
async def path_back(message: Message) -> None:
    await _back_to_path_select(message)


@labeler.message(state=SubclassSelectState.PATH_CONFIRM)
async def path_confirm_fallback(message: Message) -> None:
    await message.answer(await _confirm_question(message), keyboard=path_confirm_keyboard())


async def _back_to_path_select(message: Message) -> None:
    # Состояние в базу не пишем: PATH_SELECT там значит «уже заплатил».
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        titles = [s.title for s in subclass_service.paths_for(character.base_class)]
        decline = _can_decline(character)
    await _dispenser.set(message.peer_id, SubclassSelectState.PATH_SELECT)
    await message.answer(KEEPER["path_relisten"], keyboard=paths_keyboard(titles, decline=decline))


# --- Переделка персонажа (альфа-тест) -------------------------------------
# На время альфы бесплатно и без ограничений: цена включится сама, когда
# выключат «Дар первопроходцев» (game/economy/prerelease_config.py).

_REMAKE_INTRO = (
    "- Запись можно переписать. - Хранитель разворачивает страницу к тебе. - "
    "Пока Список не затвердел, это ничего не стоит.\n\n"
    "Сменить класс - сбросятся подкласс и характеристики.\n"
    "Сменить подкласс - сбросится только он, характеристики останутся.\n"
    "Сбросить характеристики - очки вернутся нераспределёнными.\n"
    "Руны и пресеты при любой смене остаются как есть."
)
_REMAKE_WARNINGS = {
    BTN_REMAKE_CLASS: (
        "Сменить класс. Подкласс и характеристики будут сброшены, очки вернутся "
        "нераспределёнными. Уровень, вещи, руны и пресеты останутся."
    ),
    BTN_REMAKE_SUBCLASS: (
        "Сменить подкласс. Сменится пассивка подкласса. Характеристики, уровень, "
        "руны и пресеты останутся."
    ),
    BTN_REMAKE_STATS: (
        "Сбросить характеристики. Все вложенные очки вернутся нераспределёнными. "
        "Класс, подкласс, руны и пресеты останутся."
    ),
}


async def _open_remake_menu(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        # Отказ от пути - тоже подкласс: его можно сменить (2026-10-21).
        has_subclass = subclass_service.path_chosen(character)
    await _dispenser.set(message.peer_id, SubclassSelectState.REMAKE_MENU)
    await message.answer(_REMAKE_INTRO, keyboard=remake_keyboard(has_subclass),
                         attachment=KEEPER_ATTACHMENT)


@labeler.message(text=[BTN_REMAKE])
async def remake_open(message: Message) -> None:
    await _open_remake_menu(message)


@labeler.message(text=[BTN_KEEPER_LEAVE])
async def keeper_leave(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
    await _dispenser.delete(message.peer_id)
    await message.answer("Хранитель возвращается к своим записям.",
                         keyboard=tavern_keyboard(character))


@labeler.message(state=SubclassSelectState.REMAKE_MENU, text=[BTN_REMAKE_CLASS])
async def remake_pick_class(message: Message) -> None:
    """Смена класса — сначала выбор нового, подтверждение уже на нём."""
    await _dispenser.set(message.peer_id, SubclassSelectState.REMAKE_CLASS)
    await message.answer(
        f"{_REMAKE_WARNINGS[BTN_REMAKE_CLASS]}\n\nКакой путь теперь?",
        keyboard=base_class_keyboard(list(CLASS_BUTTONS)),
    )


@labeler.message(state=SubclassSelectState.REMAKE_CLASS, text=list(CLASS_BUTTONS))
async def remake_apply_class(message: Message) -> None:
    picked = text_match.canonical(CLASS_BUTTONS, message.text)
    if picked is None:
        return
    new_class = CLASS_BUTTONS[picked]
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        await respec_service.full_class_reset(db, character, new_class)
        await _set_select_state(db, character, None)
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
    await _dispenser.delete(message.peer_id)
    await message.answer(
        f"- Переписано. - Перо идёт по странице. - Теперь ты {picked}.\n\n"
        "Подкласс стёрт, характеристики ждут распределения. Руны и пресеты остались при вас.",
        keyboard=tavern_keyboard(character), attachment=KEEPER_ATTACHMENT,
    )


@labeler.message(
    state=SubclassSelectState.REMAKE_MENU, text=[BTN_REMAKE_SUBCLASS, BTN_REMAKE_STATS]
)
async def remake_confirm_ask(message: Message) -> None:
    action = text_match.canonical([BTN_REMAKE_SUBCLASS, BTN_REMAKE_STATS], message.text)
    if action is None:
        return
    await _dispenser.set(
        message.peer_id, SubclassSelectState.REMAKE_CONFIRM, pending_action=action
    )
    await message.answer(
        f"{_REMAKE_WARNINGS[action]}\n\nПереписываем?",
        keyboard=remake_confirm_keyboard(),
    )


@labeler.message(state=SubclassSelectState.REMAKE_CONFIRM, text=[BTN_REMAKE_CONFIRM])
async def remake_apply(message: Message) -> None:
    state = await _dispenser.get(message.peer_id)
    action = (state.payload.get("pending_action") if state else None) or ""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if action == BTN_REMAKE_SUBCLASS:
            if not subclass_service.path_chosen(character):
                return
            await respec_service.reset_subclass(db, character)
            reply = ("- Путь стёрт. - Хранитель закрывает страницу. - "
                     "Приходи, когда решишь заново.")
        elif action == BTN_REMAKE_STATS:
            await respec_service.reset_stats(db, character)
            reply = ("- Готово. - Хранитель откладывает перо. - "
                     "Очки снова твои, распредели их заново.")
        else:
            return
        await _set_select_state(db, character, None)
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
    await _dispenser.delete(message.peer_id)
    await message.answer(reply, keyboard=tavern_keyboard(character),
                         attachment=KEEPER_ATTACHMENT)


@labeler.message(
    state=SubclassSelectState.REMAKE_MENU, text=[BTN_REMAKE_CANCEL]
)
@labeler.message(
    state=SubclassSelectState.REMAKE_CONFIRM, text=[BTN_REMAKE_CANCEL]
)
@labeler.message(
    state=SubclassSelectState.REMAKE_CLASS, text=[BTN_REMAKE_CANCEL]
)
async def remake_cancel(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        await screen_service.set_screen(db, character, "tavern")
        await db.commit()
    await _dispenser.delete(message.peer_id)
    await message.answer("- Как скажешь. - Страница остаётся прежней.",
                         keyboard=tavern_keyboard(character))


@labeler.message(state=SubclassSelectState.REMAKE_MENU)
async def remake_menu_fallback(message: Message) -> None:
    await _open_remake_menu(message)


@labeler.message(state=SubclassSelectState.REMAKE_CONFIRM)
async def remake_confirm_fallback(message: Message) -> None:
    await message.answer("Переписываем?", keyboard=remake_confirm_keyboard())


@labeler.message(state=SubclassSelectState.REMAKE_CLASS)
async def remake_class_fallback(message: Message) -> None:
    await message.answer("Какой путь теперь?", keyboard=base_class_keyboard(list(CLASS_BUTTONS)))
