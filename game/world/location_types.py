"""Типы локаций по клетке карты (патч 10, блок 4).

Тип детерминирован по координатам — игрок, вернувшись на ту же клетку, видит
тот же тип локации (просто другое случайное описание из его пула). Регион
клетки — по сектору карты (может не совпадать с домашним регионом персонажа,
если тот забрёл далеко): север Кряж, восток Пристани, юг Предел, запад Пущи.
"""

from game.content_loader import LocationTypeDef, load_location_types

_types_by_region: dict[str, list[LocationTypeDef]] | None = None


def _by_region() -> dict[str, list[LocationTypeDef]]:
    global _types_by_region
    if _types_by_region is None:
        result: dict[str, list[LocationTypeDef]] = {}
        for type_def in load_location_types():
            result.setdefault(type_def.region, []).append(type_def)
        _types_by_region = result
    return _types_by_region


def region_for(x: int, y: int) -> str:
    """Геогр. регион клетки (патч 108): сектор в 90° вокруг своей стороны
    света - север Кряж, восток Пристани, юг Предел, запад Пущи. Границы
    секторов идут по диагоналям; клетка ровно на диагонали отходит к северу
    или югу (так делит и картинка карты)."""
    if abs(y) >= abs(x):
        return "ridge" if y >= 0 else "scorched"
    return "docks" if x > 0 else "woods"


def _type_index(x: int, y: int, count: int) -> int:
    """Детерминированный псевдо-хеш (x,y) -> [0, count) — не зависит от версии
    Python (не используем встроенный hash(), он рандомизирован для строк, а тут
    важна воспроизводимость на годы вперёд)."""
    h = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    h ^= h >> 16
    return h % count


def location_type_at(x: int, y: int) -> LocationTypeDef:
    region = region_for(x, y)
    types = _by_region()[region]
    return types[_type_index(x, y, len(types))]
