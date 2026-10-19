"""2026-10-19: передача через пересланное сообщение не раскрывает ник
(кроме своих по гильдии)."""

from bot.handlers import transfer


def _pending(name):
    return transfer.Pending(token="t", recipient_id=2, recipient_name=name, recipient_peer=5, offers=[], qty=None)


def test_whom_hides_name_outside_guild():
    assert transfer._whom(_pending(None)) == "игроку из пересланного сообщения"
    assert transfer._whom(_pending("EGERb")) == "игроку EGERb"
    assert transfer._pending is not None and _pending(None).reveal_sender is False
