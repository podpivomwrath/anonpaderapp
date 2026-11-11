"""Живой прогон всех рун-навыков (2026-11-11, перед выкаткой без вайпа).

Каждая руна-навык вставляется настоящему персонажу в тестовой базе, бойца
собирает тот же код, что и в бою бота (модификаторы - preset_service, боец -
pvp._build_combatant_for), и навык применяется в четырёх боях: соло против
мобов, группа против мобов, дуэль 1×1 и PvP 2×2. Так у каждого из 9 классов и
подклассов на нулевой ступени, а на одной строке - ещё ступени III и IV с обеими
развилками. Проверка: бой не падает, навык есть на клавиатуре, навык
срабатывает (уходит на перезарядку или пишет строку в лог), урон навыка с
масштабом - не ноль.
"""

from __future__ import annotations

import random
import re

import pytest

import game.classes  # noqa: F401
from game.combat import balance_config as bc
from game.combat import skill_catalog
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatSessionState,
    DeclaredAction,
)
from game.economy import ability_config as ac
from game.economy import runes_config as rc
from game.world import encounters
from game.world import world_config as wc
from services import preset_service, rune_service

pytestmark = pytest.mark.real_abilities

POOLS = [("warrior", None), ("rogue", None), ("mage", None), ("warrior", "guardian"),
         ("warrior", "blood_knight"), ("rogue", "shadow_blade"), ("rogue", "poisoner"),
         ("mage", "elementalist"), ("mage", "dark_mystic")]
SKILLS = sorted(skill_catalog.ALL_SKILL_DEFS)


async def _hero(db, make_character, base_class, subclass, skill_id, level=40):
    from sqlalchemy import select

    from models import CharacterStats

    character = await make_character(level=level, base_class=base_class, subclass=subclass)
    character.region = "ridge"
    character.pos_x, character.pos_y = wc.CITY_COORDS["ridge"]
    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    primary = bc.primary_stat_of(character)
    values = {"strength": 30, "agility": 30, "intellect": 30, "will": 30, "vitality": 60}
    values[{"str": "strength", "agi": "agility", "int": "intellect", "wil": "will"}[primary]] = 72
    for field, value in values.items():
        setattr(stats, field, value)
    await rune_service.grant(db, character.id, skill_id, 1)
    await rune_service.equip(db, character, rc.ABILITY, "0", skill_id)
    # подходящая огранка в первое гнездо - чтобы огранки тоже были в бою
    skill = skill_catalog.skill_def(skill_id)
    from game.economy import runes

    facet = next((r for r in rc.RUNES if r.kind == rc.SKILL and runes.fits_skill(r, skill)), None)
    if facet is not None:
        await rune_service.grant(db, character.id, facet.id, 1)
        await rune_service.equip(db, character, rc.SKILL, f"{skill_id}:0", facet.id)
    await db.flush()
    return character


async def _reach_step(db, character, skill_id, step, fork):
    need = ac.step_thresholds(ac.BY_ID[skill_id].curve)[step - 1]
    have = (await rune_service.mastery(db, character.id)).get(skill_id, 0)
    if need > have:
        await rune_service.grant(db, character.id, skill_id, need - have)
        await rune_service.absorb(db, character, skill_id, need - have)
    if step >= 3:
        await rune_service.choose_fork(db, character, skill_id, fork)


async def _fighter(db, character, cid, side, pvp):
    from bot.handlers import pvp as pvp_handlers

    fighter = await pvp_handlers._build_combatant_for(db, character)
    if not pvp:
        fighter.buff_modifiers = dict(await preset_service.resolve_active_modifiers(db, character))
    fighter.id, fighter.side = cid, side
    return fighter


def _mob(cid, rng):
    dist = next(lo for lo, hi, (zlo, zhi) in wc.ZONE_TABLE if zlo <= 40 <= zhi)
    mob = encounters.spawn_mob(cid, "ridge", 40, dist, rng).combatant
    mob.side = 1
    return mob


def _fight(mode, actor, allies, foes, skill_id, rng) -> dict:
    session = CombatSessionState(session_id=1, mode=mode)
    for c in [actor, *allies, *foes]:
        session.add(c)
    for ally in allies:
        ally.current_hp = ally.max_hp // 2  # есть кого лечить
    actor.current_hp = int(actor.max_hp * 0.8)
    used, lines, best = 0, [], 0
    name = skill_catalog.ALL_SKILL_DEFS[skill_id].name
    for _ in range(10):
        enemies = [c for c in foes if c.alive]
        if not enemies or not actor.alive:
            break
        actions = {}
        for c in [actor, *allies, *foes]:
            if c.kind != "character" or not c.alive:
                continue
            targets = [e for e in session.combatants.values() if e.alive and e.side != c.side]
            if not targets:
                continue
            if c is actor and not actor.is_on_cooldown(skill_id):
                actions[c.id] = DeclaredAction(type=ActionType.SKILL, skill_id=skill_id, target_id=targets[0].id)
            else:
                actions[c.id] = DeclaredAction(type=ActionType.ATTACK, target_id=targets[0].id)
        was_ready = not actor.is_on_cooldown(skill_id)
        result = resolve_tick(session, actions, rng)
        lines += result.lines
        for ln in result.lines:
            m = re.search(r"использует (.+?) на .+? - (\d+) урона", ln)
            if m and m.group(1) == name:
                best = max(best, int(m.group(2)))
        if was_ready and (actor.is_on_cooldown(skill_id)
                          or any(skill_catalog.ALL_SKILL_DEFS[skill_id].name in ln for ln in result.lines)):
            used += 1
        if result.finished:
            break
    return {"used": used, "lines": lines, "best": best}


def _on_keyboard(fighter, skill_id) -> bool:
    from bot.keyboards import combat_modes

    items = combat_modes.skill_items(fighter, "pvp_skill", fresh=True)
    return any(skill_id in str(item) for item in items)


async def _all_fights(db, make_character, character, skill_id, label, rng):
    partner = await make_character(level=40, base_class="mage", subclass="dark_mystic")
    await rune_service.grant_starter(db, partner)
    foes_chars = []
    for base in ("warrior", "rogue"):
        foe = await make_character(level=40, base_class=base)
        await rune_service.grant_starter(db, foe)
        foes_chars.append(foe)

    pve_actor = await _fighter(db, character, 1, 0, pvp=False)
    assert _on_keyboard(pve_actor, skill_id), f"{label}: навыка нет на клавиатуре"
    out = [_fight(CombatMode.PVE, pve_actor, [], [_mob(10, rng)], skill_id, rng)]
    out.append(_fight(CombatMode.PVE, await _fighter(db, character, 1, 0, pvp=False),
                      [await _fighter(db, partner, 2, 0, pvp=False)], [_mob(10, rng), _mob(11, rng)], skill_id, rng))
    out.append(_fight(CombatMode.PVP_GROUP, await _fighter(db, character, 1, 0, pvp=True), [],
                      [await _fighter(db, foes_chars[0], 10, 1, pvp=True)], skill_id, rng))
    out.append(_fight(CombatMode.PVP_GROUP, await _fighter(db, character, 1, 0, pvp=True),
                      [await _fighter(db, partner, 2, 0, pvp=True)],
                      [await _fighter(db, f, 10 + i, 1, pvp=True) for i, f in enumerate(foes_chars)], skill_id, rng))
    for name, fight in zip(("соло", "группа", "дуэль", "PvP 2x2"), out):
        assert fight["used"] >= 1, f"{label} / {name}: навык ни разу не сработал\n" + "\n".join(fight["lines"][-12:])
    if skill_id in ac.SCALING_SHARES or skill_id == "reckoning":
        # урон навыка заметный хотя бы в одном бою (не «1 урона»)
        assert max(f["best"] for f in out) >= 20, f"{label}: урон навыка {[f['best'] for f in out]}"


@pytest.mark.parametrize("skill_id", SKILLS)
async def test_every_rune_skill_works_in_every_fight(db_session, make_character, skill_id) -> None:
    rng = random.Random(hash(skill_id) & 0xFFFF)
    for base_class, subclass in POOLS:
        character = await _hero(db_session, make_character, base_class, subclass, skill_id)
        await _all_fights(db_session, make_character, character, skill_id,
                          f"{skill_id} у {subclass or base_class}, ступень 0", rng)
    # ступени III и IV с обеими развилками - у одного класса
    base_class, subclass = POOLS[SKILLS.index(skill_id) % len(POOLS)]
    for step, fork in ((3, 1), (3, 2), (4, 1), (4, 2)):
        character = await _hero(db_session, make_character, base_class, subclass, skill_id)
        await _reach_step(db_session, character, skill_id, step, fork)
        assert character.rune_effects.get(f"step:{skill_id}") == step
        await _all_fights(db_session, make_character, character, skill_id,
                          f"{skill_id} у {subclass or base_class}, ступень {step}, развилка {fork}", rng)
