"""Магазин: смена ника и названия фирмы за самоцветы (2026-10-16)."""

import pytest

from services import shop_service, trade_service
from services.wallet_service import get_wallet


async def test_rename_character_charges_only_on_success(db_session, make_character):
    c = await make_character(donate=1000)
    other = await make_character()
    for bad in ("аб", "плохой ник", other.name, c.name):
        with pytest.raises(shop_service.ShopError):
            await shop_service.rename_character(db_session, c, bad)
    assert (await get_wallet(db_session, c.id)).donate_currency == 1000
    old = await shop_service.rename_character(db_session, c, "НовыйНик")
    assert c.name == "НовыйНик" and old.startswith("Тестовый")
    assert (await get_wallet(db_session, c.id)).donate_currency == 1000 - shop_service.RENAME_PRICE


async def test_rename_needs_gems(db_session, make_character):
    c = await make_character(donate=10)
    with pytest.raises(shop_service.ShopError, match="самоцветов"):
        await shop_service.rename_character(db_session, c, "Богач")
    assert c.name != "Богач"


async def test_rename_firm(db_session, make_character):
    c = await make_character(level=20, farm=10_000, donate=1000, region="ridge")
    with pytest.raises(shop_service.ShopError, match="фирму"):
        await shop_service.rename_firm(db_session, c, "Новое Имя")
    await trade_service.buy_firm(db_session, c, "Старая Лавка")
    other = await make_character(level=20, farm=10_000, region="docks")
    await trade_service.buy_firm(db_session, other, "Занятая Лавка")
    with pytest.raises(shop_service.ShopError, match="уже есть"):
        await shop_service.rename_firm(db_session, c, "занятая лавка")
    assert (await get_wallet(db_session, c.id)).donate_currency == 1000
    old = await shop_service.rename_firm(db_session, c, "Новая Лавка")
    firm = await trade_service.get_firm(db_session, c.id)
    assert old == "Старая Лавка" and firm.name == "Новая Лавка" and firm.name_key == "новая лавка"
    assert (await get_wallet(db_session, c.id)).donate_currency == 1000 - shop_service.FIRM_RENAME_PRICE


def test_catalog_lists_rename_items(make_character):
    from types import SimpleNamespace

    from datetime import datetime, timezone

    c = SimpleNamespace(name="Ник", premium_until=datetime(2000, 1, 1, tzinfo=timezone.utc), region="ridge", has_donka=False,
                        ash_tincture_until=None, secret_pocket=False, faction_changed_at=None,
                        pending_faction=None, has_courier=False, has_house=False)
    items = {i["id"]: i for i in shop_service.catalog(c, 0)["items"]}
    assert items["rename"]["price"] == 300 and items["firm_rename"]["price"] == 500
    assert items["firm_rename"]["available"] is False
    assert items["house"]["price"] == 500 and items["house"]["available"] is True


def test_every_catalog_item_is_buyable() -> None:
    """Дом был в каталоге, но не в списке покупки - игрок получал bad_request."""
    from datetime import datetime, timezone
    from types import SimpleNamespace

    from bot.miniapp_shop_api import BUYABLE

    c = SimpleNamespace(name="Ник", premium_until=datetime(2000, 1, 1, tzinfo=timezone.utc), region="ridge", has_donka=False,
                        ash_tincture_until=None, secret_pocket=False, faction_changed_at=None,
                        pending_faction=None, has_courier=False, has_house=False)
    ids = {i["id"] for i in shop_service.catalog(c, 0, "Фирма")["items"]}
    assert ids <= set(BUYABLE), ids - set(BUYABLE)
