"""Рейд-лобби (патч 53): сбор группы (или соло) у Монолита перед стартом
рейда. Лидер лобби — тот, кто выбрал рейд ПЕРВЫМ (см. текст патча: «Лидер
выбирает рейд первым. Создаётся лобби») — для группы это, как правило,
лидер группы, но сервис не требует этого явно: игровое дизайн-намерение
подкреплено тем, что именно первый нажавший видит рейд-меню и запускает
лобби; остальные лишь присоединяются к уже созданному.

RaidError — игроко-читаемая причина отказа (тот же паттерн, что GroupError/
PresetValidationError)."""

from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Character, Group, GroupMember, RaidLobby, RaidLobbyMember, RaidRun


class RaidError(Exception):
    pass


@dataclass
class LobbySnapshot:
    id: int
    raid_id: str
    group_id: int | None
    leader_character_id: int
    status: str
    members: list[tuple[Character, bool]]  # (персонаж, готов)
    denominator: int  # знакомое "N/M" — размер группы (1, если соло)


async def get_membership(db: AsyncSession, character_id: int) -> RaidLobbyMember | None:
    return await db.scalar(
        select(RaidLobbyMember).where(RaidLobbyMember.character_id == character_id)
    )


async def active_lobby_for_group(db: AsyncSession, group_id: int) -> RaidLobby | None:
    return await db.scalar(
        select(RaidLobby).where(RaidLobby.group_id == group_id, RaidLobby.status == "waiting")
    )


async def get_snapshot(db: AsyncSession, lobby_id: int) -> LobbySnapshot | None:
    lobby = await db.get(RaidLobby, lobby_id)
    if lobby is None:
        return None
    rows = (
        await db.execute(
            select(RaidLobbyMember, Character)
            .join(Character, Character.id == RaidLobbyMember.character_id)
            .where(RaidLobbyMember.lobby_id == lobby.id)
        )
    ).all()
    members = [(character, member.ready) for member, character in rows]
    denominator = len(members) if lobby.group_id is None else await _group_size(db, lobby.group_id)
    return LobbySnapshot(
        id=lobby.id, raid_id=lobby.raid_id, group_id=lobby.group_id,
        leader_character_id=lobby.leader_character_id, status=lobby.status,
        members=members, denominator=max(denominator, len(members)),
    )


async def _group_size(db: AsyncSession, group_id: int) -> int:
    return await db.scalar(
        select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group_id)
    )


async def touch_monolith(
    db: AsyncSession, character: Character, raid_id: str, group_id: int | None,
) -> LobbySnapshot:
    """Персонаж нажал «Прикоснуться» и выбрал raid_id. Соло (group_id=None) —
    лобби на одного, сразу готов, можно стартовать немедленно. В группе —
    либо создаёт лобби (если он первый), либо присоединяется/отмечается
    готовым к уже существующему (RaidError, если группа уже выбрала другой
    рейд, или персонаж уже состоит в каком-то лобби)."""
    if group_id is not None:
        await db.scalar(select(Group).where(Group.id == group_id).with_for_update())
    membership = await get_membership(db, character.id)
    if membership is not None:
        lobby = await lock_lobby(db, membership.lobby_id)
        if lobby is None or lobby.status != "waiting" or lobby.raid_id != raid_id or lobby.group_id != group_id:
            raise RaidError("Ты уже в очереди на другой рейд.")
        membership.ready = True
        await db.flush()
        return await get_snapshot(db, lobby.id)

    lobby = await active_lobby_for_group(db, group_id) if group_id is not None else None
    if lobby is None:
        lobby = RaidLobby(
            group_id=group_id, raid_id=raid_id, leader_character_id=character.id, status="waiting",
        )
        db.add(lobby)
        await db.flush()
    elif lobby.raid_id != raid_id:
        raise RaidError("Твоя группа уже выбрала другой рейд — сначала разберитесь с ним.")

    db.add(RaidLobbyMember(lobby_id=lobby.id, character_id=character.id, ready=True))
    await db.flush()
    snapshot = await get_snapshot(db, lobby.id)
    assert snapshot is not None
    return snapshot


async def cancel_readiness(db: AsyncSession, character_id: int) -> LobbySnapshot | None:
    """«Отменить готовность» — персонаж остаётся в лобби (счётчик
    уменьшается), но не выходит из него совсем. None — не было в лобби."""
    membership = await get_membership(db, character_id)
    if membership is None:
        return None
    lobby = await lock_lobby(db, membership.lobby_id)
    if lobby is None or lobby.status != "waiting":
        return None
    membership.ready = False
    await db.flush()
    return await get_snapshot(db, membership.lobby_id)


async def leave_lobby_if_present(db: AsyncSession, character_id: int) -> LobbySnapshot | None:
    """Полный выход из лобби (вышел из группы / ушёл с клетки Монолита) —
    знаменатель уменьшается (была 4/5 → 4/4, см. текст патча). Пустое
    лобби (последний ушёл) распускается целиком. None — не было в лобби."""
    membership = await get_membership(db, character_id)
    if membership is None:
        return None
    lobby_id = membership.lobby_id
    lobby = await lock_lobby(db, lobby_id)
    await db.delete(membership)
    await db.flush()
    remaining = (
        await db.scalars(select(RaidLobbyMember).where(RaidLobbyMember.lobby_id == lobby_id))
    ).all()
    if not remaining:
        lobby = await db.get(RaidLobby, lobby_id)
        if lobby is not None:
            await db.delete(lobby)
            await db.flush()
        return None
    if lobby is not None and lobby.leader_character_id == character_id:
        lobby.leader_character_id = min(remaining, key=lambda m: m.id).character_id
        await db.flush()
    return await get_snapshot(db, lobby_id)


def is_ready_to_start(snapshot: LobbySnapshot) -> bool:
    """Все члены денаминатора готовы — денаминатор берётся из фактического
    размера группы (или 1 для соло), см. get_snapshot."""
    if snapshot.status != "waiting" or not snapshot.members:
        return False
    if len(snapshot.members) < snapshot.denominator:
        return False
    return all(ready for _, ready in snapshot.members)


async def lock_lobby(db: AsyncSession, lobby_id: int) -> RaidLobby | None:
    lobby = await db.get(RaidLobby, lobby_id)
    if lobby is None:
        return None
    if lobby.group_id is not None:
        await db.scalar(select(Group).where(Group.id == lobby.group_id).with_for_update())
    return await db.scalar(
        select(RaidLobby).where(RaidLobby.id == lobby_id).with_for_update()
        .execution_options(populate_existing=True)
    )


async def record_run(db: AsyncSession, snapshot: LobbySnapshot) -> RaidRun:
    run = RaidRun(leader_character_id=snapshot.leader_character_id, raid_id=snapshot.raid_id,
                  members=[c.id for c, _ in snapshot.members], status="active")
    db.add(run)
    await db.flush()
    return run


async def finish_run(db: AsyncSession, run_id: int | None) -> None:
    if run_id is not None:
        await db.execute(update(RaidRun).where(RaidRun.id == run_id, RaidRun.status == "active")
                         .values(status="finished"))


async def recover_interrupted(db: AsyncSession, run_id: int | None = None) -> list[int]:
    """Startup only (or failed start). Refund and receipt status commit together.

    Compensation may exceed the normal drop cap: never discard a paid key.
    Already awarded stage loot is deliberately retained.
    """
    query = select(RaidRun).where(RaidRun.status == "active").order_by(RaidRun.id).with_for_update()
    if run_id is not None:
        query = query.where(RaidRun.id == run_id)
    affected = []
    for run in (await db.scalars(query)).all():
        await db.execute(update(Character).where(Character.id == run.leader_character_id)
                         .values(raid_keys=Character.raid_keys + 1))
        for cid in run.members:
            character = await db.get(Character, cid)
            if character is not None:
                character.screen = None
                affected.append(cid)
        run.status = "interrupted"
    await db.flush()
    return affected


async def start_lobby(db: AsyncSession, lobby_id: int) -> None:
    """Помечает лобби started — вызывается ПОСЛЕ успешной проверки/списания
    ключа (см. bot/handlers/raid.py), непосредственно перед запуском боя.
    Строки лобби здесь НЕ удаляются — bot-слой уже прочитал снапшот
    участников для старта боя; удаление — отдельным вызовом
    dissolve_lobby после того, как участники переданы в raid_combat."""
    lobby = await db.get(RaidLobby, lobby_id)
    if lobby is not None:
        lobby.status = "started"
        await db.flush()


async def dissolve_lobby(db: AsyncSession, lobby_id: int) -> None:
    """Удаляет лобби и всех его участников — вызывается либо сразу после
    успешного старта боя (участники переданы в raid_combat, персистентная
    запись лобби больше не нужна), либо при отказе (нет ключа)."""
    rows = (
        await db.scalars(select(RaidLobbyMember).where(RaidLobbyMember.lobby_id == lobby_id))
    ).all()
    for row in rows:
        await db.delete(row)
    await db.flush()  # delete children before the parent's ON DELETE CASCADE
    lobby = await db.get(RaidLobby, lobby_id)
    if lobby is not None:
        await db.delete(lobby)
    await db.flush()


async def consume_key_and_start(
    db: AsyncSession, leader: Character,
) -> bool:
    """Ключ проверяется и списывается у ЛИДЕРА в момент старта, когда все
    собрались — сгорает ВСЕГДА, независимо от исхода рейда (списывается
    здесь же, до самого боя, а не по итогу). False — ключа нет, лобби не
    стартует (вызывающий обязан распустить лобби и уведомить лидера)."""
    if leader.raid_keys <= 0:
        return False
    leader.raid_keys -= 1
    await db.flush()
    return True
