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


async def test_second_continue_while_riding_does_not_strand(monkeypatch) -> None:
    """2026-10-24: кнопка «Продолжить путь» под сообщением о нападении жива и
    после первого нажатия. Второе писало «Путь прерван - ты остаёшься на
    месте» и давало карту, хотя маунт ехал дальше."""
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from bot.handlers import mounts

    sent = []

    class _Api:
        class messages:  # noqa: N801
            @staticmethod
            async def send(**kw):
                sent.append(kw["message"])
                return 1

    @asynccontextmanager
    async def _db():
        yield None

    async def _char(db, peer):
        return SimpleNamespace(id=1, pos_x=4, pos_y=-6)

    async def _travel(db, cid):
        return SimpleNamespace(id=7, status="traveling")

    monkeypatch.setattr(mounts, "_bot_api", _Api)
    monkeypatch.setattr(mounts, "get_session_factory", lambda: _db)
    monkeypatch.setattr(mounts.onboarding_svc, "get_character", _char)
    monkeypatch.setattr(mounts.mount_service, "active_travel", _travel)
    await mounts._recover_stranded(123)
    assert sent == ["🐎 Ты и так в пути."]
