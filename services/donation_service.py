"""Учёт донатов (2026-10-16): кто и сколько задонатил - для выдачи после
вайпа. Покупки через ЮKassa пишутся сами (payment_service.apply_status),
остальное админ вносит вручную во вкладке «Донаты» админки. Каждая запись
попадает и в журнал админки."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Character, Donation, User
from services import admin_service


class DonationError(Exception):
    pass


async def _vk_name(db: AsyncSession, vk_id: int | None) -> str | None:
    if vk_id is None:
        return None
    user = await db.scalar(select(User).where(User.vk_id == vk_id))
    if user is None:
        return None
    name = " ".join(p for p in (user.vk_first_name, user.vk_last_name) if p)
    return name or None


async def _character_of(db: AsyncSession, vk_id: int | None) -> Character | None:
    if vk_id is None:
        return None
    return await db.scalar(
        select(Character).join(User, User.id == Character.user_id).where(User.vk_id == vk_id)
    )


async def record_payment(
    db: AsyncSession, vk_id: int, character_id: int | None, rub: int, gems: int, payment_id: str,
) -> Donation | None:
    """Оплата ЮKassa подтверждена - запись в учёт (повторно - ничего)."""
    if await db.scalar(select(Donation.id).where(Donation.payment_id == payment_id)) is not None:
        return None
    character = await db.get(Character, character_id) if character_id else await _character_of(db, vk_id)
    donor = await _vk_name(db, vk_id) or (character.name if character else f"vk {vk_id}")
    row = Donation(
        vk_id=vk_id, donor=donor, character_name=character.name if character else None,
        amount_rub=rub, gems=gems, source="yookassa", payment_id=payment_id,
    )
    db.add(row)
    await db.flush()
    await admin_service.log_action(
        db, vk_id, "donation", character.id if character else None,
        new_value={"rub": rub, "gems": gems, "donor": donor, "source": "yookassa"},
    )
    return row


async def add_manual(
    db: AsyncSession, admin_vk_id: int, donor, amount, vk_id=None, note=None,
) -> Donation:
    """Донат, принятый мимо ЮKassa: имя, сумма в рублях, по желанию vk_id и заметка."""
    donor = donor.strip() if isinstance(donor, str) else ""
    if not 1 <= len(donor) <= 160:
        raise DonationError("Укажи, кто задонатил.")
    if not isinstance(amount, int) or isinstance(amount, bool) or not 1 <= amount <= 10_000_000:
        raise DonationError("Сумма - целое число рублей больше нуля.")
    if vk_id is not None and (not isinstance(vk_id, int) or isinstance(vk_id, bool) or vk_id <= 0):
        raise DonationError("vk id - положительное число.")
    note = note.strip()[:256] if isinstance(note, str) and note.strip() else None
    character = await _character_of(db, vk_id)
    row = Donation(
        vk_id=vk_id, donor=donor, character_name=character.name if character else None,
        amount_rub=amount, source="manual", note=note, added_by=admin_vk_id,
    )
    db.add(row)
    await db.flush()
    await admin_service.log_action(
        db, admin_vk_id, "donation_manual", character.id if character else None,
        new_value={"rub": amount, "donor": donor}, note=note,
    )
    return row


async def delete_manual(db: AsyncSession, admin_vk_id: int, donation_id) -> Donation:
    """Удалить ошибочно внесённую вручную запись. Записи ЮKassa не удаляются."""
    row = await db.get(Donation, donation_id) if isinstance(donation_id, int) else None
    if row is None:
        raise DonationError("Записи нет.")
    if row.source != "manual":
        raise DonationError("Оплаты ЮКассы из учёта не удаляются.")
    await db.delete(row)
    await admin_service.log_action(
        db, admin_vk_id, "donation_deleted", None,
        old_value={"rub": row.amount_rub, "donor": row.donor},
    )
    await db.flush()
    return row


@dataclass
class DonorTotal:
    key: str
    donor: str
    vk_id: int | None
    character_name: str | None
    total_rub: int
    count: int


async def ledger(db: AsyncSession) -> tuple[list[Donation], list[DonorTotal]]:
    """Все записи (новые сверху) и итог по каждому донатеру (по vk_id, без
    него - по имени), по убыванию суммы."""
    rows = list((await db.scalars(select(Donation).order_by(Donation.created_at.desc(), Donation.id.desc()))).all())
    totals: dict[str, DonorTotal] = {}
    for r in reversed(rows):  # от старых к новым: имя и персонаж - самые свежие
        key = f"vk{r.vk_id}" if r.vk_id else f"name:{r.donor.lower()}"
        t = totals.get(key)
        if t is None:
            t = totals[key] = DonorTotal(key, r.donor, r.vk_id, r.character_name, 0, 0)
        t.total_rub += r.amount_rub
        t.count += 1
        t.donor = r.donor
        t.character_name = r.character_name or t.character_name
    return rows, sorted(totals.values(), key=lambda t: -t.total_rub)
