"""Выбор маунта перед поездкой (2026-10-19): кнопка «Выбор маунта» под
переключателем пути, если маунтов больше одного; список - в пределах
лимитов inline VK, выбранный отмечен."""

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


def test_choose_button_goes_under_the_route_toggle() -> None:
    targets = [("📜 Квест", 3, 4), ("🐾 К следу", -2, 7)]
    rows = _labels(mounts_handlers._route_keyboard(True, targets, [STEED, TURBO, HERALD], HERALD))
    assert rows[-2] == ["➡️ Сделать прямым"]
    assert rows[-1] == [mounts_handlers.BTN_CHOOSE_MOUNT]


def test_mount_list_marks_current_and_fits_vk() -> None:
    owned = [STEED, TURBO, HERALD]
    rows = _labels(mounts_handlers._mounts_keyboard(owned, TURBO))
    assert rows == [["🔵 Пепельный скакун"], ["✅ 🟣 Турбоишак Машина смерти"], ["🛠 Пепельный вестник"]]
    many = [SimpleNamespace(mount_id=f"m{i}", name=f"Конь {i}", emoji="⚪") for i in range(9)]
    assert len(_labels(mounts_handlers._mounts_keyboard(many, None))) <= 6


def test_remembered_mount_is_chosen() -> None:
    assert mounts_handlers._chosen([STEED, TURBO], "turbo_ishak") is TURBO
    assert mounts_handlers._chosen([STEED, TURBO], "gone") is STEED
