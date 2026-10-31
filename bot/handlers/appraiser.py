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
    appraiser_fish_keyboard,
    appraiser_ore_keyboard,
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
from game.economy import fishing as game_fishing
from game.economy import fishing_config as fc
from game.economy import mining
from game.economy import mining_config as mc
from services import guild_service
from services import daily_service, fishing_service, item_service, mining_service, screen_service
from services import onboarding_service as onboarding_svc
from services import faction_service
from services import trophy_service
from services import wallet_service
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»

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


async def _back_to_root(db, character, mult: float, prefix: str) -> tuple[str, str]:
    """После «Продать всё» - сразу к выбору раздела (2026-10-13): в
    опустевшем разделе делать уже нечего."""
    await screen_service.set_screen(db, character, "appraiser")
    await db.commit()
    return (f"{prefix}\n\n{_intro(mult)}" if prefix else _intro(mult)), appraiser_root_keyboard()


@labeler.message(payload_contains={"type": "appraiser_back"})
async def appraiser_back(message: Message) -> None:
    """Патч 39: выход из скупщика целиком — обратно в Торговый квартал
    (родитель "appraiser" в screen_service.PARENT), не сразу на площадь."""
    from bot.keyboards.world import market_quarter_keyboard
    from bot.world_texts import market_quarter_text

    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            await screen_service.set_screen(db, character, None)
            await db.commit()
            return
        await screen_service.set_screen(db, character, "market_quarter")
        await db.commit()
        is_foreign = region != character.region

    text = market_quarter_text(region, is_foreign)
    keyboard = market_quarter_keyboard(is_foreign)
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, keyboard)


async def _render_trophies(db, character, mult: float, prefix: str = "") -> tuple[str, str]:
    # Кровавое клеймо 5+ и процветание города (2026-10-15).
    mult *= await faction_service.relic_mult(db, character)
    # Венец «по убийствам» и гильдия - их доля входит в цену при продаже.
    mult *= trophy_service.display_multiplier(character)
    stock = await trophy_service.get_stock(db, character.id)
    if not stock:
        text = appraiser_empty()
    else:
        lines = "\n".join(
            f"{d.emoji} {d.name} ×{count} - {round(d.sell_price * count * mult)} зол." for d, count in stock
        )
        note = await faction_service.city_line(db, character, relics=True)
        text = f"{note}\n\n{lines}" if note else lines
    if prefix:
        text = f"{prefix}\n\n{text}"
    return text, appraiser_trophies_keyboard(stock, mult)


RELICS_EMPTY_TEXT = "💀 Реликвий в сумке нет. Их приносят с убитых мобов."


def relics_text(stock: list, mult: float, foreign: bool) -> str:
    """/реликвии (2026-10-23): реликвии по ступеням и что за них даст скупщик.
    Цена - теми же множителями, что у скупщика; в чужом городе - его скидка."""
    if not stock:
        return RELICS_EMPTY_TEXT
    lines = ["💀 Реликвии и цена у скупщика" + (" этого города" if foreign else "") + ":", ""]
    total = 0
    for d, count in stock:
        each = round(d.sell_price * mult)
        total += each * count
        lines.append(f"{d.emoji} {d.name} ×{count} - по {each}, всего {each * count} зол.")
    lines += ["", f"💰 Всё вместе: {total} зол."]
    if foreign:
        lines.append("В родном городе скупщик заплатит больше.")
    return "\n".join(lines)


@labeler.message(text=["/реликвии", "/relics"])
async def relics_command(message: Message) -> None:
    from bot import info_reply

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        mult = _price_multiplier(character, region)
        mult *= await faction_service.relic_mult(db, character)
        mult *= trophy_service.display_multiplier(character)
        stock = await trophy_service.get_stock(db, character.id)
        text = relics_text(stock, mult, foreign=region is not None and region != character.region)
    await info_reply.answer(message, text)


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
        relic_mult = mult * await faction_service.relic_mult(db, character)
        if trophy_id == SELL_ALL_ID:
            gold = await trophy_service.sell_all(db, character, relic_mult)
        else:
            gold = await trophy_service.sell_one(db, character, trophy_id, relic_mult)
        daily_progress = await daily_service.record_sell_gold(db, character, gold)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        sold = appraiser_sold(gold, total, guild_service.after_tax(character, gold)) if gold > 0 else ""
        if trophy_id == SELL_ALL_ID:
            text, kb = await _back_to_root(db, character, mult, sold)
        else:
            text, kb = await _render_trophies(db, character, mult, prefix=sold)

    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb, attachment=appraiser_attachment())

    if gold > 0:
        daily_notice = dailies_texts.progress_notice(daily_progress)
        if daily_notice:
            await _bot_api.messages.send(peer_id=peer_id, message=daily_notice, random_id=0)


#: _sell_now: продать то, что слабее надетого (не id редкости).
WEAKER = "_weaker"


def _sellable(items: list[tuple], mult: float) -> list[tuple]:
    """Только то, что скупщик реально купит. Раньше отсеивались лишь служебные
    вещи, и уникальная Игла Хирурга висела в списке «за 0 зол.» с кнопкой
    продажи, которая ничего не продавала (живой прогон на pupsik)."""
    return [
        (item, item_service.sell_price(item, mult))
        for item, equipped in items if not equipped and not item_service.is_unsellable(item)
    ]


def _warning_lines(warnings: list[tuple]) -> str:
    return "\n".join(
        f"{item_service.rarity_def(item.rarity).emoji} {item.name}{item_service.level_note(item)} "
        f"- сильнее надетого на {delta}"
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
        f"{rdef.emoji} {rdef.name} - {len(gitems)} шт. · {total} зол." for rdef, gitems, total in groups
    )
    weak = set(item_service.weaker_than_equipped(
        [item for item, _ in sellable], await item_service.get_equipped(db, character.id),
    ))
    weaker = (len(weak), sum(price for item, price in sellable if item in weak))
    text = f"🗡 Продать снаряжение\n\n{lines}"
    if weaker[0]:
        text += f"\n\n⬇️ Слабее надетого: {weaker[0]} шт. · {weaker[1]} зол."
    if prefix:
        text = f"{prefix}\n\n{text}"
    return text, sell_gear_main_keyboard(groups, grand_total, weaker)


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
        f"{i}. {item_service.rarity_def(item.rarity).emoji} {item.name}{item_service.level_note(item)}"
        f" - {price} зол."
        for i, (item, price) in enumerate(page_entries, start=1)
    )
    text = f"🎒 Снаряжение (стр. {page} из {total_pages})\n\n{lines}"
    if prefix:
        text = f"{prefix}\n\n{text}"
    page_items = [item for item, _ in page_entries]
    return text, sell_gear_detail_keyboard(page_items, page, total_pages)


async def _sell_now(peer_id: int, from_id: int, rarity_id: str | None) -> None:
    """rarity_id=None продаёт всё снаряжение разом, WEAKER - то, что слабее
    надетого, иначе — одну редкость."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        if rarity_id is None:
            gold = await item_service.sell_all_gear(db, character, mult)
        elif rarity_id == WEAKER:
            gold = await item_service.sell_weaker(db, character, mult)
        else:
            gold = await item_service.sell_by_rarity(db, character, rarity_id, mult)
        daily_progress = await daily_service.record_sell_gold(db, character, gold)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        sold = appraiser_sold(gold, total, guild_service.after_tax(character, gold)) if gold > 0 else ""
        if rarity_id is None:
            text, kb = await _back_to_root(db, character, mult, sold)
        else:
            text, kb = await _render_gear_main(db, character, mult, prefix=sold)

    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, text, kb, attachment=appraiser_attachment() if rarity_id is None else None,
    )

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


@labeler.message(payload_contains={"type": "sell_weaker_gear"})
async def sell_weaker_gear(message: Message) -> None:
    """Продать всё, что слабее надетого (2026-10-23). Подтверждения нет:
    вещи лучше надетого сюда не попадают по определению."""
    await _sell_now(message.peer_id, message.from_id, WEAKER)


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
            db, character, mult, page, prefix=appraiser_sold(gold, total, guild_service.after_tax(character, gold)) if gold > 0 else "",
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
    if character.screen == "appraiser_ore":
        return await _render_ore(db, character, mult)
    if character.screen == "appraiser_fish":
        # Найдено сверкой tests/test_wiring.py (2026-10-21): экран рыбы
        # после /клавиатура получал чужую клавиатуру.
        return await _render_fish(db, character)
    return None


# --- Рыба (патч 58) ----------------------------------------------------------
# Иргал берёт рыбу со скидкой APPRAISER_FISH_MULTIPLIER: он скупщик пепла, а
# не рыбник. Зато берёт всегда и в любом городе — это гарантированный ПОЛ
# цены, относительно которого ивент «Рыбак у воды» и является надбавкой.
#
# Наценка чужака (_price_multiplier) на рыбу НЕ накладывается: скидка за
# профиль и наценка за чужой город — разные правила, и перемножать их значило
# бы наказывать дважды за одно.

async def _render_fish(db, character) -> tuple[str, str]:
    bag = await fishing_service.get_bag(db, character.id)
    gold = await fishing_service.bag_value(db, character.id, fc.APPRAISER_FISH_MULTIPLIER)
    if not bag:
        text = "- Рыбы нет - нечего и смотреть."
        return text, appraiser_fish_keyboard(0)

    lines = ["- Рыбой не торгую, но возьму. По своей цене.", ""]
    for definition, grade_id, grams in bag:
        emoji = fc.GRADE_EMOJI.get(grade_id, "")
        mark = f"{emoji} " if emoji else ""
        price = round(
            game_fishing.price_of(definition.id, grams, grade_id)
            * fc.APPRAISER_FISH_MULTIPLIER
        )
        lines.append(
            f"{mark}{definition.emoji} {definition.name} "
            f"({game_fishing.grade_name(grade_id)}) - "
            f"{game_fishing.format_kg(grams)} · {price} зол."
        )
    lines.append("")
    lines.append(f"Итого: {gold} зол.")
    return chr(10).join(lines), appraiser_fish_keyboard(gold)


@labeler.message(payload_contains={"type": "appraiser_fish"})
async def appraiser_fish(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        await screen_service.set_screen(db, character, "appraiser_fish")
        await db.commit()
        text, kb = await _render_fish(db, character)
    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, text, kb, attachment=appraiser_attachment()
    )


@labeler.message(payload_contains={"type": "sell_fish"})
async def sell_fish(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        gold, grams = await fishing_service.sell_bag(
            db, character, fc.APPRAISER_FISH_MULTIPLIER
        )
        daily_progress = await daily_service.record_sell_gold(db, character, gold)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        sold = (
            f"Продано {game_fishing.format_kg(grams)} рыбы за {guild_service.gold_label(character, gold, 'зол.')} "
            f"(всего: {total})"
        ) if gold else ""
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        text, kb = await _back_to_root(db, character, mult, sold)
    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, text, kb, attachment=appraiser_attachment()
    )
    notice = dailies_texts.progress_notice(daily_progress)
    if notice:
        await _bot_api.messages.send(peer_id=peer_id, message=notice, random_id=0)


# --- Руда (2026-10-21) ---------------------------------------------------------
# Иргал берёт только мелкую руду (mc.APPRAISER_ORE_IDS) и дёшево: это сброс
# излишков, а не заработок. Наценка чужого города - как у трофеев; процветание,
# клеймо и перк гильдии «за реликвии» к руде не относятся.

async def _render_ore(db, character, mult: float, prefix: str = "") -> tuple[str, str]:
    stacks = await mining_service.sellable_ore(db, character.id)
    by_ore: dict[str, tuple] = {}
    best_count, best_gold = 0, 0.0
    lines = []
    for definition, grade_id, count in stacks:
        price = mining_service.ore_sell_price(definition.id, grade_id) * mult
        emoji = mc.GRADE_EMOJI.get(grade_id, "")
        mark = f"{emoji} " if emoji else ""
        lines.append(
            f"{mark}{definition.emoji} {definition.name} ({mining.grade_name(grade_id)})"
            f" ×{count} - {round(price * count)} зол."
        )
        if grade_id == "common":
            by_ore[definition.id] = (definition.id, definition.emoji, count, round(price * count))
        else:
            best_count += count
            best_gold += price * count
    if not lines:
        text = "- Железо и кварц возьму, остальное оставь себе. А у тебя ни того, ни другого."
    else:
        text = "- Железо и кварц беру, дорого не дам. Остальная руда мне не нужна.\n\n" + "\n".join(lines)
    if prefix:
        text = f"{prefix}\n\n{text}"
    return text, appraiser_ore_keyboard(list(by_ore.values()), (best_count, round(best_gold)))


@labeler.message(payload_contains={"type": "appraiser_ore"})
async def appraiser_ore(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        mult = _price_multiplier(character, grid.city_region_at(character.pos_x, character.pos_y))
        await screen_service.set_screen(db, character, "appraiser_ore")
        await db.commit()
        text, kb = await _render_ore(db, character, mult)
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb, attachment=appraiser_attachment())


@labeler.message(payload_contains={"type": "sell_ore"})
async def sell_ore(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    ore_id = payload.get("ore")
    best = bool(payload.get("best"))
    if not best and ore_id not in mc.APPRAISER_ORE_IDS:
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        region = grid.city_region_at(character.pos_x, character.pos_y)
        if region is None:
            return  # скупщик только в городе
        mult = _price_multiplier(character, region)
        gold, _pieces = await mining_service.sell_ore(db, character.id, ore_id, best, mult)
        daily_progress = await daily_service.record_sell_gold(db, character, gold)
        total = (await wallet_service.get_wallet(db, character.id)).farm_currency
        await db.commit()
        sold = appraiser_sold(gold, total, guild_service.after_tax(character, gold)) if gold > 0 else ""
        text, kb = await _render_ore(db, character, mult, prefix=sold)
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, kb, attachment=appraiser_attachment())
    if gold > 0:
        notice = dailies_texts.progress_notice(daily_progress)
        if notice:
            await _bot_api.messages.send(peer_id=peer_id, message=notice, random_id=0)
