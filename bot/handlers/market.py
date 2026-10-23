"""/рынок в чате (2026-10-23): свои заявки и что ждёт в ящике купленного.

Торгуют в мини-аппе (раздел «Рынок»); в чате - только справка, кнопок не
трогает, как остальные справочные команды (bot/info_reply.py).
"""

from vkbottle.bot import BotLabeler, Message

from bot import info_reply
from services import market_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True

EMPTY_TEXT = "🏪 На рынке у тебя ничего нет. Торговать - в мини-аппе, раздел «Рынок»."


@labeler.message(text=["/рынок", "/market"])
async def market_command(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        orders = await market_service.my_orders(db, character.id)
        inbox = await market_service.inbox(db, character.id)
        lines = []
        for o in orders:
            side = "продаю" if o.side == market_service.SELL else "куплю"
            name = await market_service.label(db, o.good)
            lines.append(f"· {side} {name} ×{o.qty_left} по {market_service.money(o.price)}")
        box = [f"· {await market_service.label(db, r.good)} ×{r.qty}" for r in inbox]
        await db.commit()
    if not lines and not box:
        await info_reply.answer(message, EMPTY_TEXT)
        return
    text = "🏪 Рынок"
    if lines:
        text += "\n\nМои заявки:\n" + "\n".join(lines)
    if box:
        text += "\n\nКуплено, ждёт в ящике (забрать - в любом городе, в мини-аппе):\n" + "\n".join(box)
    await info_reply.answer(message, text)
