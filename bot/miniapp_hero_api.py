"""Мини-апп, вкладка «Герой» (2026-10-22): пол персонажа и полка трофеев.

Силуэт и слоты снаряжения берут данные из инвентаря (/api/miniapp/inventory),
здесь - только то, чего там нет.
"""

from aiohttp import web
from sqlalchemy import or_, select

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import fishing
from game.economy import raid_archive_config as ac
from game.economy import raid_config as rc
from game.economy import raid_field_config as fc
from game.economy import raid_mill_config as mc
from game.economy import raid_trail_config as tc
from models import CharacterFishRecord, Inventory, Item, RaidRun
from services import item_service, title_service
from services.title_service import TITLE_NAMES

GENDERS = ("m", "f")

#: Рейды в порядке выхода: id рейда и уникальная вещь с его босса.
RAIDS = (
    (rc.RAID_PUPPET_THEATRE_ID, rc.RAID_UNIQUE_ITEM_ID),
    (fc.RAID_FIELD_ID, fc.RAID_UNIQUE_ITEM_ID),
    (ac.RAID_ARCHIVE_ID, ac.RAID_UNIQUE_ITEM_ID),
    (mc.RAID_MILL_ID, mc.RAID_UNIQUE_ITEM_ID),
    (tc.RAID_TRAIL_ID, tc.RAID_UNIQUE_ITEM_ID),
)


async def handle_post_gender(request: web.Request) -> web.Response:
    from bot import miniapp_api

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "bad_request"}, status=400)
    gender = body.get("gender") if isinstance(body, dict) else None
    if gender not in GENDERS:
        return web.json_response({"error": "bad_request"}, status=400)
    async with request.app[SESSION_FACTORY_KEY]() as session:
        character = await miniapp_api._load_character(session, request[VK_USER_ID_KEY])
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        # Один раз (2026-10-22, владелец): сменить пол пока нельзя.
        if character.gender is not None:
            return web.json_response({"error": "already_set", "gender": character.gender}, status=409)
        character.gender = gender
        await session.commit()
        return web.json_response({"gender": gender})


async def _raid_shelf(session, character_id: int) -> list[dict]:
    """Трофей рейда горит, если игрок был в победившем заходе (победы пишутся
    с 2026-10-22) или у него есть вещь с этого босса - так видны и прошлые
    победы того, кому досталась уникальная вещь."""
    won = set()
    rows = await session.execute(select(RaidRun.raid_id, RaidRun.members).where(RaidRun.status == "won"))
    for raid_id, members in rows:
        if character_id in (members or []):
            won.add(raid_id)
    uniques = item_service.unique_items()
    names = {uid: uniques[uid].name for _, uid in RAIDS if uid in uniques}
    owned_rows = await session.execute(
        select(Item.craft_source_id, Item.name)
        .join(Inventory, Inventory.item_id == Item.id)
        .where(
            Inventory.character_id == character_id,
            or_(Item.craft_source_id.in_(list(names)), Item.name.in_(list(names.values()))),
        )
    )
    owned = set()
    for source_id, name in owned_rows:
        owned.add(source_id or next((u for u, n in names.items() if n == name), None))
    shelf = []
    for raid_id, uid in RAIDS:
        shelf.append({
            "raid": raid_id,
            "icon": f"unique:{uid}",
            "name": names.get(uid, uid),
            "won": raid_id in won or uid in owned,
        })
    return shelf


async def handle_get_trophies(request: web.Request) -> web.Response:
    from bot import miniapp_api

    async with request.app[SESSION_FACTORY_KEY]() as session:
        character = await miniapp_api._load_character(session, request[VK_USER_ID_KEY])
        if character is None:
            return web.json_response({"error": "character_not_found"}, status=404)
        best = (await session.execute(
            select(CharacterFishRecord.fish_id, CharacterFishRecord.weight_grams)
            .where(CharacterFishRecord.character_id == character.id)
            .order_by(CharacterFishRecord.weight_grams.desc())
            .limit(1)
        )).first()
        best_fish = None
        if best is not None:
            definition = fishing.fish_def(best.fish_id)
            best_fish = {
                "name": definition.name if definition else best.fish_id,
                "emoji": definition.emoji if definition else "🐟",
                "weight": fishing.format_kg(best.weight_grams),
            }
        titles_open = len([t for t in await title_service.unlocked_ids(session, character.id) if t in TITLE_NAMES])
        shelf = await _raid_shelf(session, character.id)
        return web.json_response({
            "raids": shelf,
            "mobs_killed": character.mobs_killed,
            "pvp_wins": character.pvp_wins,
            "best_fish": best_fish,
            "titles_open": titles_open,
            "titles_total": len(TITLE_NAMES),
        })


def register_routes(app: web.Application) -> None:
    app.router.add_post("/api/miniapp/gender", handle_post_gender)
    app.router.add_get("/api/miniapp/trophies", handle_get_trophies)

