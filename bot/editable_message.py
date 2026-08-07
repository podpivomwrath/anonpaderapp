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
    resp = await bot_api.messages.send(
        peer_id=peer_id, message=text, random_id=0, keyboard=keyboard, attachment=attachment,
    )
    try:
        _tracked[key] = int(resp)
    except (TypeError, ValueError):
        pass
