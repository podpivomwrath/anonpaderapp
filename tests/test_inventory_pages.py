"""Патч 109: текст инвентаря постраничный, как и кнопки - по 10 вещей."""

from bot.handlers import inventory
from bot.keyboards.items import INVENTORY_PAGE_SIZE
from models import Inventory, Item


async def _fill(db, character, count: int) -> None:
    for i in range(count):
        item = Item(name=f"Вещь {i:02d}", slot="weapon", base_stats={"str": 1}, rarity="common", ilvl=10)
        db.add(item)
        await db.flush()
        db.add(Inventory(character_id=character.id, item_id=item.id, equipped=False))
    await db.flush()


async def test_text_shows_only_the_current_page(db_session, make_character) -> None:
    me = await make_character()
    await _fill(db_session, me, 25)
    page1, _ = await inventory._render_list(db_session, me, 1)
    page3, _ = await inventory._render_list(db_session, me, 3)
    assert INVENTORY_PAGE_SIZE == 10
    assert page1.count("Вещь ") == 10 and "стр. 1 из 3" in page1
    assert page3.count("Вещь ") == 5 and "стр. 3 из 3" in page3
    assert "вещей: 25" in page1


async def test_page_out_of_range_is_clamped(db_session, make_character) -> None:
    me = await make_character()
    await _fill(db_session, me, 12)
    text, _ = await inventory._render_list(db_session, me, 99)
    assert "стр. 2 из 2" in text and text.count("Вещь ") == 2


async def test_short_inventory_has_no_page_header(db_session, make_character) -> None:
    me = await make_character()
    await _fill(db_session, me, 3)
    text, _ = await inventory._render_list(db_session, me)
    assert text.startswith("🎒 Инвентарь:") and "стр." not in text
