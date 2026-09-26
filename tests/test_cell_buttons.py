"""Кнопки клетки приходят на ВСЕХ путях входа (патч 104).

Игрок вышел за ворота прямо на клетку мирового босса и не получил кнопку:
её звал только пеший переход, а выход за ворота - нет. До этого так же
потерялась кнопка рудника у прибытия на маунте. Теперь кнопки озера,
рудника и босса зовутся только из world.send_cell_buttons, а все пути
входа зовут её.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUTTONS = ("maybe_send_lake_button", "maybe_send_mine_button", "maybe_send_here_button")


def _calls(text: str, name: str) -> int:
    return len(re.findall(rf"await [\w.]*\b{name}\(", text))


def test_buttons_are_sent_only_through_the_one_helper() -> None:
    world_path = ROOT / "bot/handlers/world.py"
    world = world_path.read_text(encoding="utf-8")
    helper = world.split("async def send_cell_buttons", 1)[1].split("\nasync def ", 1)[0]
    for path in (ROOT / "bot").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name in BUTTONS:
            outside = _calls(text, name) - (_calls(helper, name) if path == world_path else 0)
            assert outside == 0, f"{path.name}: {name} в обход send_cell_buttons"


def test_every_way_onto_a_cell_sends_the_buttons() -> None:
    world = (ROOT / "bot/handlers/world.py").read_text(encoding="utf-8")
    for handler in ("async def show_location", "async def gate_exit_direction", "async def handle_arrival"):
        body = world.split(handler, 1)[1].split("\n@labeler", 1)[0].split("\nasync def ", 1)[0]
        assert "send_cell_buttons(" in body, handler
    mounts = (ROOT / "bot/handlers/mounts.py").read_text(encoding="utf-8")
    assert "send_cell_buttons(" in mounts, "прибытие на маунте"
