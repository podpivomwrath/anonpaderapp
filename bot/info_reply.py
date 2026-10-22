"""Ответ на справочную команду (/разломы, /квест, /топ, /профиль...) - одно
место, где решается, какая клавиатура уходит с таким ответом (2026-10-23,
просьба владельца разделить «что ответить» и «какие кнопки дать»).

Справка ничего не меняет в игре, поэтому и кнопки не должна менять:
- в бою - боевая клавиатура (без неё ответ стёр бы кнопки боя, патч 30);
- на озере и в руднике - кнопки этого экрана. Они были одноразовыми
  (one_time), и VK прятал их после любой набранной команды: /разломы и
  /руда посреди рыбалки оставляли без кнопок (Арина Александрова,
  2026-10-23). С тех пор они постоянные, а здесь - вторая страховка;
- в остальных местах клавиатуру не трогаем (None): посреди события, пути или
  ожидания группы «текущая» подменяла бы нужные кнопки (2026-10-16).

Новая справочная команда отвечает через answer() - и всё это получает сама.
"""

from bot.battle_keyboard import active_battle_keyboard

#: Экраны ремёсел: справка возвращает их кнопки (см. выше).
ONE_TIME_SCREENS = ("lake", "mine")


async def keyboard_for(peer_id: int, vk_id: int | None = None) -> str | None:
    battle = active_battle_keyboard(peer_id)
    if battle is not None:
        return battle
    from bot.handlers import world
    from services import onboarding_service
    from services.db import get_session_factory

    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, vk_id or peer_id)
        if character is None or character.screen not in ONE_TIME_SCREENS:
            return None
        return await world._screen_keyboard(db, character)


async def answer(message, text: str, **kwargs) -> None:
    await message.answer(text, keyboard=await keyboard_for(message.peer_id, message.from_id), **kwargs)
