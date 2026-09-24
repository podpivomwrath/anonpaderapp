"""Человеческие названия для внутренних id (патч 73).

Заведено после того, как в мини-аппе всплыло «dark_mystic» вместо «Тёмный
мистик». Проблема была не в одном месте: id подкласса, региона, слота и
редкости отдавались наружу сырыми в нескольких payload-ах сразу, и каждый
решал сам, резолвить их или нет.

Правило прежнее (патч 57): ФОРМАТ ПРИНАДЛЕЖИТ СЕРВЕРУ. Клиент получает
готовую строку и ничего не пересказывает своими словами. Поэтому резолв
живёт здесь, в одной точке, а не в каждом обработчике.

Неизвестный id возвращается как есть: показать «dark_mystic» некрасиво, но
честнее, чем прочерк, за которым не видно, что именно сломалось.
"""

from bot.onboarding_texts import REGION_TITLES
from game.classes import REGISTRY
from services.item_service import SLOT_TITLES, bases, rarities

#: Базовые классы. Живут здесь, а не в админке, откуда их пришлось бы
#: импортировать всем остальным - названия принадлежат этому модулю.
BASE_CLASS_TITLES = {"warrior": "Воин", "rogue": "Разбойник", "mage": "Маг"}


def subclass_title(subclass_id: str | None) -> str | None:
    if not subclass_id:
        return None
    definition = REGISTRY.get(subclass_id)
    return definition.title if definition is not None else subclass_id


def base_class_title(base_class_id: str | None) -> str | None:
    if not base_class_id:
        return None
    return BASE_CLASS_TITLES.get(base_class_id, base_class_id)


def region_title(region_id: str | None) -> str | None:
    if not region_id:
        return None
    return REGION_TITLES.get(region_id, region_id)


def slot_title(slot_id: str | None) -> str | None:
    if not slot_id:
        return None
    return SLOT_TITLES.get(slot_id, slot_id)


def rarity_title(rarity_id: str | None) -> str | None:
    if not rarity_id:
        return None
    definition = rarities().get(rarity_id)
    return definition.name if definition is not None else rarity_id


# --- Иконки ---------------------------------------------------------------------

def item_icon_key(item) -> str | None:
    """Ключ картинки предмета (см. miniapp/src/itemIcons.js).

    Считает СЕРВЕР, а не клиент: у процедурной экипировки имя собрано из
    суффикса редкости и базы («Кровавый клинок»), и чтобы достать из него
    базу, нужен каталог баз — на клиенте его нет, а дублировать разбор имени
    туда значило бы завести второе место, где это правило живёт.

    Порядок проверок = от частного к общему: скованное оружие носит имя
    результата ковки, уникальное — своё собственное, и ни то ни другое
    искать среди баз не нужно.
    """
    if item.craft_spec:
        return f"craft:{item.craft_spec}"
    if item.craft_source_id:
        return f"unique:{item.craft_source_id}"
    if not item.slot or not item.name:
        return None
    lowered = item.name.lower()
    for base in bases().get(item.slot, []):
        if base.name.lower() in lowered:
            return f"base:{item.slot}:{base.name}"
    return None
