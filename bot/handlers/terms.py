"""Пользовательское соглашение в чате (2026-10-15, решение владельца).

Пока игрок не принял актуальную редакцию (services/terms_service.py), на
любое сообщение он видит одно окно: текст, приложенные документы и
единственную кнопку «✅ Принимаю» - остальные кнопки убраны, дальше не пускает.
Новичок видит его до создания персонажа, старый игрок - когда закончит
текущее дело: бой, поход, отдых, событие не прерываем, окно появится на
первом же действии после выхода на сводку локации.
"""

from datetime import datetime, timezone
from pathlib import Path

from loguru import logger
from vkbottle import BaseMiddleware, DocMessagesUploader, Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from services import terms_service
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # как у всех модулей команд

ACCEPT_PAYLOAD = {"type": "terms_accept"}
PDF_DIR = Path(__file__).resolve().parents[2] / "content" / "legal_pdf"
_api = None
#: Загруженные для диалога документы: peer -> строка вложений. VK отдаёт
#: документ для конкретного диалога, поэтому грузим на каждого игрока раз.
_attachments: dict[int, str] = {}


def accept_keyboard() -> str:
    kb = Keyboard(one_time=False)
    kb.add(Text("✅ Принимаю", payload=ACCEPT_PAYLOAD), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


async def _docs_for(peer_id: int) -> str | None:
    if peer_id in _attachments:
        return _attachments[peer_id]
    if _api is None:
        return None
    uploader = DocMessagesUploader(_api)
    parts = []
    for doc_id, title, _url in terms_service.DOCS:
        path = PDF_DIR / f"{doc_id}.pdf"
        if not path.exists():
            continue
        try:
            parts.append(await uploader.upload(str(path), peer_id=peer_id, title=f"{title}.pdf"))
        except Exception:  # noqa: BLE001 - без файлов окно всё равно работает: ссылки в тексте
            logger.warning("Соглашение: не загрузился {} для {}", doc_id, peer_id)
    joined = ",".join(parts)
    # Неполный набор не запоминаем - в следующий показ окна догрузим.
    if len(parts) == len(terms_service.DOCS):
        _attachments[peer_id] = joined
    return joined or None


async def send_gate(peer_id: int) -> None:
    await _api.messages.send(
        peer_id=peer_id, random_id=0, message=terms_service.TEXT,
        attachment=await _docs_for(peer_id), keyboard=accept_keyboard(),
    )


async def _busy(db, peer_id: int) -> bool:
    """Игрок посреди дела - окно подождёт до выхода на сводку локации."""
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import pvp as pvp_handlers
    from bot.handlers import scene_events as scene_handlers
    from bot.handlers import world as world_handlers
    from services import fishing_service, mining_service, mount_service, movement_service
    from services.onboarding_service import get_character

    if in_any_battle(peer_id) or world_handlers.is_busy(peer_id) or scene_handlers.has_pending(peer_id):
        return True
    if peer_id in pvp_handlers._pending_join_prompt or await world_handlers._pending_event_id(peer_id):
        return True
    character = await get_character(db, peer_id)
    if character is None or character.creation_state is not None:
        return False
    if movement_service.is_traveling(character, datetime.now(timezone.utc)):
        return True
    if mining_service.is_digging(character) or fishing_service.is_casting(character):
        return True
    return await mount_service.active_travel(db, character.id) is not None


class TermsGateMiddleware(BaseMiddleware[Message]):
    async def pre(self) -> None:
        event = self.event
        if event.from_id <= 0 or event.peer_id != event.from_id:
            return
        if (event.get_payload_json() or {}).get("type") == ACCEPT_PAYLOAD["type"]:
            return
        async with get_session_factory()() as db:
            if terms_service.accepted(await terms_service.user_of(db, event.from_id)):
                return
            if await _busy(db, event.peer_id):
                return
        await send_gate(event.peer_id)
        self.stop("terms")


@labeler.message(payload=ACCEPT_PAYLOAD)
async def accept_terms(message: Message) -> None:
    from bot.handlers import onboarding
    from bot.handlers import world as world_handlers
    from services.onboarding_service import get_character

    async with get_session_factory()() as db:
        already = terms_service.accepted(await terms_service.user_of(db, message.from_id))
        await terms_service.accept(db, message.from_id)
        await db.commit()
        character = await get_character(db, message.from_id)
        if character is not None and character.creation_state is None:
            if not already:
                await message.answer("✅ Спасибо! Соглашение принято, можно продолжать.")
            await world_handlers.show_location(message, db, character)
            await db.commit()
            return
    # Новичок или посреди создания персонажа - дальше обычный старт.
    await message.answer("✅ Спасибо! Соглашение принято.")
    await onboarding.handle_start(message)


def setup(bot) -> None:
    global _api
    _api = bot.api
    bot.labeler.message_view.register_middleware(TermsGateMiddleware)
