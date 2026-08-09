"""Скупщик — Тощий Иргал: трофеи (патч 9, блок 3) + снаряжение (патч 11, блок 2).
Один NPC во всех городах.

Патч 13, ч.1: окно скупщика — ОДНО сообщение, редактируется на месте при
каждой продаже (поштучно), вместо каскада новых сообщений.

Патч 37: скупщик — дерево экранов (services/screen_service.py), не одно окно.
Раньше клавиатура скупщика была INLINE и накапливалась ПОВЕРХ городской
reply-клавиатуры, которая так и оставалась висеть внизу — при достаточном
числе кнопок (патч 35 это частично лечило группировкой) экран всё равно
визуально ломался, а корень проблемы был в том, что клавиатура принадлежала
сообщению, а не экрану. Теперь вход к скупщику показывает ОБЫЧНУЮ (не inline)
клавиатуру из 2 действий + назад, которая ЦЕЛИКОМ заменяет городскую; у
каждого вложенного экрана — свой [← Назад], character.screen хранит текущий
экран (переживает рестарт бота, см. bot/handlers/world.py::_current_keyboard)."""

from vkbottle.bot import BotLabeler, Message

from bot import dailies_texts, editable_message
from bot.appraiser_texts import (
    appraiser_attachment,
    appraiser_empty,
    appraiser_gear_empty,
    appraiser_intro,
    appraiser_sold,
)
from bot.keyboards.appraiser import (
    GEAR_DETAIL_PAGE_SIZE,
    SELL_ALL_ID,
    appraiser_root_keyboard,
    appraiser_trophies_keyboard,
    sell_confirm_keyboard,
    sell_gear_detail_keyboard,
    sell_gear_main_keyboard,
)
from bot.keyboards.world import BTN_APPRAISER
from bot.world_texts import FOREIGN_APPRAISER_INTRO_SUFFIX
from game.combat import balance_config as bc
from game.world import grid
from services import daily_service, item_service, screen_service
from services import onboarding_service as onboarding_svc
from services import trophy_service
from services import wallet_service
from services.db import get_session_factory

labeler = BotLabeler()

_NS = "appraiser"
_bot_api = None


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def _price_multiplier(character, region: str | None) -> float:
    """Патч 26: скупщик в чужом городе платит FOREIGN_CITY_PRICE_PENALTY."""
    if region is not None and region != character.region:
        return bc.FOREIGN_CITY_PRICE_PENALTY
    return 1.0


def _intro(price_multiplier: float) -> str:
    return appraiser_intro() + (FOREIGN_APPRAISER_INTRO_SUFFIX if price_multiplier < 1.0 else "")


@labeler.message(text=[BTN_APPRAISER])
async def open_appraiser(message: Message) -> None:
    """Патч 37: корневой экран скупщика — просто выбор «трофеи / снаряжение»,
    больше не вываливает список трофеев сразу (это теперь appraiser_trophies)."""
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # скупщик только в городе
        mult = _price_multiplier(character, region)
        await screen_service.set_screen(db, character, "appraiser")
        await db.commit()

    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, _intro(mult), appraiser_root_keyboard(), attachment=appraiser_attachment(),
    )


@labeler.message(payload_contains={"type": "appraiser_root"})
async def appraiser_root(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        await screen_service.set_screen(db, character, "appraiser")
        await db.commit()

    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, _intro(mult), appraiser_root_keyboard(), attachment=appraiser_attachment(),
    )


@labeler.message(payload_contains={"type": "appraiser_back"})
async def appraiser_back(message: Message) -> None:
    """Патч 37: выход из скупщика целиком — обратно к городской клавиатуре."""
    from bot.keyboards.world import city_menu_keyboard
    from services import mount_service, story_service

    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        await screen_service.set_screen(db, character, None)
        await db.commit()
        if region is None:
            return
        has_mount = await mount_service.has_any_mount(db, character.id)
        is_foreign = region != character.region
        mentor_badge = not is_foreign and await story_service.mentor_badge_active(db, character)

    keyboard = city_menu_keyboard(character, mentor_badge, has_mount=has_mount, is_foreign=is_foreign)
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, "До встречи.", keyboard)


async def _render_trophies(db, character, mult: float, prefix: str = "") -> tuple[str, str]:
    stock = await trophy_service.get_stock(db, character.id)
    if not stock:
        text = appraiser_empty()
    else:
        lines = "\n".join(
            f"{d.emoji} {d.name} ×{count} — {round(d.sell_price * mult) * count} зол." for d, count in stock
        )
        text = lines
    if prefix:
        text = f"{prefix}\n\n{text}"
    return text, appraiser_trophies_keyboard(stock)


@labeler.message(payload_contains={"type": "appraiser_trophies"})
async def appraiser_trophies(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        await screen_service.set_screen(db, character, "appraiser_trophies")
        await db.commit()
        text, kb = await _render_trophies(db, character, mult)

    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb, attachment=appraiser_attachment())


@labeler.message(payload_contains={"type": "sell_trophies"})
async def sell_trophies(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    trophy_id = payload.get("id")
    if not trophy_id:
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        if trophy_id == SELL_ALL_ID:
            gold = await trophy_service.sell_all(db, character, mult)
        else:
            gold = await trophy_service.sell_one(db, character, trophy_id, mult)
        daily_progress = await daily_service.record_sell_gold(db, character, gold)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        text, kb = await _render_trophies(
            db, character, mult, prefix=appraiser_sold(gold, total) if gold > 0 else "",
        )

    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb, attachment=appraiser_attachment())

    if gold > 0:
        daily_notice = dailies_texts.progress_notice(daily_progress)
        if daily_notice:
            await _bot_api.messages.send(peer_id=peer_id, message=daily_notice, random_id=0)


def _sellable(items: list[tuple], mult: float) -> list[tuple]:
    return [
        (item, item_service.sell_price(item, mult))
        for item, equipped in items if not equipped and not item.admin_only
    ]


def _warning_lines(warnings: list[tuple]) -> str:
    return "\n".join(
        f"{item_service.rarity_def(item.rarity).emoji} {item.name} (ур. {item.ilvl}) "
        f"— сильнее надетого на {delta}"
        for item, delta in warnings
    )


async def _render_gear_main(db, character, mult: float, prefix: str = "") -> tuple[str, str]:
    """Патч 35/37: экран продажи снаряжения — сгруппирован по редкости
    (до 5 строк) вместо предмета на строку/кнопку."""
    items = await item_service.get_inventory(db, character.id)
    sellable = _sellable(items, mult)
    groups = item_service.group_sellable_by_rarity(sellable)
    if not groups:
        text = appraiser_gear_empty()
        return (f"{prefix}\n\n{text}" if prefix else text), sell_gear_main_keyboard([], 0)

    grand_total = sum(total for _, _, total in groups)
    lines = "\n".join(
        f"{rdef.emoji} {rdef.name} — {len(gitems)} шт. · {total} зол." for rdef, gitems, total in groups
    )
    text = f"🗡 Продать снаряжение\n\n{lines}"
    if prefix:
        text = f"{prefix}\n\n{text}"
    return text, sell_gear_main_keyboard(groups, grand_total)


async def _render_gear_detail(db, character, mult: float, page: int, prefix: str = "") -> tuple[str, str]:
    """Патч 35/37: подробный режим «По предметам» — постранично, показывает уровень."""
    items = await item_service.get_inventory(db, character.id)
    sellable = _sellable(items, mult)
    if not sellable:
        text = appraiser_gear_empty()
        return (f"{prefix}\n\n{text}" if prefix else text), sell_gear_detail_keyboard([], 1, 1)

    total_pages = (len(sellable) + GEAR_DETAIL_PAGE_SIZE - 1) // GEAR_DETAIL_PAGE_SIZE
    page = max(1, min(page, total_pages))
    start = (page - 1) * GEAR_DETAIL_PAGE_SIZE
    page_entries = sellable[start:start + GEAR_DETAIL_PAGE_SIZE]

    lines = "\n".join(
        f"{i}. {item_service.rarity_def(item.rarity).emoji} {item.name} (ур. {item.ilvl}) — {price} зол."
        for i, (item, price) in enumerate(page_entries, start=1)
    )
    text = f"🎒 Снаряжение (стр. {page} из {total_pages})\n\n{lines}"
    if prefix:
        text = f"{prefix}\n\n{text}"
    page_items = [item for item, _ in page_entries]
    return text, sell_gear_detail_keyboard(page_items, page, total_pages)


async def _sell_now(peer_id: int, from_id: int, rarity_id: str | None) -> None:
    """rarity_id=None продаёт всё снаряжение разом, иначе — одну редкость."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        if rarity_id is None:
            gold = await item_service.sell_all_gear(db, character, mult)
        else:
            gold = await item_service.sell_by_rarity(db, character, rarity_id, mult)
        daily_progress = await daily_service.record_sell_gold(db, character, gold)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        text, kb = await _render_gear_main(
            db, character, mult, prefix=appraiser_sold(gold, total) if gold > 0 else "",
        )

    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb)

    if gold > 0:
        daily_notice = dailies_texts.progress_notice(daily_progress)
        if daily_notice:
            await _bot_api.messages.send(peer_id=peer_id, message=daily_notice, random_id=0)


@labeler.message(payload_contains={"type": "appraiser_gear"})
async def appraiser_gear(message: Message) -> None:
    """Экран продажи снаряжения — открытие из корня скупщика, ОТМЕНА
    предупреждения и «Назад» из подробного режима ведут сюда же (патч 37:
    единая точка «показать актуальный экран снаряжения»)."""
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        await screen_service.set_screen(db, character, "appraiser_gear")
        await db.commit()
        text, kb = await _render_gear_main(db, character, mult)

    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb)


@labeler.message(payload_contains={"type": "gear_detail"})
async def gear_detail(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    page = payload.get("page", 1)
    if not isinstance(page, int) or page < 1:
        page = 1

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        await screen_service.set_screen(db, character, "appraiser_gear_detail")
        await db.commit()
        text, kb = await _render_gear_detail(db, character, mult, page)

    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb)


@labeler.message(payload_contains={"type": "sell_rarity"})
async def sell_rarity(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    rarity_id = payload.get("rarity")
    if not isinstance(rarity_id, str):
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        items = await item_service.get_inventory(db, character.id)
        sellable = _sellable(items, mult)
        groups = item_service.group_sellable_by_rarity(sellable)
        group = next((g for g in groups if g[0].id == rarity_id), None)
        if group is None:
            text, kb = await _render_gear_main(db, character, mult)
            await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb)
            return
        equipped = await item_service.get_equipped(db, character.id)
        warnings = item_service.stronger_than_equipped(group[1], equipped)

    if warnings:
        text = (
            f"⚠️ Среди них есть снаряжение лучше того, что на тебе:\n{_warning_lines(warnings)}\n\n"
            "Продать всё равно?"
        )
        kb = sell_confirm_keyboard({"type": "sell_rarity_confirm", "rarity": rarity_id})
        await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb)
        return

    await _sell_now(peer_id, message.from_id, rarity_id)


@labeler.message(payload_contains={"type": "sell_rarity_confirm"})
async def sell_rarity_confirm(message: Message) -> None:
    payload = message.get_payload_json() or {}
    rarity_id = payload.get("rarity")
    if not isinstance(rarity_id, str):
        return
    await _sell_now(message.peer_id, message.from_id, rarity_id)


@labeler.message(payload_contains={"type": "sell_all_gear"})
async def sell_all_gear(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        items = await item_service.get_inventory(db, character.id)
        sellable = _sellable(items, mult)
        equipped = await item_service.get_equipped(db, character.id)
        warnings = item_service.stronger_than_equipped([item for item, _ in sellable], equipped)

    if warnings:
        text = (
            f"⚠️ Среди них есть снаряжение лучше того, что на тебе:\n{_warning_lines(warnings)}\n\n"
            "Продать всё равно?"
        )
        kb = sell_confirm_keyboard({"type": "sell_all_gear_confirm"})
        await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb)
        return

    await _sell_now(peer_id, message.from_id, None)


@labeler.message(payload_contains={"type": "sell_all_gear_confirm"})
async def sell_all_gear_confirm(message: Message) -> None:
    await _sell_now(message.peer_id, message.from_id, None)


@labeler.message(payload_contains={"type": "sell_item"})
async def sell_gear_item(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    item_id = payload.get("item")
    page = payload.get("page", 1)
    if not isinstance(item_id, int):
        return
    if not isinstance(page, int) or page < 1:
        page = 1

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        gold = await item_service.sell_item(db, character, item_id, mult)
        daily_progress = await daily_service.record_sell_gold(db, character, gold)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        text, kb = await _render_gear_detail(
            db, character, mult, page, prefix=appraiser_sold(gold, total) if gold > 0 else "",
        )

    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb)

    if gold > 0:
        daily_notice = dailies_texts.progress_notice(daily_progress)
        if daily_notice:
            await _bot_api.messages.send(peer_id=peer_id, message=daily_notice, random_id=0)


async def rebuild(db, character) -> tuple[str, str] | None:
    """Патч 37: перестроить текст+клавиатуру ТЕКУЩЕГО экрана скупщика для
    /клавиатура и восстановления после рестарта бота (bot/handlers/world.py).
    None — character.screen не принадлежит этому модулю."""
    mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
    if character.screen == "appraiser":
        return _intro(mult), appraiser_root_keyboard()
    if character.screen == "appraiser_trophies":
        return await _render_trophies(db, character, mult)
    if character.screen == "appraiser_gear":
        return await _render_gear_main(db, character, mult)
    if character.screen == "appraiser_gear_detail":
        return await _render_gear_detail(db, character, mult, page=1)
    return None
