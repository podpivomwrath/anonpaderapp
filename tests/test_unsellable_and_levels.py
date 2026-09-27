"""Живой прогон на pupsik (27.09): скупщик показывал уникальную Иглу
Хирурга «за 0 зол.» с кнопкой продажи, а вещи без уровня печатались
как «ур. None»."""

from types import SimpleNamespace

from bot.handlers import appraiser
from services import item_service


def _item(**kw):
    base = {"name": "Вещь", "rarity": "common", "ilvl": 10, "admin_only": False, "bound": False,
            "slot": "weapon", "base_stats": {"str": 5}}
    base.update(kw)
    return SimpleNamespace(**base)


def test_appraiser_lists_only_what_it_buys() -> None:
    unique = _item(name="Игла Хирурга", rarity="unique", ilvl=None)
    bound = _item(name="Скованное", bound=True)
    admin = _item(name="Перо", rarity="admin", ilvl=None, admin_only=True)
    plain = _item(name="Клинок")
    listed = [item.name for item, _ in appraiser._sellable(
        [(unique, False), (bound, False), (admin, False), (plain, False)], 1.0)]
    assert listed == ["Клинок"]


def test_item_without_level_has_no_level_note() -> None:
    assert item_service.level_note(_item(ilvl=None)) == ""
    assert item_service.level_note(_item(ilvl=60)) == " (ур. 60)"
    label = item_service.format_item_label(_item(name="Игла Хирурга", rarity="unique", ilvl=None))
    assert "None" not in label and "ур." not in label
