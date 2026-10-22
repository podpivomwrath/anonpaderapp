"""Кнопки рыбалки и рудника - постоянные (2026-10-23): одноразовые VK прятал
после любой набранной команды (/руда1, /разломы), и игрок оставался без кнопок."""

import json

from bot.keyboards import fishing, mining


def test_fishing_and_mining_keyboards_are_not_one_time() -> None:
    boards = [fishing.catch_keyboard(), fishing.lake_keyboard(), fishing.casting_keyboard(),
              fishing.bite_keyboard(), fishing.bag_keyboard(),
              mining.mine_keyboard(True), mining.digging_keyboard(), mining.ore_keyboard()]
    for raw in boards:
        assert json.loads(raw)["one_time"] is False
