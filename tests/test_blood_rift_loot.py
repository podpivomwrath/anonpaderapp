"""Добыча кровавого разлома (2026-10-13): Ларец руды, Ларец расходников,
свитки и листание сумки в бою."""

import json
import random

from bot.keyboards.combat_items import PAGE_SIZE, paged_items_keyboard
from game.combat import elixir_effects
from game.combat.session import EffectKind
from game.content_loader import load_elixirs
from models import CharacterOre
from services import elixir_service, lootbox_service
from tests.conftest import combatant


def _buttons(kb_json: str) -> list[list[dict]]:
    return json.loads(kb_json)["buttons"]


def test_bag_pages_by_eight_with_forward_and_back() -> None:
    stock = [(d, 1) for d in load_elixirs().values()]
    assert len(stock) > PAGE_SIZE
    first = _buttons(paged_items_keyboard(stock, "use_item", "pg", 0))
    labels = [b["action"]["label"] for row in first for b in row]
    assert len(labels) == PAGE_SIZE + 1 and labels[-1] == "Вперёд ▶"
    assert len(first) <= 6
    second = _buttons(paged_items_keyboard(stock, "use_item", "pg", 1))
    labels = [b["action"]["label"] for row in second for b in row]
    assert labels[-1] == "◀ Назад" and len(labels) == len(stock) - PAGE_SIZE + 1
    short = _buttons(paged_items_keyboard(stock[:3], "use_item", "pg", 0))
    assert sum(len(r) for r in short) == 3  # одна страница - без листания


def test_scrolls_are_not_sold() -> None:
    assert not any(e.category == "scroll" for e in elixir_service.shop_elixirs())


def test_scrolls_hit_the_whole_side() -> None:
    a = combatant(1, side=0)
    b = combatant(2, side=0)
    m1 = combatant(3, side=1, kind="mob")
    m2 = combatant(4, side=1, kind="mob")
    everyone = {c.id: c for c in (a, b, m1, m2)}
    a.current_hp = b.current_hp = 1
    elixir_effects.apply_combat_elixir(a, "scroll_healing", everyone)
    assert a.current_hp == 1 + round(a.max_hp * 0.3) and b.current_hp == 1 + round(b.max_hp * 0.3)
    line = elixir_effects.apply_combat_elixir(a, "scroll_ward", everyone)
    assert "Свиток оберега" in line
    assert all(c.effects_of(EffectKind.SHIELD_POOL) for c in (a, b))
    assert not m1.effects_of(EffectKind.SHIELD_POOL)
    elixir_effects.apply_combat_elixir(a, "scroll_vulnerability", everyone)
    assert m1.effect_total(EffectKind.VULNERABILITY) == 0.35 and m2.effect_total(EffectKind.VULNERABILITY) == 0.35
    assert a.effect_total(EffectKind.VULNERABILITY) == 0


async def test_blood_chests_open_by_kind(db_session, make_character) -> None:
    character = await make_character(level=60)
    await lootbox_service.grant_chest(db_session, character, 1, lootbox_service.ORE)
    await lootbox_service.grant_chest(db_session, character, 1, lootbox_service.SUPPLY)
    await lootbox_service.grant_chest(db_session, character, 1)
    rng = random.Random(4)
    chest, result = await lootbox_service.open_owned(db_session, character, None, rng, lootbox_service.ORE)
    assert chest.kind == "ore" and result.kind == "ore"
    from sqlalchemy import func, select

    got = await db_session.scalar(
        select(func.sum(CharacterOre.count)).where(CharacterOre.character_id == character.id)
    )
    assert 1 <= got <= 3
    strip, win = lootbox_service.roulette_strip(result, 1, rng)
    assert strip[win]["icon"].startswith("ore:")
    _chest, supply = await lootbox_service.open_owned(db_session, character, None, rng, lootbox_service.SUPPLY)
    assert supply.kind == "supply" and supply.lines
    left = await lootbox_service.closed_chests(db_session, character.id)
    assert [c.kind for c in left] == ["ashen"]


def test_supply_chest_scroll_only_on_the_rarest_card() -> None:
    grades = lootbox_service.grade_catalog(lootbox_service.SUPPLY)
    for g in grades:
        ids = {p.elixir_id for opt in g.options for p in opt}
        has_scroll = any(i.startswith("scroll_") for i in ids)
        assert has_scroll == (g.id == "tear"), g.id
    ore_grades = lootbox_service.grade_catalog(lootbox_service.ORE)
    assert all(p.max <= 3 for g in ore_grades for opt in g.options for p in opt)


def test_flee_is_harder_from_stronger_mobs() -> None:
    from bot.handlers.combat import flee_chance

    assert flee_chance(20, 20) == 0.5
    assert flee_chance(20, 10) == 0.5  # слабее - как раньше
    assert abs(flee_chance(20, 25) - 0.35) < 1e-9
    assert flee_chance(10, 40) == 0.10  # не ниже 10%
