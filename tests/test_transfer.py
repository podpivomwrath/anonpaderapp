"""Передача между игроками.

Можно: золото, самоцветы, расходники, руду, экипировку (и уникальную,
вроде Скальпеля Хирурга). Нельзя: скованное, надетое, служебное, трофеи,
рыбу. У экипировки число в команде - номер экземпляра, а не количество.
"""

import pytest
from sqlalchemy import select

from models import CharacterConsumable, CharacterOre, Inventory, Item, TransferLog
from services import elixir_service, mining_service, trophy_service, wallet_service
from services import transfer_service as ts


def test_parse_splits_name_and_number() -> None:
    assert ts.parse("Малое исцеление 5") == ("малое исцеление", 5)
    assert ts.parse("  золото   500 ") == ("золото", 500)
    assert ts.parse("Скальпель Хирурга") == ("скальпель хирурга", None)


async def _item(db, owner, name="Скальпель Хирурга", rarity="unique", equipped=False, **extra):
    item = Item(name=name, slot="weapon", base_stats={"int": 30}, rarity=rarity, ilvl=None, **extra)
    db.add(item)
    await db.flush()
    db.add(Inventory(character_id=owner.id, item_id=item.id, equipped=equipped))
    await db.flush()
    return item


async def _owner(db, item_id: int) -> int:
    return await db.scalar(select(Inventory.character_id).where(Inventory.item_id == item_id))


async def test_gold_moves_and_is_logged(db_session, make_character) -> None:
    a = await make_character(farm=1000)
    b = await make_character(farm=10)
    offer = (await ts.find(db_session, a.id, "золото")).offers[0]
    assert await ts.execute(db_session, a.id, b.id, offer, 300) == 300
    assert (await wallet_service.get_wallet(db_session, a.id)).farm_currency == 700
    # 5% (вниз) - налог фракции получателя (2026-10-15).
    assert (await wallet_service.get_wallet(db_session, b.id)).farm_currency == 10 + 285
    log = await db_session.scalar(select(TransferLog))
    assert (log.kind, log.amount, log.from_character_id, log.to_character_id) == ("gold", 300, a.id, b.id)


async def test_cannot_give_more_gold_than_owned(db_session, make_character) -> None:
    a = await make_character(farm=100)
    b = await make_character()
    offer = (await ts.find(db_session, a.id, "золото")).offers[0]
    with pytest.raises(ts.TransferFailed):
        await ts.execute(db_session, a.id, b.id, offer, 101)


async def test_gems_move(db_session, make_character) -> None:
    a = await make_character(donate=500)
    b = await make_character()
    offer = (await ts.find(db_session, a.id, "самоцветы")).offers[0]
    await ts.execute(db_session, a.id, b.id, offer, 200)
    assert (await wallet_service.get_wallet(db_session, b.id)).donate_currency == 190


async def test_elixirs_move_into_new_and_existing_stacks(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    await elixir_service.grant(db_session, a.id, "heal_small", 5)
    offer = (await ts.find(db_session, a.id, "малое исцеление")).offers[0]
    await ts.execute(db_session, a.id, b.id, offer, 2)
    await ts.execute(db_session, a.id, b.id, offer, 1)

    async def count(cid):
        return await db_session.scalar(select(CharacterConsumable.count).where(
            CharacterConsumable.character_id == cid, CharacterConsumable.elixir_id == "heal_small"))
    assert await count(a.id) == 2 and await count(b.id) == 3


async def test_ore_by_grade_and_ambiguity(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    await mining_service.add_ore(db_session, a.id, "brown_iron", "common", 5)
    await mining_service.add_ore(db_session, a.id, "brown_iron", "rare", 2)
    name = next(d.name for d, _, _ in await mining_service.get_ore(db_session, a.id)).lower()

    assert len((await ts.find(db_session, a.id, name)).offers) == 2, "без градации - выбор"
    rare = (await ts.find(db_session, a.id, f"{name} редкая")).offers
    assert len(rare) == 1 and rare[0].ref == "brown_iron:rare"
    await ts.execute(db_session, a.id, b.id, rare[0], 2)
    got = await db_session.scalar(select(CharacterOre.count).where(
        CharacterOre.character_id == b.id, CharacterOre.grade == "rare"))
    assert got == 2


async def test_unique_item_moves_and_number_picks_the_exact_one(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    first = await _item(db_session, a)
    second = await _item(db_session, a)

    assert len((await ts.find(db_session, a.id, "скальпель хирурга")).offers) == 2
    exact = (await ts.find(db_session, a.id, "скальпель хирурга", second.id)).offers
    assert [o.ref for o in exact] == [str(second.id)]

    moved = await ts.execute(db_session, a.id, b.id, exact[0], 99)  # число у вещи - не количество
    assert moved == 1
    assert await _owner(db_session, second.id) == b.id
    assert await _owner(db_session, first.id) == a.id


@pytest.mark.parametrize("extra, reason_part", [
    ({"bound": True, "craft_spec": "dps"}, "Скованная"),
    ({"admin_only": True}, "Служебные"),
])
async def test_forbidden_items_are_refused(db_session, make_character, extra, reason_part) -> None:
    a = await make_character()
    await _item(db_session, a, name="Особая вещь", **extra)
    lookup = await ts.find(db_session, a.id, "особая вещь")
    assert not lookup.offers and reason_part in lookup.refusal


async def test_equipped_item_is_refused(db_session, make_character) -> None:
    a = await make_character()
    await _item(db_session, a, name="Надетый клинок", rarity="rare", equipped=True)
    lookup = await ts.find(db_session, a.id, "надетый клинок")
    assert not lookup.offers and "Надетое" in lookup.refusal


async def test_item_already_gone_is_not_given_twice(db_session, make_character) -> None:
    a = await make_character()
    b = await make_character()
    c = await make_character()
    item = await _item(db_session, a)
    offer = (await ts.find(db_session, a.id, "скальпель хирурга")).offers[0]
    await ts.execute(db_session, a.id, b.id, offer, 1)
    with pytest.raises(ts.TransferFailed):
        await ts.execute(db_session, a.id, c.id, offer, 1)
    assert await _owner(db_session, item.id) == b.id


async def test_trophies_are_refused(db_session, make_character) -> None:
    a = await make_character()
    trophy = trophy_service.trophy_defs_ordered()[0]
    await trophy_service.grant_specific(db_session, a.id, trophy.id, 3)
    assert "Трофеи" in (await ts.find(db_session, a.id, trophy.name.lower())).refusal


async def test_herbs_food_and_fish_change_hands(db_session, make_character) -> None:
    """2026-10-21: травы и блюда - штуками, рыба - стаком «вид + градация» целиком."""
    from game.economy import cooking, fishing
    from game.economy import cooking_config as cc
    from models import CharacterFish
    from services import cooking_service, fishing_service, herb_service

    a = await make_character()
    b = await make_character()
    await herb_service.add_herb(db_session, a.id, "bitter_wormwood", 5)
    dish = cc.DISHES[0]
    await cooking_service.add_food(db_session, a.id, dish.dish_id, "trophy", 3)
    fish = fishing.fish_defs_ordered()[0]
    db_session.add(CharacterFish(character_id=a.id, fish_id=fish.id, grade="big", total_grams=2300))
    await db_session.flush()

    herb = (await ts.find(db_session, a.id, "горькая полынь")).offers[0]
    assert await ts.execute(db_session, a.id, b.id, herb, 2) == 2
    assert [(h.id, n) for h, n in await herb_service.get_bag(db_session, b.id)] == [("bitter_wormwood", 2)]

    name, qty = ts.parse(ts.food_command(cooking.dish_def(dish.dish_id).name, "trophy")[len("/передать "):] + " 2")
    food = (await ts.find(db_session, a.id, name, qty)).offers
    assert len(food) == 1 and food[0].kind == "food"
    await ts.execute(db_session, a.id, b.id, food[0], 2)
    assert [(g, n) for _d, _dish, g, n in await cooking_service.get_food(db_session, b.id)] == [("trophy", 2)]

    name, qty = ts.parse(ts.fish_command(fish.name, "big")[len("/передать "):])
    offers = (await ts.find(db_session, a.id, name, qty)).offers
    assert len(offers) == 1 and not offers[0].stackable and "2,3" in offers[0].label
    await ts.execute(db_session, a.id, b.id, offers[0], 1)
    assert await fishing_service.bag_total_grams(db_session, a.id) == 0
    assert await fishing_service.bag_total_grams(db_session, b.id) == 2300


async def test_nothing_named_like_that(db_session, make_character) -> None:
    a = await make_character()
    lookup = await ts.find(db_session, a.id, "меч тысячи истин")
    assert not lookup.offers and lookup.refusal is None


def test_command_for_names_the_exact_item() -> None:
    from types import SimpleNamespace

    assert ts.command_for(SimpleNamespace(name="Скальпель Хирурга", id=1212)) == "/передать Скальпель Хирурга 1212"


async def test_equipped_service_item_says_it_is_never_transferable(db_session, make_character) -> None:
    """Перо Хранителя надето и служебное: «сначала сними» обещало бы то, чего нет."""
    a = await make_character()
    await _item(db_session, a, name="Перо Хранителя", rarity="admin", equipped=True, admin_only=True)
    assert "Служебные" in (await ts.find(db_session, a.id, "перо хранителя")).refusal


def test_miniapp_offers_the_command_for_every_transferable_item() -> None:
    from types import SimpleNamespace

    from bot.miniapp_api import _transfer_command

    def item(**kw):
        base = {"id": 7, "name": "Пепельный клинок", "rarity": "common", "admin_only": False,
                "bound": False, "craft_spec": None}
        base.update(kw)
        return SimpleNamespace(**base)

    assert _transfer_command(item()) == "/передать Пепельный клинок 7"
    assert _transfer_command(item(rarity="unique", name="Скальпель Хирурга")) == "/передать Скальпель Хирурга 7"
    assert _transfer_command(item(bound=True, craft_spec="dps")) is None
    assert _transfer_command(item(admin_only=True)) is None


def test_short_forms_and_number_first() -> None:
    """«передать 100 зол», «передать 100 сам» - как пишут в чате."""
    assert ts.parse("100 зол") == ("зол", 100)
    assert ts.parse("100 Сам") == ("сам", 100)
    assert ts.parse("3 Малое Исцеление") == ("малое исцеление", 3)
    assert "зол" in ts.GOLD_WORDS and "сам" in ts.GEM_WORDS


async def test_gems_by_short_word(db_session, make_character) -> None:
    a = await make_character(donate=5)
    name, qty = ts.parse("5 сам")
    offer = (await ts.find(db_session, a.id, name, qty)).offers[0]
    assert offer.kind == "gems"


async def test_inventory_payload_lists_relics_and_consumables(db_session, make_character) -> None:
    from bot.miniapp_api import _full_inventory

    a = await make_character()
    await trophy_service.grant_specific(db_session, a.id, "blood_shard", 3)
    await elixir_service.grant(db_session, a.id, "heal_small", 4)
    payload = await _full_inventory(db_session, a.id)
    relic = payload["trophies"][0]
    assert relic["rarity_title"] == "Редкая" and relic["price_total"] == relic["price"] * 3
    assert relic["icon"] == "trophy:blood_shard" and relic["description"]
    potion = payload["consumables"][0]
    assert potion["transfer_prefix"] == "/передать Малое исцеление" and potion["count"] == 4


# --- Налог фракции на переводы валюты (2026-10-15) ---


async def test_currency_minimum(db_session, make_character) -> None:
    a = await make_character(farm=1000, donate=1000)
    b = await make_character(region="docks")
    for word in ("золото", "самоцветы"):
        offer = (await ts.find(db_session, a.id, word)).offers[0]
        with pytest.raises(ts.TransferFailed, match="от 100"):
            await ts.execute(db_session, a.id, b.id, offer, 99)


async def test_tax_rounds_down_and_feeds_first_supplier(db_session, make_character) -> None:
    from datetime import date

    from models import FactionPayout, FactionWeek
    from services import faction_service

    a = await make_character(farm=10_000, donate=1000, region="ridge")
    b = await make_character(region="docks")
    leader = await make_character(region="docks")
    today = faction_service.msk_day(faction_service._now())
    prev = faction_service.week_start(today) - __import__("datetime").timedelta(days=7)
    db_session.add(FactionWeek(city="docks", week_start=prev, first_id=leader.id))
    await db_session.flush()
    gold = (await ts.find(db_session, a.id, "золото")).offers[0]
    await ts.execute(db_session, a.id, b.id, gold, 139)
    assert (await wallet_service.get_wallet(db_session, b.id)).farm_currency == 133  # налог 6
    gems = (await ts.find(db_session, a.id, "самоцветы")).offers[0]
    await ts.execute(db_session, a.id, b.id, gems, 400)
    assert (await wallet_service.get_wallet(db_session, b.id)).donate_currency == 380  # налог 20
    row = await db_session.get(FactionPayout, leader.id)
    assert (row.gold, row.gems) == (1, 5)  # 25% от 6 и от 20, вниз
    payouts = await faction_service.pay_leaders(db_session)
    assert [(p.character_id, p.gold, p.gems) for p in payouts] == [(leader.id, 1, 5)]
    w = await wallet_service.get_wallet(db_session, leader.id)
    assert (w.farm_currency, w.donate_currency) == (1, 5)
    assert await faction_service.pay_leaders(db_session) == []
    assert isinstance(prev, date)


async def test_no_guild_tax_on_transfer(db_session, make_character) -> None:
    from models import Guild

    a = await make_character(farm=1000)
    b = await make_character()
    guild = Guild(name="Налоговики", tag="НАЛ", gold_tax=20)
    db_session.add(guild)
    await db_session.flush()
    b.guild_id = guild.id
    await db_session.flush()
    offer = (await ts.find(db_session, a.id, "золото")).offers[0]
    await ts.execute(db_session, a.id, b.id, offer, 200)
    assert (await wallet_service.get_wallet(db_session, b.id)).farm_currency == 190


def test_recipient_nick_hidden_in_group_chats_even_for_guildmates() -> None:
    from bot.handlers.transfer import recipient_name_visible

    assert recipient_name_visible(5, 5, peer_id=100, from_id=100)          # личка, одна гильдия
    assert not recipient_name_visible(5, 5, peer_id=2_000_000_001, from_id=100)  # беседа
    assert not recipient_name_visible(5, 6, peer_id=100, from_id=100)      # разные гильдии
    assert not recipient_name_visible(None, None, peer_id=100, from_id=100)


def test_parse_drops_the_word_pieces() -> None:
    assert ts.parse("горькая полынь 1 штука") == ("горькая полынь", 1)
    assert ts.parse("Малое исцеление 3 шт") == ("малое исцеление", 3)
    assert ts.parse("пепельный кварц штуки") == ("пепельный кварц", None)


async def test_batch_through_commas(db_session, make_character) -> None:
    """2026-10-21: «/передать горькая полынь 1 штука, Малое исцеление 2» - всё
    одним подтверждением; без числа - одна штука; нашлось не всё - отказ целиком."""
    from bot.handlers import transfer as th
    from services import herb_service

    a = await make_character()
    await herb_service.add_herb(db_session, a.id, "bitter_wormwood", 5)
    elixir = elixir_service.elixir_defs_ordered()[0]
    await elixir_service.grant(db_session, a.id, elixir.id, 4)

    batch, refusal = await th._resolve_batch(
        db_session, a.id, ["горькая полынь 1 штука", f" {elixir.name} 2", ]
    )
    assert refusal is None and [(o.kind, q) for o, q in batch] == [("herb", 1), ("elixir", 2)]
    batch, refusal = await th._resolve_batch(db_session, a.id, ["горькая полынь", "меч тысячи истин"])
    assert batch == [] and "меч тысячи истин" in refusal
    batch, refusal = await th._resolve_batch(db_session, a.id, ["горькая полынь 9"])
    assert batch == [] and "5" in refusal
