"""Вести группе (2026-10-12): участник пришёл на твою клетку; на участника
напал игрок - узнаёт вся группа, где бы ни была."""

import asyncio

from bot.handlers import group as group_handlers
from services import group_service as gs
from services import onboarding_service as onboarding_svc


class FakeApi:
    def __init__(self):
        self.sent = []

        class Messages:
            async def send(inner, **kw):
                self.sent.append((kw["peer_id"], kw["message"]))

        self.messages = Messages()


async def _group(db, make_character):
    a = await make_character()
    b = await make_character()
    c = await make_character()
    for target in (b, c):
        invite = await gs.send_invite(db, a, target)
        await gs.accept_invite(db, invite.id, target.id)
    return a, b, c


async def _peer(db, character):
    return await onboarding_svc.vk_id_for_character(db, character.id)


async def test_arrival_notifies_only_groupmates_on_the_same_cell(db_session, make_character, monkeypatch) -> None:
    api = FakeApi()
    monkeypatch.setattr(group_handlers, "_bot_api", api)
    a, b, c = await _group(db_session, make_character)
    a.pos_x, a.pos_y = 3, 26
    b.pos_x, b.pos_y = 3, 26
    c.pos_x, c.pos_y = 5, 20
    await db_session.flush()

    await group_handlers.notify_arrival(db_session, a)
    await asyncio.sleep(0)
    assert [peer for peer, _ in api.sent] == [await _peer(db_session, b)]
    assert a.name in api.sent[0][1]


async def test_attack_notifies_whole_group_except_victim_and_attacker(db_session, make_character, monkeypatch) -> None:
    api = FakeApi()
    monkeypatch.setattr(group_handlers, "_bot_api", api)
    a, b, c = await _group(db_session, make_character)
    stranger = await make_character()
    c.pos_x, c.pos_y = 40, 40  # далеко - всё равно узнаёт

    await group_handlers.notify_attacked(db_session, a, stranger)
    await asyncio.sleep(0)
    assert sorted(peer for peer, _ in api.sent) == sorted([await _peer(db_session, b), await _peer(db_session, c)])
    assert stranger.name in api.sent[0][1]
