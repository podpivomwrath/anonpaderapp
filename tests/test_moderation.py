"""Патч 27: bot/handlers/moderation.py — только чистые части (ban_message,
_format_report). BanCheckMiddleware, _build_snapshot (завязан на живой
combat_handlers._engine, инициализируемый только в main.create_bot) и
_handle_bug_report открывают/трогают состояние, которое в этом проекте не
юнит-тестируется напрямую (см. докстринг tests/test_pvp.py)."""

from datetime import datetime, timezone

from bot.handlers.moderation import _format_report, ban_message
from models import Character


def _character(**overrides) -> Character:
    character = Character(user_id=1, name="Валгар", base_class="warrior", level=23)
    for key, value in overrides.items():
        setattr(character, key, value)
    return character


def test_ban_message_permanent_no_reason() -> None:
    text = ban_message(_character(is_banned=True))
    assert "🚫" in text
    assert "Срок: бессрочно" in text
    assert "Причина:" not in text


def test_ban_message_with_reason_and_expiry() -> None:
    until = datetime(2026, 8, 12, 14, 32, tzinfo=timezone.utc)
    text = ban_message(_character(is_banned=True, ban_reason="спам", banned_until=until))
    assert "Причина: спам" in text
    assert "12.08.2026 14:32" in text


def test_format_report_includes_quest_line_when_present() -> None:
    snapshot = {
        "name": "Валгар", "level": 23, "class_title": "Кровавый рыцарь", "region": "Кряж",
        "pos_x": 34, "pos_y": 38, "state": "в бою", "quest": "Пропавший патруль", "hp_percent": 41,
    }
    text = _format_report(47, 123456789, snapshot, "после боя пропали кнопки", datetime(2026, 8, 12, 14, 32))
    assert "🐞 РЕПОРТ #47" in text
    assert "Валгар (vk_id 123456789)" in text
    assert "Квест: Пропавший патруль" in text
    assert "HP: 41%" in text
    assert "после боя пропали кнопки" in text


def test_format_report_omits_quest_line_when_absent() -> None:
    snapshot = {
        "name": "Валгар", "level": 1, "class_title": "Воин", "region": "—",
        "pos_x": 0, "pos_y": 0, "state": "в городе/на карте", "quest": None, "hp_percent": 100,
    }
    text = _format_report(1, 1, snapshot, "тест", datetime(2026, 8, 12, 14, 32))
    assert "Квест:" not in text
