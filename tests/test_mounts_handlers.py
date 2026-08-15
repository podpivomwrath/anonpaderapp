"""Патч 40, баг 2: состояние ожидания координат маунта не должно перехватывать
нажатия кнопок (payload) — регресс на конкретный баг («Продолжить путь»
после победы над засадой читалось как «Не понял координаты»).

Патч 42: то же правило (bot.dispatch_rules.TEXT_ONLY) переиспользуется
bot/handlers/mounts.py и bot/handlers/pvp.py — единый объект, тесты общие."""

from dataclasses import dataclass

from bot.dispatch_rules import TEXT_ONLY


@dataclass
class _FakeMessage:
    payload: str | None = None
    text: str | None = None


async def test_text_only_rule_matches_plain_text() -> None:
    assert await TEXT_ONLY.check(_FakeMessage(payload=None, text="12:-30")) is True


async def test_text_only_rule_rejects_button_payload() -> None:
    msg = _FakeMessage(payload='{"type": "continue_travel", "travel": 1}', text="Продолжить путь")
    assert await TEXT_ONLY.check(msg) is False


async def test_text_only_rule_rejects_digit_label_button_payload() -> None:
    """Патч 42, баг-репорт #17: кнопка «1» в подробном режиме скупщика несёт
    payload {"type": "sell_item", ...} — тот же текст, что и выбор стороны в
    PvP по цифре (bot/handlers/pvp.py::join_via_text). TEXT_ONLY обязана
    отклонить её, иначе join_via_text глушит нажатие скупщика."""
    msg = _FakeMessage(payload='{"type": "sell_item", "item": 5, "page": 1}', text="1")
    assert await TEXT_ONLY.check(msg) is False
