"""Окно распределения статов в чате (патч 11, блок 1).

Дублирует функционал мини-аппа — оба пути пишут в CharacterStats.unspent_points
(гонка разрешается в stat_alloc_service.finalize при нажатии "Готово").

Открывается автоматически при левелапе (см. bot.handlers.combat) или вручную
кнопкой [📊 Характеристики]. Редактируется НА МЕСТЕ (inline-клавиатура на
конкретном сообщении) — несколько левелапов подряд обновляют одно и то же
окно, а не плодят новые.
"""

from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message

from bot.keyboards.stats_window import no_keyboard, stats_alloc_keyboard
from bot.keyboards.world import BTN_STATS
from models import CharacterStats
from services import onboarding_service as onboarding_svc
from services import stat_alloc_service as sas
from services.db import get_session_factory

labeler = BotLabeler()

_bot_api = None

# peer_id -> {stat: вложено в этой сессии}, НЕ пишется в БД до "Готово"
_pending: dict[int, dict[str, int]] = {}
# peer_id -> conversation_message_id открытого окна (для edit на месте)
_window_message: dict[int, int] = {}
# peer_id -> заголовок текущего окна (сохраняется между правками одного окна)
_window_header: dict[int, str] = {}


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def _get_stats(db, character_id: int) -> CharacterStats:
    return await db.scalar(
        select(CharacterStats).where(CharacterStats.character_id == character_id)
    )


def _clear(peer_id: int) -> None:
    _pending.pop(peer_id, None)
    _window_message.pop(peer_id, None)
    _window_header.pop(peer_id, None)


async def _send_or_edit(peer_id: int, text: str, keyboard: str | None) -> None:
    """Правит уже открытое окно на месте; если сообщение недоступно для правки
    (истекло/удалено) — открывает новое взамен. Граница с внешним API —
    сознательно широкий except (see также respawn.py)."""
    existing = _window_message.get(peer_id)
    if existing is not None:
        try:
            await _bot_api.messages.edit(
                peer_id=peer_id, conversation_message_id=existing, message=text,
                keyboard=keyboard,
            )
            return
        except Exception:
            _window_message.pop(peer_id, None)
    resp = await _bot_api.messages.send(peer_id=peer_id, message=text, random_id=0, keyboard=keyboard)
    try:
        _window_message[peer_id] = int(resp)
    except (TypeError, ValueError):
        pass


async def open_or_update_window(peer_id: int, header: str) -> None:
    """Открывает окно распределения; если для игрока уже открыто — редактирует
    его (несколько левелапов подряд не плодят новых окон, патч 11)."""
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        stats = await _get_stats(db, character.id)
        unspent = stats.unspent_points
        char_stats = sas.snapshot(stats)

    _window_header[peer_id] = header

    if unspent <= 0:
        _clear(peer_id)
        await _bot_api.messages.send(
            peer_id=peer_id, message=sas.render_readonly(header, char_stats), random_id=0
        )
        return

    pending = _pending.setdefault(peer_id, {})
    text = sas.render_window(header, unspent, char_stats, pending)
    await _send_or_edit(peer_id, text, stats_alloc_keyboard())


@labeler.message(text=[BTN_STATS])
async def open_stats_button(message: Message) -> None:
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
    await open_or_update_window(message.peer_id, header="📊 Характеристики")


@labeler.message(payload_contains={"type": "stat_alloc"})
async def stat_alloc(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    stat_key = payload.get("stat")
    if stat_key not in sas.STAT_ORDER:
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        stats = await _get_stats(db, character.id)
        unspent = stats.unspent_points
        char_stats = sas.snapshot(stats)

    pending = _pending.setdefault(peer_id, {})
    if sum(pending.values()) >= unspent:
        await message.answer("Очков не осталось.")
        return
    pending[stat_key] = pending.get(stat_key, 0) + 1

    header = _window_header.get(peer_id, "📊 Характеристики")
    text = sas.render_window(header, unspent, char_stats, pending)
    await _send_or_edit(peer_id, text, stats_alloc_keyboard())


@labeler.message(payload_contains={"type": "stat_alloc_cancel"})
async def stat_alloc_cancel(message: Message) -> None:
    peer_id = message.peer_id
    if peer_id not in _window_message and peer_id not in _pending:
        return
    _pending[peer_id] = {}

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        stats = await _get_stats(db, character.id)
        unspent = stats.unspent_points
        char_stats = sas.snapshot(stats)

    header = _window_header.get(peer_id, "📊 Характеристики")
    if unspent <= 0:
        _clear(peer_id)
        await _send_or_edit(peer_id, sas.render_readonly(header, char_stats), no_keyboard())
        return
    text = sas.render_window(header, unspent, char_stats, {})
    await _send_or_edit(peer_id, text, stats_alloc_keyboard())


@labeler.message(payload_contains={"type": "stat_alloc_done"})
async def stat_alloc_done(message: Message) -> None:
    peer_id = message.peer_id
    pending = _pending.get(peer_id)
    header = _window_header.get(peer_id, "📊 Характеристики")

    if not pending:
        async with get_session_factory()() as db:
            character = await onboarding_svc.get_character(db, peer_id)
            if character is None:
                return
            stats = await _get_stats(db, character.id)
            char_stats = sas.snapshot(stats)
        _clear(peer_id)
        await _send_or_edit(peer_id, sas.render_readonly(header, char_stats), no_keyboard())
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        stats = await _get_stats(db, character.id)
        result = await sas.finalize(db, stats, pending)
        await db.commit()

    _clear(peer_id)
    note = None
    if result.applied_total < result.requested_total:
        note = f"Часть очков уже была вложена в другом месте. Закреплено: {result.applied_total}."
    await _send_or_edit(peer_id, sas.render_final(result.char_stats, note), no_keyboard())
