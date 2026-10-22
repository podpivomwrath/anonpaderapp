"""HTTP-эндпоинты мини-аппа (/api/miniapp/*).

Игрок определяется ТОЛЬКО из request[VK_USER_ID_KEY], положенного
miniapp_auth_middleware после проверки подписи — тело запроса на это никогда
не влияет.
"""

import random

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.app_keys import SESSION_FACTORY_KEY, SETTINGS_KEY
from bot import dailies_texts
from bot.miniapp_auth import VK_USER_ID_KEY
from game.combat import balance_config as bc
from game.economy import crafting
from services import naming, subclass_service, transfer_service
from bot.onboarding_texts import REGION_TITLES
from config import Settings
from game.content_loader import load_content
from game.economy import buff_descriptions
from models import BaseClass, Character, User
from services import (
    daily_service,
    elixir_service,
    derived_stats_service,
    experience_service,
    item_service,
    crown_service,
    leaderboard_service,
    lootbox_service,
    power_service,
    preset_service,
    quest_service,
    song_service,
    story_service,
    stat_alloc_service,
    title_service,
    trial_service,
    trophy_service,
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
    power=None, titles: list[dict] | None = None,
) -> dict:
    stats = character.stats
    derived = derived_stats_service.compute(character, stats, gear_bonus)
    return {
        "name": character.name,
        "is_admin": is_admin,
        "title": daily_service.title_name(character),
        # Тир - цвет титула в шапке; titles - открытые титулы для подменю.
        "title_tier": title_service.tier_of(character.active_title_id) if daily_service.title_name(character) else None,
        "titles": titles or [],
        "base_class": character.base_class,
        "base_class_title": CLASS_TITLES.get(character.base_class, character.base_class),
        "subclass": character.subclass,
        # Название резолвит СЕРВЕР (патч 73): раньше клиент показывал
        # сырой id и в шапке висело «dark_mystic».
        "subclass_title": naming.subclass_title(character.subclass),
        # Пул пресетов: подкласс или базовый класс после отказа (2026-10-20).
        "buff_pool": subclass_service.buff_pool(character),
        "subclass_declined": subclass_service.declined(character),
        # Венец топ-1 (патч 91). Держать можно сразу несколько досок, но
        # рамка в шапке одна: берём первую в порядке BOARDS, иначе она
        # менялась бы от показа к показу вслед за порядком выдачи из базы.
        "crowns": crown_service.crown_boards(character),
        # Рамка выбирается, бонусы действуют ВСЕ. Подменю приходит готовыми
        # строками: формат принадлежит серверу (патч 57).
        "crown_frame": crown_service.frame_board(character),
        "crown_menu": crown_service.menu(character),
        "region": character.region,
        "region_title": REGION_TITLES.get(character.region, "-") if character.region else "-",
        "level": character.level,
        # Кольцо опыта вокруг эмблемы (2026-10-22). На потолке уровня - None.
        "xp": character.experience,
        "xp_to_next": experience_service.xp_to_next(character.level) if character.level < bc.MAX_LEVEL else None,
        "gender": character.gender or "m",
        # Гильдии: вкладка видна с 20 уровня - и всегда тому, кто уже в гильдии.
        "in_guild": character.guild_id is not None,
        # Патч 111: Мощь - одно число силы персонажа (services/power_service.py).
        "power": power.total if power is not None else None,
        "power_parts": {
            "stats": power.stats, "gear": power.gear,
            "subclass_pct": round(power.subclass_bonus * 100), "buffs": power.buffs,
            "buff_pct": round(power_service.PER_BUFF_BONUS * 100),
        } if power is not None else None,
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
        # Травничество (2026-10-21): с потолком, в отличие от рыбалки и руды.
        "herbalism": herbalism_payload(character),
        "alchemy": alchemy_payload(character),
        "cooking": cooking_payload(character),
        "mobs_killed": character.mobs_killed,
        # Патч 32, баг 1: экипировка нужна фронтенду ОТДЕЛЬНО от derived — живой
        # предпросмотр (miniapp/src/formulas.js) пересчитывает derived сам при
        # вложении очка и без этого поля считал бы "после" без бонусов
        # экипировки, расходясь с "до" (derived ниже, который её уже учитывает).
        "gear_bonus": gear_bonus or {},
        # Что игрок уже видел в мини-аппе и включён ли звук (handle_post_ui).
        "ui": dict(character.ui_flags or {}),
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
    from services import staff

    return staff.has_panel_access(settings, vk_user_id)


async def handle_post_terms(request: web.Request) -> web.Response:
    """Игрок нажал «Принимаю» в мини-аппе или на сайте (2026-10-15)."""
    from services import terms_service

    async with request.app[SESSION_FACTORY_KEY]() as session:
        await terms_service.accept(session, request[VK_USER_ID_KEY])
        await session.commit()
    return web.json_response({"ok": True})


async def handle_get_character(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            # Новичок без персонажа видит в мини-аппе страницу «создай персонажа
            # в диалоге», а не ошибку (2026-10-12). in_creation - начал и
            # бросил на полпути: ему - «вернись и продолжи».
            in_creation = await session.scalar(
                select(Character.id).join(User, User.id == Character.user_id)
                .where(User.vk_id == vk_user_id, Character.creation_state.is_not(None))
            ) is not None
            return web.json_response(
                {"error": "character_not_found", "in_creation": in_creation}, status=404,
            )
        gear_bonus = await item_service.compute_gear_bonus(session, character.id)
        wallet = await get_wallet(session, character.id)
        power = await power_service.power_of(session, character)
        titles = await title_service.menu(session, character)
        await session.commit()
        return web.json_response(
            _character_payload(character, gear_bonus, wallet, _is_admin(request, vk_user_id), power, titles)
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
        power = await power_service.power_of(session, character)
        titles = await title_service.menu(session, character)
        await session.commit()
        return web.json_response(
            _character_payload(character, gear_bonus, wallet, _is_admin(request, vk_user_id), power, titles)
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
        if subclass_service.buff_pool(character) is None:
            return web.json_response({"subclass": None, "trials": []})
        states = await trial_service.get_trial_states(session, character)
        catalog = load_content().buffs
        return web.json_response(
            {
                "subclass": subclass_service.buff_pool(character),
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


async def handle_post_crown_frame(request: web.Request) -> web.Response:
    """Какую рамку носить. {"board": "pvp"} или {"board": null} — снять."""
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)

    board = body.get("board")
    if board is not None and not isinstance(board, str):
        return web.json_response({"error": "bad_request"}, status=400)

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        # Венец могли отобрать между открытием подменю и нажатием: выбор
        # чужой рамки отклоняем, а не молча показываем её.
        if not crown_service.set_frame(character, board):
            return web.json_response({"error": "crown_not_held"}, status=400)
        await session.commit()
        return web.json_response({
            "crown_frame": crown_service.frame_board(character),
            "crown_menu": crown_service.menu(character),
        })


async def handle_post_title(request: web.Request) -> web.Response:
    """Какой титул носить. {"title_id": "chronicler"} или {"title_id": null} - без титула."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)
    title_id = body.get("title_id")
    if title_id is not None and not isinstance(title_id, str):
        return web.json_response({"error": "bad_request"}, status=400)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, request[VK_USER_ID_KEY])
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        if not await title_service.set_active(session, character, title_id):
            return web.json_response({"error": "title_locked"}, status=400)
        titles = await title_service.menu(session, character)
        await session.commit()
        return web.json_response({
            "title": daily_service.title_name(character),
            "title_tier": title_service.tier_of(character.active_title_id),
            "titles": titles,
        })


#: Флаги мини-аппа, которые клиент может выставить: что игрок уже видел и
#: звук. Остальное отбрасывается - это не хранилище для чего попало.
# safe_route (2026-10-13) - безопасный путь верхом: включают на карте,
# действует и при отправке маунта из чата.
#: fish_auto_keep (2026-10-21) - вытащенная рыба сразу в садок, без «Отпустить».
UI_FLAGS = {"intro": int, "tour": int, "sound": bool, "safe_route": bool, "fish_auto_keep": bool}
UI_HINTS_MAX = 32


async def handle_post_ui(request: web.Request) -> web.Response:
    """{"set": {"intro": 1, "sound": false}, "hint": "map"} - отметить, что
    игрок видел вступление, тур или подсказку вкладки; выбрать звук."""
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    if not isinstance(body, dict):
        return web.json_response({"error": "bad_request"}, status=400)
    updates = body.get("set") or {}
    hint = body.get("hint")
    if not isinstance(updates, dict) or (hint is not None and not isinstance(hint, str)):
        return web.json_response({"error": "bad_request"}, status=400)
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, request[VK_USER_ID_KEY])
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        flags = dict(character.ui_flags or {})
        for key, kind in UI_FLAGS.items():
            value = updates.get(key)
            if isinstance(value, kind) and not (kind is int and isinstance(value, bool)):
                flags[key] = value
        if hint and len(hint) <= 24:
            hints = list(flags.get("hints") or [])
            if hint not in hints and len(hints) < UI_HINTS_MAX:
                hints.append(hint)
            flags["hints"] = hints
        character.ui_flags = flags  # новый dict: JSON-поле не следит за изменением на месте
        await session.commit()
        return web.json_response({"ui": flags})


async def handle_post_glance(request: web.Request) -> web.Response:
    """Секрет «Внимательный»: мини-апп зовёт сюда после 100 нажатий подряд на
    трещину Монолита. Проверить сами нажатия сервер не может - это пасхалка
    без силы, титул только для вида. Повторный вызов ничего не меняет."""
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, request[VK_USER_ID_KEY])
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        fresh = not await title_service.has_unlocked(session, character.id, "attentive")
        if fresh:
            await title_service.unlock(session, character, "attentive")
            await session.commit()
    return web.json_response({"ok": True, "fresh": fresh})


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
        powers = {}
        if board_id in leaderboard_service.COMBAT_BOARDS:
            for e in entries:
                if e.character_id is not None:
                    powers[e.character_id] = await power_service.power_by_id(session, e.character_id)
        from game.economy import crown_config as cc

        frames = await crown_service.frames_by_id(session, [e.character_id for e in entries])
        return web.json_response({
            "board": board_id,
            "boards": [
                {"id": b, "title": leaderboard_service.BOARD_TITLES[b]}
                for b in leaderboard_service.BOARDS
            ],
            # Подсказка «?»: за что место и что даёт венец первого места.
            "crown": {
                "rule": leaderboard_service.BOARD_RULES[board_id],
                "title": cc.CROWN_TITLES[board_id],
                "effect": cc.CROWN_EFFECTS[board_id],
                "all": [
                    {"board": leaderboard_service.BOARD_TITLES[b], "title": cc.CROWN_TITLES[b],
                     "effect": cc.CROWN_EFFECTS[b]}
                    for b in leaderboard_service.BOARDS
                ],
            },
            "top": [
                {"rank": e.rank, "name": e.name, "value": e.value,
                 "title": e.title, "title_tier": e.title_tier, "premium": e.premium,
                 # Значок класса в строке. Подкласс есть не у всех (до 30
                 # уровня его нет вовсе), поэтому клиенту отдаются оба, а
                 # он показывает подкласс, если тот выбран.
                 "base_class": e.base_class, "subclass": e.subclass,
                 # Патч 111: Мощь рядом с ником - только в боевых топах.
                 "power": powers.get(e.character_id),
                 # Рамка венца, которую носит игрок (своя у каждого).
                 "crown_frame": frames.get(e.character_id)}
                for e in entries
            ],
        })


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
        lootbox_history = await lootbox_service.recent_history(session, character.id, limit=5)
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
                # Летопись: титулы - открытые и как получить остальные.
                "titles": await title_service.catalog(session, character),
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


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/character", handle_get_character)
    app.router.add_post("/api/miniapp/stats", handle_post_stats)
    app.router.add_post("/api/miniapp/crown-frame", handle_post_crown_frame)
    app.router.add_post("/api/miniapp/glance", handle_post_glance)
    app.router.add_post("/api/miniapp/title", handle_post_title)
    app.router.add_post("/api/miniapp/ui", handle_post_ui)
    app.router.add_get("/api/miniapp/trials", handle_get_trials)
    app.router.add_get("/api/miniapp/inventory", handle_get_inventory)
    app.router.add_post("/api/miniapp/terms", handle_post_terms)
    app.router.add_post("/api/miniapp/equip", handle_post_equip)
    app.router.add_post("/api/miniapp/unequip", handle_post_unequip)
    app.router.add_post("/api/miniapp/chest/open", handle_post_chest_open)
    app.router.add_post("/api/miniapp/eat", handle_post_eat)
    app.router.add_get("/api/miniapp/presets", handle_get_presets)
    app.router.add_post("/api/miniapp/presets", handle_post_presets)
    app.router.add_post("/api/miniapp/presets/switch", handle_post_preset_switch)
    app.router.add_post("/api/miniapp/presets/buy_slot", handle_post_preset_buy_slot)
    app.router.add_get("/api/miniapp/leaderboard", handle_get_leaderboard)
    app.router.add_get("/api/miniapp/dailies", handle_get_dailies)


# Нарезка (2026-10-22): этот блок живёт в bot.miniapp_presets_api.
# Старые адреса (miniapp_api.X в других модулях и тестах) работают через ссылку.
from bot.miniapp_presets_api import (  # noqa: E402,F401
    _in_battle,
    handle_get_presets,
    handle_post_preset_buy_slot,
    handle_post_preset_switch,
    handle_post_presets,
)


# Нарезка (2026-10-22): этот блок живёт в bot.miniapp_inventory_api.
# Старые адреса (miniapp_api.X в других модулях и тестах) работают через ссылку.
from bot.miniapp_inventory_api import (  # noqa: E402,F401
    _ELIXIR_CATEGORY_TITLES,
    _FISH_GLOW,
    _ORE_GLOW,
    _chest_rng,
    _chests_payload,
    _consumables_payload,
    _fish_payload,
    _food_payload,
    _full_inventory,
    _herb_payload,
    _inventory_payload,
    _ore_payload,
    _transfer_command,
    _trophies_payload,
    _unique_flavor,
    alchemy_payload,
    cooking_payload,
    food_buff_payload,
    handle_get_inventory,
    handle_post_chest_open,
    handle_post_eat,
    handle_post_equip,
    handle_post_unequip,
    herbalism_payload,
)
