"""Патч 73: внутренние id не должны утекать в текст, который видит игрок.

Поймано на проде: в шапке мини-аппа вместо «Тёмный мистик» висело
«dark_mystic». Причина системная - id подкласса, региона, слота и редкости
отдавались наружу сырыми сразу в нескольких payload-ах, и каждый решал сам,
резолвить их или нет. Теперь резолв один (services/naming.py), а эти тесты
держат правило.
"""

import re
from pathlib import Path

import pytest

from game.classes import REGISTRY
from services import naming

ROOT = Path(__file__).resolve().parent.parent


# --- Резолв ---------------------------------------------------------------------


@pytest.mark.parametrize("subclass_id", sorted(REGISTRY))
def test_every_subclass_has_a_human_name(subclass_id: str) -> None:
    title = naming.subclass_title(subclass_id)
    assert title != subclass_id, f"{subclass_id} отдаётся сырым"
    assert re.search(r"[а-яА-ЯёЁ]", title), f"{subclass_id}: название не по-русски"


def test_unknown_id_comes_back_as_is() -> None:
    """Прочерк спрятал бы поломку: по «-» не видно, ЧТО именно не нашлось."""
    assert naming.subclass_title("нет_такого") == "нет_такого"
    assert naming.region_title("нет_такого") == "нет_такого"


def test_empty_stays_empty() -> None:
    for resolve in (naming.subclass_title, naming.region_title,
                    naming.slot_title, naming.rarity_title, naming.base_class_title):
        assert resolve(None) is None
        assert resolve("") is None


def test_known_vocabularies_resolve() -> None:
    assert naming.region_title("ridge") != "ridge"
    assert naming.slot_title("weapon") == "Оружие"
    assert naming.rarity_title("epic") == "Эпическая"
    assert naming.base_class_title("mage") == "Маг"


# --- Мини-апп: рендерим названия, а не id ----------------------------------------

ID_FIELDS = ("subclass", "region", "rarity", "slot")


def _jsx_files() -> list[Path]:
    return sorted((ROOT / "miniapp" / "src").rglob("*.jsx"))


def test_miniapp_never_renders_a_raw_id() -> None:
    """Поля-id нужны клиенту для запросов и ключей, но НЕ для показа."""
    offenders: list[str] = []
    for path in _jsx_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if "key={" in line or "onClick" in line or "onChange" in line:
                continue  # служебное использование, не текст
            for field in ID_FIELDS:
                if re.search(rf"\.{field}_(title|name)", line):
                    continue
                rendered = re.search(
                    rf"(\$\{{[^}}]*\.{field}\b(?!_)|value=\{{[^}}]*\.{field}\b(?!_))", line
                )
                if rendered:
                    offenders.append(f"{path.name}:{number} [{field}] {line.strip()[:90]}")
    assert not offenders, "сырые id в интерфейсе:\n" + "\n".join(offenders)


# --- Боевой лог -------------------------------------------------------------------


def test_no_developer_notes_reach_the_player() -> None:
    """«TODO: content» и внутренний id навыка когда-то печатались прямо в
    боевом логе. Страховочная ветка должна выглядеть как часть игры.

    Смотрим СТРОКОВЫЕ ЛИТЕРАЛЫ, а не текст файла: упоминание в комментарии -
    это история правки, и запрещать её незачем. Запрещено ровно то, что
    может дойти до игрока.
    """
    import ast

    for name in ("game/combat/resolver.py", "game/combat/duel_engine.py"):
        tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
        literals = [
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        # Докстринги тоже строки - отсеиваем по тому, что игроку уходят
        # только короткие однострочные реплики.
        player_facing = [text for text in literals if "\n" not in text]
        for text in player_facing:
            assert "TODO" not in text, f"{name}: записка разработчика в тексте - {text!r}"
            assert "не реализовано" not in text, f"{name}: служебная формулировка - {text!r}"


def test_unimplemented_line_uses_the_skill_name() -> None:
    from game.combat import combat_flavor

    line = combat_flavor.unimplemented_skill_line("Боец", "dark_mystic_ward")
    assert "dark_mystic_ward" not in line
    assert "Боец" in line

    # Неизвестный навык тоже не должен светить id.
    fallback = combat_flavor.unimplemented_skill_line("Боец", "нет_такого")
    assert "нет_такого" not in fallback


def test_every_skill_has_a_handler() -> None:
    """Пока это так, страховочная ветка недостижима - а значит игрок её и не
    увидит. Тест ловит момент, когда навык добавили, а обработчик забыли."""
    import game.classes  # noqa: F401  - регистрирует обработчики подклассов
    from game.combat.base_skills import BASE_SKILL_DEFS
    from game.combat.skills import DEFENSIVE_SKILLS, OFFENSIVE_SKILLS
    from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS

    declared = set(BASE_SKILL_DEFS) | set(SUBCLASS_SKILL_DEFS)
    handled = set(OFFENSIVE_SKILLS) | set(DEFENSIVE_SKILLS)
    assert not declared - handled, f"навыки без обработчика: {sorted(declared - handled)}"
