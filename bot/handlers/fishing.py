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
from game.economy import gem_goods_config as ggc
from game.world import grid
from game.world.scheduler import PeerScheduler
from services import experience_service, guild_quest_service
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
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»

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
    _bite_scheduler = scheduler


#: После перезапуска поклёвка приходит через столько секунд, а окно
#: подсечки отсчитывается заново - игрок не виноват, что бот перезапускался.
RESUME_BITE_DELAY_SECONDS = 3


async def resume_after_restart() -> int:
    """Забросы, у которых перезапуск унёс таймер поклёвки (2026-10-12).

    Заброс целиком лежит в базе, пропадала только задача «клюёт!». Поклёвка
    ещё впереди - будильник на её время. Уже прошла или прошла и окно
    подсечки (бот лежал) - поклёвка заново через пару секунд и с полным
    окном: иначе игрок после каждого деплоя терял рыбу ни за что."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from models import Character, User

    if _bite_scheduler is None:
        return 0
    now = datetime.now(timezone.utc)
    resumed = 0
    async with get_session_factory()() as db:
        rows = (await db.execute(
            select(User.vk_id, Character)
            .join(Character, Character.user_id == User.id)
            .where(Character.fishing_cast_at.is_not(None), Character.fishing_bite_at.is_not(None),
                   Character.fishing_pending_fish.is_not(None))
        )).all()
        for peer_id, character in rows:
            bite_at = character.fishing_bite_at
            if bite_at.tzinfo is None:
                bite_at = bite_at.replace(tzinfo=timezone.utc)
            if bite_at <= now + timedelta(seconds=1):
                bite_at = now + timedelta(seconds=RESUME_BITE_DELAY_SECONDS)
                character.fishing_bite_at = bite_at
            _bite_scheduler.schedule(peer_id, max((bite_at - now).total_seconds(), 0.0))
            resumed += 1
        await db.commit()
    return resumed


async def on_bite(peer_id: int) -> None:
    """Сработал таймер поклёвки: шлём сообщение с кнопкой подсечки.

    Окно STRIKE_WINDOW_SECONDS отсчитывается от fishing_bite_at, проставленного
    при забросе, а не от этого момента — если планировщик задержался, окно
    честно уменьшается, а не продлевается.
    """
    if _bot_api is None:
        return
    from sqlalchemy import select

    from models import Character, User

    async with get_session_factory()() as db:
        # Не через onboarding.get_character: та отмечает игрока активным, и
        # каждая поклёвка донки продлевала бы «игрок рядом» - донка не
        # сматывалась никогда (2026-10-23, жалоба владельца).
        character = await db.scalar(
            select(Character).join(User, User.id == Character.user_id).where(User.vk_id == peer_id)
        )
        if character is None or character.screen != "lake":
            return
        if not fishing_service.is_casting(character):
            return
        if character.fishing_pending_fish is None:
            return
        if character.fishing_auto:
            text, keyboard, wait = await _donka_bite(db, character, peer_id)
            await db.commit()
            if wait is not None and _bite_scheduler is not None:
                _bite_scheduler.schedule(peer_id, wait)
            await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, keyboard=keyboard)
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

        if character.screen != "lake":
            # Был не у воды - вытащенная рыба уже ушла (2026-10-21).
            fishing_service.drop_catch(character)
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
    from services import craft_gear_service

    bait = craft_gear_service.bait_minutes_left(character)
    if bait:
        text += f"\n🪱 Прикормка: клюёт быстрее ещё {bait} мин."
    # Вытащенная рыба ждёт решения - сначала оно, потом заброс.
    if fishing_service.has_catch(character):
        keyboard = kb.catch_keyboard()
    elif character.fishing_auto:
        keyboard = kb.donka_keyboard()
    else:
        keyboard = kb.lake_keyboard(character.has_donka)
        if character.has_donka:
            text += f"\n{ft.DONKA_CHOICE_LINE}"
    await message.answer(text, keyboard=keyboard, attachment=ft.lake_attachment(lake))


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
        if fishing_service.has_catch(character):
            await message.answer(ft.DECIDE_FIRST_TEXT, keyboard=kb.catch_keyboard())
            return
        from services import craft_gear_service

        rod = await craft_gear_service.tier(db, character.id, "rod")
        result = fishing_service.start_cast(
            character, lake, _rng, rod_tier=rod, bite_mult=craft_gear_service.bite_mult(character),
        )
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
        guild_lines = await guild_quest_service.record(db, character, "fish", 1) if result.landed else []
        # Опыт - по уровню клетки озера (2026-10-15), как у мобов этой клетки.
        char_xp = await experience_service.grant_activity_xp(
            db, character, "fish", place_level=grid.mob_level_at(character.pos_x, character.pos_y, character.level),
        ) if result.landed else None
        # Включено «всю рыбу в садок» - решение принимаем за игрока. Садок
        # полон - кнопки всё равно приходят: рыбу можно только отпустить.
        kept = None
        if result.landed and fishing_service.auto_keep(character):
            kept = await fishing_service.keep_catch(db, character)
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
        body += f"\n{ft.fishing_xp_line(character)}"
    else:
        body = ft.catch_text(result, character)
        xp_line = experience_service.activity_xp_line(char_xp) if char_xp else ""
        if xp_line:
            body += f"\n{xp_line}"

    if result.landed and kept is not None and kept.bag_full:
        text, keyboard = f"{body}\n\n{ft.bag_full_decide_text(capacity)}", kb.catch_keyboard()
    elif result.landed and kept is None:
        # Садок - после решения «В садок» / «Отпустить» (2026-10-21).
        text, keyboard = body, kb.catch_keyboard()
    else:
        text, keyboard = (
            f"{body}\n\n{ft.SEP}\n{ft.bag_line(grams, capacity)}\n{ft.SEP}", kb.lake_keyboard(character.has_donka),
        )
    if guild_lines:
        text += "\n\n" + "\n".join(guild_lines)
    await message.answer(text, keyboard=keyboard)
    if char_xp is not None and char_xp.levels_gained:
        from bot.handlers import stats_window  # избегаем цикла импортов

        await stats_window.notify_levelup(message.peer_id, char_xp.levels_gained, char_xp.new_level)


@labeler.message(payload_contains=kb.KEEP_PAYLOAD)
@activity_action
async def keep(message: Message) -> None:
    await _decide(message, keep=True)


@labeler.message(payload_contains=kb.RELEASE_PAYLOAD)
@activity_action
async def release(message: Message) -> None:
    await _decide(message, keep=False)


async def _decide(message: Message, keep: bool) -> None:
    """Вытащенная рыба: в садок или в воду. Только у воды: ушёл - рыба ушла
    (2026-10-21, владелец)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        if character.screen != "lake":
            fishing_service.drop_catch(character)
            await db.commit()
            await message.answer(ft.CATCH_GONE_TEXT)
            return
        if keep:
            decision = await fishing_service.keep_catch(db, character)
        else:
            decision = fishing_service.release_catch(character)
        grams = await fishing_service.bag_total_grams(db, character.id)
        capacity = fishing.bag_capacity_grams(character.fishing_level)
        at_lake = character.screen == "lake"
        await db.commit()
    if decision is None:
        await message.answer(ft.NOTHING_TO_DECIDE_TEXT, keyboard=kb.lake_keyboard() if at_lake else None)
        return
    if decision.bag_full:
        await message.answer(ft.bag_full_decide_text(capacity), keyboard=kb.catch_keyboard())
        return
    line = ft.kept_line(decision) if decision.kept else ft.released_line(decision)
    await message.answer(
        f"{line}\n\n{ft.SEP}\n{ft.bag_line(grams, capacity)}\n{ft.SEP}",
        keyboard=kb.lake_keyboard(character.has_donka) if at_lake else None,
    )


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
            return (f"⚔️ Крючок вытаскивает со дна находку: {item.name}. Утопленнику она больше не нужна.",
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
    return ft.junk_text(junk_id, character), kb.lake_keyboard()


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
        ft.bag_screen(rows, grams, capacity, value),
        keyboard=kb.donka_keyboard() if character.fishing_auto else kb.bag_keyboard(),
    )


@labeler.message(payload_contains=kb.CANCEL_CAST_PAYLOAD)
@activity_action
async def cancel_cast(message: Message) -> None:
    """Снасть из воды, игрок остаётся у озера (2026-10-19, вместо «Отойти»
    на экране заброса)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.screen != "lake":
            return
        if _bite_scheduler is not None:
            _bite_scheduler.cancel(message.peer_id)
        fishing_service.clear_cast(character)
        await db.commit()
    await message.answer(ft.CANCEL_CAST_TEXT, keyboard=kb.lake_keyboard(character.has_donka))


# --- Пепельная донка (2026-10-23): авторыбалка из магазина ------------------------

#: Донка ждёт поклёвку во столько раз дольше обычного заброса (владелец: «в 4 раза медленнее»).
DONKA_SLOWDOWN = 4
#: Игрок молчит дольше - донку сматывает: ловит только пока ты рядом.
DONKA_IDLE_MINUTES = ggc.DONKA_IDLE_MINUTES


async def _donka_cast(db, character, lake) -> float:
    """Новый заброс донки: поклёвка вчетверо дольше. Секунды до неё."""
    from datetime import datetime, timedelta, timezone

    from services import craft_gear_service

    rod = await craft_gear_service.tier(db, character.id, "rod")
    result = fishing_service.start_cast(
        character, lake, _rng, rod_tier=rod, bite_mult=craft_gear_service.bite_mult(character),
    )
    wait = result.seconds * DONKA_SLOWDOWN
    character.fishing_bite_at = datetime.now(timezone.utc) + timedelta(seconds=wait)
    character.fishing_auto = True
    return wait


@labeler.message(payload_contains=kb.DONKA_ON_PAYLOAD)
@activity_action
async def donka_on(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.screen != "lake" or not character.has_donka:
            return
        lake = fishing_service.lake_at(character)
        if lake is None:
            await message.answer(ft.NOT_AT_LAKE_TEXT)
            return
        if fishing_service.has_catch(character):
            await message.answer(ft.DECIDE_FIRST_TEXT, keyboard=kb.catch_keyboard())
            return
        if fishing_service.is_casting(character) and not fishing_service.cast_is_stale(character):
            await message.answer(ft.ALREADY_CASTING_TEXT)
            return
        if await fishing_service.bag_total_grams(db, character.id) >= fishing.bag_capacity_grams(character.fishing_level):
            await message.answer(ft.DONKA_FULL_TEXT, keyboard=kb.lake_keyboard(True))
            return
        wait = await _donka_cast(db, character, lake)
        await db.commit()
    if _bite_scheduler is not None:
        _bite_scheduler.schedule(message.peer_id, wait)
    await message.answer(ft.DONKA_ON_TEXT, keyboard=kb.donka_keyboard())


@labeler.message(payload_contains=kb.DONKA_OFF_PAYLOAD)
@activity_action
async def donka_off(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None:
            return
        if _bite_scheduler is not None:
            _bite_scheduler.cancel(message.peer_id)
        fishing_service.clear_cast(character)
        await db.commit()
    keyboard = kb.lake_keyboard(character.has_donka) if character.screen == "lake" else None
    await message.answer(ft.DONKA_OFF_TEXT, keyboard=keyboard)


async def _donka_bite(db, character, peer_id: int) -> tuple[str, str | None, float | None]:
    """Поклёвка у донки: подсечка сама, рыба в садок, следующий заброс.
    (текст, клавиатура, через сколько следующая поклёвка или None - донка снята)."""
    from datetime import datetime, timedelta, timezone

    lake = fishing_service.lake_at(character)
    if lake is None:
        fishing_service.clear_cast(character)
        return ft.DONKA_OFF_TEXT, None, None
    last = character.last_active_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is not None and datetime.now(timezone.utc) - last > timedelta(minutes=DONKA_IDLE_MINUTES):
        fishing_service.clear_cast(character)
        return ft.DONKA_IDLE_TEXT, kb.lake_keyboard(True), None
    # Опыт за донку - как за рыбалку руками (2026-10-23, владелец вернул).
    result = await fishing_service.strike(db, character, lake, _rng)
    capacity = fishing.bag_capacity_grams(character.fishing_level)
    if result.landed:
        await guild_quest_service.record(db, character, "fish", 1)
        kept = await fishing_service.keep_catch(db, character)
        if kept is None or kept.bag_full:
            fishing_service.drop_catch(character)
            fishing_service.clear_cast(character)
            return ft.DONKA_FULL_TEXT, kb.lake_keyboard(True), None
        char_xp = await experience_service.grant_activity_xp(
            db, character, "fish", place_level=grid.mob_level_at(character.pos_x, character.pos_y, character.level),
        )
        text = ft.donka_catch_line(result.fish, result.grams, result.grade_label)
        text += "\n" + ft.donka_xp_lines(result, character)
        xp_line = experience_service.activity_xp_line(char_xp) if char_xp else ""
        if xp_line:
            text += "\n" + xp_line
        if char_xp is not None and char_xp.levels_gained:
            from bot.handlers import stats_window  # избегаем цикла импортов

            await stats_window.notify_levelup(peer_id, char_xp.levels_gained, char_xp.new_level)
    else:
        text = ft.DONKA_BREAK_TEXT
        if result.xp:
            text += "\n" + ft.donka_xp_lines(result, character)
    if await fishing_service.bag_total_grams(db, character.id) >= capacity:
        fishing_service.clear_cast(character)
        return f"{text}\n{ft.DONKA_FULL_TEXT}", kb.lake_keyboard(True), None
    wait = await _donka_cast(db, character, lake)
    return text, None, wait


def cancel_bite(peer_id: int) -> None:
    """Снять таймер поклёвки: игрок ушёл от воды другим путём (маунт с карты)."""
    if _bite_scheduler is not None:
        _bite_scheduler.cancel(peer_id)


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


@labeler.message(regex=r"(?i)^\s*/(?:рыба|fish)\s*(\d*)\s*$")
async def ring_list_command(message: Message, match: tuple) -> None:
    """/рыба1 - озёра первого кольца (2026-10-15)."""
    from bot.onboarding_texts import REGION_TITLES
    from game.economy import fishing as fishing_rules

    ring = int(match[0]) if match and match[0] else 0
    rings = sorted({lake.tier for lake in fishing_rules.all_lakes()})
    if ring not in rings:
        await message.answer(
            "Напиши номер кольца: " + ", ".join(f"/рыба{r}" for r in rings)
            + ". Первое - внешнее (1-15 ур.), дальше ближе к Монолиту."
        )
        return
    lines = [
        f"🎣 {lake.name} ({lake.x}; {lake.y}) - {REGION_TITLES.get(lake.region, 'центр мира')}"
        for lake in fishing_rules.all_lakes() if lake.tier == ring
    ]
    await message.answer(f"Озёра {ring}-го кольца:\n\n" + "\n".join(lines))
