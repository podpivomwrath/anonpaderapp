"""Порядок регистрации обработчиков (2026-10-21).

Бот отдаёт сообщение первому подходящему обработчику, поэтому порядок -
это поведение: поход перехватывает всё раньше мира, рыбалка стоит раньше
промокодов и т.п. При нарезке больших файлов порядок легко сдвинуть, и
кнопка молча уйдёт не тому. Меняешь порядок - меняй снимок осознанно.
"""

import importlib
import pkgutil

import bot.handlers as handlers

EXPECTED = [
    "terms", "onboarding", "combat_log", "voyage", "rift", "raid_archive", "raid_procession", "raid_trail", "scene_events",
    "group_events", "turbo_ishak", "world", "explore", "rest", "stuck", "combat", "group_combat", "pvp", "arena", "house", "herbs",
    "appraiser", "market", "inventory", "list_keeper", "presets", "elixir_shop", "dailies", "mounts", "stats_window",
    "moderation", "basic", "raid", "raid_combat", "fishing", "mining", "world_boss", "guild", "group", "contracts",
    "transfer", "promo", "fallback",
]


def test_labelers_registered_in_expected_order() -> None:
    by_id = {}
    for info in pkgutil.iter_modules(handlers.__path__):
        module = importlib.import_module(f"bot.handlers.{info.name}")
        labeler = getattr(module, "labeler", None)
        if labeler is not None:
            by_id[id(labeler)] = info.name
    assert [by_id.get(id(lab), "?") for lab in handlers.LABELERS] == EXPECTED
