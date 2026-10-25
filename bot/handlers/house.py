"""Дом (2026-10-21): кнопка на площади родного города, внутри печь и
алхимический стол. Числа и продажа - game/economy/house_config.py.

Экран дома живёт рядом с кварталами города (bot/handlers/world.py,
_render_city_screen): «← Площадь» и восстановление клавиатуры - общие.
Экраны стола ("alchemy"), печи ("oven", "oven_fish") и работы ("brewing",
"cooking") восстанавливает rebuild().

Варка и готовка - «работа в доме» (character.house_work): идёт 30 секунд и
не выпускает из дома (bot/activity.py). Доделывает её tick_job раз в пару
секунд - по времени в БД, так что рестарт бота её не теряет.
"""

import random

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot.keyboards import world as kb
from bot.vk_media import photo_attachment
from bot.keyboards.world import add_miniapp_button
from bot.world_texts import FOREIGN_NPC_REJECTION
from game.combat import display
from game.economy import alchemy, cooking, fishing, herbalism
from game.economy import cooking_config as cc
from game.economy import fishing_config as fc
from game.world import grid
from models import Character
from bot import dailies_texts
from services import alchemy_service, cooking_service, daily_service, elixir_service, herb_service
from services import onboarding_service as onboarding_svc
from services import screen_service
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра

HOUSE_TEXT = "🏠 Дом\n\nТвои стены в городе. У окна печь, в углу стол с ретортами и склянками."
BUSY_TEXT = "🏠 Работа на огне. Дождись ее или брось - тогда все, что пошло в дело, пропадет."

#: Картинки в альбоме группы (tools/crafts_art_prompts.md, 2026-10-21).
HOUSE_PHOTO, OVEN_PHOTO, TABLE_PHOTO = "457239277", "457239278", "457239279"

BTN_HOUSE_BACK = "← Дом"
BTN_OVEN_BACK = "← Печь"
BTN_BREW_CANCEL = "✖️ Бросить варку"
BTN_COOK_CANCEL = "✖️ Бросить готовку"
#: Вариантов рыбы на экране выбора - чтобы клавиатура влезла в лимит VK.
FISH_CHOICES = 6

_bot_api = None
_rng = random.Random()


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def house_text() -> str:
    return HOUSE_TEXT


# --- Клавиатуры ---------------------------------------------------------------


#: Короткие подписи для кнопок стола и печи (2026-10-21): 10 рецептов по 3 в
#: ряд - 4 ряда, и «← Дом» виден без прокрутки. Полные названия - в тексте.
SHORT = {
    "heal_small": "🧪 Малое", "heal_medium": "🧪 Среднее", "heal_large": "🧪 Большое",
    "ashen_fever": "🔥 Лихорадка", "blood_for_blood": "🩸 Кровь", "ashen_haze": "🌫️ Морок",
    "shard_blood": "⚡ Осколки", "blood_clarity": "🧿 Ясность", "second_heart": "🛡️ Сердце",
    "last_breath": "💀 Вздох",
    "wormwood_soup": "🍲 Уха", "baked_gudgeon": "🐟 Пескарь", "orache_stew": "🥣 Похлебка",
    "smoked_tench": "🐠 Линь", "thistle_pie": "🥧 Пирог", "bloodwort_eel": "🍢 Угорь",
    "sturgeon_roast": "🍖 Жаркое", "coal_flounder": "🔥 Камбала", "deep_tear_root": "🍱 Слеза",
    "monolith_feast": "🍽 Пир",
}


def _rows_of_three(kb_: Keyboard, items: list[tuple[str, dict]]) -> None:
    for i, (label, payload) in enumerate(items):
        kb_.add(Text(label, payload=payload), color=KeyboardButtonColor.SECONDARY)
        if i % 3 == 2:
            kb_.row()
    if len(items) % 3:
        kb_.row()


def _with_back(kb_: Keyboard, label: str, payload: dict, miniapp: bool = True) -> str:
    if miniapp:
        add_miniapp_button(kb_)
        kb_.row()
    kb_.add(Text(label, payload=payload), color=KeyboardButtonColor.SECONDARY)
    return kb_.get_json()


BTN_MASTER = "✨ Мастерский отвар"
MASTER_DONE_TEXT = (
    "Камень шипит в котле, тварь растворяется без следа, пыль ложится на поверхность "
    "и гаснет. Когда пар уходит, на дне лежит перстень, а рядом - флакон с тёмным отваром.\n\n"
    "💍 Перстень Мастера - на пальце: всё, что добывают и делают ремёсла, теперь приходит вдвое.\n"
    "🧪 Эликсир Мастера - в сумке, в еде: выпей, когда будешь готов.\n"
    "👑 Новый титул: Мастер всех ремёсел."
)


def alchemy_keyboard(level: int, master: bool = False) -> str:
    """master - в сумке всё для мастерского рецепта (кнопка только тогда)."""
    kb_ = Keyboard(one_time=False)
    rows = [(SHORT[r.elixir_id], {"type": "brew", "id": r.elixir_id}) for r in alchemy.known(level)]
    if master:
        rows.append((BTN_MASTER, {"type": "brew_master"}))
    _rows_of_three(kb_, rows)
    return _with_back(kb_, BTN_HOUSE_BACK, {"type": "house_back"}, miniapp=False)


def oven_keyboard(level: int) -> str:
    kb_ = Keyboard(one_time=False)
    _rows_of_three(kb_, [(SHORT[d.dish_id], {"type": "cook", "id": d.dish_id}) for d in cooking.known(level)])
    return _with_back(kb_, BTN_HOUSE_BACK, {"type": "house_back"}, miniapp=False)


def fish_keyboard(dish: cc.Dish, options: list) -> str:
    kb_ = Keyboard(one_time=False)
    for i, opt in enumerate(options[:FISH_CHOICES]):
        mark = fc.GRADE_EMOJI.get(opt.grade, "")
        kb_.add(Text(
            f"{mark}{opt.fish.name} ×{opt.portions}".strip()[:40],
            payload={"type": "cook_fish", "d": dish.dish_id, "f": opt.fish.id, "g": opt.grade},
        ), color=KeyboardButtonColor.POSITIVE)
        if i % 2 == 1:
            kb_.row()
    if min(len(options), FISH_CHOICES) % 2 == 1:
        kb_.row()
    return _with_back(kb_, BTN_OVEN_BACK, {"type": "oven"}, miniapp=False)


def work_keyboard(character: Character | None = None) -> str:
    cooking_now = character is not None and cooking_service.cooking_now(character) is not None
    kb_ = Keyboard(one_time=False)
    kb_.add(Text(BTN_COOK_CANCEL if cooking_now else BTN_BREW_CANCEL, payload={"type": "brew_cancel"}),
            color=KeyboardButtonColor.NEGATIVE)
    return kb_.get_json()


def brewing_keyboard() -> str:
    """Старое имя: зовут площадь и тесты, когда в доме идёт работа."""
    return work_keyboard()


# --- Тексты: алхимия ----------------------------------------------------------


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


def brewed_text(result: alchemy_service.Brewed, character: Character | None = None) -> str:
    d = elixir_service.elixir_def(result.recipe.elixir_id)
    text = f"⚗️ Готово: {d.emoji} {d.name} ×{result.amount}, уже в инвентаре. Алхимия +{result.xp} опыта."
    if result.level_after > result.level_before:
        text += f"\n⚗️ Алхимия: {result.level_after} уровень."
    if result.unlocked:
        names = ", ".join(elixir_service.elixir_def(r.elixir_id).name for r in result.unlocked)
        text += f"\nНовые рецепты: {names}."
    if character is not None:
        text += "\n" + display.craft_xp_line(
            "⚗️", "Алхимия", character.alchemy_level, character.alchemy_xp, alchemy.xp_to_next(character.alchemy_level),
        )
    return text


# --- Тексты: кулинария --------------------------------------------------------


async def oven_text(db, character: Character) -> str:
    level = character.cooking_level
    bag = {h.id: n for h, n in await herb_service.get_bag(db, character.id)}
    xp = f" ({character.cooking_xp}/{cooking.xp_to_next(level)} опыта)" if cooking.xp_to_next(level) else ""
    lines = ["🔥 Печь", f"Кулинария: {level} ур.{xp}", f"Блюдо действует {cooking.food_minutes(level)} мин.", ""]
    for dish in cooking.known(level):
        d = cooking.dish_def(dish.dish_id)
        need = [f"рыба {dish.fish_tier}-го тира"]
        if dish.herb:
            h = herbalism.herb_def(dish.herb)
            need.append(f"{h.name} 1 (есть {bag.get(dish.herb, 0)})")
        need.append(f"{dish.gold} зол.")
        lines.append(f"{d.emoji} {d.name}: {', '.join(need)}. {cooking.buff_text(dish, 'common')}")
    nxt = cooking.next_locked(level)
    if nxt is not None:
        lines.append(f"🔒 Дальше: {cooking.dish_def(nxt.dish_id).name} с {nxt.level} ур.")
    lines += ["", "Чем тяжелее рыба, тем больше порций; чем лучше градация, тем сильнее блюдо."]
    return "\n".join(lines)


def fish_text(dish: cc.Dish, options: list) -> str:
    d = cooking.dish_def(dish.dish_id)
    if not options:
        return (f"{d.emoji} {d.name}: нужна рыба {dish.fish_tier}-го тира, хотя бы "
                f"{fishing.format_kg(cc.PORTION_GRAMS[dish.fish_tier])} кг одного вида и градации. В садке такой нет.")
    lines = [f"{d.emoji} {d.name} - какую рыбу взять?", ""]
    for opt in options[:FISH_CHOICES]:
        mark = fc.GRADE_EMOJI.get(opt.grade, "")
        lines.append(
            f"{mark}{opt.fish.name} ({fishing.grade_name(opt.grade)}, {fishing.format_kg(opt.grams)} кг) - "
            f"{opt.portions} порц., {cooking.buff_text(dish, opt.grade)}"
        )
    return "\n".join(lines)


def cooking_text(character: Character) -> str:
    found = cooking_service.cooking_now(character)
    name = cooking.dish_def(found[0].dish_id).name if found else "блюдо"
    return (f"🔥 В печи {name}. Готово через {alchemy_service.seconds_left(character)} сек.\n"
            "Выйти из дома до конца готовки нельзя. Бросишь - рыба, трава и золото пропадут.")


def cooked_text(result: cooking_service.Cooked, character: Character | None = None) -> str:
    d = cooking.dish_def(result.dish.dish_id)
    text = (f"🔥 Готово: {d.emoji} {d.name} ×{result.portions} · рыба {fishing.grade_name(result.grade)}. "
            f"Съесть - в мини-аппе (Инвентарь, «Еда») или командой /съесть. Кулинария +{result.xp} опыта.")
    if result.level_after > result.level_before:
        text += f"\n🔥 Кулинария: {result.level_after} уровень."
    if result.unlocked:
        text += "\nНовые рецепты: " + ", ".join(cooking.dish_def(x.dish_id).name for x in result.unlocked) + "."
    if character is not None:
        text += "\n" + display.craft_xp_line(
            "🔥", "Кулинария", character.cooking_level, character.cooking_xp, cooking.xp_to_next(character.cooking_level),
        )
    return text


def work_text(character: Character) -> str:
    return cooking_text(character) if cooking_service.cooking_now(character) else brewing_text(character)


async def rebuild(db, character: Character) -> tuple[str, str] | None:
    """Экраны дома - для /клавиатура и после рестарта."""
    if alchemy_service.is_working(character):
        return work_text(character), work_keyboard(character)
    if character.screen in ("alchemy", "brewing"):
        from services import master_recipe_service

        return await alchemy_text(db, character), alchemy_keyboard(
            character.alchemy_level, await master_recipe_service.ready(db, character),
        )
    if character.screen in ("oven", "oven_fish", "cooking"):
        return await oven_text(db, character), oven_keyboard(character.cooking_level)
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


async def _busy(message: Message, character: Character) -> bool:
    """Идёт работа - показать её вместо любого другого экрана дома."""
    if not alchemy_service.is_working(character):
        return False
    await message.answer(work_text(character), keyboard=work_keyboard(character))
    return True


@labeler.message(text=[kb.BTN_HOUSE])
async def open_house(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None or await _busy(message, character):
            return
        await screen_service.set_screen(db, character, "house")
        await db.commit()
    await message.answer(HOUSE_TEXT, keyboard=kb.house_keyboard(), attachment=photo_attachment(HOUSE_PHOTO))


@labeler.message(payload_contains={"type": "house_back"})
async def house_back(message: Message) -> None:
    await open_house(message)


# --- Алхимия ------------------------------------------------------------------


@labeler.message(text=[kb.BTN_ALCHEMY, kb.BTN_ALCHEMY_OLD])
async def open_alchemy(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None or await _busy(message, character):
            return
        await screen_service.set_screen(db, character, "alchemy")
        await db.commit()
        text = await alchemy_text(db, character)
        from services import master_recipe_service

        master = await master_recipe_service.ready(db, character)
    await message.answer(text, keyboard=alchemy_keyboard(character.alchemy_level, master),
                         attachment=photo_attachment(TABLE_PHOTO))


@labeler.message(payload_contains={"type": "brew_master"})
async def brew_master(message: Message) -> None:
    from services import master_recipe_service

    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None or await _busy(message, character):
            return
        level = character.alchemy_level
        try:
            await master_recipe_service.brew(db, character)
        except master_recipe_service.MasterError as exc:
            await db.rollback()
            await message.answer(str(exc), keyboard=alchemy_keyboard(level))
            return
        await db.commit()
    await message.answer(MASTER_DONE_TEXT, keyboard=alchemy_keyboard(level))


@labeler.message(payload_contains={"type": "brew"})
async def brew(message: Message) -> None:
    elixir_id = (message.get_payload_json() or {}).get("id")
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None or await _busy(message, character):
            return
        # Уровень - до отката: после rollback персонаж просрочен, и чтение
        # поля в асинхронной сессии падает (бот отвечал «кнопка устарела»).
        level = character.alchemy_level
        try:
            await alchemy_service.start(db, character, elixir_id)
        except alchemy_service.AlchemyError as exc:
            await db.rollback()
            await message.answer(str(exc), keyboard=alchemy_keyboard(level))
            return
        await screen_service.set_screen(db, character, "brewing")
        await db.commit()
    await message.answer(brewing_text(character), keyboard=work_keyboard(character))


# --- Печь ---------------------------------------------------------------------


@labeler.message(text=[kb.BTN_OVEN])
async def open_oven(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None or await _busy(message, character):
            return
        await screen_service.set_screen(db, character, "oven")
        await db.commit()
        text = await oven_text(db, character)
    await message.answer(text, keyboard=oven_keyboard(character.cooking_level),
                         attachment=photo_attachment(OVEN_PHOTO))


@labeler.message(payload_contains={"type": "oven"})
async def oven_back(message: Message) -> None:
    await open_oven(message)


@labeler.message(payload_contains={"type": "cook"})
async def choose_dish(message: Message) -> None:
    dish = cc.DISHES_BY_ID.get((message.get_payload_json() or {}).get("id"))
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None or dish is None or await _busy(message, character):
            return
        if dish.level > character.cooking_level:
            return
        options = await cooking_service.fish_options(db, character.id, dish)
        await screen_service.set_screen(db, character, "oven_fish")
        await db.commit()
    await message.answer(fish_text(dish, options), keyboard=fish_keyboard(dish, options))


@labeler.message(payload_contains={"type": "cook_fish"})
async def cook(message: Message) -> None:
    payload = message.get_payload_json() or {}
    async with get_session_factory()() as db:
        character = await _home_character(db, message)
        if character is None or await _busy(message, character):
            return
        level = character.cooking_level  # до отката, как в brew
        try:
            await cooking_service.start(db, character, payload.get("d"), payload.get("f"), payload.get("g"))
        except cooking_service.CookingError as exc:
            await db.rollback()
            await message.answer(str(exc), keyboard=oven_keyboard(level))
            return
        await screen_service.set_screen(db, character, "cooking")
        await db.commit()
    await message.answer(cooking_text(character), keyboard=work_keyboard(character))


# --- Отмена и фоновый шаг -----------------------------------------------------


@labeler.message(payload_contains={"type": "brew_cancel"})
async def work_cancel(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or not alchemy_service.is_working(character):
            return
        was_cooking = cooking_service.cooking_now(character) is not None
        alchemy_service.cancel(character)
        await screen_service.set_screen(db, character, "oven" if was_cooking else "alchemy")
        await db.commit()
        if was_cooking:
            text = f"🔥 Готовка брошена, рыба, трава и золото пропали.\n\n{await oven_text(db, character)}"
            keyboard = oven_keyboard(character.cooking_level)
        else:
            text = f"⚗️ Варка брошена, травы и золото пропали.\n\n{await alchemy_text(db, character)}"
            keyboard = alchemy_keyboard(character.alchemy_level)
    await message.answer(text, keyboard=keyboard)


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
                progress = await daily_service.record_craft(db, character, "brew")
                done.append((peer, f"{brewed_text(result, character)}\n\n{await alchemy_text(db, character)}",
                             alchemy_keyboard(character.alchemy_level), progress))
            for character in await cooking_service.due(db):
                result = await cooking_service.finish(db, character)
                if result is None:
                    continue
                await screen_service.set_screen(db, character, "oven")
                peer = await onboarding_svc.vk_id_for_character(db, character.id)
                progress = await daily_service.record_craft(db, character, "cook")
                done.append((peer, f"{cooked_text(result, character)}\n\n{await oven_text(db, character)}",
                             oven_keyboard(character.cooking_level), progress))
            await db.commit()
    except Exception:
        logger.exception("Дом: работа не доделалась")
        return
    for peer, text, keyboard, progress in done:
        if peer is None:
            continue
        try:
            await _bot_api.messages.send(peer_id=peer, random_id=0, message=text, keyboard=keyboard)
            notice = dailies_texts.progress_notice(progress)
            if notice:
                await _bot_api.messages.send(peer_id=peer, random_id=0, message=notice)
        except Exception:
            logger.warning("Дом: сообщение о работе не доставлено {}", peer)


# --- /съесть: еда без мини-аппа (2026-10-21) ------------------------------------


def _food_line(d, dish, grade, n) -> str:
    return f"{d.emoji} {d.name} (рыба {fishing.grade_name(grade)}) ×{n}: {cooking.buff_text(dish, grade)}"


@labeler.message(text=["/съесть", "/съесть <name>", "/eat", "/eat <name>"])
async def eat_command(message: Message, name: str | None = None) -> None:
    """Для тех, у кого не открывается мини-апп. Только вне боя и исследования,
    как кнопка «Съесть»: бафф ложится на следующий бой."""
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import world as world_handlers

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        food = await cooking_service.get_food(db, character.id)
        if not name:
            if not food:
                await message.answer("🍲 Еды в сумке нет. Блюда готовят в печи дома.")
                return
            lines = ["🍲 Еда в сумке:"] + [_food_line(*f) for f in food]
            lines.append("\nСъесть: /съесть и название, например /съесть " + food[0][0].name.lower())
            await message.answer("\n".join(lines))
            return
        if in_any_battle(message.peer_id) or world_handlers.is_busy(message.peer_id):
            await message.answer("🍲 Сейчас не до еды: сначала закончи бой или исследование.")
            return
        found = await cooking_service.find_food(db, character.id, name)
        names = {f[0].name for f in found}
        if not found:
            await message.answer("🍲 Такого блюда в сумке нет. Посмотреть, что есть: /съесть")
            return
        if len(names) > 1:
            await message.answer("🍲 Подходит несколько блюд: " + ", ".join(sorted(names)) + ". Напиши название точнее.")
            return
        d, dish, grade, _n = found[0]  # лучшая градация рыбы - первой
        try:
            await cooking_service.eat(db, character, dish.dish_id, grade)
        except cooking_service.CookingError as exc:
            await db.rollback()
            await message.answer(f"🍲 {exc}")
            return
        await db.commit()
        minutes = cooking_service.minutes_left(character)
    await message.answer(
        f"{d.emoji} Съедено: {d.name} (рыба {fishing.grade_name(grade)}). "
        f"{cooking.buff_text(dish, grade)} на {minutes} мин. Прежний бафф еды, если был, сменился этим."
    )
