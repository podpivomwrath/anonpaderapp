"""Активация промокодов (патч 50) — игрок вводит код ПРОСТЫМ ТЕКСТОМ в чат,
без команды/префикса, в любом состоянии (город/карта/бой/в пути).

Приоритет в общей цепочке разбора ввода (правило патчей 40/42, см.
bot/dispatch_rules.py): этот labeler зарегистрирован ПОЗЖЕ всех
FSM-состояний и command-хендлеров (bot/handlers/__init__.py::LABELERS,
непосредственно перед fallback) — координаты маунта/никнейм/поиск в админке
уже гарантированно забрали своё раньше, если игрок реально в соответствующем
состоянии (см. докстринг TEXT_ONLY). Совпадения с несуществующим кодом —
молча пропускаются дальше (никакого "код не найден"), см. промо_service.activate_code.
"""

import re

from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules.base import FuncRule

from bot.dispatch_rules import TEXT_ONLY
from services import onboarding_service as onboarding_svc
from services import promo_service
from services.db import get_session_factory

labeler = BotLabeler()

# Длина/алфавит — как у промокодов вида MONOLITH2026: буквы (оба алфавита),
# цифры, дефис/подчёркивание. Явно БЕЗ ":" (координаты маунта X:Y) и без
# пробелов (перехватывались бы только полные однословные сообщения).
_CODE_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_-]{3,32}$")


def _looks_like_code(message: Message) -> bool:
    text = (message.text or "").strip()
    return bool(_CODE_RE.match(text))


def _render(outcome: promo_service.ActivationOutcome) -> str:
    if outcome.status != "success":
        return promo_service.STATUS_TEXTS[outcome.status]
    if not outcome.lines:
        return "Код принят, но наград в нём не оказалось."
    return "🎟 Код принят! Получено:\n" + "\n".join(outcome.lines)


@labeler.message(TEXT_ONLY, FuncRule(_looks_like_code))
async def try_activate_promo(message: Message) -> None:
    text = (message.text or "").strip()
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        outcome = await promo_service.activate_code(db, character, text)
        if outcome is None:
            return  # не совпало ни с одним кодом — не наше сообщение, оставляем как есть
        await db.commit()
    await message.answer(_render(outcome))
