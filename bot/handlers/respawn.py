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
from game.world import grid
from models import Character, User
from services import death_service, guild_territory_service, pvp_shield, screen_service, vitals_service
from services.db import get_session_factory

_bot_api = None
_live_countdown = True
# peer_id -> message_id сообщения о смерти (для edit-отсчёта)
_death_message: dict[int, int] = {}
# peer_id -> потерянный при смерти опыт: отсчёт пересобирает сообщение
# каждый скан, и без этого строка штрафа пропадала после первой правки
# (2026-10-19, жалоба игрока: «не написало про потерянный опыт»).
_death_xp: dict[int, int] = {}
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


TINCTURE_SAVED_LINE = "🫗 Настойка пепла ещё действует: опыт не потерян."
POCKET_SAVED_LINE = "🎒 Секретный карман цел: что было в нём, осталось при тебе."


async def _gem_goods_lines(peer_id: int, now: datetime, pvp: bool) -> list[str]:
    """Что сберегли товары за самоцветы. Опыт в PvP теряет только клеймёный -
    остальным строку про настойку не показываем, она ничего не спасла."""
    from game.combat import balance_config as bc
    from services import pk_service, trophy_service

    # Только чтение, без get_character: тот пишет строку персонажа (смена
    # дня), а смерть приходит, пока бой ещё держит её своей сессией.
    async with get_session_factory()() as db:
        character = await db.scalar(
            select(Character).join(User, User.id == Character.user_id).where(User.vk_id == peer_id)
        )
        if character is None:
            return []
        lines = []
        would_lose_xp = character.level < bc.MAX_LEVEL and (not pvp or pk_service.costly_death(character))
        if would_lose_xp and death_service.tincture_active(character, now):
            lines.append(TINCTURE_SAVED_LINE)
        if character.secret_pocket and await trophy_service.get_stock(db, character.id):
            lines.append(POCKET_SAVED_LINE)
        await db.rollback()
    return lines


async def register_death(
    peer_id: int, respawn_at: datetime, xp_lost: int = 0, relics_lost: dict[str, int] | None = None,
    fish_lost: int = 0,
) -> None:
    """Смерть игрока: убрать кнопки, показать атмосферный текст (+ штраф опыта
    и сгоревшие реликвии - отдельной строкой, её не трогает отсчёт)."""
    now = datetime.now(timezone.utc)
    resp = await _bot_api.messages.send(
        peer_id=peer_id, message=_death_text(respawn_at, now, xp_lost), random_id=0,
        attachment=photo_attachment(DEATH_PHOTO_ID), keyboard=kb.waiting_keyboard(),
    )
    from services import trophy_service

    lines = [trophy_service.lost_line(relics_lost)] if relics_lost else []
    if fish_lost:
        from game.economy import fishing as game_fishing

        lines.append(f"🧺 Садок пропал: {game_fishing.format_kg(fish_lost)} рыбы.")
    try:
        lines += await _gem_goods_lines(peer_id, now, pvp=peer_id in _pvp_death_pending)
    except Exception:
        logger.warning("Строки настойки/кармана для {} не собрались", peer_id)
    if lines:
        await _bot_api.messages.send(peer_id=peer_id, message="\n".join(lines), random_id=0)
    # messages.send с peer_id возвращает message_id - по нему и правим. Раньше
    # его передавали как conversation_message_id (номер в диалоге, совсем другое
    # число): правка всегда падала, и отсчёт не обновлялся никогда.
    try:
        _death_message[peer_id] = int(resp)
        _death_xp[peer_id] = xp_lost
    except (TypeError, ValueError):
        pass


CHAPEL_RESPAWN_TEXT = (
    "⛪ Ты приходишь в себя у часовни своей гильдии. Колокол ещё гудит.\n"
    "🛡 Две минуты на тебя не нападут, пока не уйдешь с этой клетки."
)


def _outside_gate(region: str) -> tuple[int, int]:
    """Ближайшая к Монолиту клетка у стен родного города - не город."""
    cx, cy = wc.CITY_COORDS[region]
    best = None
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            x, y = cx + dx, cy + dy
            if (dx or dy) and grid.in_bounds(x, y) and grid.city_region_at(x, y) is None:
                key = grid.monolith_distance(x, y)
                if best is None or key < best[0]:
                    best = (key, (x, y))
    return best[1] if best else (cx, cy)


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
                from services import pk_service

                if pk_service.city_banned(character):
                    # Клеймо 20+: стража не пускает - встаёт у ворот.
                    character.pos_x, character.pos_y = _outside_gate(character.region)
                    await screen_service.set_screen(db, character, None)
                    to_revive.append((vk_id, None))
                    continue
                if character.respawn_at_chapel and character.guild_id is not None:
                    chapel = await guild_territory_service.chapel_cell(db, character.guild_id)
                    if chapel is not None:
                        character.pos_x, character.pos_y = chapel.x, chapel.y
                        # Часовня стоит в поле: без щита у неё добивали бы
                        # только что очнувшихся (2026-10-21, владелец).
                        pvp_shield.grant(character.id, pvp_shield.CHAPEL, cell=(chapel.x, chapel.y))
                # Патч 39: возрождение — всегда корневой экран (площадь).
                await screen_service.set_screen(db, character, None)
                to_revive.append((vk_id, None if chapel is not None else character.region))
            else:
                to_update.append((vk_id, character.respawn_at))
        await db.commit()

    for peer_id, region in to_revive:
        _death_message.pop(peer_id, None)
        _death_xp.pop(peer_id, None)
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
        # Клавиатура площади по персонажу: пустая city_square_keyboard()
        # теряла кнопку маунта и значок наставника.
        await _bot_api.messages.send(
            peer_id=peer_id,
            message=text,
            random_id=0,
            keyboard=await _field_keyboard(peer_id) or kb.city_square_keyboard(),
        )

    # Смерть в PvP (дуэль, массовый бой, осада) приходила только строкой
    # «Тебя побеждает …» - без таймера возрождения (2026-10-13, жалоба
    # игроков). Сообщение смерти с отсчётом шлём здесь, при первом скане:
    # PvP регистрирует смерть внутри открытой транзакции, слать оттуда нельзя.
    for peer_id, respawn_at in to_update:
        if peer_id in _pvp_death_pending and peer_id not in _death_message:
            try:
                await register_death(peer_id, respawn_at)
            except Exception:
                logger.warning("Не удалось показать отсчёт PvP-смерти {}", peer_id)
                _death_message[peer_id] = 0  # не долбить VK каждый скан

    if _live_countdown:
        for peer_id, respawn_at in to_update:
            msg_id = _death_message.get(peer_id)
            if msg_id is None:
                continue
            try:
                await _bot_api.messages.edit(
                    peer_id=peer_id,
                    message_id=msg_id,
                    message=_death_text(respawn_at, now, _death_xp.get(peer_id, 0)),
                )
            except Exception:
                logger.debug("Не удалось обновить отсчёт респавна для {}", peer_id)
