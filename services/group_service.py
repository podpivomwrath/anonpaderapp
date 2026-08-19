"""Группы (патч 51, ч.2): создание/приглашение/лидерство/лимиты.

Группа создаётся автоматически при ПРИНЯТИИ первого приглашения (не при
отправке) — см. GroupInvite.group_id (nullable, models/group.py). До этого
момента у будущего лидера ещё нет группы, но он уже ведёт себя как лидер
(только он может слать приглашения). Лидер — тот, кто пригласил первого
участника; при его выходе лидерство переходит следующему по joined_at.

GroupError — игроко-читаемая причина отказа, текст исключения показывается
как есть в чат (тот же паттерн, что PresetValidationError в preset_service).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import group_config as gc
from models import Character, Group, GroupInvite, GroupMember


class GroupError(Exception):
    pass


def _aware(dt: datetime) -> datetime:
    """SQLite (тестовая БД) не хранит смещение у DateTime(timezone=True) —
    при перечитывании объекта из идентити-мапа по слабой ссылке (после сборки
    мусора) значение может вернуться наивным. Postgres (прод, TIMESTAMPTZ)
    всегда отдаёт aware — здесь просто страховка для комфортных тестов."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


@dataclass
class GroupSnapshot:
    id: int
    leader_character_id: int
    members: list[Character]  # упорядочены по joined_at (порядок вступления)


async def get_membership(db: AsyncSession, character_id: int) -> GroupMember | None:
    return await db.scalar(select(GroupMember).where(GroupMember.character_id == character_id))


async def get_group_snapshot(db: AsyncSession, character_id: int) -> GroupSnapshot | None:
    """None — персонаж не в группе."""
    membership = await get_membership(db, character_id)
    if membership is None:
        return None
    group = await db.get(Group, membership.group_id)
    rows = (
        await db.execute(
            select(GroupMember, Character)
            .join(Character, Character.id == GroupMember.character_id)
            .where(GroupMember.group_id == group.id)
            .order_by(GroupMember.joined_at)
        )
    ).all()
    return GroupSnapshot(
        id=group.id, leader_character_id=group.leader_character_id,
        members=[character for _, character in rows],
    )


async def find_character_by_name(db: AsyncSession, nickname: str) -> Character | None:
    return await db.scalar(
        select(Character).where(func.lower(Character.name) == nickname.strip().lower())
    )


def level_gap(levels: list[int]) -> int:
    if not levels:
        return 0
    return max(levels) - min(levels)


# --- Приглашения ---


async def _active_invite_to(db: AsyncSession, to_character_id: int) -> GroupInvite | None:
    """Единственное активное (pending, не истёкшее) приглашение адресату, если
    есть — от кого бы оно ни было. Просроченные лениво помечаются 'expired'."""
    now = datetime.now(timezone.utc)
    invite = await db.scalar(
        select(GroupInvite)
        .where(GroupInvite.to_character_id == to_character_id, GroupInvite.status == "pending")
        .order_by(GroupInvite.created_at.desc())
    )
    if invite is None:
        return None
    if _aware(invite.expires_at) <= now:
        invite.status = "expired"
        await db.flush()
        return None
    return invite


async def send_invite(db: AsyncSession, inviter: Character, target: Character) -> GroupInvite:
    if target.id == inviter.id:
        raise GroupError("Нельзя пригласить самого себя.")

    inviter_membership = await get_membership(db, inviter.id)
    current_levels = [inviter.level]
    if inviter_membership is not None:
        group = await db.get(Group, inviter_membership.group_id)
        if group.leader_character_id != inviter.id:
            raise GroupError("Приглашать может только лидер группы.")
        snapshot = await get_group_snapshot(db, inviter.id)
        if len(snapshot.members) >= gc.GROUP_MAX_SIZE:
            raise GroupError(f"Группа уже полная (максимум {gc.GROUP_MAX_SIZE} игроков).")
        current_levels = [m.level for m in snapshot.members]

    target_membership = await get_membership(db, target.id)
    if target_membership is not None:
        raise GroupError(f"{target.name} уже состоит в группе.")

    if await _active_invite_to(db, target.id) is not None:
        raise GroupError(f"{target.name} уже рассматривает другое приглашение.")

    gap = level_gap(current_levels + [target.level])
    if gap > gc.GROUP_MAX_LEVEL_GAP:
        raise GroupError(
            f"Разрыв уровней станет {gap} (максимум {gc.GROUP_MAX_LEVEL_GAP}) — приглашение не отправлено."
        )

    now = datetime.now(timezone.utc)
    invite = GroupInvite(
        group_id=inviter_membership.group_id if inviter_membership is not None else None,
        from_character_id=inviter.id,
        to_character_id=target.id,
        expires_at=now + timedelta(seconds=gc.INVITE_TTL_SECONDS),
        status="pending",
    )
    db.add(invite)
    await db.flush()
    return invite


_STATUS_TEXT = {
    "accepted": "Это приглашение уже принято.",
    "declined": "Это приглашение уже отклонено.",
    "expired": "Это приглашение истекло.",
}


@dataclass
class InviteAcceptResult:
    group: GroupSnapshot
    newly_created: bool


async def accept_invite(db: AsyncSession, invite_id: int, character_id: int) -> InviteAcceptResult:
    invite = await db.get(GroupInvite, invite_id)
    if invite is None or invite.to_character_id != character_id:
        raise GroupError("Приглашение не найдено.")
    if invite.status != "pending":
        raise GroupError(_STATUS_TEXT.get(invite.status, "Это приглашение больше не действует."))
    now = datetime.now(timezone.utc)
    if _aware(invite.expires_at) <= now:
        invite.status = "expired"
        await db.flush()
        raise GroupError("Приглашение истекло.")

    # Повторная проверка — состояние могло измениться за минуту ожидания.
    if await get_membership(db, character_id) is not None:
        invite.status = "declined"
        await db.flush()
        raise GroupError("Ты уже в другой группе.")

    newly_created = False
    if invite.group_id is None:
        if await get_membership(db, invite.from_character_id) is not None:
            invite.status = "declined"
            await db.flush()
            raise GroupError("Это приглашение больше не действует.")
        group = Group(leader_character_id=invite.from_character_id)
        db.add(group)
        await db.flush()
        db.add(
            GroupMember(
                group_id=group.id, character_id=invite.from_character_id, joined_at=invite.created_at,
            )
        )
        invite.group_id = group.id
        newly_created = True
    else:
        group = await db.get(Group, invite.group_id)
        if group is None:
            invite.status = "declined"
            await db.flush()
            raise GroupError("Группа уже не существует.")
        existing = (
            await db.scalars(select(GroupMember).where(GroupMember.group_id == group.id))
        ).all()
        if len(existing) >= gc.GROUP_MAX_SIZE:
            invite.status = "declined"
            await db.flush()
            raise GroupError("Группа уже полная.")

    db.add(GroupMember(group_id=invite.group_id, character_id=character_id))
    invite.status = "accepted"
    await db.flush()
    snapshot = await get_group_snapshot(db, character_id)
    return InviteAcceptResult(group=snapshot, newly_created=newly_created)


async def decline_invite(db: AsyncSession, invite_id: int, character_id: int) -> None:
    invite = await db.get(GroupInvite, invite_id)
    if invite is None or invite.to_character_id != character_id:
        raise GroupError("Приглашение не найдено.")
    if invite.status != "pending":
        raise GroupError(_STATUS_TEXT.get(invite.status, "Это приглашение больше не действует."))
    invite.status = "declined"
    await db.flush()


# --- Выход / исключение ---


@dataclass
class LeaveResult:
    dissolved: bool
    new_leader_character_id: int | None  # заполнено, только если лидерство ПЕРЕШЛО
    remaining_member_character_ids: list[int]


async def _remove_member(db: AsyncSession, group: Group, character_id: int, was_leader: bool) -> LeaveResult:
    remaining = (
        await db.scalars(
            select(GroupMember)
            .where(GroupMember.group_id == group.id, GroupMember.character_id != character_id)
            .order_by(GroupMember.joined_at)
        )
    ).all()
    if not remaining:
        await db.delete(group)
        await db.flush()
        return LeaveResult(dissolved=True, new_leader_character_id=None, remaining_member_character_ids=[])
    new_leader_id = None
    if was_leader:
        new_leader_id = remaining[0].character_id
        group.leader_character_id = new_leader_id
    await db.flush()
    return LeaveResult(
        dissolved=False, new_leader_character_id=new_leader_id,
        remaining_member_character_ids=[m.character_id for m in remaining],
    )


async def leave_group(db: AsyncSession, character_id: int) -> LeaveResult:
    membership = await get_membership(db, character_id)
    if membership is None:
        raise GroupError("Ты не в группе.")
    group = await db.get(Group, membership.group_id)
    was_leader = group.leader_character_id == character_id
    await db.delete(membership)
    await db.flush()
    return await _remove_member(db, group, character_id, was_leader)


async def kick_member(db: AsyncSession, leader: Character, target_character_id: int) -> LeaveResult:
    membership = await get_membership(db, leader.id)
    if membership is None:
        raise GroupError("Ты не в группе.")
    group = await db.get(Group, membership.group_id)
    if group.leader_character_id != leader.id:
        raise GroupError("Исключать может только лидер.")
    if target_character_id == leader.id:
        raise GroupError("Нельзя исключить самого себя — используй /выйти.")
    target_membership = await db.scalar(
        select(GroupMember).where(
            GroupMember.group_id == group.id, GroupMember.character_id == target_character_id,
        )
    )
    if target_membership is None:
        raise GroupError("Этого игрока нет в твоей группе.")
    await db.delete(target_membership)
    await db.flush()
    return await _remove_member(db, group, target_character_id, was_leader=False)


# --- Разрыв уровней при левелапе ---


@dataclass
class LevelGapKick:
    kicked_character_id: int
    kicked_name: str
    dissolved: bool
    new_leader_character_id: int | None
    remaining_member_character_ids: list[int]


async def enforce_level_gap(db: AsyncSession, character: Character) -> LevelGapKick | None:
    """Вызывается ПОСЛЕ левелапа (levels_gained > 0), ДО commit — если разрыв
    уровней в группе персонажа превысил лимит, исключается ИМЕННО тот, кто
    только что повысил уровень (не остальные участники). None — исключение
    не потребовалось (не в группе, или разрыв в пределах нормы)."""
    membership = await get_membership(db, character.id)
    if membership is None:
        return None
    snapshot = await get_group_snapshot(db, character.id)
    if snapshot is None or len(snapshot.members) < 2:
        return None
    if level_gap([m.level for m in snapshot.members]) <= gc.GROUP_MAX_LEVEL_GAP:
        return None
    leave = await leave_group(db, character.id)
    return LevelGapKick(
        kicked_character_id=character.id, kicked_name=character.name,
        dissolved=leave.dissolved, new_leader_character_id=leave.new_leader_character_id,
        remaining_member_character_ids=leave.remaining_member_character_ids,
    )
