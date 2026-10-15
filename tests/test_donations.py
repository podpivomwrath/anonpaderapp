"""Учёт донатов (services/donation_service.py, 2026-10-16)."""

import pytest
from sqlalchemy import select

from models import AdminAction, Donation
from services import donation_service, payment_service
from tests.test_payments import _create


async def test_yookassa_payment_lands_in_ledger_once(db_session, make_character, monkeypatch):
    c = await make_character()
    await _create(db_session, c, monkeypatch)
    paid = {"id": "yk-1", "status": "succeeded", "paid": True, "amount": {"value": "100.00", "currency": "RUB"}}
    await payment_service.apply_status(db_session, paid)
    await payment_service.apply_status(db_session, paid)
    rows = (await db_session.scalars(select(Donation))).all()
    assert len(rows) == 1
    row = rows[0]
    assert (row.vk_id, row.amount_rub, row.gems, row.source, row.payment_id) == (555, 100, 100, "yookassa", "yk-1")
    action = await db_session.scalar(select(AdminAction).where(AdminAction.action_type == "donation"))
    assert action.admin_vk_id == 555 and action.new_value["rub"] == 100


async def test_manual_add_validate_and_delete(db_session, make_character):
    for bad in (("", 100), ("Кто-то", 0), ("Кто-то", "100")):
        with pytest.raises(donation_service.DonationError):
            await donation_service.add_manual(db_session, 1, *bad)
    row = await donation_service.add_manual(db_session, 1, " Вася Пупкин ", 500, None, "перевод на карту")
    assert row.donor == "Вася Пупкин" and row.note == "перевод на карту"
    await donation_service.delete_manual(db_session, 1, row.id)
    assert (await db_session.scalars(select(Donation))).all() == []


async def test_yookassa_entry_cannot_be_deleted(db_session):
    db_session.add(Donation(donor="X", amount_rub=100, source="yookassa", payment_id="p1"))
    await db_session.flush()
    row = await db_session.scalar(select(Donation))
    with pytest.raises(donation_service.DonationError, match="не удаляются"):
        await donation_service.delete_manual(db_session, 1, row.id)


async def test_ledger_totals_by_donor(db_session):
    await donation_service.add_manual(db_session, 1, "Михаил", 5000, 84430623)
    await donation_service.add_manual(db_session, 1, "Михаил С.", 1000, 84430623)
    await donation_service.add_manual(db_session, 1, "Без вк", 300)
    rows, totals = await donation_service.ledger(db_session)
    assert len(rows) == 3
    assert [(t.vk_id, t.total_rub, t.count) for t in totals] == [(84430623, 6000, 2), (None, 300, 1)]
    assert totals[0].donor == "Михаил С."  # последнее имя


def test_journal_text() -> None:
    from services.admin_journal_text import describe

    action = AdminAction(action_type="donation", admin_vk_id=1, new_value={"rub": 500, "gems": 500, "donor": "A"})
    assert "задонатил 500 ₽" in describe(action, None)
