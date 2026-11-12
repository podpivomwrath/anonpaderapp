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
"""

from sqlalchemy import select

_quiet: set[int] = set()
#: Кому VK не даёт писать (900/901/902: бот в чёрном списке, сообщения
#: сообществу закрыты). Оповещения им не шлём, пока игрок сам не напишет
#: боту (2026-11-13: объявления мирового босса упирались в отказ VK 600 раз
#: за неделю). Отмечает обёртка отправки в bot/silent_guard.py.
_unreachable: set[int] = set()


async def load(session_factory) -> int:
    """Прочитать при старте, кто выключил оповещения."""
    from models import Character, User

    async with session_factory() as db:
        rows = (await db.execute(
            select(User.vk_id, Character.ui_flags).join(Character, Character.user_id == User.id)
        )).all()
    _quiet.clear()
    _quiet.update(int(vk_id) for vk_id, flags in rows if isinstance(flags, dict) and flags.get("no_notices"))
    return len(_quiet)


def set_quiet(vk_id: int, on: bool) -> None:
    if on:
        _quiet.add(int(vk_id))
    else:
        _quiet.discard(int(vk_id))


def mark_unreachable(vk_id) -> None:
    try:
        _unreachable.add(int(vk_id))
    except (TypeError, ValueError):
        pass


def reachable_again(vk_id) -> None:
    """Игрок написал боту - значит, писать ему снова можно."""
    try:
        _unreachable.discard(int(vk_id))
    except (TypeError, ValueError):
        pass


def quiet(vk_id) -> bool:
    """True - этому игроку оповещения не слать."""
    try:
        vk_id = int(vk_id)
    except (TypeError, ValueError):
        return False
    return vk_id in _quiet or vk_id in _unreachable


def keep(peers):
    """Отсеять из списка тех, кто выключил оповещения."""
    return [p for p in peers if not quiet(p)]
