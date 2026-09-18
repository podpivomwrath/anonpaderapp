"""Патч 54: защита от РЕЦИДИВА «кнопки нового боевого режима не работают».

Три патча подряд (30 — PvP, 52 — эликсиры в PvP, 54 — рейд) выкатывались с
неработающими боевыми кнопками по одной и той же причине: vkbottle
диспетчерит по ПЕРВОМУ совпавшему правилу и на этом останавливается, поэтому
кнопка с подписью, уже занятой другим режимом, уходит ЧУЖОМУ обработчику —
тот не находит у игрока своего боя и молча выходит.

Эти тесты закрывают весь класс: уникальность подписей/payload между
режимами, полнота каждой боевой клавиатуры и — главное — автоматический
разбор ВСЕХ `text=`-правил в bot/handlers/ на предмет пересечений.
"""

import ast
import collections
import importlib
import json
import pathlib

from bot.keyboards import combat_modes
from bot.keyboards.group_combat import group_combat_keyboard
from bot.keyboards.pvp import pvp_combat_keyboard
from bot.keyboards.raid import raid_combat_keyboard
from bot.keyboards.world import combat_keyboard

_HANDLERS_DIR = pathlib.Path(__file__).resolve().parent.parent / "bot" / "handlers"


def _labels(keyboard_json: str) -> list[str]:
    data = json.loads(keyboard_json)
    return [button["action"]["label"] for row in data["buttons"] for button in row]


def _payload_types(keyboard_json: str) -> set[str]:
    data = json.loads(keyboard_json)
    types = set()
    for row in data["buttons"]:
        for button in row:
            payload = _payload(button)
            if payload and "type" in payload:
                types.add(payload["type"])
    return types


def _payload(button: dict) -> dict | None:
    """vkbottle отдаёт payload то словарём, то JSON-строкой — принимаем оба."""
    raw = button["action"].get("payload")
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else None


# --- Реестр режимов ---


def test_combat_mode_action_labels_are_unique_across_modes() -> None:
    """Главный инвариант: ни одна подпись боевой кнопки не принадлежит двум
    режимам. Именно это нарушал рейд (все три кнопки дублировали групповой
    PvE) и массовый PvP («🎯 Цель» дублировала групповой PvE с патча 51)."""
    owners: dict[str, str] = {}
    duplicates: list[str] = []
    for mode in combat_modes.ALL_MODES:
        for label in mode.action_labels:
            if label in owners:
                duplicates.append(f"{label!r}: {owners[label]} и {mode.mode_id}")
            owners[label] = mode.mode_id
    assert not duplicates, "Подписи боевых кнопок дублируются между режимами: " + "; ".join(duplicates)


def test_skill_payload_types_are_unique_across_modes() -> None:
    payloads = [mode.skill_payload for mode in combat_modes.ALL_MODES]
    assert len(payloads) == len(set(payloads))


def test_raid_has_no_escape_and_solo_pve_does() -> None:
    """Патч 53: выйти из рейда нельзя — кнопки побега не должно быть вовсе.
    Соло-PvE, наоборот, побег разрешает."""
    assert combat_modes.RAID.allows_escape is False
    assert combat_modes.PVP.allows_escape is False
    assert combat_modes.GROUP_PVE.allows_escape is False
    assert combat_modes.SOLO_PVE.allows_escape is True


# --- Полнота клавиатур (класс бага патча 30: не было кнопки предметов) ---


def test_every_combat_keyboard_contains_its_declared_actions() -> None:
    keyboards = {
        combat_modes.SOLO_PVE: combat_keyboard("warrior", {}),
        combat_modes.PVP: pvp_combat_keyboard("warrior", {}, show_target=True),
        combat_modes.GROUP_PVE: group_combat_keyboard("warrior", {}),
        combat_modes.RAID: raid_combat_keyboard("warrior", {}),
    }
    for mode, keyboard in keyboards.items():
        labels = _labels(keyboard)
        for label in mode.action_labels:
            assert label in labels, f"{mode.mode_id}: на клавиатуре нет кнопки {label!r}"


def test_raid_keyboard_has_no_escape_button() -> None:
    labels = _labels(raid_combat_keyboard("warrior", {}))
    assert combat_modes.SOLO_PVE.escape not in labels


def test_raid_buttons_carry_unique_payloads() -> None:
    """Второй рубеж: даже если подписи когда-нибудь сойдутся, рейдовые кнопки
    разводятся по payload (обработчики рейда слушают именно его)."""
    types = _payload_types(raid_combat_keyboard("warrior", {}))
    assert {"raid_attack", "raid_open_target", "raid_open_items", combat_modes.RAID.skill_payload} <= types


# --- Автоматический разбор правил диспетчера ---


def _text_rule_owners() -> dict[str, set[str]]:
    """{текст правила: модули-обработчики, которые его забирают}.

    Правила, разведённые по FSM-состоянию (`state=...`), НЕ учитываются:
    у них совпадение текста безопасно, состояния взаимно исключают друг друга
    (так устроены диалоги онбординга и Хранителя Списков)."""
    owners: dict[str, set[str]] = collections.defaultdict(set)
    for path in sorted(_HANDLERS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module_name = f"bot.handlers.{path.stem}"
        module = importlib.import_module(module_name)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                keywords = {kw.arg for kw in decorator.keywords or []}
                if "state" in keywords:
                    continue  # разведено по FSM-состоянию
                for keyword in decorator.keywords or []:
                    if keyword.arg != "text":
                        continue
                    node_value = keyword.value
                    elements = (
                        node_value.elts if isinstance(node_value, (ast.List, ast.Tuple)) else [node_value]
                    )
                    for element in elements:
                        value = _resolve(element, module)
                        if isinstance(value, str):
                            owners[value].add(module_name)
    return owners


def _resolve(node: ast.AST, module) -> str | None:
    """Значение элемента правила: литерал, константа модуля (BTN_*) или
    атрибут импортированного модуля (texts.BTN_*). Что не разрешилось
    статически — пропускаем, тест не должен падать из-за динамики."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return getattr(module, node.id, None)
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        base = getattr(module, node.value.id, None)
        return getattr(base, node.attr, None) if base is not None else None
    return None


def test_no_text_rule_is_claimed_by_two_handler_modules() -> None:
    """РЕГРЕССИЯ патчей 30/52/54. Если два лейблера слушают один и тот же
    текст без разведения по состоянию, второй по порядку регистрации не
    вызовется НИКОГДА — игрок жмёт кнопку и не получает ничего."""
    collisions = {
        text: sorted(modules)
        for text, modules in _text_rule_owners().items()
        if len(modules) > 1
    }
    assert not collisions, (
        "Один и тот же текст кнопки слушают несколько обработчиков - "
        "сработает только первый по порядку в bot/handlers/__init__.py::LABELERS: "
        f"{collisions}"
    )


def _buttons(keyboard_json: str) -> list[tuple[str, str | None]]:
    """[(подпись, payload-type или None)] по всем кнопкам клавиатуры."""
    data = json.loads(keyboard_json)
    result = []
    for row in data["buttons"]:
        for button in row:
            payload = _payload(button)
            payload_type = payload.get("type") if payload else None
            result.append((button["action"]["label"], payload_type))
    return result


def test_every_combat_action_button_has_a_handler() -> None:
    """Каждая кнопка действия обязана кем-то обрабатываться — по тексту или
    по payload. Иначе кнопка на клавиатуре есть, а нажатие не делает ничего
    (ровно симптом патчей 30 и 54)."""
    text_owners = _text_rule_owners()
    payload_types = _payload_rule_types()
    keyboards = {
        combat_modes.SOLO_PVE: combat_keyboard("warrior", {}),
        combat_modes.PVP: pvp_combat_keyboard("warrior", {}, show_target=True),
        combat_modes.GROUP_PVE: group_combat_keyboard("warrior", {}),
        combat_modes.RAID: raid_combat_keyboard("warrior", {}),
    }
    for mode, keyboard in keyboards.items():
        action_labels = set(mode.action_labels)
        for label, payload_type in _buttons(keyboard):
            if label not in action_labels:
                continue  # навыки — у них свой payload, проверяется отдельно
            dispatched = label in text_owners or (payload_type is not None and payload_type in payload_types)
            assert dispatched, f"{mode.mode_id}: кнопку {label!r} никто не обрабатывает"


def _payload_rule_types() -> set[str]:
    types: set[str] = set()
    for path in sorted(_HANDLERS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords or []:
                if keyword.arg != "payload_contains":
                    continue
                if isinstance(keyword.value, ast.Dict):
                    for key, value in zip(keyword.value.keys, keyword.value.values, strict=True):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == "type"
                            and isinstance(value, ast.Constant)
                        ):
                            types.add(value.value)
    return types
