"""Клавиатура карты (патч 25, п.1/п.4/п.7): крест перемещения + условные
кнопки Горстка пепла/Маунт."""

import json

from bot import ash_handful_state
from bot.keyboards.world import (
    BTN_ASH_HANDFUL, BTN_CHARACTER, BTN_EXPLORE, BTN_MOUNT, ash_handful_keyboard, movement_keyboard,
)


def _labels(kb_json: str) -> list[str]:
    rows = json.loads(kb_json)["buttons"]
    return [btn["action"]["label"] for row in rows for btn in row]


def test_explore_always_present() -> None:
    labels = _labels(movement_keyboard(0, 0))
    assert BTN_EXPLORE in labels


def test_ash_button_hidden_by_default() -> None:
    peer_id = 424242
    ash_handful_state.clear(peer_id)
    labels = _labels(movement_keyboard(0, 0, peer_id))
    assert BTN_ASH_HANDFUL not in labels


def test_ash_button_lives_in_chat_not_in_movement_keyboard() -> None:
    """2026-10-13: горстка пепла - инлайн-кнопкой под отдельным сообщением,
    нижняя клавиатура карты её больше не несёт."""
    peer_id = 424243
    ash_handful_state.mark(peer_id)
    try:
        assert BTN_ASH_HANDFUL not in _labels(movement_keyboard(0, 0, peer_id))
        inline = json.loads(ash_handful_keyboard())
        assert inline["inline"] is True
        assert _labels(ash_handful_keyboard()) == [BTN_ASH_HANDFUL]
    finally:
        ash_handful_state.clear(peer_id)


def test_non_combat_keyboards_carry_miniapp_button(monkeypatch) -> None:
    """2026-10-13: кнопка персонажа (мини-апп) - на всех нижних клавиатурах
    вне боя: рыбалка, рудник, Хранитель списков, рейды, лавки."""
    from config import get_settings
    from bot.keyboards import fishing, list_keeper, mining, raid

    monkeypatch.setattr(get_settings(), "vk_miniapp_url", "https://vk.com/app1")
    for kb_json in (
        fishing.lake_keyboard(), fishing.casting_keyboard(), fishing.bite_keyboard(), fishing.bag_keyboard(),
        mining.mine_keyboard(True), mining.digging_keyboard(), mining.ore_keyboard(),
        list_keeper.offer_keyboard(), list_keeper.trials_keyboard(), raid.raid_list_keyboard(),
    ):
        assert BTN_CHARACTER in _labels(kb_json)


def test_mount_button_only_when_has_mount() -> None:
    assert BTN_MOUNT not in _labels(movement_keyboard(0, 0))
    assert BTN_MOUNT in _labels(movement_keyboard(0, 0, has_mount=True))
