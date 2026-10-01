"""Эндпоинты гильдий: /api/miniapp/guild*.

GET /guild - всё состояние для вкладки «Гильдия» одним ответом.
GET /guild/tree - древо (почти двести узлов с координатами - отдельно,
чтобы не гонять его с каждым действием).
POST /guild/action {"action": ..., ...} - любое действие. В ответ - новое
состояние целиком: клиенту не нужно знать, что именно поменялось.

Отказ - 409 с готовым текстом для игрока (GuildError). Личность - только из
request[VK_USER_ID_KEY], как во всём мини-аппе.
"""

from aiohttp import web
from loguru import logger

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.economy import guild_config as gc
from game.economy import mining
from game.world import grid
from models import Character, Guild, GuildCell
from services import (
    guild_boss_service,
    guild_quest_service,
    guild_season_service,
    guild_service,
    guild_siege_service,
    guild_territory_service,
    guild_tree_service,
    item_service,
    mining_service,
    naming,
    wallet_service,
)
from services import onboarding_service as onboarding_svc
from services.guild_service import GuildError, aware

STAT_TITLES = {"str": "Сила", "agi": "Ловкость", "int": "Интеллект", "vit": "Выносливость", "wil": "Воля"}


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _iso(moment) -> str | None:
    moment = aware(moment)
    return moment.isoformat() if moment else None


def _ore_line(ore_id: str, grade: str, count: int) -> dict:
    ore = mining.ore_def(ore_id)
    return {
        "ore_id": ore_id, "grade": grade, "count": count,
        "name": ore.name if ore else ore_id, "emoji": ore.emoji if ore else "",
        "tier": ore.tier if ore else 0, "grade_name": mining.grade_name(grade),
    }


def _ore_name(ore_id: str) -> str:
    ore = mining.ore_def(ore_id)
    return ore.name if ore else ore_id


def _quote(q) -> dict:
    return {"gold": q.gold, "ore": _ore_name(q.ore_id), "ore_count": q.ore_count, "hours": q.hours}


def _perms(member) -> dict:
    rank = member.rank
    return {
        "treasury": guild_service.can_manage_treasury(member),
        "invite": gc.RANK_ORDER[rank] >= gc.RANK_ORDER[gc.RANK_VETERAN],
        "applications": gc.RANK_ORDER[rank] >= gc.RANK_ORDER[gc.RANK_OFFICER],
        "leader": rank == gc.RANK_LEADER,
    }


async def _no_guild_state(db, character: Character) -> dict:
    wallet = await wallet_service.get_wallet(db, character.id)
    invites = await guild_service.invites_for(db, character.id)
    directory = await guild_service.directory(db)
    return {
        "in_guild": False,
        "level": character.level,
        "gems": wallet.donate_currency,
        "found_cost": gc.FOUND_COST_GEMS,
        "found_min_level": gc.FOUND_MIN_LEVEL,
        "rejoin_wait_hours": round(guild_service.rejoin_wait_hours(character), 1),
        "invites": [
            {"guild_id": g.id, "name": g.name, "tag": g.tag, "level": g.level, "kind": i.kind}
            for i, g in invites
        ],
        "directory": [
            {"id": g.id, "name": g.name, "tag": g.tag, "level": g.level, "members": count,
             "cap": gc.member_cap(g.level), "crown": guild_season_service.has_crown(g)}
            for g, count in directory
        ],
    }


async def _cell_payload(db, guild: Guild, cell: GuildCell, character: Character, gate_ids: set[int]) -> dict:
    buildings = await guild_territory_service.buildings_of(db, cell.id)
    by_type = {b.building: b for b in buildings}
    mine = mining.mine_by_id(cell.mine_id) if cell.mine_id else None
    rows = []
    for building in gc.BUILDINGS:
        current = by_type.get(building)
        max_level = guild_territory_service.building_max_level(cell, building)
        if max_level == 0 and current is None:
            continue
        level = current.level if current else 0
        next_level = level + 1
        rows.append({
            "building": building, "title": gc.BUILDING_TITLES[building],
            "emoji": gc.BUILDING_EMOJI[building], "level": level, "max": max_level,
            "built": current is not None,
            "upgrading_to": current.upgrading_to if current else None,
            "done_at": _iso(current.done_at) if current else None,
            "next": _quote(guild_territory_service.quote(guild, building, next_level))
            if next_level <= max_level else None,
        })
    upgrade = None
    index = gc.BASE_ORDER.index(cell.base_tier)
    if cell.status == "held" and index + 1 < len(gc.BASE_ORDER):
        target = gc.BASE_ORDER[index + 1]
        gold, (ore_id, ore_count), hours = gc.BASE_UPGRADE_COST[target]
        upgrade = {
            "to": target, "title": gc.BASE_TITLES[target], "gold": gold,
            "ore": _ore_name(ore_id), "ore_count": ore_count, "hours": hours,
            "level_needed": gc.BASE_UNLOCK_LEVEL[target],
        }
    return {
        "id": cell.id, "x": cell.x, "y": cell.y, "status": cell.status,
        "ring": grid.ring_tier(cell.x, cell.y),
        "mine": mine.name if mine else None,
        "base_tier": cell.base_tier, "base_title": gc.BASE_TITLES[cell.base_tier],
        "slots": gc.BASE_SLOTS[cell.base_tier], "used_slots": len(buildings),
        "claim_progress": cell.claim_progress, "claim_needed": cell.claim_needed,
        "claim_expires_at": _iso(cell.claim_expires_at),
        "shield_until": _iso(cell.shield_until),
        "upgrade_to": cell.upgrade_to, "upgrade_done_at": _iso(cell.upgrade_done_at),
        "upgrade": upgrade,
        "buildings": rows,
        "gates": cell.id in gate_ids,
        "here": (character.pos_x, character.pos_y) == (cell.x, cell.y),
    }


async def _here_payload(db, guild: Guild, character: Character) -> dict:
    """Что можно сделать на клетке, где стоит игрок: знамя или осада."""
    x, y = character.pos_x, character.pos_y
    if x is None:
        return {}
    cell = await guild_territory_service.cell_at(db, x, y)
    result: dict = {"x": x, "y": y}
    if cell is None:
        reason = guild_territory_service.claim_reason(x, y)
        mine = mining.mine_at(x, y)
        cells = await guild_territory_service.cells_of(db, guild.id)
        tier = grid.ring_tier(x, y)
        ore = gc.CLAIM_ORE.get(tier)
        result["banner"] = {
            "reason": reason,
            "mine": mine.name if mine else None,
            "cost": gc.banner_cost(mine is not None, len(cells)),
            "ore": _ore_name(ore[0]) if ore else None,
            "ore_count": ore[1] * (gc.CLAIM_ORE_MINE_MULT if mine else 1) if ore else 0,
            "explorations": gc.CLAIM_EXPLORATIONS,
            "hours": gc.CLAIM_HOURS,
        }
        return result
    owner = await db.get(Guild, cell.guild_id)
    result["owner"] = {"tag": owner.tag, "name": owner.name, "own": owner.id == guild.id}
    if owner.id != guild.id and cell.status == "held":
        result["siege"] = {
            "cell_id": cell.id, "base_title": gc.BASE_TITLES[cell.base_tier],
            "cost": guild_siege_service.siege_cost(guild, cell.base_tier),
            "shield_until": _iso(cell.shield_until),
            "starts_at": _iso(guild_siege_service.next_window(owner.siege_hour)),
        }
    return result


async def _state(db, character: Character) -> dict:
    guild = await guild_service.guild_of(db, character)
    if guild is None:
        return await _no_guild_state(db, character)
    await guild_territory_service.complete_due(db)
    member = await guild_service.membership(db, character.id)
    wallet = await wallet_service.get_wallet(db, character.id)
    rows = await guild_service.members(db, guild.id)
    week = guild_service.week_start_msk()
    cells = await guild_territory_service.cells_of(db, guild.id)
    gate_ids = {c.id for c in await guild_territory_service.gate_targets(db, guild.id)}
    cap = await guild_service.capacity(db, guild)
    held_cells = [c for c in cells if not c.mine_id]
    held_mines = [c for c in cells if c.mine_id]
    sieges = []
    for siege in await guild_siege_service.recent_of(db, guild.id):
        attacking = siege.attacker_guild_id == guild.id
        enemy = await db.get(Guild, siege.defender_guild_id if attacking else siege.attacker_guild_id)
        sieges.append({
            "id": siege.id, "role": "attack" if attacking else "defense", "x": siege.x, "y": siege.y,
            "enemy": f"[{enemy.tag}] {enemy.name}" if enemy else "?", "status": siege.status,
            "starts_at": _iso(siege.starts_at), "result": siege.result,
        })
    standings = await guild_season_service.standings(db)
    place = next((i + 1 for i, (g, _p) in enumerate(standings) if g.id == guild.id), None)
    boss = await guild_boss_service.active_boss(db, guild.id)
    my_ore = await mining_service.get_ore(db, character.id)
    my_items = [
        item for item, equipped in await item_service.get_inventory(db, character.id)
        if not equipped and not item.bound and not item.admin_only
    ]
    stored = await guild_service.stored_items(db, guild.id)
    here_cell = await guild_territory_service.cell_at(db, character.pos_x, character.pos_y) \
        if character.pos_x is not None else None
    gates = []
    if here_cell is not None and here_cell.id in gate_ids:
        gates = [
            {"cell_id": c.id, "x": c.x, "y": c.y}
            for c in await guild_territory_service.gate_targets(db, guild.id) if c.id != here_cell.id
        ]
    effects = await guild_service.guild_effects(db, guild)
    return {
        "in_guild": True,
        "guild": {
            "id": guild.id, "name": guild.name, "tag": guild.tag, "level": guild.level,
            "fame": guild.fame, "fame_next": gc.fame_to_next(guild.level), "fame_total": guild.fame_total,
            "members": len(rows), "cap": gc.member_cap(guild.level),
            "treasury_gold": guild.treasury_gold, "treasury_gems": guild.treasury_gems,
            "siege_hour": guild.siege_hour, "crown": guild_season_service.has_crown(guild),
            "season_wins": guild.season_wins,
            "tree_points": guild_service.tree_points_available(guild),
            "tree_taken": len(guild.tree_nodes or []),
            "effects": [line for k, v in sorted(effects.items()) if (line := _effect_line(k, v))],
        },
        "me": {
            "id": character.id, "rank": member.rank, "rank_title": gc.RANK_TITLES[member.rank],
            "perms": _perms(member), "gold": wallet.farm_currency, "gems": wallet.donate_currency,
            "respawn_at_chapel": character.respawn_at_chapel,
            "prayer": {
                "active": guild_territory_service.prayer_active(character),
                "stat": character.prayer_stat, "until": _iso(character.prayer_until),
                "cost": guild_territory_service.prayer_cost(character),
                "available": guild_service.perk(character, "_chapel") >= 1,
                "stats": STAT_TITLES,
            },
            "pos": [character.pos_x, character.pos_y],
            "contribution_week": member.contribution_week if member.week_start == week else 0,
            "contribution_total": member.contribution_total,
        },
        "members": [
            {
                "id": c.id, "name": c.name, "level": c.level, "class": naming.base_class_title(c.base_class),
                "rank": m.rank, "rank_title": gc.RANK_TITLES[m.rank],
                "week": m.contribution_week if m.week_start == week else 0, "total": m.contribution_total,
            }
            for m, c in sorted(rows, key=lambda mc: (-gc.RANK_ORDER[mc[0].rank], mc[1].name))
        ],
        "applications": [
            {"id": c.id, "name": c.name, "level": c.level}
            for _i, c in await guild_service.applications_of(db, guild.id)
        ] if _perms(member)["applications"] else [],
        "quests": await guild_quest_service.overview(db, character),
        "tops": await guild_quest_service.contribution_tops(db, guild.id),
        "warehouse": {
            "capacity": {"ore": cap.ore, "items": cap.items},
            "ore_total": await guild_service.ore_total(db, guild.id),
            "ore": [_ore_line(o.ore_id, o.grade, o.count) for o in await guild_service.ore_stock(db, guild.id)],
            "items": [
                {"id": i.id, "name": i.name, "slot": naming.slot_title(i.slot), "rarity": i.rarity,
                 "icon": naming.item_icon_key(i), "stats": i.base_stats or {}}
                for i in stored
            ],
            "my_ore": [_ore_line(d.id, grade, count) for d, grade, count in my_ore if count > 0],
            "my_items": [
                {"id": i.id, "name": i.name, "slot": naming.slot_title(i.slot), "rarity": i.rarity,
                 "icon": naming.item_icon_key(i)}
                for i in my_items
            ],
        },
        "slots": {
            "cells": len(held_cells), "cells_max": gc.cell_slots(guild.level),
            "mines": len(held_mines), "mines_max": gc.mine_slots(guild.level),
            "next_cell_level": next((lv for lv, n in gc.CELL_SLOTS if gc.cell_slots(guild.level) < n), None),
            "mine_level": gc.MINE_SLOT_LEVEL,
        },
        "cells": [await _cell_payload(db, guild, c, character, gate_ids) for c in cells],
        "here": await _here_payload(db, guild, character),
        "gates": gates,
        "sieges": sieges,
        "season": {
            "season": guild_season_service.season_of(guild_service.today_msk()),
            "place": place,
            "top": [{"tag": g.tag, "name": g.name, "points": pts} for g, pts in standings[:10]],
        },
        "boss": {
            "active": boss is not None,
            "hp": boss.hp if boss else 0, "max_hp": boss.max_hp if boss else 0,
            "x": boss.x if boss else None, "y": boss.y if boss else None,
            "expires_at": _iso(boss.expires_at) if boss else None,
            "cooldown_hours": round(guild_boss_service.cooldown_days_left(guild) * 24, 1),
            "summon_gold": gc.BOSS_SUMMON_GOLD,
            "summon_ore": _ore_name(gc.BOSS_SUMMON_ORE[0]), "summon_ore_count": gc.BOSS_SUMMON_ORE[1],
            "has_citadel": any(c.base_tier == gc.BASE_CITADEL and c.status == "held" for c in cells),
        },
        "log": [
            {"text": row.text, "at": _iso(row.created_at)} for row in await guild_service.recent_log(db, guild.id)
        ],
        "config": {
            "ranks": gc.RANK_TITLES, "siege_hours": list(gc.SIEGE_HOURS_ALLOWED),
            "gather_minutes": gc.SIEGE_GATHER_MINUTES,
        },
    }


def _effect_line(key: str, value: float) -> str | None:
    from game.guild import tree as guild_tree

    if key.startswith("_") or not value:
        return None
    return guild_tree.effect_text(key, value)


# --- Действия -------------------------------------------------------------------------


def _int(body: dict, key: str) -> int:
    value = body.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise GuildError("Неверный запрос.")
    return value


def _str(body: dict, key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GuildError("Неверный запрос.")
    return value.strip()


async def _act(db, character: Character, vk_user_id: int, body: dict) -> list:
    """Выполняет действие. Возвращает отложенные уведомления [(peers|guild_id, text)]."""
    from bot.activity import blocked_reason

    action = body.get("action")
    notes: list = []
    if action == "create":
        await guild_service.create(db, character, _str(body, "name"), _str(body, "tag"))
    elif action == "apply":
        guild = await guild_service.apply(db, character, _int(body, "guild_id"))
        notes.append(("guild_officers", guild.id, f"📨 {character.name} ({character.level} ур.) просится в гильдию."))
    elif action == "invite":
        target = await guild_service.invite(db, character, _str(body, "name"))
        guild = await guild_service.guild_of(db, character)
        notes.append(("char", target.id, f"📨 Тебя зовут в гильдию [{guild.tag}] {guild.name}. Ответить можно в мини-аппе."))
    elif action == "accept_invite":
        guild = await guild_service.accept_invite(db, character, _int(body, "guild_id"))
        notes.append(("guild", guild.id, f"🏰 {character.name} вступает в гильдию."))
    elif action == "decline_invite":
        await guild_service.decline_invite(db, character, _int(body, "guild_id"))
    elif action == "accept_application":
        target = await guild_service.accept_application(db, character, _int(body, "character_id"))
        guild = await guild_service.guild_of(db, character)
        notes.append(("char", target.id, f"🏰 Тебя приняли в гильдию [{guild.tag}] {guild.name}!"))
    elif action == "decline_application":
        await guild_service.decline_application(db, character, _int(body, "character_id"))
    elif action == "leave":
        await guild_service.leave(db, character)
    elif action == "kick":
        target = await guild_service.kick(db, character, _int(body, "character_id"))
        notes.append(("char", target.id, "🏰 Тебя исключили из гильдии."))
    elif action == "rank":
        await guild_service.set_rank(db, character, _int(body, "character_id"), _str(body, "rank"))
    elif action == "transfer":
        target = await guild_service.transfer_leadership(db, character, _int(body, "character_id"))
        notes.append(("char", target.id, "🏰 Ты теперь глава гильдии."))
    elif action == "disband":
        former = await guild_service.disband(db, character)
        for cid in former:
            if cid != character.id:
                notes.append(("char", cid, "🏰 Гильдию распустили."))
    elif action == "deposit":
        await guild_service.deposit(db, character, _str(body, "currency"), _int(body, "amount"))
    elif action == "withdraw":
        to = body.get("to")
        await guild_service.withdraw(
            db, character, _str(body, "currency"), _int(body, "amount"), to if isinstance(to, int) else None,
        )
    elif action == "deposit_ore":
        await guild_service.deposit_ore(db, character, _str(body, "ore_id"), _str(body, "grade"), _int(body, "count"))
    elif action == "withdraw_ore":
        to = body.get("to")
        await guild_service.withdraw_ore(
            db, character, _str(body, "ore_id"), _str(body, "grade"), _int(body, "count"),
            to if isinstance(to, int) else None,
        )
    elif action == "deposit_item":
        await guild_service.deposit_item(db, character, _int(body, "item_id"))
    elif action == "withdraw_item":
        to = body.get("to")
        await guild_service.withdraw_item(db, character, _int(body, "item_id"), to if isinstance(to, int) else None)
    elif action == "banner":
        reason = await blocked_reason(db, character, vk_user_id)
        if reason:
            raise GuildError(reason)
        cell = await guild_territory_service.plant_banner(db, character, character.pos_x, character.pos_y)
        notes.append((
            "guild", cell.guild_id,
            f"🚩 Знамя заложено на ({cell.x}; {cell.y})! Нужно {cell.claim_needed} исследований этой клетки "
            f"участниками гильдии за {gc.CLAIM_HOURS} ч.",
        ))
    elif action == "abandon":
        await guild_territory_service.abandon(db, character, _int(body, "cell_id"))
    elif action == "build":
        await guild_territory_service.start_build(db, character, _int(body, "cell_id"), _str(body, "building"))
    elif action == "upgrade_base":
        await guild_territory_service.start_base_upgrade(db, character, _int(body, "cell_id"))
    elif action == "gates":
        reason = await blocked_reason(db, character, vk_user_id)
        if reason:
            raise GuildError(reason)
        target = await guild_territory_service.travel_gates(db, character, _int(body, "cell_id"))
        notes.append(("self_move", target.x, target.y))
    elif action == "pray":
        await guild_territory_service.pray(db, character, _str(body, "stat"))
    elif action == "respawn_pref":
        await guild_service.require_member(db, character)
        character.respawn_at_chapel = bool(body.get("on"))
    elif action == "declare_siege":
        siege = await guild_siege_service.declare(db, character, _int(body, "cell_id"))
        attacker = await db.get(Guild, siege.attacker_guild_id)
        defender = await db.get(Guild, siege.defender_guild_id)
        when = siege.starts_at.astimezone(guild_siege_service._TZ).strftime("%d.%m в %H:%M")
        notes.append(("guild", attacker.id, f"⚔️ Объявлена осада [{defender.tag}] на ({siege.x}; {siege.y}): {when} МСК."))
        notes.append(("guild", defender.id, f"🛡 [{attacker.tag}] объявляет осаду ({siege.x}; {siege.y}): {when} МСК. Готовьте оборону!"))
    elif action == "siege_hour":
        await guild_siege_service.set_siege_hour(db, character, _int(body, "hour"))
    elif action == "tree_allocate":
        await guild_tree_service.allocate(db, character, _str(body, "node_id"))
    elif action == "tree_reset":
        await guild_tree_service.reset(db, character)
    elif action == "summon_boss":
        boss = await guild_boss_service.summon(db, character)
        notes.append(("boss", boss.guild_id, boss.x, boss.y))
    else:
        raise GuildError("Неизвестное действие.")
    return notes


async def _deliver(db, notes: list, vk_user_id: int) -> None:
    from bot.handlers import guild as guild_handlers

    for note in notes:
        kind = note[0]
        try:
            if kind == "char":
                peer = await onboarding_svc.vk_id_for_character(db, note[1])
                if peer is not None:
                    guild_handlers.notify_peers([peer], note[2])
            elif kind == "guild":
                await guild_handlers.notify_guild(note[1], note[2])
            elif kind == "guild_officers":
                await guild_handlers.notify_guild(note[1], note[2], min_rank=gc.RANK_OFFICER)
            elif kind == "boss":
                await guild_handlers.announce_boss(note[1], note[2], note[3])
            elif kind == "self_move":
                guild_handlers.notify_peers(
                    [vk_user_id], f"🌀 Врата переносят тебя на ({note[1]}; {note[2]})."
                )
        except Exception:
            logger.exception("Гильдии: не доставлено уведомление {}", note)


async def handle_get(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, vk_user_id)
        if character is None:
            return _error("character_not_found", 404)
        state = await _state(db, character)
        await db.commit()
    return web.json_response(state)


async def handle_get_tree(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, vk_user_id)
        if character is None:
            return _error("character_not_found", 404)
        guild = await guild_service.guild_of(db, character)
        member = await guild_service.membership(db, character.id)
        payload = guild_tree_service.payload(guild)
        payload["can_edit"] = guild_service.can_manage_treasury(member)
        payload["treasury_gold"] = guild.treasury_gold if guild else 0
    return web.json_response(payload)


async def handle_post(request: web.Request) -> web.Response:
    vk_user_id = request[VK_USER_ID_KEY]
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    if not isinstance(body, dict):
        return _error("bad_request")
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, vk_user_id)
        if character is None:
            return _error("character_not_found", 404)
        try:
            notes = await _act(db, character, vk_user_id, body)
        except GuildError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        await db.commit()
        await db.refresh(character)
        state = await _state(db, character)
        await db.commit()
        await _deliver(db, notes, vk_user_id)
    return web.json_response(state)


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/guild", handle_get)
    app.router.add_get("/api/miniapp/guild/tree", handle_get_tree)
    app.router.add_post("/api/miniapp/guild/action", handle_post)

