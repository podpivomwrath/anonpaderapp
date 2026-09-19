"""Reservations for activity transitions in the single bot process.

Reserve synchronously before the first await; other actions cannot pass their
checks while a battle/trip is still being constructed. Nested starts share the
reservation owner, including group and raid participants.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps

_owners: dict[int, object] = {}
_owner: ContextVar[object | None] = ContextVar("activity_owner", default=None)


class ActivityBusy(ValueError):
    pass


@contextmanager
def transition(peer_ids):
    owner = _owner.get() or object()
    peers = set(peer_ids)
    if any(p in _owners and _owners[p] is not owner for p in peers):
        raise ActivityBusy("Действие ещё выполняется. Подожди немного.")
    added = peers - _owners.keys()
    for peer in added:
        _owners[peer] = owner
    token = _owner.set(owner)
    try:
        yield
    finally:
        for peer in added:
            _owners.pop(peer, None)
        _owner.reset(token)


def activity_action(handler):
    @wraps(handler)
    async def wrapped(message, *args, **kwargs):
        from bot.battle_keyboard import active_battle_keyboard
        try:
            with transition([message.peer_id]):
                return await handler(message, *args, **kwargs)
        except ActivityBusy as exc:
            await message.answer(str(exc), keyboard=active_battle_keyboard(message.peer_id))
    return wrapped


async def blocked_reason(db, character, peer_id: int) -> str | None:
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import world
    from services import death_service, mining_service, mount_service, movement_service
    if in_any_battle(peer_id):
        return "Сначала закончи текущий бой."
    if death_service.is_dead(character):
        return "Сначала дождись возрождения."
    if movement_service.is_traveling(character):
        return "Сначала дождись прибытия."
    if world.is_busy(peer_id):
        return "Сначала закончи исследование или отдых."
    # Патч 59: добыча руды блокирует ВСЁ до конца — это её единственный
    # ограничитель. Проверка по БД, а не по памяти процесса: добыча длится
    # минутами и переживает рестарт бота.
    #
    # Блокирует только пока игрок реально в забое (screen == "mine"). После
    # рестарта бота экран сбрасывается, и игрок оказывается свободен «в хабе»:
    # он сам решает, вернуться в жилу и доработать остаток или уйти с клетки и
    # потерять его. Без этой оговорки он был бы заморожен и не смог бы ни того
    # ни другого.
    if character.screen == "mine" and mining_service.is_digging(character):
        from bot import mining_texts

        return mining_texts.busy_text(mining_service.remaining_seconds(character))
    travel = await mount_service.active_travel(db, character.id)
    if travel is not None and travel.status == "traveling":
        return "Сначала дождись окончания поездки."
    return None
