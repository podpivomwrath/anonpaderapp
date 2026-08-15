"""Патч 40, баг 2: состояние ожидания координат маунта не должно перехватывать
нажатия кнопок (payload) — регресс на конкретный баг («Продолжить путь»
после победы над засадой читалось как «Не понял координаты»)."""

from dataclasses import dataclass

from bot.handlers.mounts import _TEXT_ONLY


@dataclass
class _FakeMessage:
    payload: str | None = None
    text: str | None = None


async def test_text_only_rule_matches_plain_text() -> None:
    assert await _TEXT_ONLY.check(_FakeMessage(payload=None, text="12:-30")) is True


async def test_text_only_rule_rejects_button_payload() -> None:
    msg = _FakeMessage(payload='{"type": "continue_travel", "travel": 1}', text="Продолжить путь")
    assert await _TEXT_ONLY.check(msg) is False
