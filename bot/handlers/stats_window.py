"""Окно распределения статов в чате (патч 11, блок 1).

Дублирует функционал мини-аппа — оба пути пишут в CharacterStats.unspent_points
(гонка разрешается в stat_alloc_service.finalize при нажатии "Готово").

Открывается автоматически при левелапе (см. bot.handlers.combat) или вручную
кнопкой [📊 Характеристики]. Редактируется НА МЕСТЕ (inline-клавиатура на
конкретном сообщении) — несколько левелапов подряд обновляют одно и то же
окно, а не плодят новые.
"""

import asyncio

from loguru import logger
from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message

from bot import editable_message
from bot.keyboards.stats_window import levelup_keyboard, no_keyboard, stats_alloc_keyboard
from bot.keyboards.world import BTN_STATS
from models import Character, CharacterStats, User
from services import daily_service
from services import onboarding_service as onboarding_svc
from services import stat_alloc_service as sas
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра: «Пригласить» = «пригласить»

_NS = "stats_window"

_bot_api = None

# peer_id -> {stat: вложено в этой сессии}, НЕ пишется в БД до "Готово"
_pending: dict[int, dict[str, int]] = {}
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
    _window_header.pop(peer_id, None)
    editable_message.clear(_NS, peer_id)


async def _send_or_edit(peer_id: int, text: str, keyboard: str | None) -> None:
    await editable_message.send_or_edit(_bot_api, _NS, peer_id, text, keyboard)


#: Через столько окно нового уровня открывается после начисления опыта.
LEVELUP_DELAY_SECONDS = 1.5


async def notify_levelup(peer_id: int, levels_gained: int, new_level: int) -> None:
    """Единая точка входа для ЛЮБОГО источника опыта (патч 14, ч.2.3: килл,
    квест, событие) — если начисление вызвало левелап, открывает/обновляет
    окно распределения статов. Источники опыта не должны сами решать, звать
    им это или нет — они просто передают сюда levels_gained/new_level.

    ОТЛОЖЕННО и в своей задаче (2026-10-11). Групповой бой и рейд звали это
    изнутри ещё открытой транзакции награды, которая держит строку
    персонажа, - а окно читало персонажа через get_character, тот писал
    last_active_at в ту же строку и ждал блокировку. Взаимная блокировка
    до таймаута, исключение рушило разбор хода, и бой оставался в памяти
    полумёртвым: игрок «в бою», но ходы не проходят и /застрял не помогает.
    Теперь вызывающий не ждёт окна вовсе, а окно открывается после его
    коммита и персонажа только читает."""
    if levels_gained > 0:
        asyncio.get_running_loop().create_task(_levelup_later(peer_id, sas.levelup_header(new_level)))


async def _levelup_later(peer_id: int, header: str) -> None:
    """Новый уровень: окно распределения не навязываем (2026-10-13) - только
    строка и кнопка «Распределить»; можно и в мини-аппе. Уже открытое окно
    обновляется на месте, как раньше."""
    await asyncio.sleep(LEVELUP_DELAY_SECONDS)
    try:
        if peer_id in _window_header:
            await open_or_update_window(peer_id, header)
            return
        async with get_session_factory()() as db:
            character = await _read_character(db, peer_id)
            if character is None or character.creation_state is not None:
                return
            unspent = (await _get_stats(db, character.id)).unspent_points
        if unspent <= 0:
            await _bot_api.messages.send(peer_id=peer_id, message=header, random_id=0)
            return
        await _bot_api.messages.send(
            peer_id=peer_id, message=f"{header} Свободных очков: {unspent}.",
            random_id=0, keyboard=levelup_keyboard(),
        )
    except Exception:
        logger.exception("Весть о новом уровне не ушла {}", peer_id)


async def _read_character(db, peer_id: int) -> Character | None:
    """Персонаж без записи last_active_at - чтение блокировок не ждёт."""
    return await db.scalar(
        select(Character).join(User, User.id == Character.user_id).where(User.vk_id == peer_id)
    )


async def open_or_update_window(peer_id: int, header: str) -> None:
    """Открывает окно распределения; если для игрока уже открыто — редактирует
    его (несколько левелапов подряд не плодят новых окон, патч 11)."""
    async with get_session_factory()() as db:
        character = await _read_character(db, peer_id)
        if character is None or character.creation_state is not None:
            return
        stats = await _get_stats(db, character.id)
        unspent = stats.unspent_points
        char_stats = sas.snapshot(stats)

    _window_header[peer_id] = header

    if unspent <= 0:
        _clear(peer_id)
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=sas.render_readonly(
                header, char_stats, character.pvp_wins, character.pvp_losses, daily_service.title_name(character),
                pts=character.pts,
            ),
            random_id=0,
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


@labeler.message(payload_contains={"type": "stat_alloc_open"})
async def stat_alloc_open(message: Message) -> None:
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
    if peer_id not in _pending:
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
        text = sas.render_readonly(
            header, char_stats, character.pvp_wins, character.pvp_losses, daily_service.title_name(character),
                pts=character.pts,
        )
        await _send_or_edit(peer_id, text, no_keyboard())
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
            pvp_wins, pvp_losses, pts = character.pvp_wins, character.pvp_losses, character.pts
            title = daily_service.title_name(character)
        _clear(peer_id)
        text = sas.render_readonly(header, char_stats, pvp_wins, pvp_losses, title, pts=pts)
        await _send_or_edit(peer_id, text, no_keyboard())
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
