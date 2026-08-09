"""Общий примитив «одно сообщение, редактируемое на месте» (патч 11, блок 1 —
окно статов; обобщено патчем 13, ч.1 на скупщика/сравнение экипировки/инвентарь).

Каждый вызывающий модуль работает под своим namespace, чтобы окна разных
потоков для одного peer_id не затирали id сообщений друг друга (игрок может
держать открытым, например, и инвентарь, и окно статов одновременно)."""

# (namespace, peer_id) -> conversation_message_id уже открытого окна
_tracked: dict[tuple[str, int], int] = {}


def clear(namespace: str, peer_id: int) -> None:
    _tracked.pop((namespace, peer_id), None)


async def send_or_edit(
    bot_api, namespace: str, peer_id: int, text: str, keyboard: str | None,
    attachment: str | None = None,
) -> None:
    """Правит уже открытое окно этого namespace на месте; если сообщение
    недоступно для правки (истекло/удалено) — открывает новое взамен.
    Граница с внешним API — сознательно широкий except (см. также respawn.py)."""
    key = (namespace, peer_id)
    existing = _tracked.get(key)
    if existing is not None:
        try:
            await bot_api.messages.edit(
                peer_id=peer_id, conversation_message_id=existing, message=text,
                keyboard=keyboard, attachment=attachment,
            )
            return
        except Exception:
            _tracked.pop(key, None)
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
