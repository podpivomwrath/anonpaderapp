"""Лобби, которое пережило своих участников (патч 89).

На проде лобби Гостуса провисело шесть дней и рассылало «Готовы: 0/4» в
случайные часы. Три разные поломки сложились в один симптом:

1. Уйти с Монолита можно шагом, на маунте (в том числе с карты мини-аппа) и
   телепортом администратора. Из лобби выводил только шаг, поэтому уехавший
   оставался в нём навсегда.
2. Лобби ничем не ограничено во времени: пока в нём кто-то числится, оно
   живёт.
3. Метки «это уже отправлено» лежат в памяти процесса. После перезапуска
   бота их нет, и первая же сверка рассылала неизменившуюся строку заново -
   отсюда «случайные часы»: это были деплои.

Здесь проверяются первая и третья.
"""

import pytest

from game.economy import raid_config as rc
from services import group_service as gs
from services import raid_service as rs

AWAY = (41, -41)  # где на проде стоял Гостус, оставаясь в лобби


async def _group(db_session, make_character, size: int):
    leader = await make_character(level=60)
    members = [leader]
    group_id = None
    for _ in range(size - 1):
        member = await make_character(level=60)
        invite = await gs.send_invite(db_session, leader, member)
        group_id = (await gs.accept_invite(db_session, invite.id, member.id)).group.id
        members.append(member)
    for character in members:
        character.pos_x, character.pos_y = rc.MONOLITH_COORDS
    await db_session.flush()
    return group_id, members


async def test_member_who_left_the_monolith_is_dropped(db_session, make_character) -> None:
    """Не важно, КАК он ушёл - важно, что его там нет."""
    group_id, (leader, second) = await _group(db_session, make_character, 2)
    lobby = await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    await rs.touch_monolith(db_session, second, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)

    second.pos_x, second.pos_y = AWAY
    await db_session.flush()

    snapshot = await rs.prune_absent_members(db_session, lobby.id)
    assert snapshot is not None
    assert [c.id for c, _ in snapshot.members] == [leader.id]


async def test_member_standing_on_the_monolith_stays(db_session, make_character) -> None:
    """Чистка не должна выгонять тех, кто честно ждёт."""
    group_id, (leader, second) = await _group(db_session, make_character, 2)
    lobby = await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    await rs.touch_monolith(db_session, second, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)

    snapshot = await rs.prune_absent_members(db_session, lobby.id)
    assert snapshot is not None
    assert len(snapshot.members) == 2


async def test_member_who_started_travelling_counts_as_gone(db_session, make_character) -> None:
    """pos_x/y меняются только по ПРИБЫТИИ, а поездка с Монолита всегда ведёт
    с него. Ждать прибытия, чтобы это признать, незачем."""
    group_id, (leader, second) = await _group(db_session, make_character, 2)
    lobby = await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    await rs.touch_monolith(db_session, second, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)

    second.travel_target_x, second.travel_target_y = AWAY
    await db_session.flush()
    assert (second.pos_x, second.pos_y) == rc.MONOLITH_COORDS  # ещё «здесь»

    snapshot = await rs.prune_absent_members(db_session, lobby.id)
    assert snapshot is not None
    assert [c.id for c, _ in snapshot.members] == [leader.id]


async def test_lobby_dies_with_its_last_member(db_session, make_character) -> None:
    """Ровно случай с прода: в лобби остался один, и тот ушёл."""
    player = await make_character(level=60)
    player.pos_x, player.pos_y = rc.MONOLITH_COORDS
    await db_session.flush()
    lobby = await rs.touch_monolith(db_session, player, rc.RAID_PUPPET_THEATRE_ID, group_id=None)

    player.pos_x, player.pos_y = AWAY
    await db_session.flush()

    assert await rs.prune_absent_members(db_session, lobby.id) is None
    assert await rs.get_snapshot(db_session, lobby.id) is None


async def test_leadership_moves_when_the_leader_walks_off(db_session, make_character) -> None:
    group_id, (leader, second) = await _group(db_session, make_character, 2)
    lobby = await rs.touch_monolith(db_session, leader, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
    await rs.touch_monolith(db_session, second, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)

    leader.pos_x, leader.pos_y = AWAY
    await db_session.flush()

    snapshot = await rs.prune_absent_members(db_session, lobby.id)
    assert snapshot is not None
    assert snapshot.leader_character_id == second.id


# --- Рассылка после перезапуска бота ---------------------------------------


@pytest.fixture
def lobby_handler(monkeypatch):
    """Обработчик лобби со счётчиком отправленных сообщений вместо ВК."""
    from bot.handlers import raid as handler

    sent: list[int] = []

    class _Messages:
        async def send(self, **kwargs):
            sent.append(kwargs["peer_id"])

    class _Api:
        messages = _Messages()

    async def _peers(_db, character_ids):
        return {cid: 1000 + cid for cid in character_ids}

    monkeypatch.setattr(handler, "_bot_api", _Api())
    monkeypatch.setattr(handler, "_peer_ids_for", _peers)
    handler._published.clear()
    handler._primed = False
    return handler, sent


class _Member:
    def __init__(self, character_id: int) -> None:
        self.id = character_id
        self.name = f"Игрок{character_id}"


def _snapshot(*, denominator: int = 4, members=(3,)):
    class _Snapshot:
        id = 11
        leader_character_id = 3

    snapshot = _Snapshot()
    snapshot.denominator = denominator
    snapshot.members = [(_Member(cid), False) for cid in members]
    return snapshot


async def test_restart_does_not_resend_an_unchanged_lobby(lobby_handler) -> None:
    """Пока бот лежит, менять состояние лобби некому. Значит, строка, которую
    игроки видят на экране, всё ещё верна, и повторять её нечего.

    Без этого каждый деплой давал игрокам ещё одну копию - ровно то, что
    видел Гостус."""
    handler, sent = lobby_handler
    snapshot = _snapshot()
    handler._published[snapshot.id] = handler._signature(snapshot)

    await handler.publish_lobby(snapshot)

    assert sent == []


async def test_a_real_change_still_goes_out(lobby_handler) -> None:
    """Подавление касается ТОЛЬКО неизменившейся строки: иначе чистка лобби
    прошла бы для остальных незаметно."""
    handler, sent = lobby_handler
    handler._published[11] = handler._signature(_snapshot(denominator=4, members=(3, 7)))

    # кого-то вычистили: и знаменатель, и состав другие
    await handler.publish_lobby(_snapshot(denominator=3, members=(3,)))

    assert sent == [1003], "оставшийся обязан увидеть новую строку"


async def test_without_priming_every_restart_sends_again(lobby_handler) -> None:
    """Контрольный выстрел: если метку не запомнить, строка уходит снова.

    Проверяется не догадка о причине, а сама причина - пустые метки после
    перезапуска процесса."""
    handler, sent = lobby_handler
    snapshot = _snapshot()

    await handler.publish_lobby(snapshot)  # метки пусты, как после рестарта
    assert sent == [1003]

    await handler.publish_lobby(snapshot)  # метка уже стоит - молчим
    assert sent == [1003]


# --- Сама сверка, а не только рассылка -------------------------------------


@pytest.fixture
async def wired_handler(monkeypatch):
    """Обработчик лобби, подключённый к отдельной тестовой БД.

    Своя фабрика сессий нужна именно здесь: reconcile_lobbies открывает
    сессию сам, и проверить его через db_session нельзя. Ради одного теста
    это оправдано - в нём и живёт починка, из-за которой игрок получал
    лишние сообщения.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from bot.handlers import raid as handler
    from models import Base

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    sent: list[int] = []

    class _Messages:
        async def send(self, **kwargs):
            sent.append(kwargs["peer_id"])

    class _Api:
        messages = _Messages()

    async def _peers(_db, character_ids):
        return {cid: 1000 + cid for cid in character_ids}

    monkeypatch.setattr(handler, "get_session_factory", lambda: factory)
    monkeypatch.setattr(handler, "_bot_api", _Api())
    monkeypatch.setattr(handler, "_peer_ids_for", _peers)
    handler._published.clear()
    handler._primed = False

    yield handler, factory, sent
    await engine.dispose()


async def _waiting_lobby(factory, size: int = 2, touched: int = 1):
    """Лобби, которое ещё не готово к старту.

    size - размер группы (он же знаменатель), touched - сколько человек
    отметилось у Монолита. Пока touched < size, сверка не попытается
    запустить рейд, и виден именно обмен строками лобби.
    """
    from models import Character, User

    async with factory() as db:
        people = []
        for n in range(1, size + 1):
            user = User(vk_id=2000 + n)
            db.add(user)
            await db.flush()
            character = Character(
                user_id=user.id, name=f"Игрок{n}", base_class="warrior", level=60,
                pos_x=rc.MONOLITH_COORDS[0], pos_y=rc.MONOLITH_COORDS[1], region="ridge",
            )
            db.add(character)
            people.append(character)
        await db.flush()
        leader = people[0]
        group_id = None
        for other in people[1:]:
            invite = await gs.send_invite(db, leader, other)
            group_id = (await gs.accept_invite(db, invite.id, other.id)).group.id
        lobby = None
        for person in people[:touched]:
            lobby = await rs.touch_monolith(db, person, rc.RAID_PUPPET_THEATRE_ID, group_id=group_id)
        ids = [p.id for p in people]
        lobby_id = lobby.id
        await db.commit()
    return lobby_id, ids


async def test_reconcile_after_restart_stays_silent(wired_handler) -> None:
    """Главная проверка этого файла.

    Бот перезапустился: метки публикации пусты, лобби в базе то же. Игроки
    ничего не делали, значит и говорить им нечего. Без запоминания подписей
    первый же проход сверки слал строку заново - каждый деплой давал ещё
    одну копию «Готовы: 0/4».
    """
    handler, factory, sent = wired_handler
    await _waiting_lobby(factory)

    await handler.reconcile_lobbies()

    assert sent == [], f"после перезапуска ушли лишние сообщения: {sent}"


async def test_reconcile_tells_the_others_when_someone_leaves(wired_handler) -> None:
    """Молчание не должно стать глухотой: если сверка кого-то вычистила,
    оставшиеся обязаны это увидеть."""
    from models import Character

    handler, factory, sent = wired_handler
    _lobby_id, ids = await _waiting_lobby(factory, size=3, touched=2)
    leader_id, second_id = ids[0], ids[1]

    await handler.reconcile_lobbies()          # первый проход - запомнил
    assert sent == []

    async with factory() as db:                # лидер уехал с Монолита
        leader = await db.get(Character, leader_id)
        leader.pos_x, leader.pos_y = AWAY
        await db.commit()

    await handler.reconcile_lobbies()

    assert sent == [1000 + second_id], "оставшийся обязан увидеть новый состав"
    async with factory() as db:
        snapshot = await rs.get_snapshot(db, _lobby_id)
        assert [c.id for c, _ in snapshot.members] == [second_id]
        assert snapshot.leader_character_id == second_id


async def test_empty_lobby_is_dissolved_by_reconcile(wired_handler) -> None:
    """Случай с прода: в лобби остался один, и тот уехал."""
    from models import Character

    handler, factory, sent = wired_handler
    lobby_id, ids = await _waiting_lobby(factory)

    await handler.reconcile_lobbies()
    async with factory() as db:
        person = await db.get(Character, ids[0])
        person.pos_x, person.pos_y = AWAY
        await db.commit()

    await handler.reconcile_lobbies()

    assert sent == [], "в лобби больше никого - и сообщать некому"
    async with factory() as db:
        assert await rs.get_snapshot(db, lobby_id) is None, "пустое лобби должно быть распущено"
