"""Хендлер активации промокода текстом (патч 50, bot/handlers/promo.py):
regex не должен перехватывать координаты маунта (X:Y), однозначные ответы
PvP-приглашения ("1"/"2") — коллизии этого типа уже случались в патчах 40/42.
Полный сценарий (регистронезависимость, приоритет в цепочке разбора) —
services/promo_service.py, тестируется в tests/test_promo_service.py; здесь —
только чистая логика хендлера, не завязанная на его собственную сессию БД
(см. докстринг bot/handlers/promo.py и тот же принцип в tests/test_pvp.py)."""

from dataclasses import dataclass

from bot.handlers.promo import _looks_like_code, _render
from services import promo_service


@dataclass
class FakeMessage:
    text: str | None


def test_looks_like_code_matches_typical_promo_code() -> None:
    assert _looks_like_code(FakeMessage("MONOLITH2026")) is True


def test_looks_like_code_matches_lowercase_and_cyrillic() -> None:
    assert _looks_like_code(FakeMessage("монолит_50")) is True


def test_looks_like_code_rejects_mount_coordinates() -> None:
    assert _looks_like_code(FakeMessage("12:34")) is False


def test_looks_like_code_rejects_pvp_join_digits() -> None:
    assert _looks_like_code(FakeMessage("1")) is False
    assert _looks_like_code(FakeMessage("2")) is False


def test_looks_like_code_rejects_empty_and_none() -> None:
    assert _looks_like_code(FakeMessage("")) is False
    assert _looks_like_code(FakeMessage(None)) is False


def test_looks_like_code_rejects_multiword_nickname_search() -> None:
    assert _looks_like_code(FakeMessage("Иван Петров")) is False


def test_looks_like_code_rejects_too_long() -> None:
    assert _looks_like_code(FakeMessage("x" * 33)) is False


def test_render_success_lists_rewards() -> None:
    outcome = promo_service.ActivationOutcome(status="success", lines=["500 золота", "💎 5 самоцветов"])
    text = _render(outcome)
    assert text.startswith("🎟 Код принят!")
    assert "500 золота" in text
    assert "💎 5 самоцветов" in text


def test_render_success_no_rewards() -> None:
    outcome = promo_service.ActivationOutcome(status="success", lines=[])
    assert _render(outcome) == "Код принят, но наград в нём не оказалось."


def test_render_already_used() -> None:
    outcome = promo_service.ActivationOutcome(status="already_used")
    assert _render(outcome) == "Ты уже воспользовался этим кодом."


def test_render_limit_reached() -> None:
    outcome = promo_service.ActivationOutcome(status="limit_reached")
    assert _render(outcome) == "Этот код больше не действует."


def test_render_expired() -> None:
    outcome = promo_service.ActivationOutcome(status="expired")
    assert _render(outcome) == "Этот код истёк."
