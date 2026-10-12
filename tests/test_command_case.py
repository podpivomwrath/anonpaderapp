"""Текстовые команды бота не зависят от регистра (2026-10-12): «Пригласить
Ник», «ПРИГЛАСИТЬ ник» и «пригласить Ник» - одна команда. Ник при этом
доходит как написан: искать его - дело сервиса (там поиск без регистра)."""

import importlib
import pkgutil

import bot.handlers as handlers


def _labelers():
    for module in pkgutil.iter_modules(handlers.__path__):
        mod = importlib.import_module(f"bot.handlers.{module.name}")
        labeler = getattr(mod, "labeler", None)
        if labeler is not None:
            yield module.name, labeler


def test_every_handler_labeler_ignores_case() -> None:
    missing = [name for name, labeler in _labelers() if not labeler.vbml_ignore_case]
    assert not missing, f"команды с учётом регистра: {missing}"


async def test_invite_matches_any_case_and_keeps_the_name() -> None:
    from bot.handlers import group

    rule = next(
        r for handler in group.labeler.message_view.handlers for r in handler.rules
        if type(r).__name__ == "VBMLRule"
        and any("<name>" in p.text for p in r.patterns if hasattr(p, "text"))
    )

    class Msg:
        text = "ПРИГЛАСИТЬ ПупсиК"

    assert await rule.check(Msg()) == {"name": "ПупсиК"}
