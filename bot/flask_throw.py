"""Метательные склянки в бою (2026-10-23): выпить зелье самому или метнуть
на всю группу слабее. Общее для группового боя и рейда - обработчики зелий
зовут ask() до траты зелья и spend() после.

Спрашиваем только когда есть смысл: склянки есть, рядом живые союзники,
и это не свиток (свиток и так на всех). Часть зелий метать нельзя
(craft_gear_config.FLASK_FORBIDDEN) - их только пьют сами.
"""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from bot import editable_message
from game.economy import craft_gear_config as gc
from services import craft_gear_service
from services.db import get_session_factory

BTN_SELF = "🍶 Выпить самому"
ASK_TEXT = "{emoji} {name}: выпить самому или метнуть склянкой на всю группу (слабее)?"


def _keyboard(use_type: str, elixir_id: str, flasks: int) -> str:
    kb = Keyboard(inline=True)
    kb.add(Text(BTN_SELF, payload={"type": use_type, "id": elixir_id, "mode": "self"}),
           color=KeyboardButtonColor.SECONDARY)
    kb.add(Text(f"🧴 На группу (склянок {flasks})", payload={"type": use_type, "id": elixir_id, "mode": "throw"}),
           color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


def can_throw(elixir) -> bool:
    return elixir.category != "scroll" and elixir.id not in gc.FLASK_FORBIDDEN


async def ask(api, key: str, peer_id: int, character_id: int, use_type: str, elixir, mode, allies: int) -> bool:
    """True - спросили (обработчик выходит и ждёт выбора)."""
    if mode is not None or allies <= 0 or not can_throw(elixir):
        return False
    async with get_session_factory()() as db:
        row = (await craft_gear_service.gear(db, character_id)).get("flasks")
    flasks = row.count if row is not None else 0
    if flasks <= 0:
        return False
    await editable_message.send_or_edit(
        api, key, peer_id, ASK_TEXT.format(emoji=elixir.emoji, name=elixir.name),
        _keyboard(use_type, elixir.id, flasks),
    )
    return True


async def spend(character_id: int) -> bool:
    """Потратить склянку. False - кончились (тогда пьёт сам)."""
    async with get_session_factory()() as db:
        ok = bool(await craft_gear_service.use_charge(db, character_id, "flasks"))
        await db.commit()
    return ok
