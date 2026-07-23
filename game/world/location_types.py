"""Типы локаций по клетке карты (патч 10, блок 4).

Тип детерминирован по координатам — игрок, вернувшись на ту же клетку, видит
тот же тип локации (просто другое случайное описание из его пула). Регион
клетки — по четверти карты (может не совпадать с домашним регионом персонажа,
если тот забрёл далеко): (+;+) Кряж, (-;+) Пущи, (+;-) Пристани, (-;-) Предел.
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
    """Геогр. регион клетки по четверти карты (знаки координат)."""
    if x >= 0 and y >= 0:
        return "ridge"
    if x < 0 and y >= 0:
        return "woods"
    if x >= 0 and y < 0:
        return "docks"
    return "scorched"


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
