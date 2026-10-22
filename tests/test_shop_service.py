"""Магазин мини-аппа (2026-10-13): Метка Хранителя за самоцветы."""

from datetime import datetime, timedelta, timezone

import pytest

from game.economy import premium_config as pc
from services import shop_service, wallet_service


def test_price_curve_from_50_to_800_and_day_gets_cheaper() -> None:
    prices = [pc.shop_price(d) for d in range(1, 31)]
    assert prices[0] == 50 and prices[-1] == 800
    assert prices == sorted(prices)  # дольше - дороже в сумме
    per_day = [p / d for d, p in enumerate(prices, start=1)]
    assert per_day[0] > per_day[6] > per_day[13] > per_day[-1]  # но дешевле за день
    assert all(p % 5 == 0 for p in prices)


async def test_buy_charges_gems_and_grants_mark(db_session, make_character) -> None:
    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "donate", 1000)
    until = await shop_service.buy_premium(db_session, character, 7)
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.donate_currency == 1000 - pc.shop_price(7)
    left = until - datetime.now(timezone.utc)
    assert timedelta(days=6, hours=23) < left <= timedelta(days=7)


async def test_repeat_purchase_adds_on_top_of_remaining(db_session, make_character) -> None:
    """Повторная покупка прибавляет срок к оставшемуся, а не заменяет его."""
    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "donate", 2000)
    first = await shop_service.buy_premium(db_session, character, 10)
    second = await shop_service.buy_premium(db_session, character, 5)
    assert second - first == timedelta(days=5)


async def test_not_enough_gems_and_bad_days(db_session, make_character) -> None:
    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "donate", 40)
    with pytest.raises(shop_service.ShopError):
        await shop_service.buy_premium(db_session, character, 1)
    for bad in (0, 31, "7", None):
        with pytest.raises(shop_service.ShopError):
            await shop_service.buy_premium(db_session, character, bad)
    assert (await wallet_service.get_wallet(db_session, character.id)).donate_currency == 40
    assert character.premium_until is None


async def test_elixir_pack_gives_ten_large_heals_and_two_of_each_combat(db_session, make_character) -> None:
    """2026-10-19: набор зелий за 100 самоцветов."""
    from services import elixir_service

    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "donate", 150)
    await shop_service.buy_elixir_pack(db_session, character)
    assert (await wallet_service.get_wallet(db_session, character.id)).donate_currency == 50
    stock = {d.id: n for d, n in await elixir_service.get_stock(db_session, character.id)}
    assert stock.pop("heal_large") == 10
    combat = [d.id for d in elixir_service.elixir_defs_ordered() if d.category == "combat"]
    assert stock == {cid: 2 for cid in combat} and len(combat) >= 5
    with pytest.raises(shop_service.ShopError):
        await shop_service.buy_elixir_pack(db_session, character)


async def test_elixir_pack_by_quantity(db_session, make_character) -> None:
    """2026-10-22, владелец: повторяемые товары - ползунком до 100 штук."""
    from services import elixir_service

    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "donate", shop_service.ELIXIR_PACK_PRICE * 3)
    await shop_service.buy_elixir_pack(db_session, character, 3)
    assert (await wallet_service.get_wallet(db_session, character.id)).donate_currency == 0
    stock = {d.id: n for d, n in await elixir_service.get_stock(db_session, character.id)}
    assert stock["heal_large"] == 30
    for bad in (0, shop_service.MAX_QTY + 1, "5", True):
        with pytest.raises(shop_service.ShopError):
            await shop_service.buy_elixir_pack(db_session, character, bad)
