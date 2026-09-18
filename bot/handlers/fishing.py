"""Рыбалка (патч 58): экран озера, заброс, подсечка, садок.

Вход к воде устроен как вход к Монолиту (bot/handlers/raid.py): кнопка в
клавиатуре движения приходит только при ВХОДЕ на клетку, поэтому есть вторая
дверь — команда словом «Озеро». Иначе игроку, который уже стоит на озере,
пришлось бы уходить и возвращаться.

Обычное исследование на клетке озера продолжает работать как на любой другой
клетке: озеро — это ДОПОЛНИТЕЛЬНОЕ занятие, а не замена содержимому клетки.
"""

import random

from vkbottle.bot import BotLabeler, Message

from bot import fishing_texts as ft
from bot.activity import activity_action, blocked_reason
from bot.keyboards import fishing as kb
from bot.keyboards.world import movement_keyboard
from game.economy import fishing
from game.economy import fishing_config as fc
from game.world.scheduler import PeerScheduler
from services import (
    fishing_service,
    item_service,
    mount_service,
    raid_key_service,
    screen_service,
    trophy_service,
    wallet_service,
)
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()

_bot_api = None
_rng = random.Random()

#: Поклёвка приходит ОТДЕЛЬНЫМ сообщением через этот планировщик — тот же
#: механизм, что у прибытия и исследования (game/world/scheduler.py). Именно
#: он делает подсечку подсечкой: кнопка появляется в момент события, а не
#: висит заранее.
_bite_scheduler: PeerScheduler | None = None

# Экран озера — вложенный, родитель корневой (карта), как у рейд-лобби:
# озеро стоит в мире, а не в городе.
screen_service.PARENT["lake"] = None


def setup(bot_api, scheduler: PeerScheduler | None = None) -> None:
    global _bot_api, _bite_scheduler
    _bot_api = bot_api
    _bite_scheduler = scheduler or PeerScheduler(_on_bite, "fishing_bite")
    _bite_scheduler.start()


async def _on_bite(peer_id: int) -> None:
    """Сработал таймер поклёвки: шлём сообщение с кнопкой подсечки.

    Окно STRIKE_WINDOW_SECONDS отсчитывается от fishing_bite_at, проставленного
    при забросе, а не от этого момента — если планировщик задержался, окно
    честно уменьшается, а не продлевается.
    """
    if _bot_api is None:
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.screen != "lake":
            return
        if not fishing_service.is_casting(character):
            return
        if character.fishing_pending_fish is None:
            return
    await _bot_api.messages.send(
        peer_id=peer_id, message=_rng.choice(ft.BITE_TEXTS), random_id=0,
        keyboard=kb.bite_keyboard(),
    )


async def _enter_lake(message: Message) -> None:
    """Открывает экран озера. Общая точка для кнопки и команды «Озеро» —
    чтобы проверки не разъехались между двумя входами."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        lake = fishing_service.lake_at(character)
        if lake is None:
            # Вне озера команда МОЛЧИТ (а не отвечает ошибкой): слово «Озеро»
            # может встретиться в обычном разговоре, и бот не должен влезать.
            return
        reason = await blocked_reason(db, character, message.peer_id)
        if reason:
            await message.answer(reason)
            return

        await screen_service.set_screen(db, character, "lake")
        grams = await fishing_service.bag_total_grams(db, character.id)
        capacity = fishing.bag_capacity_grams(character.fishing_level)
        await db.commit()

    text = (
        f"{ft.lake_intro(lake, _rng)}\n\n"
        f"{ft.SEP}\n"
        f"{ft.level_line(character)}\n"
        f"{ft.bag_line(grams, capacity)}\n"
        f"{ft.SEP}"
    )
    await message.answer(text, keyboard=kb.lake_keyboard())


@labeler.message(text=[ft.LAKE_COMMAND])
@activity_action
async def lake_command(message: Message) -> None:
    await _enter_lake(message)


@labeler.message(payload_contains={"type": "approach_lake"})
@activity_action
async def lake_button(message: Message) -> None:
    """Инлайн-кнопка «К воде», приходящая отдельным сообщением при входе на
    клетку (bot/handlers/world.py::_maybe_send_lake_button)."""
    await _enter_lake(message)


@labeler.message(text=[ft.BTN_CAST])
@activity_action
async def cast(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.screen != "lake":
            return
        lake = fishing_service.lake_at(character)
        if lake is None:
            await message.answer(ft.NOT_AT_LAKE_TEXT)
            return
        # Протухший заброс (бот перезапускался, и таймер поклёвки умер вместе
        # с процессом) не должен запирать снасть в воде навсегда.
        if fishing_service.is_casting(character) and not fishing_service.cast_is_stale(character):
            await message.answer(ft.ALREADY_CASTING_TEXT, keyboard=kb.casting_keyboard())
            return
        result = fishing_service.start_cast(character, lake, _rng)
        await db.commit()

    if _bite_scheduler is not None:
        _bite_scheduler.schedule(message.peer_id, result.seconds)
    await message.answer(ft.CAST_TEXT, keyboard=kb.casting_keyboard())


@labeler.message(text=[ft.BTN_STRIKE])
@activity_action
async def strike(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.screen != "lake":
            return
        lake = fishing_service.lake_at(character)
        if lake is None:
            await message.answer(ft.NOT_AT_LAKE_TEXT)
            return
        if not fishing_service.is_casting(character):
            await message.answer(ft.NOT_CASTING_TEXT, keyboard=kb.lake_keyboard())
            return
        if _bite_scheduler is not None:
            _bite_scheduler.cancel(message.peer_id)

        # Находка вместо рыбы разыгрывается ЗДЕСЬ, а не при забросе: она не
        # рвётся леской и не зависит от веса, поэтому ей нечего делать в
        # состоянии заброса.
        if character.fishing_pending_fish is not None and _rng.random() < fc.JUNK_CHANCE:
            text, keyboard = await _resolve_junk(db, character)
            await db.commit()
            await message.answer(text, keyboard=keyboard)
            return

        result = await fishing_service.strike(db, character, lake, _rng)
        grams = await fishing_service.bag_total_grams(db, character.id)
        capacity = fishing.bag_capacity_grams(character.fishing_level)
        await db.commit()

    if result.bag_full:
        await message.answer(ft.bag_full_text(capacity), keyboard=kb.casting_keyboard())
        return
    if result.nothing:
        body = ft.NOTHING_TEXT
    elif result.too_early:
        body = ft.TOO_EARLY_TEXT
    elif result.broke:
        prefix = ft.STRIKE_MISSED_TEXT + chr(10) if result.missed else ""
        body = prefix + ft.break_text(result.fraction) + f"\n🎣 +{result.xp} опыта рыбалки"
        if result.levels_gained:
            body += f"\n⬆️ Уровень рыбалки: {result.new_level}"
    else:
        body = ft.catch_text(result)

    text = f"{body}\n\n{ft.SEP}\n{ft.bag_line(grams, capacity)}\n{ft.SEP}"
    await message.answer(text, keyboard=kb.lake_keyboard())


async def _resolve_junk(db, character) -> tuple[str, str]:
    """Со дна пришла не рыба. Начисление целиком переиспользует механику
    горстки пепла — сундук/предмет/ключ там уже написаны и откалиброваны."""
    fishing_service.clear_cast(character)
    roll = _rng.random()
    # Ключ выдаётся НАПРЯМУЮ, не через raid_key_service.maybe_grant: там свой
    # внутренний бросок шанса, и вызов отсюда гейтил бы выдачу дважды. Кап на
    # накопление при этом соблюдаем — он не наш. Если кап уже выбран, бросок
    # проваливается в следующую ветку и игрок получает что-то другое, а не
    # пустую находку.
    if roll < fc.JUNK_RAID_KEY_CHANCE and character.raid_keys < raid_key_service.current_cap(character):
            character.raid_keys += 1
            return ("🗝 Крючок цепляет что-то тяжёлое. Ключ Монолита.",
                    kb.lake_keyboard())
    if roll < fc.JUNK_RAID_KEY_CHANCE + fc.JUNK_ITEM_CHANCE:
        item = await item_service.grant_random_item(db, character, character.level, _rng)
        if item is not None:
            return (f"⚔️ Со дна поднимается {item.name}. Кто-то её там оставил.",
                    kb.lake_keyboard())
    if roll < fc.JUNK_RAID_KEY_CHANCE + fc.JUNK_ITEM_CHANCE + fc.JUNK_CHEST_CHANCE:
        drop = await trophy_service.grant_from_event(db, character, _rng)
        names = ", ".join(
            f"{trophy_service.trophy_def(tid).emoji} {trophy_service.trophy_def(tid).name} x{n}"
            for tid, n in drop.items()
        )
        return (f"📦 Отсыревший ящик. Внутри: {names}", kb.lake_keyboard())

    junk_id = _rng.choice(list(fc.JUNK_ITEMS))
    _emoji, _name, price = fc.JUNK_ITEMS[junk_id]
    await wallet_service.deposit(db, character.id, "farm", price)
    return ft.junk_text(junk_id), kb.lake_keyboard()


@labeler.message(text=[ft.BTN_BAG])
@activity_action
async def bag(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.screen != "lake":
            return
        rows = await fishing_service.get_bag(db, character.id)
        grams = await fishing_service.bag_total_grams(db, character.id)
        value = await fishing_service.bag_value(db, character.id, fc.APPRAISER_FISH_MULTIPLIER)
        capacity = fishing.bag_capacity_grams(character.fishing_level)
    await message.answer(
        ft.bag_screen(rows, grams, capacity, value), keyboard=kb.bag_keyboard()
    )


@labeler.message(text=[ft.BTN_LEAVE_LAKE])
@activity_action
async def leave_lake(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        # Заброшенная снасть при уходе снимается вместе с таймером: иначе
        # сообщение о поклёвке прилетело бы игроку, который уже ушёл.
        if _bite_scheduler is not None:
            _bite_scheduler.cancel(message.peer_id)
        fishing_service.clear_cast(character)
        await screen_service.set_screen(db, character, None)
        has_mount = await mount_service.has_any_mount(db, character.id)
        await db.commit()
    await message.answer(
        "Ты отходишь от воды.",
        keyboard=movement_keyboard(
            character.pos_x, character.pos_y, message.peer_id, has_mount
        ),
    )
