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
from bot.miniapp_auth import VK_USER_ID_KEY
from bot.onboarding_texts import REGION_TITLES
from config import Settings
from game.content_loader import load_content
from models import BaseClass, Character, CharacterBuffPreset, User
from services import (
    daily_service,
    derived_stats_service,
    item_service,
    lootbox_service,
    preset_service,
    pvp_service,
    quest_service,
    song_service,
    story_service,
    trial_service,
)
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
        "region": character.region,
        "region_title": REGION_TITLES.get(character.region, "—") if character.region else "—",
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

    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)

        stats = character.stats
        if total == 0:
            return web.json_response({"error": "nothing_to_apply"}, status=400)
        if total > stats.unspent_points:
            return web.json_response({"error": "not_enough_points"}, status=400)

        for key, amount in increments.items():
            if amount == 0:
                continue
            attr = STAT_FIELDS[key]
            setattr(stats, attr, getattr(stats, attr) + amount)
        stats.unspent_points -= total

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
                    }
                    for s in states
                ],
            }
        )


async def handle_get_pvp_leaderboard(request: web.Request) -> web.Response:
    """Патч 22: топ-10 по PvP-победам + место игрока, если он вне десятки."""
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
                    {"rank": e.rank, "name": e.name, "wins": e.wins, "losses": e.losses, "title": e.title}
                    for e in entries
                ],
                "you": {"rank": rank, "wins": character.pvp_wins, "losses": character.pvp_losses},
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
                    "claimed_today": login_state.claimed_today,
                    "rewards": login_state.rewards,
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
                {"subclass": None, "preset_slots": character.preset_slots, "next_slot_cost": None, "presets": [], "buffs": []}
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
                "buffs": [
                    {"id": b.id, "name": b.name, "category": b.category, "unlocked": b.id in unlocked}
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
            await preset_service.switch_active_preset(session, character.id, preset_id)
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
    app.router.add_get("/api/miniapp/dailies", handle_get_dailies)
