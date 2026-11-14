"""Клавиатура вне лимитов VK чинится при отправке (2026-11-14): VK отбивал
сообщение целиком, и игрок не получал ничего."""

import json

from vkbottle import Keyboard, KeyboardButtonColor, OpenLink, Text

from bot import keyboard_guard


def _rows(kb) -> list[list[str]]:
    data = json.loads(kb)
    return [[b["action"].get("label", b["action"]["type"]) for b in row] for row in data["buttons"]]


def _kb(rows: int, inline: bool = False, per_row: int = 1) -> str:
    kb = Keyboard(inline=inline)
    for r in range(rows):
        if r:
            kb.row()
        for c in range(per_row):
            kb.add(Text(f"к{r}.{c}"), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()


def test_good_keyboard_is_untouched() -> None:
    kb = _kb(5)
    assert keyboard_guard.checked(kb) is kb
    assert keyboard_guard.checked(None) is None


def test_too_many_rows_are_merged_and_nothing_lost() -> None:
    kb = _kb(12)
    fixed = keyboard_guard.checked(kb)
    rows = _rows(fixed)
    assert len(rows) <= keyboard_guard.MAX_ROWS
    assert sum(len(r) for r in rows) == 12


def test_inline_limit_is_six_rows() -> None:
    fixed = keyboard_guard.checked(_kb(8, inline=True))
    assert len(_rows(fixed)) <= keyboard_guard.MAX_ROWS_INLINE


def test_link_row_of_three_is_split() -> None:
    """05.11: кнопка-ссылка в ряду из трёх - VK отклонял каждое сообщение руин."""
    kb = Keyboard(one_time=False)
    kb.add(Text("Мешок"), color=KeyboardButtonColor.SECONDARY)
    kb.add(Text("Группа"), color=KeyboardButtonColor.SECONDARY)
    kb.add(OpenLink("https://vk.com/app1", "Персонаж"))
    rows = _rows(keyboard_guard.checked(kb.get_json()))
    assert all(len(r) <= 2 for r in rows)
    assert sum(len(r) for r in rows) == 3


def test_wide_rows_that_cannot_merge_are_trimmed_keeping_the_last() -> None:
    kb = Keyboard(one_time=False)
    for i in range(12):
        if i:
            kb.row()
        kb.add(OpenLink(f"https://vk.com/app{i}", f"ссылка {i}"))
    rows = _rows(keyboard_guard.checked(kb.get_json()))
    assert len(rows) == keyboard_guard.MAX_ROWS
    assert rows[-1] == ["ссылка 11"]


async def test_send_wrapper_fixes_keyboard_before_vk() -> None:
    from bot import silent_guard

    sent = []

    class Api:
        async def request(self, method, data, version=None):
            sent.append(data)
            return 1

    api = Api()
    silent_guard.install(api)
    await api.request("messages.send", {"peer_id": 5, "message": "x", "keyboard": _kb(11)})
    assert len(_rows(sent[0]["keyboard"])) <= keyboard_guard.MAX_ROWS
