"""Игрой управляют только кнопки и команды через «/» (2026-10-21, владелец).

Каждая текстовая кнопка бота несёт метку в payload (bot/keyboard_mark.py).
Сообщение в личке без payload и без «/» бот не читает: «Исследовать»,
набранное рукой, молча пропускается.

Набранный текст нужен игре в немногих местах - они перечислены в
_typed_input_expected. Новое место, где бот ждёт ввод словами, - добавить
туда, иначе фильтр его отрежет (тест tests/test_button_gate.py).
"""

from sqlalchemy import select
from vkbottle import BaseMiddleware
from vkbottle.bot import Message

from models import Character, PromoCode, User
from services.db import get_session_factory

async def _typed_input_expected(message: Message) -> bool:
    """Бот сам ждёт от игрока слова: ник при создании и координаты маунта
    (диспенсер состояний), код арены, ответ загадке Архива и сцены, ставку в
    костях и Котле, имя ишака, выбор стороны в PvP цифрой. Команды - только
    через «/» (2026-10-21, владелец)."""
    from bot.handlers import arena, group_events, pvp, raid_archive, scene_events, turbo_ishak

    peer = message.peer_id
    if message.state_peer is not None:
        return True
    if peer in turbo_ishak._naming or peer in pvp._pending_join_prompt:
        return True
    if group_events._pot_scene_of(peer) is not None:
        return True
    for rule in (arena.CodeInput(), raid_archive.ArchiveAnswer(), scene_events.RiddleAnswer(),
                 scene_events.StakeAnswer()):
        if await rule.check(message):
            return True
    return False


async def allowed(message: Message) -> bool:
    if message.payload is not None or message.peer_id != message.from_id or message.from_id <= 0:
        return True  # кнопка или беседа - как раньше
    if (message.text or "").lstrip().startswith("/"):
        return True
    if await _typed_input_expected(message):
        return True
    async with get_session_factory()() as db:
        created = await db.scalar(
            select(Character.id)
            .join(User, User.id == Character.user_id)
            .where(User.vk_id == message.from_id, Character.creation_state.is_(None))
        )
        if created is None:
            return True  # нет персонажа или он создаётся: онбординг читает текст
        code = (message.text or "").strip().lower()
        if code and await db.scalar(select(PromoCode.id).where(PromoCode.code == code)) is not None:
            return True
    return False


class ButtonGateMiddleware(BaseMiddleware[Message]):
    async def pre(self) -> None:
        from bot import action_log

        ok = await allowed(self.event)
        await action_log.record(self.event, ok)
        if not ok:
            self.stop("typed text ignored")


def setup_middleware(bot) -> None:
    bot.labeler.message_view.register_middleware(ButtonGateMiddleware)
