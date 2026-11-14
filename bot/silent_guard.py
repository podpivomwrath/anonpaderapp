"""Страховка от «немых» кнопок (2026-10-13).

Игрок жмёт кнопку, а бот молчит: обработчик сработал и тихо вышел (инвентарь
вне города, старая клавиатура после рестарта, кнопка не по состоянию). Таких
выходов десятки, и каждый по отдельности не закрыть. Здесь - общая сеть:
если на сообщение в личке бот за GRACE_SECONDS ничего не отправил этому
игроку, он получает свежую клавиатуру под текущее состояние.

Как узнаём, что бот ответил: обёртка над api.request отмечает время каждого
messages.send/messages.edit по peer_id. Отложенные ответы (исследование,
планировщики) тоже идут через неё.

Бой не трогаем: там повторное нажатие в том же ходу молчит нарочно.
"""

import asyncio
import time

from loguru import logger

from bot import background, no_images
from vkbottle import BaseMiddleware
from vkbottle.bot import Message

GRACE_SECONDS = 2.5
STALE_TEXT = "Кнопки обновлены."
#: Ошибки VK при отправке, которые ждём и глотаем у вызова молча: игрок закрыл
#: личку (901/902, 7 - «нельзя писать контактам»), бот в чёрном списке (900),
#: сообщение нельзя править (909, 15), VK режет поток одному игроку (9 - на
#: быстром фарме не обновляется отсчёт пути). Любой другой код - битая клавиатура (911/912),
#: длинный текст (914), неверный параметр (100) - это баг, его пишем в журнал
#: ошибок здесь же: у вызова он часто тонет в `except Exception: pass`
#: (2026-10-22).
EXPECTED_SEND_ERRORS = {7, 9, 900, 901, 902, 909, 15}

_last_out: dict[int, float] = {}
_api = None
#: Лимит частоты VK (код 9) - в журнал предупреждением, не чаще раза в
#: FLOOD_LOG_SECONDS на игрока (2026-11-05, аудит: «Сводку» отбивал лимит, а
#: в журнале не было ни следа).
FLOOD_LOG_SECONDS = 60
_flood_logged: dict[int, float] = {}


def _note_flood(method: str, peer) -> None:
    try:
        peer = int(peer)
    except (TypeError, ValueError):
        return
    now = time.time()
    if now - _flood_logged.get(peer, 0.0) < FLOOD_LOG_SECONDS:
        return
    _flood_logged[peer] = now
    logger.warning("VK {}: лимит частоты (9) для {} - сообщение не дошло", method, peer)


def install(api) -> None:
    """Обернуть api.request один раз при старте (main.create_bot)."""
    global _api
    _api = api
    original = api.request

    async def request(method, data, version=None):
        # «Убрать картинки в игре» (2026-10-22): фото вырезаются здесь, для всех
        # отправок разом - bot/no_images.py.
        data = no_images.strip(method, data)
        if method == "messages.delete":
            routed = await _app_delete(original, data, version)
            if routed is not None:
                return routed
        if method in ("messages.send", "messages.edit"):
            targets = no_images.peers_of(data)
            # Клавиатура вне лимитов VK - VK отбил бы сообщение целиком
            # (2026-11-14): чиним на лету и пишем в журнал, какой экран.
            if data.get("keyboard"):
                from bot import keyboard_guard

                data = {**data, "keyboard": keyboard_guard.checked(data["keyboard"])}
            now = time.time()
            # peer_id числом, peer_ids списком (message.answer) или строкой.
            for p in targets:
                _last_out[p] = now
            # Приложение «Монолит» открыто (2026-11-15, владелец: «бот должен
            # молчать, работать только в одном месте») - сообщение уходит в
            # приложение, в VK ничего. bot/app_channel.py.
            routed = await _app_route(method, data, targets)
            if routed is not None and _REST in routed:
                data = routed[_REST]
                targets = no_images.peers_of(data)
            elif routed is not None:
                return routed
            # Закрыл сообщения сообществу (2026-11-14, владелец) - не пишем
            # ничего и в VK не ходим: тот же отказ 901, что вернул бы сам VK,
            # поэтому вызовы ведут себя как раньше.
            from bot import notices

            if targets and all(notices.unreachable(p) for p in targets):
                from vkbottle.exception_factory.base_exceptions import VKAPIError

                raise VKAPIError[901](error_msg="Игрок закрыл сообщения сообществу - бот ему не пишет")
        try:
            return await original(method, data, version)
        except Exception as exc:
            # Код 10 - «Internal server error, try later» у самого VK. В логах
            # он ронял разбор хода боя: игрок не получал сообщение о ходе
            # (2026-10-19). Один повтор через секунду почти всегда проходит.
            code = getattr(exc, "code", None)
            if code != 10:
                if method in ("messages.send", "messages.edit") and code not in EXPECTED_SEND_ERRORS:
                    logger.error("VK {}: ошибка {} для {} - {}", method, code, data.get("peer_id"), exc)
                elif code in (900, 901, 902) and method == "messages.send":
                    from bot import notices

                    notices.mark_unreachable(data.get("peer_id"))
                elif code == 9 and method == "messages.send":
                    # Правки (messages.edit) - это отсчёты пути и возрождения:
                    # следующая правка перекрывает пропущенную. В журнале их
                    # было 2745 за неделю, настоящие сбои в них тонули.
                    _note_flood(method, data.get("peer_id"))
                raise
            logger.warning("VK {}: внутренняя ошибка VK (10), повтор", method)
            await asyncio.sleep(1.0)
            return await original(method, data, version)

    api.request = request


def _refresh_world(vk_id: int) -> None:
    """После сообщения бота - снимок мира для приложения (bot/app_state.py)."""
    from bot import app_state

    app_state.refresh_soon(vk_id)


#: Ответ _app_route «остальным - в VK»: под этим ключом урезанный запрос.
_REST = "__vk_rest__"


async def _app_route(method: str, data: dict, targets: list[int]):
    """Отправка или правка игроку с открытым приложением - в приложение.
    None - пусть идёт в VK как обычно. Ответ - в том же виде, что вернул бы VK."""
    from bot import app_channel

    if method == "messages.edit":
        message_id = data.get("message_id")
        peer = targets[0] if targets else None
        if app_channel.is_fake(message_id):
            owner = app_channel.owner_of(message_id)
            if app_channel.active(owner):
                await app_channel.publish(owner, app_channel.edit_event(data))
                _refresh_world(owner)
                return {"response": 1}
            # Приложение закрыли, а окно было там - в VK такого сообщения нет:
            # тот же отказ, что у VK, и вызов пришлёт окно заново.
            from vkbottle.exception_factory.base_exceptions import VKAPIError

            raise VKAPIError[909](error_msg="Сообщение было в приложении")
        if peer is not None and app_channel.active(peer):
            return {"response": 1}  # правка старого окна в ВК, пока игрок в приложении - молчим
        return None
    in_app = [p for p in targets if app_channel.active(p)]
    if not in_app:
        return None
    ids = {}
    for p in in_app:
        ids[p] = app_channel.fake_id(p)
        await app_channel.publish(p, app_channel.message_event(data, ids[p]))
        _refresh_world(p)
    rest = [p for p in targets if p not in ids]
    if rest:
        # Рассылка многим: остальным - в VK обычным путём (повтор, отметка
        # закрывших сообщения) - обёртка продолжит с урезанным списком.
        trimmed = {k: v for k, v in data.items() if k not in ("peer_id", "peer_ids")}
        trimmed["peer_ids"] = ",".join(str(p) for p in rest)
        return {_REST: trimmed}
    if data.get("peer_ids") is not None:
        return {"response": [{"peer_id": p, "message_id": ids[p], "conversation_message_id": 0} for p in in_app]}
    return {"response": ids[in_app[0]]}


async def _app_delete(original, data: dict, version):
    """Удаление окон: номера приложения - в приложение, остальные - в VK."""
    from bot import app_channel

    raw = data.get("message_ids")
    ids = [str(i).strip() for i in (raw if isinstance(raw, (list, tuple)) else str(raw or "").split(","))]
    fake = [i for i in ids if app_channel.is_fake(i)]
    if not fake:
        return None
    for owner in {app_channel.owner_of(i) for i in fake}:
        if app_channel.active(owner):
            mine = [i for i in fake if app_channel.owner_of(i) == owner]
            await app_channel.publish(owner, {"type": "delete", "ids": mine})
    real = [i for i in ids if i and not app_channel.is_fake(i)]
    if real:
        return await original("messages.delete", {**data, "message_ids": ",".join(real)}, version)
    return {"response": {i: 1 for i in fake}}


def answered_since(peer_id: int, since: float) -> bool:
    return _last_out.get(peer_id, 0.0) >= since


async def _check_later(peer_id: int, from_id: int, started: float) -> None:
    await asyncio.sleep(GRACE_SECONDS)
    if answered_since(peer_id, started) or _api is None:
        return
    from bot.battle_keyboard import active_battle_keyboard
    from bot.handlers import world as world_handlers
    from datetime import datetime, timezone

    from services.db import get_session_factory
    from services.onboarding_service import get_character

    if active_battle_keyboard(peer_id) is not None:
        return
    logger.info(
        "Страховка кнопок: {} без ответа (начало {:.2f}, последний ответ {:.2f}, сейчас {:.2f})",
        peer_id, started, _last_out.get(peer_id, 0.0), time.time(),
    )
    try:
        async with get_session_factory()() as db:
            character = await get_character(db, from_id)
            if character is None or character.creation_state is not None:
                return
            keyboard = await world_handlers._current_keyboard(db, character, peer_id, datetime.now(timezone.utc))
        await _api.messages.send(peer_id=peer_id, random_id=0, message=STALE_TEXT, keyboard=keyboard)
    except Exception:
        logger.exception("Страховка кнопок: не удалось ответить {}", peer_id)


class SilentGuardMiddleware(BaseMiddleware[Message]):
    """Начало отсчёта - дата самого сообщения ВК (секунды, время по часам),
    а не время в pre(): vkbottle вызывает pre и post на РАЗНЫХ экземплярах
    middleware, и сохранённое в pre терялось. Так страховка 13.10 минут десять
    слала лишнее «Кнопки обновлены» всем подряд после обычных ответов."""

    async def post(self) -> None:
        event = self.event
        # Только личный диалог с игроком: в беседах бот молчит на чужие реплики.
        if event.from_id <= 0 or event.peer_id != event.from_id:
            return
        started = float(getattr(event, "date", 0) or 0) or time.time()
        background.spawn(_check_later(event.peer_id, event.from_id, started))


def setup_middleware(bot) -> None:
    bot.labeler.message_view.register_middleware(SilentGuardMiddleware)
