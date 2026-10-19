"""Выбор маунта перед поездкой (2026-10-19): кнопки остальных, если маунтов
больше одного; клавиатура в пределах лимитов inline VK."""

import json
from types import SimpleNamespace

from bot.handlers import mounts as mounts_handlers

STEED = SimpleNamespace(mount_id="ashen_steed", name="Пепельный скакун", emoji="🔵")
TURBO = SimpleNamespace(mount_id="turbo_ishak", name="Турбоишак Машина смерти", emoji="🟣")
HERALD = SimpleNamespace(mount_id="admin_ashen_herald", name="Пепельный вестник", emoji="🛠")


def _labels(raw: str) -> list[list[str]]:
    return [[b["action"]["label"] for b in row] for row in json.loads(raw)["buttons"]]


def test_one_mount_has_no_choice() -> None:
    rows = _labels(mounts_handlers._route_keyboard(False, [], [STEED], STEED))
    assert rows == [["🛡 Сделать безопасным"]]


def test_other_mounts_are_offered_and_fit_vk() -> None:
    targets = [("📜 Квест", 3, 4), ("🐾 К следу", -2, 7)]
    rows = _labels(mounts_handlers._route_keyboard(True, targets, [STEED, TURBO, HERALD], HERALD))
    flat = [b for row in rows for b in row]
    assert "🔵 Пепельный скакун" in flat and "🟣 Турбоишак Машина смерти" in flat
    assert "🛠 Пепельный вестник" not in flat  # текущий не предлагается
    assert len(rows) <= 6 and len(flat) <= 10


def test_remembered_mount_is_chosen() -> None:
    assert mounts_handlers._chosen([STEED, TURBO], "turbo_ishak") is TURBO
    assert mounts_handlers._chosen([STEED, TURBO], "gone") is STEED
