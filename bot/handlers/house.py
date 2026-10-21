"""Дом (2026-10-21): кнопка на площади родного города, внутри печь и
алхимический стол. Числа и продажа - game/economy/house_config.py.

Экран дома живёт рядом с кварталами города (bot/handlers/world.py,
_render_city_screen): «← Площадь» и восстановление клавиатуры - общие.
Экраны стола ("alchemy") и варки ("brewing") восстанавливает rebuild().

Варка идёт BREW_SECONDS и не выпускает из дома (bot/activity.py). Доваривает
её tick_job раз в пару секунд - по времени в БД, так что рестарт бота
варку не теряет.
"""

import random

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot.keyboards import world as kb
from bot.keyboards.layout import add_paired
from bot.keyboards.world import add_miniapp_button
from bot.world_texts import FOREIGN_NPC_REJECTION
from game.economy import alchemy
from game.economy import herbalism
from game.world import grid
from models import Character
from services import alchemy_service, elixir_service, herb_service
from services import onboarding_service as onboarding_svc
from services import screen_service
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра

HOUSE_TEXT = "🏠 Дом\n\nТвои стены в городе. У окна печь, в углу стол с ретортами и склянками."
OVEN_SOON = "🔥 Печь растоплена, но рецептов у тебя пока нет. Кулинария откроется следующим обновлением."
BUSY_TEXT = "⚗️ Идет варка. Дождись ее или брось - тогда травы и золото пропадут."

BTN_HOUSE_BACK = "← Дом"
BTN_BREW_CANCEL = "✖️ Бросить варку"

_bot_api = None
_rng = random.Random()


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def house_text() -> str:
    return HOUSE_TEXT


# --- Клавиатуры ---------------------------------------------------------------


def alchemy_keyboard(level: int) -> str:
    kb_ = Keyboard(one_time=False)
    items = []
    for recipe in alchemy.known(level):
        d = elixir_service.elixir_def(recipe.elixir_id)
        if d is not None:
            items.append((f"{d.emoji} {d.name}", KeyboardButtonColor.SECONDARY, {"type": "brew", "id": recipe.elixir_id}))
    add_paired(kb_, items)
    add_miniapp_button(kb_)
    kb_.row()
    kb_.add(Text(BTN_HOUSE_BACK, payload={"type": "house_back"}), color=KeyboardButtonColor.SECONDARY)
    return kb_.get_json()


def brewing_keyboard() -> str:
    kb_ = Keyboard(one_time=False)
    kb_.add(Text(BTN_BREW_CANCEL, payload={"type": "brew_cancel"}), color=KeyboardButtonColor.NEGATIVE)
    return kb_.get_json()


# --- Тексты -------------------------------------------------------------------


def _herb_list(needs: dict[str, int], bag: dict[str, int]) -> str:
    parts = []
    for herb_id, n in needs.items():
        h = herbalism.herb_def(herb_id)
        parts.append(f"{h.name if h else herb_id} {n} (есть {bag.get(herb_id, 0)})")
    return ", ".join(parts)


async def alchemy_text(db, character: Character) -> str:
    bag = {h.id: n for h, n in await herb_service.get_bag(db, character.id)}
    level = character.alchemy_level
    xp = f" ({character.alchemy_xp}/{alchemy.xp_to_next(level)} опыта)" if alchemy.xp_to_next(level) else ""
    lines = ["⚗️ Алхимический стол", f"Алхимия: {level} ур.{xp}", ""]
    for recipe in alchemy.known(level):
        d = elixir_service.elixir_def(recipe.elixir_id)
        lines.append(
            f"{d.emoji} {d.name} ×{recipe.out}: {_herb_list(recipe.herbs, bag)}, "
            f"{alchemy.gold_cost(recipe, level)} зол."
        )
    nxt = alchemy.next_locked(level)
    if nxt is not None:
        d = elixir_service.elixir_def(nxt.elixir_id)
        lines.append(f"🔒 Дальше: {d.name} с {nxt.level} ур.")
    return "\n".join(lines)


def brewing_text(character: Character) -> str:
    recipe = alchemy_service.brewing(character)
    d = elixir_service.elixir_def(recipe.elixir_id) if recipe else None
    name = d.name if d else "зелье"
    return (f"⚗️ На огне {name}. Готово через {alchemy_service.seconds_left(character)} сек.\n"
            "Выйти из дома до конца варки нельзя. Бросишь - травы и золото пропадут.")


def brewed_text(result: alchemy_service.Brewed) -> str:
    d = elixir_service.elixir_def(result.recipe.elixir_id)
    text = f"⚗️ Готово: {d.emoji} {d.name} ×{result.amount}, уже в инвентаре. Алхимия +{result.xp} опыта."
    if result.level_after > result.level_before:
        text += f"\n⚗️ Алхимия: {result.level_after} уровень."
    if result.unlocked:
        names = ", ".join(elixir_service.elixir_def(r.elixir_id).name for r in result.unlocked)
        text += f"\nНовые рецепты: {names}."
    return text


async def rebuild(db, character: Character) -> tuple[str, str] | None:
    """Экран стола или варки - для /клавиатура и после рестарта."""
    if character.screen == "brewing" or alchemy_service.is_working(character):
        if alchemy_service.is_working(character):
            return brewing_text(character), brewing_keyboard()
        return await alchemy_text(db, character), alchemy_keyboard(character.alchemy_level)
    if character.screen == "alchemy":
        return await alchemy_text(db, character), alchemy_keyboard(character.alchemy_level)
    return None


# --- Вход ---------------------------------------------------------------------


async def _home_character(db, message: Message) -> Character | None:
    """Персонаж у себя в городе и с домом, иначе None (с ответом, если нужно)."""
    character = await onboarding_svc.get_character(db, message.from_id)
    if character is None or character.creation_state is not None or not character.has_house:
        return None
    region = grid.city_region_at(character.pos_x, character.pos_y)
    if region is None:
        return None
    if region != character.region:
        await message.answer(FOREIGN_NPC_REJECTION)
        return None
    return character


@labeler.message(text=[kb.BTN_HOUSE])
async def open_house(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None:
            return
        if alchemy_service.is_working(character):
            await message.answer(brewing_text(character), keyboard=brewing_keyboard())
            return
        await screen_service.set_screen(db, character, "house")
        await db.commit()
    await message.answer(HOUSE_TEXT, keyboard=kb.house_keyboard())


@labeler.message(payload_contains={"type": "house_back"})
async def house_back(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None:
            return
        if alchemy_service.is_working(character):
            await message.answer(BUSY_TEXT, keyboard=brewing_keyboard())
            return
        await screen_service.set_screen(db, character, "house")
        await db.commit()
    await message.answer(HOUSE_TEXT, keyboard=kb.house_keyboard())


@labeler.message(text=[kb.BTN_OVEN])
async def open_oven(message: Message) -> None:
    async with get_session_factory()() as db:
        if await _home_character(db, message) is not None:
            await message.answer(OVEN_SOON, keyboard=kb.house_keyboard())


@labeler.message(text=[kb.BTN_ALCHEMY])
async def open_alchemy(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None:
            return
        if alchemy_service.is_working(character):
            await message.answer(brewing_text(character), keyboard=brewing_keyboard())
            return
        await screen_service.set_screen(db, character, "alchemy")
        await db.commit()
        text = await alchemy_text(db, character)
    await message.answer(text, keyboard=alchemy_keyboard(character.alchemy_level))


@labeler.message(payload_contains={"type": "brew"})
async def brew(message: Message) -> None:
    elixir_id = (message.get_payload_json() or {}).get("id")
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None:
            return
        try:
            await alchemy_service.start(db, character, elixir_id)
        except alchemy_service.AlchemyError as exc:
            await db.rollback()
            if alchemy_service.is_working(character):
                await message.answer(str(exc), keyboard=brewing_keyboard())
                return
            await message.answer(str(exc), keyboard=alchemy_keyboard(character.alchemy_level))
            return
        await screen_service.set_screen(db, character, "brewing")
        await db.commit()
    await message.answer(brewing_text(character), keyboard=brewing_keyboard())


@labeler.message(payload_contains={"type": "brew_cancel"})
async def brew_cancel(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or not alchemy_service.is_working(character):
            return
        alchemy_service.cancel(character)
        await screen_service.set_screen(db, character, "alchemy")
        await db.commit()
        text = await alchemy_text(db, character)
    await message.answer(f"⚗️ Варка брошена, травы и золото пропали.\n\n{text}",
                         keyboard=alchemy_keyboard(character.alchemy_level))


# --- Фоновый шаг --------------------------------------------------------------


async def tick_job() -> None:
    if _bot_api is None:
        return
    done = []
    try:
        async with get_session_factory()() as db:
            for character in await alchemy_service.due(db):
                result = await alchemy_service.finish(db, character, _rng)
                if result is None:
                    continue
                await screen_service.set_screen(db, character, "alchemy")
                peer = await onboarding_svc.vk_id_for_character(db, character.id)
                done.append((peer, result, await alchemy_text(db, character), character.alchemy_level))
            await db.commit()
    except Exception:
        logger.exception("Дом: варка не доварилась")
        return
    for peer, result, table, level in done:
        if peer is None:
            continue
        try:
            await _bot_api.messages.send(
                peer_id=peer, random_id=0, message=f"{brewed_text(result)}\n\n{table}",
                keyboard=alchemy_keyboard(level),
            )
        except Exception:
            logger.warning("Дом: сообщение о варке не доставлено {}", peer)

