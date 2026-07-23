"""Клавиатура скупщика трофеев: продать всё / поштучно по градациям (патч 9)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from game.content_loader import TrophyDef

SELL_ALL_ID = "all"


def appraiser_keyboard(stock: list[tuple[TrophyDef, int]]) -> str:
    kb = Keyboard(one_time=False)
    if not stock:
        return kb.get_json()
    total = sum(d.sell_price * count for d, count in stock)
    kb.add(
        Text(f"Продать всё — {total} зол.", payload={"type": "sell_trophies", "id": SELL_ALL_ID}),
        color=KeyboardButtonColor.POSITIVE,
    )
    kb.row()
    for trophy_def, count in stock:
        price = trophy_def.sell_price * count
        label = f"Продать {trophy_def.emoji} ×{count} — {price} зол."
        kb.add(
            Text(label, payload={"type": "sell_trophies", "id": trophy_def.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        kb.row()
    return kb.get_json()
