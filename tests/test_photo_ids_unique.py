"""Один номер фото — одна сущность (патч 90).

Картинки лежат в альбоме группы ВК, и в игре от них остаётся только номер.
Перепутанный номер не ломает ничего: сообщение уходит, картинка грузится,
просто она чужая. Заметить это можно лишь глазами и лишь у той сущности,
которая попадётся, — а мобов в игре больше полусотни.

Поэтому номера сверяются между собой. Добавляя двадцать номеров разом (рейд
и сюжетные акты), ошибиться в одной цифре очень легко.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
CODE = (
    "bot/world_texts.py",
    "bot/onboarding_texts.py",
    "bot/raid_texts.py",
    "bot/handlers/combat.py",
    "bot/handlers/respawn.py",
    # Патч 99: картинки рудников и озёр по тирам.
    "bot/mining_texts.py",
    "bot/fishing_texts.py",
)
PHOTO_ID = re.compile(r'"(\d{9})"')

#: Старый дефект, найденный этой же проверкой и НЕ исправленный: правильного
#: номера для одного из двух мобов просто нет, его нужно нарисовать. Пока
#: он здесь, чтобы проверка работала на всём остальном; когда картинка
#: появится — строку убрать, и тест сам проследит, что её не забыли.
KNOWN_COLLISION = {"457239081"}


def _collect() -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)

    def walk(node, where: str) -> None:
        if isinstance(node, dict):
            image = node.get("image")
            if isinstance(image, str) and image:
                name = node.get("name") or node.get("id") or f"акт {node.get('act')}"
                found[image].append(f"{where}: {name}")
            for value in node.values():
                walk(value, where)
        elif isinstance(node, list):
            for value in node:
                walk(value, where)

    for path in CONTENT.rglob("*.json"):
        walk(json.loads(path.read_text(encoding="utf-8")), path.name)

    for relative in CODE:
        source = (ROOT / relative).read_text(encoding="utf-8")
        for match in PHOTO_ID.finditer(source):
            found[match.group(1)].append(Path(relative).name)

    return found


def test_no_photo_is_used_by_two_different_things() -> None:
    collisions = {
        photo: users
        for photo, users in _collect().items()
        if len(users) > 1 and photo not in KNOWN_COLLISION
    }
    assert not collisions, "один номер фото на несколько сущностей:\n" + "\n".join(
        f"  {photo}: {', '.join(users)}" for photo, users in sorted(collisions.items())
    )


def test_the_known_collision_is_still_the_only_one() -> None:
    """Исключение не должно пережить свою причину: когда номер починят,
    список известных дублей обязан опустеть вместе с ним."""
    found = _collect()
    stale = [photo for photo in KNOWN_COLLISION if len(found.get(photo, [])) < 2]
    assert not stale, f"дубль {stale} уже исправлен - уберите его из KNOWN_COLLISION"


def test_every_story_act_after_the_first_has_a_picture() -> None:
    """Слот, оставшийся пустым при заливке, иначе заметит только игрок."""
    empty = []
    for path in sorted((CONTENT / "story").glob("*.json")):
        for act in json.loads(path.read_text(encoding="utf-8"))["acts"]:
            if act["act"] != 1 and not act.get("image"):
                empty.append(f"{path.stem} акт {act['act']}")
    assert not empty, f"акты без картинки: {empty}"
