"""«Без оповещений» (2026-11-09, репорт 340: «подзаебали эти оповещалки»).

Переключатель в мини-аппе (Персонаж -> Герой, внизу, рядом с картинками и
коротким логом). Кто его включил, тому бот не шлёт то, о чём игрок не
просил: открытые разломы, мировые боссы, весть об Ишаке, срочные заказы и
прибытие повозок, часовые вести долгого пути, новости гильдии, сгоревшие
баффы, венцы топов, итоги сезона PvP, заказы на голову. Ответы на действия
игрока (бой, исследование, итог похода, ремесло) идут как раньше.

Не фильтр в общей обёртке отправки, как у картинок: по самому сообщению не
понять, оповещение это или ответ. Каждое место рассылки спрашивает quiet().
Настройка - в ui_flags персонажа (ключ no_notices), копия в памяти по vk_id.

Виды по отдельности (2026-11-14, владелец): кроме общей галки каждый вид из
KINDS выключается сам - ключ notice_mute в ui_flags, список видов. Место
рассылки передаёт свой вид: quiet(peer, "boss"), keep(peers, "guild").

Закрывшие сообщения (2026-11-14, владелец: «переставать отправлять вообще
всё после того, как игрок заносит сообщество в ЧС»): после отказа VK
(900/901/902) или события message_deny бот не шлёт такому игроку НИЧЕГО -
обёртка отправки (silent_guard) отбивает запрос сама, не ходя в VK. Отметка
живёт в Redis (UNREACHABLE_KEY) и переживает выкатку: раньше она была только
в памяти, и после каждого рестарта рассылки снова упирались в отказы. Снимает
её сообщение игрока боту или событие message_allow.
"""

import asyncio

from loguru import logger
from sqlalchemy import select

_quiet: set[int] = set()
#: Виды оповещений, которые выключаются по одному. Подписи - в мини-аппе
#: (SettingsTab.jsx, NOTICE_KINDS), сверка - tests/test_notices.py.
KINDS = ("boss", "rift", "ishak", "cart", "orders", "voyage", "guild", "buffs", "crowns")
#: vk_id -> выключенные виды (только у тех, кто что-то выключил).
_muted: dict[int, frozenset[str]] = {}
#: Кому VK не даёт писать (900/901/902: бот в чёрном списке, сообщения
#: сообществу закрыты). Не шлём ничего, пока игрок сам не напишет боту
#: (2026-11-13: объявления мирового босса упирались в отказ VK 600 раз
#: за неделю). Отмечает обёртка отправки в bot/silent_guard.py.
_unreachable: set[int] = set()
UNREACHABLE_KEY = "notices:unreachable"
_redis = None
#: Личные peer_id игроков VK меньше этого числа; выше - беседы и демо-персонаж
#: (900000000001 получал объявления мирового босса и ронял их в журнал).
REAL_USER_LIMIT = 2_000_000_000


def setup(redis) -> None:
    global _redis
    _redis = redis


async def load_unreachable() -> int:
    """Прочитать при старте, кто закрыл сообщения (Redis)."""
    if _redis is None:
        return 0
    try:
        members = await _redis.smembers(UNREACHABLE_KEY)
    except Exception:  # noqa: BLE001 - Redis недоступен: стартуем без отметок
        logger.exception("Закрывшие сообщения: не прочитать из Redis")
        return 0
    for member in members:
        text = str(member)
        if text.isdecimal():
            _unreachable.add(int(text))
    return len(_unreachable)


def _persist(op: str, vk_id: int) -> None:
    if _redis is None:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    from bot import background

    background.spawn(getattr(_redis, op)(UNREACHABLE_KEY, vk_id), name=f"notices-{op}")


async def load(session_factory) -> int:
    """Прочитать при старте, кто выключил оповещения."""
    from models import Character, User

    async with session_factory() as db:
        rows = (await db.execute(
            select(User.vk_id, Character.ui_flags).join(Character, Character.user_id == User.id)
        )).all()
    _quiet.clear()
    _muted.clear()
    for vk_id, flags in rows:
        if not isinstance(flags, dict):
            continue
        if flags.get("no_notices"):
            _quiet.add(int(vk_id))
        set_muted(vk_id, flags.get("notice_mute"))
    return len(_quiet)


def set_quiet(vk_id: int, on: bool) -> None:
    if on:
        _quiet.add(int(vk_id))
    else:
        _quiet.discard(int(vk_id))


def clean_kinds(value) -> list[str]:
    """Из присланного мини-аппом - только известные виды, без повторов."""
    if not isinstance(value, list):
        return []
    return [k for k in KINDS if k in value]


def set_muted(vk_id, kinds) -> None:
    kinds = frozenset(clean_kinds(kinds))
    if kinds:
        _muted[int(vk_id)] = kinds
    else:
        _muted.pop(int(vk_id), None)


def mark_unreachable(vk_id) -> None:
    try:
        vk_id = int(vk_id)
    except (TypeError, ValueError):
        return
    if vk_id <= 0 or vk_id in _unreachable:
        return
    _unreachable.add(vk_id)
    logger.info("Игрок {} закрыл сообщения сообществу - не пишем ему, пока не напишет сам", vk_id)
    _persist("sadd", vk_id)


def reachable_again(vk_id) -> None:
    """Игрок написал боту (или разрешил сообщения) - писать ему снова можно."""
    try:
        vk_id = int(vk_id)
    except (TypeError, ValueError):
        return
    if vk_id not in _unreachable:
        return
    _unreachable.discard(vk_id)
    logger.info("Игрок {} снова принимает сообщения", vk_id)
    _persist("srem", vk_id)


def unreachable(vk_id) -> bool:
    """True - VK этому игроку писать не даёт, отправку отбиваем сами."""
    try:
        return int(vk_id) in _unreachable
    except (TypeError, ValueError):
        return False


def register(bot) -> None:
    """Снятие и постановка отметки «закрыл сообщения».

    Прослойка - ПЕРВОЙ из всех: игрок написал боту, значит, писать ему снова
    можно, и снять отметку надо до любого ответа (бан-гейт, соглашение и
    фильтр кнопок тоже отвечают, а обёртка отправки отбила бы их).

    События VK о разрешении и запрете сообщений приходят, если они включены в
    настройках Long Poll сообщества; без них отметку ставит первый отказ VK,
    а снимает сообщение игрока боту."""
    from vkbottle import BaseMiddleware, GroupEventType, GroupTypes
    from vkbottle.bot import Message

    class ReachableMiddleware(BaseMiddleware[Message]):
        async def pre(self) -> None:
            event = self.event
            if event.from_id > 0 and event.peer_id == event.from_id:
                reachable_again(event.from_id)

    bot.labeler.message_view.register_middleware(ReachableMiddleware)

    @bot.on.raw_event(GroupEventType.MESSAGE_ALLOW, dataclass=GroupTypes.MessageAllow)
    async def _allowed(event: GroupTypes.MessageAllow) -> None:
        reachable_again(event.object.user_id)

    @bot.on.raw_event(GroupEventType.MESSAGE_DENY, dataclass=GroupTypes.MessageDeny)
    async def _denied(event: GroupTypes.MessageDeny) -> None:
        mark_unreachable(event.object.user_id)


def quiet(vk_id, kind: str | None = None) -> bool:
    """True - этому игроку оповещения не слать (все или этого вида)."""
    try:
        vk_id = int(vk_id)
    except (TypeError, ValueError):
        return False
    if vk_id <= 0 or vk_id >= REAL_USER_LIMIT:
        return True
    if vk_id in _quiet or vk_id in _unreachable:
        return True
    return kind is not None and kind in _muted.get(vk_id, ())


def keep(peers, kind: str | None = None):
    """Отсеять из списка тех, кто выключил оповещения (все или этого вида)."""
    return [p for p in peers if not quiet(p, kind)]
