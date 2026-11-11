"""Руны в мини-аппе (2026-10-31): /api/miniapp/runes.

Страница «Руны» на вкладке «Герой»: подвкладки (навыки, героя, экипировки),
все слоты сразу, закрытые - под замком с ценой. Руны-навыки (2026-11-10): три
слота, в каждом гнёзда огранок и ступени навыка. Руны героя ещё и
кругом под ногами силуэта. Логика - services/rune_service.py.
"""

from aiohttp import web

from bot.app_keys import SESSION_FACTORY_KEY
from bot.miniapp_auth import VK_USER_ID_KEY
from game.combat import skill_catalog
from game.economy import ability_config as ac
from game.economy import runes
from game.economy import runes_config as rc
from services import rune_service, wallet_service
from services import onboarding_service as onboarding_svc

#: Подпись классовой руны в описании (2026-10-31, владелец).
CLASS_TITLES = {"warrior": "воин", "rogue": "разбойник", "mage": "маг"}

PLACE_TITLES = {"weapon": "Оружие", "helmet": "Шлем", "armor": "Доспех", "legs": "Штаны", "boots": "Сапоги"}


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


def _scaling_text(rune_def: rc.RuneDef, absorbed: int) -> str | None:
    """«330% Силы» / «192% Воли и 128% Интеллекта» - с мастерством."""
    if rune_def.kind != rc.ABILITY or rune_def.id not in ac.SCALING_SHARES:
        return None
    skill = skill_catalog.skill_def(rune_def.id)
    power = runes.value(rune_def, absorbed) - 1.0
    parts = [f"{round(coef * 100)}% {ac.STAT_TITLES[stat]}"
             for stat, coef in ac.scaling(rune_def.id, skill.multiplier, power).items()]
    return " и ".join(parts)


def _rune(rune_def: rc.RuneDef, absorbed: int, count: int = 0) -> dict:
    nxt, nxt_pct = runes.next_threshold(rune_def.curve, absorbed)
    return {
        "id": rune_def.id, "kind": rune_def.kind, "name": rune_def.name, "rarity": rune_def.rarity,
        "rarity_title": rc.RARITY_TITLES[rune_def.rarity], "count": count,
        "text": runes.describe(rune_def, absorbed), "base_text": runes.describe(rune_def, 0),
        "pvp": rune_def.pvp, "ready": rune_def.ready,
        "classes": list(rune_def.classes), "place": rune_def.place,
        "class_note": (f"Для класса {', '.join(CLASS_TITLES[c] for c in rune_def.classes)}"
                       if rune_def.classes else None),
        "tag": rc.SKILL_TAG_TITLES.get(rune_def.tag) if rune_def.tag else None, "tag_id": rune_def.tag or None,
        "absorbed": absorbed, "efficiency": round(runes.efficiency(rune_def.curve, absorbed) * 100, 1),
        "next": nxt, "next_pct": nxt_pct,
        # Руна-навык (2026-11-10): что делает навык и на какой он ступени.
        "summary": ac.BY_ID[rune_def.id].summary if rune_def.kind == rc.ABILITY else None,
        "scaling_text": _scaling_text(rune_def, absorbed),
        "step": ac.step_of(rune_def.id, absorbed) if rune_def.kind == rc.ABILITY else None,
    }


def _ability_info(skill_id: str, absorbed: int, fork: int | None) -> dict:
    """Ступени руны-навыка: что даёт каждая, сколько копий до неё, что открыто."""
    ability = ac.BY_ID[skill_id]
    need = ac.step_thresholds(ability.curve)
    step = ac.step_of(skill_id, absorbed)
    steps = [
        {"n": 1, "text": ability.one.text, "need": need[0], "done": step >= 1},
        {"n": 2, "text": ability.two.text + " Открывает второе гнездо огранки.", "need": need[1], "done": step >= 2},
        {"n": 3, "need": need[2], "done": step >= 3, "fork": [ability.fork[0].text, ability.fork[1].text],
         "chosen": fork if fork in (1, 2) else None},
        {"n": 4, "text": ability.four.text, "need": need[3], "done": step >= 4,
         "pvp_note": "В PvP - вполсилы."},
    ]
    return {"summary": ability.summary, "step": step, "steps": steps}


async def _hero_stats(db, character) -> dict[str, int]:
    """Характеристики героя с вещами - от них бьют навыки."""
    from sqlalchemy import select

    from models import CharacterStats
    from services import item_service

    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    gear = await item_service.compute_gear_bonus(db, character.id)
    base = {"str": stats.strength, "agi": stats.agility, "int": stats.intellect, "vit": stats.vitality,
            "wil": stats.will} if stats is not None else dict.fromkeys(("str", "agi", "int", "vit", "wil"), 0)
    return {k: v + int(gear.get(k, 0)) for k, v in base.items()}


def _scaling_info(skill_id: str, absorbed: int, character, hero: dict[str, int]) -> dict:
    """От каких характеристик бьёт навык (2026-11-11, владелец): проценты с
    мастерством, ваши значения и прикидка урона - без брони и крита."""
    from types import SimpleNamespace

    from game.combat import formulas, stat_model
    from services import subclass_service

    shares = ac.SCALING_SHARES.get(skill_id)
    if not shares:
        return {"scaling": [], "damage": None}
    rune_def = rc.BY_ID[skill_id]
    power = runes.value(rune_def, absorbed) - 1.0
    mods = ac.combat_modifiers(character.rune_effects or {}, subclass_service.buff_pool(character))
    tuned = skill_catalog.tuned(SimpleNamespace(buff_modifiers=mods), skill_id)
    level = character.level or 1
    parts, unit = [], formulas.weapon_base(formulas.tier_multiplier(formulas.tier_for_level(level)))
    for stat, coef in ac.scaling(skill_id, tuned.multiplier, power).items():
        have = hero.get(stat, 0)
        parts.append({"stat": stat, "title": ac.STAT_TITLES[stat], "pct": round(coef * 100), "have": have})
        unit += coef / tuned.multiplier * stat_model.ACTIVE.primary_value(have, level, True, stat)
    return {"scaling": parts, "damage": round(unit * tuned.multiplier)}


def _ability_slot(index: int, taken: dict, known: dict, character, socket, hero: dict | None = None) -> dict:
    out = socket(rc.ABILITY, str(index))
    rune_id = taken.get((rc.ABILITY, str(index)))
    if not rune_id or rune_id not in ac.BY_ID:
        out["facets"] = []
        return out
    absorbed = known.get(rune_id, 0)
    info = _ability_info(rune_id, absorbed, (character.skill_forks or {}).get(rune_id))
    skill = skill_catalog.skill_def(rune_id)
    out.update(info)
    out.update(_scaling_info(rune_id, absorbed, character, hero or {}))
    out["skill"] = {"id": rune_id, "name": skill.name, "cd": skill.cd, "tags": sorted(runes.skill_tags(skill))}
    out["facets"] = [socket(rc.SKILL, f"{rune_id}:0"),
                     {**socket(rc.SKILL, f"{rune_id}:1", info["step"] >= 2), "need_step": 2}]
    return out


def _passive(character) -> dict | None:
    """Пассивка подкласса или пути: она подсказывает, какие навыки брать."""
    from game.economy import passives_config
    from services import subclass_service

    passive = passives_config.passive_of(subclass_service.buff_pool(character))
    return {"title": passive.title, "lines": list(passive.lines)} if passive else None


async def _payload(db, character) -> dict:
    bag = await rune_service.bag(db, character.id)
    known = await rune_service.mastery(db, character.id)
    taken = {(r.kind, r.slot): r.rune_id for r in await rune_service.slots(db, character.id)}

    def socket(kind: str, slot: str, is_open: bool = True, price: int | None = None) -> dict:
        rune_id = taken.get((kind, slot))
        rune_def = rc.BY_ID.get(rune_id) if rune_id else None
        return {"slot": slot, "open": is_open, "price": price,
                "rune": _rune(rune_def, known.get(rune_id, 0)) if rune_def else None}

    hero = [
        socket(rc.HERO, str(i), i < character.rune_hero_slots,
               runes.hero_slot_price(i) if i == character.rune_hero_slots else None)
        for i in range(rc.HERO_SLOTS_MAX)
    ]
    gear = [
        {"place": place, "title": PLACE_TITLES[place],
         "slots": [socket(rc.GEAR, f"{place}:{i}") for i in range(rc.GEAR_SLOTS_PER_PLACE)]}
        for place in rc.GEAR_PLACES
    ]
    hero_stats = await _hero_stats(db, character)
    abilities = [_ability_slot(i, taken, known, character, socket, hero_stats) for i in range(rc.ABILITY_SLOTS)]
    worn = set(taken.values())
    owned = [
        {**_rune(r, known.get(r.id, 0), bag.get(r.id, 0)), "equipped": r.id in worn}
        for r in rc.RUNES if bag.get(r.id) or known.get(r.id) or r.id in worn
    ]
    wallet = await wallet_service.get_wallet(db, character.id)
    return {
        "home": rune_service.at_home(character), "gold": wallet.farm_currency,
        "base_class": character.base_class,
        "hero": hero, "gear": gear, "abilities": abilities, "runes": owned,
        "passive": _passive(character),
        "titles": rc.KIND_TITLES,
    }


async def handle_get(request: web.Request) -> web.Response:
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        # Огранки снятых навыков (и руны экипировки чужого класса) - в сумку.
        if await rune_service.release_lost_runes(db, character):
            await rune_service.recompute(db, character)
            await db.commit()
        return web.json_response(await _payload(db, character))


async def handle_post(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _error("bad_request")
    if not isinstance(body, dict) or not isinstance(body.get("action"), str):
        return _error("bad_request")
    action = body["action"]
    async with request.app[SESSION_FACTORY_KEY]() as db:
        character = await onboarding_svc.get_character(db, request[VK_USER_ID_KEY])
        if character is None:
            return _error("character_not_found", 404)
        try:
            if action == "equip":
                await rune_service.equip(db, character, str(body.get("kind")), str(body.get("slot")),
                                         str(body.get("rune")))
            elif action == "unequip":
                await rune_service.unequip(db, character, str(body.get("kind")), str(body.get("slot")))
            elif action == "absorb":
                count = body.get("count")
                if not isinstance(count, int) or count <= 0:
                    return _error("bad_request")
                await rune_service.absorb(db, character, str(body.get("rune")), count)
            elif action == "buy_hero":
                await rune_service.buy_hero_slot(db, character)
            elif action == "fork":
                fork = body.get("fork")
                if not isinstance(fork, int):
                    return _error("bad_request")
                await rune_service.choose_fork(db, character, str(body.get("skill")), fork)
            else:
                return _error("bad_request")
        except rune_service.RuneError as exc:
            await db.rollback()
            return _error(str(exc), 409)
        await db.commit()
        return web.json_response(await _payload(db, character))


def register_routes(app: web.Application) -> None:
    app.router.add_get("/api/miniapp/runes", handle_get)
    app.router.add_post("/api/miniapp/runes", handle_post)
