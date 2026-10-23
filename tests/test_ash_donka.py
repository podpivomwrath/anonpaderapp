"""Пепельная донка (2026-10-23, владелец): авторыбалка из магазина, вчетверо
медленнее, рыба сразу в садок, только пока игрок рядом."""

from datetime import datetime, timedelta, timezone

from bot.handlers import fishing as handler
from game.economy import fishing
from services import fishing_service, shop_service, wallet_service


async def _at_lake(character_at):
    lake = fishing.all_lakes()[0]
    c = await character_at(lake.x, lake.y)
    c.screen = "lake"
    c.has_donka = True
    c.last_active_at = datetime.now(timezone.utc)
    return c, lake


async def test_donka_is_four_times_slower_and_keeps_fishing(db_session, character_at) -> None:
    c, lake = await _at_lake(character_at)
    before = datetime.now(timezone.utc)
    wait = await handler._donka_cast(db_session, c, lake)
    assert c.fishing_auto and fishing_service.is_casting(c)
    assert c.fishing_bite_at >= before + timedelta(seconds=wait - 1)
    # Поклёвка: подсечка сама, следующий заброс - снова донкой.
    c.fishing_bite_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    xp_before = (c.fishing_level, c.fishing_xp)
    text, keyboard, nxt = await handler._donka_bite(db_session, c, 777010)
    assert text.startswith("🪝 Донка") and nxt is not None and c.fishing_auto
    assert keyboard is None
    # Опыт за донку есть и виден в сообщении (2026-10-23, владелец вернул).
    assert (c.fishing_level, c.fishing_xp) != xp_before
    assert "опыта рыбалки" in text


async def test_donka_stops_when_player_idle(db_session, character_at) -> None:
    c, lake = await _at_lake(character_at)
    await handler._donka_cast(db_session, c, lake)
    c.last_active_at = datetime.now(timezone.utc) - timedelta(hours=2)
    text, _kb, nxt = await handler._donka_bite(db_session, c, 777011)
    assert nxt is None and not c.fishing_auto and not fishing_service.is_casting(c)


async def test_donka_bought_once(db_session, make_character) -> None:
    c = await make_character()
    await wallet_service.deposit(db_session, c.id, "donate", shop_service.DONKA_PRICE * 2)
    await shop_service.buy_donka(db_session, c)
    assert c.has_donka
    import pytest

    with pytest.raises(shop_service.ShopError):
        await shop_service.buy_donka(db_session, c)
