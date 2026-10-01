"""Авто-респавн (combat-patch-2, п.5): один общий батч-сканер, НЕ задача-на-игрока.

Экономно: единственный периодический job (APScheduler interval) сканирует БД на
мёртвых игроков и:
  - возрождает тех, у кого таймер вышел (HP полное, город региона, меню города);
  - при RESPAWN_LIVE_COUNTDOWN — раз в скан обновляет сообщение о смерти остатком
    времени (edit). Боевые сообщения по частоте не трогаются — обновления таймера
    идут отдельным низкочастотным сканом.
Если упор в rate limit VK — RESPAWN_LIVE_COUNTDOWN=False: статичное сообщение.
"""

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select

from bot.keyboards import world as kb
from bot.onboarding_texts import REGION_TITLES
from bot.pvp_texts import PVP_RESPAWN_LORE
from bot.vk_media import photo_attachment
from game.world import flavor
from game.world import world_config as wc
from models import Character, User
from services import death_service, guild_territory_service, screen_service, vitals_service
from services.db import get_session_factory

_bot_api = None
_live_countdown = True
# peer_id -> message_id сообщения о смерти (для edit-отсчёта)
_death_message: dict[int, int] = {}
# peer_id -> ждёт PvP-лорную фразу возрождения вместо обычной (патч 22) —
# PvP-поражение не показывает счётчик смерти в реальном времени, само
# сообщение о поражении шлёт bot/handlers/pvp.py, а не register_death.
_pvp_death_pending: set[int] = set()


def register_pvp_death(peer_id: int) -> None:
    _pvp_death_pending.add(peer_id)

DEATH_PHOTO_ID = "457239032"  # иллюстрация смерти игрока (альбом группы VK)


def setup(bot_api, live_countdown: bool) -> None:
    global _bot_api, _live_countdown
    _bot_api = bot_api
    _live_countdown = live_countdown


def _death_text(respawn_at: datetime, now: datetime, xp_lost: int = 0) -> str:
    # Один текст на всю смерть: сообщение пересобирается каждый тик отсчёта.
    text = flavor.death_line(int(respawn_at.timestamp()) if respawn_at is not None else None)
    if xp_lost > 0:
        text += "\n" + flavor.death_penalty_line(xp_lost)
    if _live_countdown and respawn_at is not None:
        left = max(0, (respawn_at - now).total_seconds())
        if left >= 60:
            text += f"\n\nДо возрождения: ~{left / 60:.0f} мин."
        else:
            text += f"\n\nДо возрождения: ~{int(left)} сек."
    else:
        text += "\n\nВозрождение скоро."
    return text


async def register_death(peer_id: int, respawn_at: datetime, xp_lost: int = 0) -> None:
    """Смерть игрока: убрать кнопки, показать атмосферный текст (+ штраф опыта)."""
    now = datetime.now(timezone.utc)
    resp = await _bot_api.messages.send(
        peer_id=peer_id, message=_death_text(respawn_at, now, xp_lost), random_id=0,
        attachment=photo_attachment(DEATH_PHOTO_ID), keyboard=kb.waiting_keyboard(),
    )
    # messages.send с peer_id возвращает message_id - по нему и правим. Раньше
    # его передавали как conversation_message_id (номер в диалоге, совсем другое
    # число): правка всегда падала, и отсчёт не обновлялся никогда.
    try:
        _death_message[peer_id] = int(resp)
    except (TypeError, ValueError):
        pass


CHAPEL_RESPAWN_TEXT = "⛪ Ты приходишь в себя у часовни своей гильдии. Колокол ещё гудит."


async def _field_keyboard(peer_id: int) -> str | None:
    """Клавиатура клетки, где игрок очнулся: часовня стоит в поле, и
    площадь города тут неуместна."""
    from bot.handlers import world as world_handlers  # избегаем цикла импортов
    from services import onboarding_service

    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, peer_id)
        if character is None:
            return None
        return await world_handlers._current_keyboard(db, character, peer_id, datetime.now(timezone.utc))


async def scan() -> None:
    """Батч-проход: возродить готовых, обновить отсчёт остальным. Один job на всех."""
    if _bot_api is None:
        return
    now = datetime.now(timezone.utc)
    sf = get_session_factory()
    to_revive: list[tuple[int, str]] = []
    to_update: list[tuple[int, datetime]] = []
    async with sf() as db:
        rows = (
            await db.execute(
                select(Character, User.vk_id)
                .join(User, User.id == Character.user_id)
                .where(Character.respawn_at.isnot(None))
            )
        ).all()
        for character, vk_id in rows:
            if not death_service.is_dead(character, now):
                # таймер вышел — возрождаем
                death_service.respawn_if_ready(character, now)
                vitals_service.restore_full(character)
                character.pos_x, character.pos_y = wc.CITY_COORDS[character.region]
                # Гильдии: кто выбрал часовню, встаёт у неё, а не в городе.
                chapel = None
                if character.respawn_at_chapel and character.guild_id is not None:
                    chapel = await guild_territory_service.chapel_cell(db, character.guild_id)
                    if chapel is not None:
                        character.pos_x, character.pos_y = chapel.x, chapel.y
                # Патч 39: возрождение — всегда корневой экран (площадь).
                await screen_service.set_screen(db, character, None)
                to_revive.append((vk_id, None if chapel is not None else character.region))
            else:
                to_update.append((vk_id, character.respawn_at))
        await db.commit()

    for peer_id, region in to_revive:
        _death_message.pop(peer_id, None)
        if region is None:
            _pvp_death_pending.discard(peer_id)
            await _bot_api.messages.send(
                peer_id=peer_id, message=CHAPEL_RESPAWN_TEXT, random_id=0,
                keyboard=await _field_keyboard(peer_id),
            )
            continue
        if peer_id in _pvp_death_pending:
            _pvp_death_pending.discard(peer_id)
            text = PVP_RESPAWN_LORE.format(city=REGION_TITLES[region])
        else:
            text = flavor.respawn_line(REGION_TITLES[region])
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=text,
            random_id=0,
            keyboard=kb.city_square_keyboard(),
        )

    if _live_countdown:
        for peer_id, respawn_at in to_update:
            msg_id = _death_message.get(peer_id)
            if msg_id is None:
                continue
            try:
                await _bot_api.messages.edit(
                    peer_id=peer_id,
                    message_id=msg_id,
                    message=_death_text(respawn_at, now),
                )
            except Exception:
                logger.debug("Не удалось обновить отсчёт респавна для {}", peer_id)
