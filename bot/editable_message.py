"""Общий примитив «одно сообщение, редактируемое на месте» (патч 11, блок 1 —
окно статов; обобщено патчем 13, ч.1 на скупщика/сравнение экипировки/инвентарь).

Каждый вызывающий модуль работает под своим namespace, чтобы окна разных
потоков для одного peer_id не затирали id сообщений друг друга (игрок может
держать открытым, например, и инвентарь, и окно статов одновременно)."""

# (namespace, peer_id) -> message_id уже открытого окна.
#
# Именно message_id: его возвращает messages.send с peer_id. До живого
# прогона на pupsik (27.09) правка шла по conversation_message_id - номеру
# внутри диалога, это совсем другое число (4220 против 299687). ВК не находил
# сообщение, правка падала всегда, и каждое окно приходило новым сообщением.
_tracked: dict[tuple[str, int], int] = {}


def clear(namespace: str, peer_id: int) -> None:
    _tracked.pop((namespace, peer_id), None)


async def send_or_edit(
    bot_api, namespace: str, peer_id: int, text: str, keyboard: str | None,
    attachment: str | None = None,
) -> None:
    """Окно этого namespace: новое сообщение ВНИЗУ чата, прежнее окно
    удаляется - в чате остаётся одно окно, как и задумано.

    До 2026-10-13 окно правилось на месте. Но каждое нажатие кнопки само
    становится сообщением игрока, и правка случалась ВЫШЕ него: снизу ничего
    не появлялось, игроки решали, что кнопка не сработала (Nova у скупщика:
    продажа прошла, а ответа он не увидел). Граница с внешним API -
    сознательно широкий except (см. также respawn.py)."""
    key = (namespace, peer_id)
    existing = _tracked.pop(key, None)
    # Патч 33, баг 1: деградация СТУПЕНЧАТАЯ, не "всё или ничего". Патч 32
    # добавлял фолбэк без клавиатуры на случай отказа VK (напр. лимит строк) —
    # но он срабатывал и тогда, когда ломалась ТОЛЬКО картинка (напр. битый
    # photo_id скупщика, см. bot/appraiser_texts.py), и тогда игрок вместе с
    # картинкой терял ещё и кнопки продажи безо всякой связи с ними. Теперь
    # сначала пробуем без attachment (клавиатура остаётся), и только если
    # ПРОБЛЕМА В САМОЙ КЛАВИАТУРЕ — падаем до голого текста.
    try:
        resp = await bot_api.messages.send(
            peer_id=peer_id, message=text, random_id=0, keyboard=keyboard, attachment=attachment,
        )
    except Exception:
        try:
            resp = await bot_api.messages.send(
                peer_id=peer_id, message=text, random_id=0, keyboard=keyboard,
            )
        except Exception:
            resp = await bot_api.messages.send(peer_id=peer_id, message=text, random_id=0)
    try:
        _tracked[key] = int(resp)
    except (TypeError, ValueError):
        pass
    if existing is not None:
        # Удалить прежнее окно у обоих. Не вышло (старше суток, уже удалено) -
        # не беда: новое окно уже внизу.
        try:
            await bot_api.messages.delete(message_ids=[existing], delete_for_all=True)
        except Exception:
            pass
