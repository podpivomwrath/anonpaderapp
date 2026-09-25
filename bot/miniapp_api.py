"""HTTP-эндпоинты мини-аппа (/api/miniapp/*).

Игрок определяется ТОЛЬКО из request[VK_USER_ID_KEY], положенного
miniapp_auth_middleware после проверки подписи — тело запроса на это никогда
не влияет.
"""

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.app_keys import SESSION_FACTORY_KEY, SETTINGS_KEY
from bot import dailies_texts
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import crafting
from services import naming
from bot.onboarding_texts import REGION_TITLES
from config import Settings
from game.content_loader import load_content
from game.economy import buff_descriptions
from models import BaseClass, Character, CharacterBuffPreset, User
from services import (
    daily_service,
    derived_stats_service,
    item_service,
    crown_service,
    leaderboard_service,
    lootbox_service,
    premium_service,
    preset_service,
    pvp_service,
    quest_service,
    song_service,
    story_service,
    stat_alloc_service,
    trial_service,
)
from game.economy import fishing as game_fishing
from game.economy import mining as game_mining
from services.preset_service import PresetValidationError
from services.wallet_service import NotEnoughCurrency, get_wallet

STAT_FIELDS = {
    "str": "strength",
    "agi": "agility",
    "int": "intellect",
    "vit": "vitality",
    "wil": "will",
}

CLASS_TITLES = {
    BaseClass.WARRIOR: "Воин",
    BaseClass.ROGUE: "Разбойник",
    BaseClass.MAGE: "Маг",
}


async def _load_character(session: AsyncSession, vk_user_id: int) -> Character | None:
    return await session.scalar(
        select(Character)
        .join(User, User.id == Character.user_id)
        .where(User.vk_id == vk_user_id, Character.creation_state.is_(None))
        .options(selectinload(Character.stats))
    )


def _character_payload(
    character: Character, gear_bonus: dict[str, int] | None = None, wallet=None, is_admin: bool = False,
) -> dict:
    stats = character.stats
    derived = derived_stats_service.compute(character, stats, gear_bonus)
    return {
        "name": character.name,
        "is_admin": is_admin,
        "title": daily_service.title_name(character),
        "base_class": character.base_class,
        "base_class_title": CLASS_TITLES.get(character.base_class, character.base_class),
        "subclass": character.subclass,
        # Название резолвит СЕРВЕР (патч 73): раньше клиент показывал
        # сырой id и в шапке висело «dark_mystic».
        "subclass_title": naming.subclass_title(character.subclass),
        # Венец топ-1 (патч 91). Держать можно сразу несколько досок, но
        # рамка в шапке одна: берём первую в порядке BOARDS, иначе она
        # менялась бы от показа к показу вслед за порядком выдачи из базы.
        "crowns": crown_service.crown_boards(character),
        "region": character.region,
        "region_title": REGION_TITLES.get(character.region, "-") if character.region else "-",
        "level": character.level,
        "farm_currency": wallet.farm_currency if wallet is not None else None,
        "donate_currency": wallet.donate_currency if wallet is not None else None,
        "stats": {
            "str": stats.strength,
            "agi": stats.agility,
            "int": stats.intellect,
            "vit": stats.vitality,
            "wil": stats.will,
        },
        "unspent_points": stats.unspent_points,
        # Патч 58: уровень рыбалки живёт в «Характеристиках», отдельной вкладки
        # у рыбалки нет. Потолка у него НЕТ — поэтому шкала всегда осмысленна,
        # в отличие от боевого уровня, который упирается в MAX_LEVEL.
        "fishing": {
            "level": character.fishing_level,
            "xp": character.fishing_xp,
            "xp_to_next": game_fishing.xp_to_next(character.fishing_level),
        },
        # Патч 59: уровень горного дела — там же, где рыбалка. Потолка нет.
        "mining": {
            "level": character.mining_level,
            "xp": character.mining_xp,
            "xp_to_next": game_mining.xp_to_next(character.mining_level),
        },
        "mobs_killed": character.mobs_killed,
        # Патч 32, баг 1: экипировка нужна фронтенду ОТДЕЛЬНО от derived — живой
        # предпросмотр (miniapp/src/formulas.js) пересчитывает derived сам при
        # вложении очка и без этого поля считал бы "после" без бонусов
        # экипировки, расходясь с "до" (derived ниже, который её уже учитывает).
        "gear_bonus": gear_bonus or {},
        "derived": {
            "max_hp": derived.max_hp,
            "damage": derived.damage,
            "crit_chance": derived.crit_chance,
            "mitigation": derived.mitigation,
            "control_resist": derived.control_resist,
            "support_power": derived.support_power,
            "dodge_chance": derived.dodge_chance,
            "ability_dodge_chance": derived.ability_dodge_chance,
            "poison_power": derived.poison_power,
        },
    }


def _is_admin(request: web.Request, vk_user_id: int) -> bool:
    """Только для видимости вкладки на фронтенде — НЕ источник прав. Каждый
    /api/miniapp/admin/* эндпоинт (bot/miniapp_admin_api.py) перепроверяет
    vk_id самостоятельно, этот флаг обмануть бесполезно."""
    settings: Settings = request.app[SETTINGS_KEY]
    return bool(settings.admin_vk_id) and vk_user_id == settings.admin_vk_id


async def handle_get_character(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        gear_bonus = await item_service.compute_gear_bonus(session, character.id)
        wallet = await get_wallet(session, character.id)
        await session.commit()
        return web.json_response(
            _character_payload(character, gear_bonus, wallet, _is_admin(request, vk_user_id))
        )


async def handle_post_stats(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)

    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)

    increments: dict[str, int] = {}
    for key in STAT_FIELDS:
        value = body.get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return web.json_response({"error": "invalid_increment"}, status=400)
        increments[key] = value

    total = sum(increments.values())

    # Раздавать очки в разгар боя нельзя: боец собирается снимком на старте,
    # так что на текущий бой это не влияет вовсе - игрок просто потратил бы
    # очки и не увидел эффекта. Остальные состояния (путь, добыча) очкам не
    # мешают: они ничего не ломают и ждать их незачем.
    from bot.battle_keyboard import in_any_battle

    if in_any_battle(vk_user_id):
        return web.json_response({"error": "in_battle"}, status=409)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)

        stats = character.stats
        if total == 0:
            return web.json_response({"error": "nothing_to_apply"}, status=400)
        try:
            await stat_alloc_service.allocate(session, stats, increments)
        except stat_alloc_service.NotEnoughPoints:
            return web.json_response({"error": "not_enough_points"}, status=400)

        gear_bonus = await item_service.compute_gear_bonus(session, character.id)
        wallet = await get_wallet(session, character.id)
        await session.commit()
        return web.json_response(
            _character_payload(character, gear_bonus, wallet, _is_admin(request, vk_user_id))
        )


async def handle_get_trials(request: web.Request) -> web.Response:
    """Патч 12: вкладка «Испытания» — все баффы подкласса персонажа с
    состоянием (открыт / прогресс). Пока подкласс не выбран — пустой список."""
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        if character.subclass is None:
            return web.json_response({"subclass": None, "trials": []})
        states = await trial_service.get_trial_states(session, character)
        catalog = load_content().buffs
        return web.json_response(
            {
                "subclass": character.subclass,
                "trials": [
                    {
                        "id": s.trial.id,
                        "buff_id": s.trial.buff_id,
                        "buff_name": s.buff_name,
                        "unlocked": s.unlocked,
                        "progress": s.progress,
                        "target": s.target,
                        "text": s.trial.text,
                        # Патч 48: описание микробаффа для раскрывающейся панели —
                        # генерируется из тех же значений, что читает бой (сухие
                        # цифры, без лора); implemented=false → фронт показывает
                        # "в разработке" вместо описания.
                        "category": buff_descriptions.category_label(catalog[s.trial.buff_id].category),
                        "implemented": catalog[s.trial.buff_id].implemented,
                        "description": buff_descriptions.describe(catalog[s.trial.buff_id]),
                    }
                    for s in states
                ],
            }
        )


async def handle_get_leaderboard(request: web.Request) -> web.Response:
    """Патч 58: общие топы — ?board=pvp|kills|fishing|fish_weight.

    Строка достижения («14 побед», «12,4 кг · Костяная щука») приходит с
    СЕРВЕРА уже готовой: клиент однажды уже пересказывал серверное правило
    своими словами и соврал (правило пресетов, патч 57).
    """
    vk_user_id = request[VK_USER_ID_KEY]
    board_id = request.query.get("board", leaderboard_service.BOARD_PVP)
    if board_id not in leaderboard_service.BOARDS:
        return web.json_response({"error": "unknown_board"}, status=400)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        entries = await leaderboard_service.board(session, board_id, limit=10)
        return web.json_response({
            "board": board_id,
            "boards": [
                {"id": b, "title": leaderboard_service.BOARD_TITLES[b]}
                for b in leaderboard_service.BOARDS
            ],
            "top": [
                {"rank": e.rank, "name": e.name, "value": e.value,
                 "title": e.title, "premium": e.premium,
                 # Значок класса в строке. Подкласс есть не у всех (до 30
                 # уровня его нет вовсе), поэтому клиенту отдаются оба, а
                 # он показывает подкласс, если тот выбран.
                 "base_class": e.base_class, "subclass": e.subclass}
                for e in entries
            ],
        })


async def handle_get_pvp_leaderboard(request: web.Request) -> web.Response:
    """Патч 22: топ-10 по PvP-победам + место игрока, если он вне десятки.

    Патч 58: мини-апп перешёл на общий /leaderboard. Этот эндпоинт оставлен
    намеренно — у игроков могут быть закешированы старые сборки фронтенда,
    и их экран не должен ломаться до обновления кеша.
    """
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        entries = await pvp_service.leaderboard(session, limit=10)
        rank = await pvp_service.rank_of(session, character)
        return web.json_response(
            {
                "top": [
                    {
                        "rank": e.rank, "name": e.name, "wins": e.wins, "losses": e.losses,
                        "title": e.title, "premium": e.premium,
                    }
                    for e in entries
                ],
                "you": {
                    "rank": rank, "wins": character.pvp_wins, "losses": character.pvp_losses,
                    "premium": premium_service.is_premium(character),
                },
            }
        )


async def _story_payload(session: AsyncSession, character: Character) -> dict:
    """Патч 23: секция «Сюжет» вкладки «Задания» — текущий активный квест
    (первый региональный квест «убей 10» читается через quest_service, как в
    bot/handlers/world.py::quest_reminder_text — та же логика, структурировано
    для JSON) + список пройденных актов региона."""
    row = await story_service.get_progress(session, character)
    line = story_service.get_line(character.region)
    passed_acts = [
        {"act": act.act, "title": act.title}
        for act in line.acts
        if row is not None and (row.completed or act.act < row.act)
    ]
    quest = await story_service.current_quest_def(session, character)
    if quest is None:
        return {"active_quest": None, "passed_acts": passed_acts}

    if quest.kind == "first_quest":
        peek = await quest_service.peek_progress(session, character)
        active_quest = None
        if peek is not None and peek.status != "completed":
            active_quest = {
                "title": peek.title,
                "text": f"{peek.progress_label}: {peek.progress}/{peek.target_count}",
                "target": None,
                "ready": peek.status == "ready",
            }
        return {"active_quest": active_quest, "passed_acts": passed_acts}

    target = None
    if quest.target_x is not None and quest.target_y is not None:
        target = {"x": quest.target_x, "y": quest.target_y, "label": quest.target_label}
    ready = row is not None and row.status == "ready"
    return {
        "active_quest": {
            "title": quest.title,
            "text": story_service.format_text(quest.assign_text, character),
            "target": target,
            "ready": ready,
        },
        "passed_acts": passed_acts,
    }


async def handle_get_dailies(request: web.Request) -> web.Response:
    """Патч 23: вкладка «Задания» — три секции (Сюжет/Ежедневные/Вход)."""
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        story = await _story_payload(session, character)
        overview = await daily_service.get_dailies_overview(session, character)
        login_state = await daily_service.get_login_state(session, character)
        lootbox_history = await lootbox_service.recent_history(session, character.id, limit=10)
        lootbox_counts = await lootbox_service.grade_counts(session, character.id)
        song_fragments = await song_service.fragments_display(session, character.id)
        song_complete = await song_service.is_complete(session, character.id)
        song_read = await song_service.already_read(session, character.id)
        return web.json_response(
            {
                "story": story,
                "song": {
                    "fragments": [
                        {"index": f.index, "seen": f.seen, "text": f.text}
                        for f in song_fragments
                    ],
                    "complete": song_complete,
                    "read": song_read,
                },
                "dailies": {
                    "quests": [
                        {
                            "id": q.quest_id, "title": q.title, "progress_label": q.progress_label,
                            "progress": q.progress, "target": q.target, "completed": q.completed,
                            "xp_reward": q.xp_reward, "gold_reward": q.gold_reward,
                        }
                        for q in overview.quests
                    ],
                    "daily_streak": overview.daily_streak,
                    "next_milestone_day": overview.next_milestone_day,
                    "next_milestone_reward": overview.next_milestone_reward,
                    # Готовая строка, а не сырая награда: собирать её на
                    # клиенте однажды уже пробовали - получалось
                    # «heal_small ×3» (патч 78).
                    "next_milestone_reward_text": dailies_texts.reward_preview(
                        overview.next_milestone_reward
                    ),
                    "seconds_until_reset": overview.seconds_until_reset,
                    "lootbox_history": [
                        {
                            "grade": h.grade, "emoji": h.emoji, "name": h.name,
                            "reward_summary": h.reward_summary,
                            "opened_at": h.opened_at.isoformat() if h.opened_at else None,
                        }
                        for h in lootbox_history
                    ],
                    "lootbox_counts": lootbox_counts,
                    "lootbox_grades": [
                        {"id": g.id, "emoji": g.emoji, "name": g.name}
                        for g in lootbox_service.grade_catalog()
                    ],
                },
                "login": {
                    "login_streak": login_state.login_streak,
                    "cycle_day": login_state.cycle_day,
                    "cycle_length": login_state.cycle_length,
                    "today_reward": login_state.today_reward,
                    "today_reward_text": dailies_texts.reward_preview(
                        login_state.today_reward
                    ),
                    "claimed_today": login_state.claimed_today,
                    "rewards": login_state.rewards,
                    # Что даёт каждый день цикла - подписью к клеткам
                    # календаря. Данные и так уходили, просто не читались.
                    "rewards_text": {
                        str(day): dailies_texts.reward_preview(reward)
                        for day, reward in login_state.rewards.items()
                    },
                },
            }
        )


def _inventory_payload(items: list) -> dict:
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
            }
            for item, equipped in items
        ]
    }


async def handle_get_inventory(request: web.Request) -> web.Response:
    """Патч 14, ч.2.1: вкладка «Инвентарь» — все предметы персонажа (и
    надетые, и лежащие в сумке), читаем из той же таблицы, что и чат."""
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        items = await item_service.get_inventory(session, character.id)
        return web.json_response(_inventory_payload(items))


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
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        entry = await item_service.get_inventory_entry(session, character.id, item_id)
        if entry is None or entry.equipped:
            return web.json_response({"error": "cannot_equip"}, status=400)
        await item_service.equip_item(session, character.id, item_id)
        await session.commit()
        items = await item_service.get_inventory(session, character.id)
        return web.json_response(_inventory_payload(items))


async def _ordered_presets(session: AsyncSession, character_id: int) -> list[CharacterBuffPreset]:
    return (
        await session.scalars(
            select(CharacterBuffPreset)
            .where(CharacterBuffPreset.character_id == character_id)
            .order_by(CharacterBuffPreset.id)
        )
    ).all()


async def handle_get_presets(request: web.Request) -> web.Response:
    """Патч 14, ч.3: секция «Пресеты» — слоты, состав, каталог баффов подкласса
    (открытые + неоткрытые с подсказкой категории). Заглушка до выбора подкласса."""
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        if character.subclass is None:
            return web.json_response(
                {"subclass": None, "preset_slots": character.preset_slots, "next_slot_cost": None,
                 "presets": [], "buffs": [], "rule_hint": ""}
            )

        presets = await _ordered_presets(session, character.id)
        catalog = load_content().buffs
        unlocked = await trial_service.unlocked_buff_ids(session, character.id)
        subclass_buffs = [b for b in catalog.values() if b.subclass == character.subclass]
        try:
            next_cost = preset_service.next_slot_cost(character.preset_slots)
        except PresetValidationError:
            next_cost = None

        return web.json_response(
            {
                "subclass": character.subclass,
                "preset_slots": character.preset_slots,
                "next_slot_cost": next_cost,
                "presets": [
                    {"id": p.id, "name": p.name, "buff_ids": p.buff_ids, "is_active": p.is_active}
                    for p in presets
                ],
                # Правило состава приходит с сервера: клиент его пересказывал
                # своими словами и врал про групповую поддержку.
                "rule_hint": preset_service.preset_rule_hint(buff_descriptions.CATEGORY_LABELS),
                "buffs": [
                    {
                        "id": b.id,
                        "name": b.name,
                        "category": b.category,
                        "category_label": buff_descriptions.category_label(b.category),
                        # без описания игрок собирает пресет вслепую, по одним названиям
                        "description": buff_descriptions.describe(b),
                        "unlocked": b.id in unlocked,
                    }
                    for b in subclass_buffs
                ],
            }
        )


async def handle_post_presets(request: web.Request) -> web.Response:
    """Создание/изменение состава пресета — платно (services.preset_service)."""
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)

    name = body.get("name")
    buff_ids = body.get("buff_ids")
    preset_id = body.get("preset_id")
    if not isinstance(name, str) or not name.strip() or not isinstance(buff_ids, list):
        return web.json_response({"error": "bad_request"}, status=400)
    if preset_id is not None and not isinstance(preset_id, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        if character.subclass is None:
            return web.json_response({"error": "no_subclass"}, status=400)

        catalog = load_content().buffs
        try:
            preset = await preset_service.save_preset(session, character, name, buff_ids, catalog, preset_id)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except NotEnoughCurrency:
            return web.json_response({"error": "not_enough_gold"}, status=400)
        await session.commit()
        return web.json_response({"id": preset.id, "name": preset.name, "buff_ids": preset.buff_ids})


async def handle_post_preset_switch(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    preset_id = body.get("preset_id") if isinstance(body, dict) else None
    if not isinstance(preset_id, int):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        try:
            await preset_service.switch_active_preset(session, character, preset_id)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        await session.commit()
        return web.json_response({"ok": True})


async def handle_post_preset_buy_slot(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        try:
            await preset_service.buy_preset_slot(session, character)
        except PresetValidationError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        except NotEnoughCurrency:
            return web.json_response({"error": "not_enough_gold"}, status=400)
        await session.commit()
        return web.json_response({"preset_slots": character.preset_slots})


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/character", handle_get_character)
    app.router.add_post("/api/miniapp/stats", handle_post_stats)
    app.router.add_get("/api/miniapp/trials", handle_get_trials)
    app.router.add_get("/api/miniapp/inventory", handle_get_inventory)
    app.router.add_post("/api/miniapp/equip", handle_post_equip)
    app.router.add_get("/api/miniapp/presets", handle_get_presets)
    app.router.add_post("/api/miniapp/presets", handle_post_presets)
    app.router.add_post("/api/miniapp/presets/switch", handle_post_preset_switch)
    app.router.add_post("/api/miniapp/presets/buy_slot", handle_post_preset_buy_slot)
    app.router.add_get("/api/miniapp/pvp_leaderboard", handle_get_pvp_leaderboard)
    app.router.add_get("/api/miniapp/leaderboard", handle_get_leaderboard)
    app.router.add_get("/api/miniapp/dailies", handle_get_dailies)
