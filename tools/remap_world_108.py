"""Разовый перенос координат контента на круглую карту (патч 108).

Старая карта - квадрат -50..50, кольца по расстоянию Чебышёва, регионы по
четвертям (Кряж на северо-востоке и т.д.). Новая - круг радиуса 30, регионы
по сторонам света. Перенос точки:

- поворот на 45° против часовой: центр каждого региона переезжает с
  диагонали на свою сторону света;
- радиус - кусочно-линейно, кольцо в кольцо: точка у внешнего края старого
  кольца оказывается у внешнего края нового.

После переноса точка проверяется и при нужде сдвигается на ближайшую
подходящую клетку: то же кольцо, тот же регион, в пределах мира, не город,
не Монолит и не занята другим озером/рудником. У целей сюжета, где подпись -
название типа локации, предпочитается клетка именно этого типа.

Запуск: python tools/remap_world_108.py (переписывает JSON на месте; второй
запуск испортит координаты - скрипт разовый, результат коммитится).
"""

import json
import math
import re
from pathlib import Path

from game.world import grid
from game.world import world_config as wc
from game.world.location_types import location_type_at, region_for

ROOT = Path(__file__).resolve().parent.parent
OLD_RINGS = [(40, 50), (25, 39), (12, 24), (3, 11), (0, 2)]


def _old_tier(dist: int) -> int:
    for tier, (lo, hi) in enumerate(OLD_RINGS, start=1):
        if lo <= dist <= hi:
            return tier
    return 5


#: На старой карте точки региона лежали кучно у диагонали город-Монолит.
#: Простой поворот положил бы их все на одну линию, поэтому отклонение от
#: оси региона растягивается в SPREAD раз (но не за пределы сектора).
SPREAD = 5.0
MAX_OFFSET = math.radians(38)
MIN_CITY_GAP = 3


def mapped_point(x: int, y: int, regional: bool = True) -> tuple[float, float, int]:
    """(новый x, новый y, кольцо) без проверок."""
    dist = max(abs(x), abs(y))
    tier = _old_tier(dist)
    lo, hi = OLD_RINGS[tier - 1]
    nlo, nhi = wc.ring_bounds(tier)
    frac = 0.5 if hi == lo else (dist - lo) / (hi - lo)
    radius = nlo + frac * (nhi - nlo)
    theta = math.atan2(y, x)
    if regional:
        diagonal = math.copysign(math.pi / 4, y) if x >= 0 else math.copysign(3 * math.pi / 4, y)
        offset = max(-MAX_OFFSET, min(MAX_OFFSET, SPREAD * (theta - diagonal)))
        angle = diagonal + math.pi / 4 + offset
    else:
        angle = theta + math.pi / 4
    return radius * math.cos(angle), radius * math.sin(angle), tier


def place(x: int, y: int, region: str | None, taken: set, prefer_label: str | None = None):
    fx, fy, tier = mapped_point(x, y, regional=region is not None)
    candidates = []
    for cx, cy in grid.all_cells():
        if grid.ring_tier(cx, cy) != tier or (cx, cy) in taken:
            continue
        if (cx, cy) == (0, 0) or grid.city_region_at(cx, cy) is not None:
            continue
        if any(grid.cells_between(cx, cy, *city) < MIN_CITY_GAP for city in wc.CITY_COORDS.values()):
            continue
        if region is not None and region_for(cx, cy) != region:
            continue
        # Не впритык к краю мира: там уже только фон картинки.
        if grid.monolith_distance(cx, cy) > wc.WORLD_RADIUS - 1 and tier == 1:
            continue
        candidates.append((cx, cy))
    def score(c):
        d = math.hypot(c[0] - fx, c[1] - fy)
        if prefer_label and location_type_at(*c).name == prefer_label and d <= 4:
            d -= 10
        return d
    best = min(candidates, key=score)
    taken.add(best)
    return best


def main() -> None:
    taken: set = set()
    for rel in ("content/fishing/lakes.json", "content/mining/mines.json"):
        path = ROOT / rel
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            nx, ny = place(row["x"], row["y"], row["region"], taken)
            print(f"{rel.split('/')[1]:8} {row['id']:28} ({row['x']};{row['y']}) -> ({nx};{ny}) кольцо {row['tier']}")
            row["x"], row["y"] = nx, ny
        _write_rows(path, rows)
    for region in ("ridge", "woods", "docks", "scorched"):
        path = ROOT / "content" / "story" / f"{region}.json"
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        story_taken: dict = {}
        for act in data["acts"]:
            for quest in act["quests"]:
                if quest.get("target_x") is None:
                    continue
                old = (quest["target_x"], quest["target_y"])
                if old not in story_taken:
                    story_taken[old] = place(*old, region, set(taken), quest.get("target_label"))
                nx, ny = story_taken[old]
                print(f"{region:8} {quest['id']:28} {old} -> ({nx};{ny}) {quest.get('target_label')}")
                text = _replace_target(text, quest["id"], old, (nx, ny))
        path.write_text(text, encoding="utf-8")


def _write_rows(path: Path, rows: list[dict]) -> None:
    """Тот же формат, что и был: одна запись - заголовок строкой, потом
    название и описания. Правим только числа в исходном тексте, чтобы диф
    показывал ровно перенос."""
    text = path.read_text(encoding="utf-8")
    for row in rows:
        marker = f'"id": "{row["id"]}"'
        start = text.index(marker)
        end = text.index("\n", start)
        line = text[start:end]
        line = re.sub(r'"x": -?\d+', f'"x": {row["x"]}', line, count=1)
        line = re.sub(r'"y": -?\d+', f'"y": {row["y"]}', line, count=1)
        text = text[:start] + line + text[end:]
    path.write_text(text, encoding="utf-8")


def _replace_target(text: str, quest_id: str, old, new) -> str:
    start = text.index(f'"id": "{quest_id}"')
    x_at = text.index('"target_x":', start)
    y_at = text.index('"target_y":', start)
    x_end = text.index(",", x_at)
    y_end = min(i for i in (text.find(",", y_at), text.find("\n", y_at)) if i != -1)
    assert int(text[x_at + 11:x_end]) == old[0] and int(text[y_at + 11:y_end]) == old[1]
    text = text[:y_at] + f'"target_y": {new[1]}' + text[y_end:]
    return text[:x_at] + f'"target_x": {new[0]}' + text[x_end:]


if __name__ == "__main__":
    main()
