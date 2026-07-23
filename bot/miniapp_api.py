"""HTTP-эндпоинты мини-аппа (/api/miniapp/*).

Игрок определяется ТОЛЬКО из request[VK_USER_ID_KEY], положенного
miniapp_auth_middleware после проверки подписи — тело запроса на это никогда
не влияет.
"""

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from bot.onboarding_texts import REGION_TITLES
from models import BaseClass, Character, User
from services import derived_stats_service, item_service, trial_service

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


def _character_payload(character: Character, gear_bonus: dict[str, int] | None = None) -> dict:
    stats = character.stats
    derived = derived_stats_service.compute(character, stats, gear_bonus)
    return {
        "name": character.name,
        "base_class": character.base_class,
        "base_class_title": CLASS_TITLES.get(character.base_class, character.base_class),
        "subclass": character.subclass,
        "region": character.region,
        "region_title": REGION_TITLES.get(character.region, "—") if character.region else "—",
        "level": character.level,
        "stats": {
            "str": stats.strength,
            "agi": stats.agility,
            "int": stats.intellect,
            "vit": stats.vitality,
            "wil": stats.will,
        },
        "unspent_points": stats.unspent_points,
        "derived": {
            "max_hp": derived.max_hp,
            "damage": derived.damage,
            "crit_chance": derived.crit_chance,
            "mitigation": derived.mitigation,
            "control_resist": derived.control_resist,
            "support_power": derived.support_power,
        },
    }


async def handle_get_character(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    session_factory = request.app[SESSION_FACTORY_KEY]
    async with session_factory() as session:
        character = await _load_character(session, vk_user_id)
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        gear_bonus = await item_service.compute_gear_bonus(session, character.id)
        return web.json_response(_character_payload(character, gear_bonus))


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
        await session.commit()
        return web.json_response(_character_payload(character, gear_bonus))


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


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/character", handle_get_character)
    app.router.add_post("/api/miniapp/stats", handle_post_stats)
    app.router.add_get("/api/miniapp/trials", handle_get_trials)
