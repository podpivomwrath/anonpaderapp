"""Мини-апп, вкладка «Инвентарь» и ремёсла в профиле: вещи и трофеи,
расходники, рыба, травы, еда, руда, ларцы; надеть, снять, открыть ларец, съесть.

Вынесено из bot/miniapp_api.py без изменений (2026-10-22, нарезка); маршруты
по-прежнему регистрирует miniapp_api.register_routes.
"""

import random
from aiohttp import web
from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import crafting
from services import naming, transfer_service
from models import Character
from services import elixir_service, item_service, lootbox_service, trophy_service
from game.economy import fishing as game_fishing
from game.economy import mining as game_mining
from bot import miniapp_api


_ELIXIR_CATEGORY_TITLES = {"heal": "Лечебное", "combat": "Боевой эликсир", "scroll": "Свиток"}


def _unique_flavor(item) -> str | None:
    """Описание уникальной вещи (content/items/unique_items.json, поле flavor)."""
    if item.rarity != item_service.UNIQUE_RARITY_ID:
        return None
    for unique in item_service.unique_items().values():
        if unique.name == item.name:
            return unique.flavor or None
    return None


def _trophies_payload(stock) -> list[dict]:
    """Реликвии на продажу: редкость по цвету кружка (он совпадает с
    редкостью вещей), описание из контента и цена у скупщика в своём
    городе - в чужом он платит меньше (FOREIGN_CITY_PRICE_PENALTY)."""
    by_emoji = {r.emoji: (rid, r.name) for rid, r in item_service.rarities().items()}
    out = []
    for trophy, count in stock:
        rarity_id, rarity_name = by_emoji.get(trophy.emoji, (None, None))
        out.append({
            "id": trophy.id,
            "name": trophy.name,
            "count": count,
            "icon": f"trophy:{trophy.id}",
            "rarity": rarity_id,
            "rarity_title": rarity_name,
            "description": trophy.description,
            "price": trophy.sell_price,
            "price_total": trophy.sell_price * count,
        })
    return out


def _consumables_payload(stock) -> list[dict]:
    return [
        {
            "id": elixir.id,
            "name": elixir.name,
            "count": count,
            "icon": f"elixir:{elixir.id}",
            "category_title": _ELIXIR_CATEGORY_TITLES.get(elixir.category, elixir.category),
            "description": elixir.description,
            # Количество клиент допишет после ползунка: «/передать <имя> <N>».
            "transfer_prefix": f"/передать {elixir.name}",
        }
        for elixir, count in stock
    ]


def _transfer_command(item) -> str | None:
    """Команда передачи - у всего, что можно передать. Надетое сюда
    попадает тоже: команда верная, просто сначала вещь надо снять."""
    from services import transfer_service

    if transfer_service.is_transferable(item, equipped=False) is not None:
        return None
    return transfer_service.command_for(item)


def _inventory_payload(items: list, level: int | None = None) -> dict:
    return {
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "slot": item.slot,
                "slot_title": item_service.SLOT_TITLES[item.slot],
                "rarity": item.rarity,
                "rarity_emoji": item_service.rarity_def(item.rarity).emoji if item.rarity else None,
                "ilvl": item.ilvl,
                "base_stats": item.base_stats,
                "power": item_service.item_power(item),
                "equipped": equipped,
                # Вещь выше уровня персонажа: с какого уровня её можно надеть.
                "need_level": (
                    item_service.required_level(item)
                    if level is not None and not item_service.can_wear(item, level) else None
                ),
                # Патч 72: можно ли отнести в мастерскую и что с ним там уже
                # сделали. Решает СЕРВЕР: клиент однажды уже пересказывал
                # серверное правило своими словами и врал (патч 57).
                "icon": naming.item_icon_key(item),
                # Словом, а не только цветом: свечение рамки показывает
                # редкость быстро, но различать оттенки умеют не все
                # (патч 79).
                "rarity_title": naming.rarity_title(item.rarity),
                "craftable": crafting.is_craftable(item.craft_source_id),
                "craft_spec": item.craft_spec,
                "craft_efficiency": item.craft_efficiency,
                "bound": item.bound,
                # Готовая команда передачи с номером этого экземпляра - её
                # копирует кнопка у каждой вещи, которую можно передать.
                # Решает сервер: правила «что можно передать» живут в
                # transfer_service, клиент их не пересказывает.
                "transfer_command": _transfer_command(item),
                "description": _unique_flavor(item),
                # Уникальную (с босса или кованую) можно разобрать в
                # звёздную пыль (2026-10-22). Правило - на сервере.
                "disassemble": item_service.can_disassemble(item),
            }
            for item, equipped in items
        ]
    }


async def _full_inventory(session, character_id: int) -> dict:
    """Экипировка + реликвии + расходники - один ответ и для показа, и после
    «Надеть»: иначе после надевания реликвии и расходники пропадали бы."""
    character = await session.get(Character, character_id)
    payload = _inventory_payload(
        await item_service.get_inventory(session, character_id),
        character.level if character is not None else None,
    )
    payload["trophies"] = _trophies_payload(await trophy_service.get_stock(session, character_id))
    payload["consumables"] = _consumables_payload(await elixir_service.get_stock(session, character_id))
    payload["chests"] = _chests_payload(await lootbox_service.closed_chests(session, character_id))
    # Садок и руда - тоже в сумке (2026-10-15, просьба владельца).
    from services import fishing_service, mining_service

    payload["fish"] = _fish_payload(await fishing_service.get_bag(session, character_id))
    if character is not None:
        payload["fish_bag"] = {
            "grams": await fishing_service.bag_total_grams(session, character_id),
            "capacity": game_fishing.bag_capacity_grams(character.fishing_level),
        }
    payload["ore"] = _ore_payload(await mining_service.get_ore(session, character_id))
    from services import herb_service

    payload["herbs"] = _herb_payload(await herb_service.get_bag(session, character_id))
    from services import cooking_service

    payload["food"] = _food_payload(await cooking_service.get_food(session, character_id))
    payload["food"] += await _bait_payload(session, character_id)
    await _master_payload(session, character_id, payload)
    if character is not None:
        payload["food_buff"] = food_buff_payload(character)
        payload["star_dust"] = character.star_dust or 0
    return payload


#: Свечение рамки по градации - те же цвета, что у редкости вещей.
_FISH_GLOW = {"big": "uncommon", "trophy": "epic", "legendary": "legendary"}
_ORE_GLOW = {"rare": "rare", "epic": "epic", "legendary": "legendary"}


def _fish_payload(bag) -> list[dict]:
    """Садок: стак «вид + градация» суммарным весом и цена у Иргала
    в своём городе (как на экране садка в чате)."""
    return [
        {
            "id": f"{fish.id}:{grade}",
            "name": fish.name,
            "icon": f"fish:{fish.id}",
            "rarity": _FISH_GLOW.get(grade),
            "grade_title": game_fishing.grade_name(grade),
            "weight": game_fishing.format_kg(grams),
            "price": game_fishing.price_of(fish.id, grams, grade),
            "count": 1,
            "description": fish.description,
            "transfer_command": transfer_service.fish_command(fish.name, grade),
        }
        for fish, grade, grams in bag
    ]


def _herb_payload(bag) -> list[dict]:
    """Сумка травника (2026-10-21). Картинок пока нет - иконка эмодзи."""
    return [
        {
            "id": herb.id, "name": herb.name, "emoji": herb.emoji, "icon": f"herb:{herb.id}",
            "count": count, "description": herb.description, "tier": herb.tier,
            "transfer_prefix": f"/передать {herb.name}",
        }
        for herb, count in bag
    ]


def herbalism_payload(character) -> dict:
    """Травничество: уровень, опыт и каталог - какие травы видны и с какого уровня."""
    from game.economy import herbal_config as hc
    from game.economy import herbalism

    return {
        "level": character.herbalism_level,
        "xp": character.herbalism_xp,
        "xp_to_next": herbalism.xp_to_next(character.herbalism_level),
        "max_level": hc.MAX_LEVEL,
        "double_pct": round(herbalism.double_chance(character.herbalism_level) * 100),
        "catalog": [
            {"id": h.id, "name": h.name, "emoji": h.emoji, "icon": f"herb:{h.id}", "level": herbalism.required_level(h),
             "known": herbalism.can_see(character.herbalism_level, h)}
            for h in herbalism.herb_defs_ordered()
        ],
    }


def _food_payload(food) -> list[dict]:
    """Еда (2026-10-21): стак по блюду и градации рыбы - от неё сила."""
    from game.economy import cooking, fishing

    return [
        {
            "id": f"{dish.dish_id}:{grade}", "dish": dish.dish_id, "grade": grade, "name": d.name,
            "emoji": d.emoji, "icon": f"dish:{dish.dish_id}", "count": count, "description": d.description,
            "grade_title": f"рыба {fishing.grade_name(grade)}", "effect": cooking.buff_text(dish, grade),
            "transfer_prefix": transfer_service.food_command(d.name, grade),
        }
        for d, dish, grade, count in food
    ]


async def _bait_payload(session, character_id: int) -> list[dict]:
    """Прикормка (2026-10-23): лежит в еде - применяется той же кнопкой."""
    from game.economy import craft_gear
    from services import craft_gear_service

    row = (await craft_gear_service.gear(session, character_id)).get("bait")
    if row is None or row.count <= 0:
        return []
    return [{
        "id": "bait:common", "dish": "bait", "grade": "common", "name": "Прикормка", "emoji": "🪱",
        "icon": "gear:bait", "count": row.count, "description": "Рассыпать у воды - рыба подходит ближе.",
        "grade_title": "для рыбалки", "effect": craft_gear.effect_line("bait", 1), "transfer_prefix": None,
    }]


async def _master_payload(session, character_id: int, payload: dict) -> None:
    """Находки мастерского рецепта (2026-10-23): склянка - среди расходников
    (без применения и без подсказки, зачем она), эликсир - в еде, пьётся."""
    from game.economy import craft_gear_config as gc
    from services import master_recipe_service

    vials = await master_recipe_service.count_of(session, character_id, gc.VIAL_ID)
    if vials:
        payload["consumables"].append({
            "id": gc.VIAL_ID, "name": "Пыльная склянка", "count": vials, "icon": "special:vial",
            "category_title": "Находка",
            "description": "Толстое зелёное стекло, на воске оттиск печати, которой никто не знает. Внутри пусто.",
            "transfer_prefix": None,
        })
    draughts = await master_recipe_service.count_of(session, character_id, gc.DRAUGHT_ID)
    if draughts:
        payload["food"].append({
            "id": f"{gc.DRAUGHT_ID}:common", "dish": gc.DRAUGHT_ID, "grade": "common",
            "name": master_recipe_service.DRAUGHT_TITLE, "emoji": "🧪", "icon": "special:draught",
            "count": draughts, "description": "Тёмный отвар со дна котла. Пьют один раз в жизни.",
            "grade_title": "навсегда",
            "effect": f"+{round(gc.DRAUGHT_STAT_PCT * 100)}% ко всем характеристикам навсегда",
            "transfer_prefix": None,
        })


def food_buff_payload(character) -> dict | None:
    from game.economy import cooking
    from services import cooking_service

    found = cooking_service.active(character)
    if found is None:
        return None
    dish, grade = found
    d = cooking.dish_def(dish.dish_id)
    return {"name": d.name, "emoji": d.emoji, "effect": cooking.buff_text(dish, grade),
            "minutes_left": cooking_service.minutes_left(character)}


def cooking_payload(character) -> dict:
    """Кулинария (2026-10-21): уровень и рецепты. Готовят в чате, в доме."""
    from game.economy import cooking, herbalism
    from game.economy import cooking_config as cc

    level = character.cooking_level
    recipes = []
    for dish in cc.DISHES:
        d = cooking.dish_def(dish.dish_id)
        needs = [f"рыба {dish.fish_tier}-го тира"]
        if dish.herb:
            needs.append(herbalism.herb_def(dish.herb).name)
        needs.append(f"{dish.gold} зол.")
        recipes.append({
            "id": dish.dish_id, "name": d.name, "emoji": d.emoji, "icon": f"dish:{dish.dish_id}", "level": dish.level,
            "known": dish.level <= level, "out": None,
            "needs": f"{', '.join(needs)} · {cooking.buff_text(dish, 'common')}",
        })
    return {
        "level": level, "xp": character.cooking_xp, "xp_to_next": cooking.xp_to_next(level),
        "max_level": cc.MAX_LEVEL, "has_house": character.has_house,
        "minutes": cooking.food_minutes(level), "recipes": recipes,
    }


async def handle_post_eat(request: web.Request) -> web.Response:
    """Съесть порцию (2026-10-21). Только вне боя и не посреди исследования:
    бафф ложится на следующий бой, а не меняет идущий."""
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import world as world_handlers
    from services import cooking_service

    vk_user_id = request[VK_USER_ID_KEY]
    async with request.app[SESSION_FACTORY_KEY]() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        if in_any_battle(vk_user_id) or world_handlers.is_busy(vk_user_id):
            return web.json_response({"error": "Сейчас не до еды: сначала закончи бой или исследование."}, status=409)
        try:
            body = await request.json() if request.can_read_body else {}
        except Exception:
            body = {}
        body = body if isinstance(body, dict) else {}
        from bot import buff_notice

        try:
            if body.get("dish") == "master_draught":
                from game.economy import craft_gear_config as gc
                from services import master_recipe_service

                try:
                    await master_recipe_service.drink(session, character)
                except master_recipe_service.MasterError as exc:
                    raise cooking_service.CookingError(str(exc)) from None
                note = f"🧪 Выпит Эликсир Мастера: +{round(gc.DRAUGHT_STAT_PCT * 100)}% ко всем характеристикам, навсегда."
            elif body.get("dish") == "bait":
                from services import craft_gear_service

                try:
                    await craft_gear_service.use_bait(session, character)
                except craft_gear_service.GearError as exc:
                    raise cooking_service.CookingError(str(exc)) from None
                note = buff_notice.line(character, "bait", "рассыпана")
            else:
                await cooking_service.eat(session, character, str(body.get("dish")), str(body.get("grade")))
                note = buff_notice.line(character, "food", "съедено")
        except cooking_service.CookingError as exc:
            await session.rollback()
            return web.json_response({"error": str(exc)}, status=409)
        await session.commit()
        buff_notice.tell(vk_user_id, note)
        return web.json_response(await _full_inventory(session, character.id))


def alchemy_payload(character) -> dict:
    """Алхимия (2026-10-21): уровень и рецепты. Варят в чате, в доме."""
    from game.economy import alchemy
    from game.economy import alchemy_config as ac
    from game.economy import herbalism
    from services import elixir_service

    level = character.alchemy_level
    recipes = []
    for r in ac.RECIPES:
        d = elixir_service.elixir_def(r.elixir_id)
        herbs = [f"{herbalism.herb_def(h).name} {n}" for h, n in r.herbs.items()]
        recipes.append({
            "id": r.elixir_id, "name": d.name if d else r.elixir_id, "emoji": d.emoji if d else "🧪",
            "level": r.level, "known": r.level <= level, "out": r.out,
            "needs": ", ".join(herbs + [f"{alchemy.gold_cost(r, level)} зол."]),
        })
    return {
        "level": level, "xp": character.alchemy_xp, "xp_to_next": alchemy.xp_to_next(level),
        "max_level": ac.MAX_LEVEL, "has_house": character.has_house,
        "discount_pct": round(ac.GOLD_DISCOUNT_PER_10 * (level // 10) * 100),
        "bonus_pct": round(alchemy.bonus_chance(level) * 100), "recipes": recipes,
    }


def _ore_payload(stock) -> list[dict]:
    return [
        {
            "id": f"{ore.id}:{grade}",
            "name": ore.name,
            "icon": f"ore:{ore.id}",
            "rarity": _ORE_GLOW.get(grade),
            "grade_title": game_mining.grade_name(grade),
            "count": count,
            "description": ore.description,
            "transfer_prefix": f"/передать {ore.name} {game_mining.grade_name(grade)}",
        }
        for ore, grade, count in stock
    ]


#: Ролл ларцов - системный генератор: исход не должен угадываться по seed.
_chest_rng = random.SystemRandom()


def _chests_payload(chests) -> list[dict]:
    """Ларцы - стопкой на вид: до открытия ларцы одного вида одинаковые,
    открывается самый старый. Шансы градаций - для подсказки."""
    counts: dict[str, int] = {}
    for chest in chests:
        kind = chest.kind or lootbox_service.ASHEN
        counts[kind] = counts.get(kind, 0) + 1
    out = []
    for kind, info in lootbox_service.CHEST_KINDS.items():
        if not counts.get(kind):
            continue
        grades = lootbox_service.grade_catalog(kind)
        total = sum(g.chance for g in grades) or 1
        out.append({
            # id "ash_chest" у Пепельного - прежний, на него завязан клиент.
            "id": "ash_chest" if kind == lootbox_service.ASHEN else f"chest_{kind}",
            "kind": kind,
            "name": info.name,
            "count": counts[kind],
            "icon": info.icon,
            # Ларцы кровавого разлома - легендарное свечение вокруг иконки.
            "rarity": None if kind == lootbox_service.ASHEN else "legendary",
            "description": info.description,
            "grades": [{"name": g.name, "icon": f"chest:{g.id}", "grade": g.id,
                        "chance": round(100 * g.chance / total, 1)} for g in grades],
        })
    return out


async def handle_post_chest_open(request: web.Request) -> web.Response:
    """Открыть ларец из сумки: исход решает сервер, рулетка его показывает."""
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        try:
            body = await request.json() if request.can_read_body else {}
        except Exception:
            body = {}
        kind = body.get("kind") if isinstance(body, dict) else None
        if kind not in lootbox_service.CHEST_KINDS:
            kind = lootbox_service.ASHEN
        try:
            chest, result = await lootbox_service.open_owned(session, character, None, _chest_rng, kind)
        except lootbox_service.ChestGone:
            await session.rollback()
            return web.json_response({"error": "no_chest"}, status=409)
        strip, win_index = lootbox_service.roulette_strip(result, chest.streak or 1, _chest_rng)
        await session.commit()
        inventory = await _full_inventory(session, character.id)
        return web.json_response({
            "strip": strip,
            "win_index": win_index,
            "result": {
                "grade": result.grade.id, "grade_name": result.grade.name, "lines": result.lines,
                "kind": kind, "title": lootbox_service.CHEST_KINDS[kind].name,
                "chest_icon": lootbox_service.CHEST_KINDS[kind].icon if kind != lootbox_service.ASHEN else None,
            },
            "inventory": inventory,
        })


async def handle_get_inventory(request: web.Request) -> web.Response:
    """Патч 14, ч.2.1: вкладка «Инвентарь» — все предметы персонажа (и
    надетые, и лежащие в сумке), читаем из той же таблицы, что и чат."""
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        return web.json_response(await _full_inventory(session, character.id))


async def handle_post_equip(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)

    item_id = body.get("item_id") if isinstance(body, dict) else None
    if not isinstance(item_id, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        from bot.battle_keyboard import in_any_battle

        if in_any_battle(vk_user_id):
            return web.json_response({"error": item_service.IN_BATTLE_TEXT}, status=409)
        entry = await item_service.get_inventory_entry(session, character.id, item_id)
        if entry is None or entry.equipped:
            return web.json_response({"error": "cannot_equip"}, status=400)
        try:
            await item_service.equip_item(session, character.id, item_id)
        except item_service.LevelTooLow as exc:
            await session.rollback()
            return web.json_response({"error": str(exc)}, status=400)
        await session.commit()
        return web.json_response(await _full_inventory(session, character.id))


async def handle_post_unequip(request: web.Request) -> web.Response:
    """Снять надетую вещь в сумку (патч 111)."""
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)

    item_id = body.get("item_id") if isinstance(body, dict) else None
    if not isinstance(item_id, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        from bot.battle_keyboard import in_any_battle

        if in_any_battle(vk_user_id):
            return web.json_response({"error": item_service.IN_BATTLE_TEXT}, status=409)
        if not await item_service.unequip_item(session, character.id, item_id):
            return web.json_response({"error": "cannot_unequip"}, status=400)
        await session.commit()
        return web.json_response(await _full_inventory(session, character.id))


async def handle_post_disassemble(request: web.Request) -> web.Response:
    """Разобрать уникальную вещь в звёздную пыль (2026-10-22). Подтверждение -
    в мини-аппе вторым нажатием; надетую не разобрать."""
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    item_id = body.get("item_id") if isinstance(body, dict) else None
    if not isinstance(item_id, int):
        return web.json_response({"error": "bad_request"}, status=400)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await miniapp_api._load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        dust = await item_service.disassemble_unique(session, character, item_id)
        if dust is None:
            await session.rollback()
            return web.json_response({"error": "Эту вещь разобрать нельзя: надетую сначала сними."}, status=400)
        await session.commit()
        return web.json_response(await _full_inventory(session, character.id))
