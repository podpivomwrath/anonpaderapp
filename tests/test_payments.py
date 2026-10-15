"""Самоцветы за рубли через ЮKassa (services/payment_service.py, 2026-10-15)."""

from types import SimpleNamespace

import pytest

from services import payment_service, wallet_service


def _settings(enabled=True):
    return SimpleNamespace(
        yookassa_shop_id="1" if enabled else "", yookassa_secret_key="k" if enabled else "",
    )


async def _create(db, character, monkeypatch, pack="handful"):
    sent = {}

    async def fake_post(settings, body, idempotence_key):
        sent["body"] = body
        return {"id": "yk-1", "status": "pending", "confirmation": {"confirmation_url": "https://pay/1"}}

    monkeypatch.setattr(payment_service, "_yk_post", fake_post)
    url = await payment_service.create_payment(db, _settings(), character, 555, pack, "https://back")
    return url, sent["body"]


async def test_create_payment_uses_pack_price(db_session, make_character, monkeypatch):
    c = await make_character()
    url, body = await _create(db_session, c, monkeypatch, "pouch")
    assert url == "https://pay/1"
    assert body["amount"] == {"value": "300.00", "currency": "RUB"}
    assert body["confirmation"]["return_url"] == "https://back"


async def test_unknown_pack_and_disabled(db_session, make_character):
    c = await make_character()
    with pytest.raises(payment_service.PaymentError):
        await payment_service.create_payment(db_session, _settings(False), c, 1, "handful", "x")
    with pytest.raises(payment_service.PaymentError):
        await payment_service.create_payment(db_session, _settings(), c, 1, "nope", "x")


async def test_success_credits_once(db_session, make_character, monkeypatch):
    c = await make_character(donate=10)
    await _create(db_session, c, monkeypatch)
    paid = {"id": "yk-1", "status": "succeeded", "paid": True, "amount": {"value": "100.00", "currency": "RUB"}}
    first = await payment_service.apply_status(db_session, paid)
    second = await payment_service.apply_status(db_session, paid)
    assert first is not None and first.gems == 100 and second is None
    assert (await wallet_service.get_wallet(db_session, c.id)).donate_currency == 110


async def test_wrong_amount_or_pending_not_credited(db_session, make_character, monkeypatch):
    c = await make_character(donate=0)
    await _create(db_session, c, monkeypatch)
    assert await payment_service.apply_status(db_session, {"id": "yk-1", "status": "pending", "paid": False}) is None
    bad = {"id": "yk-1", "status": "succeeded", "paid": True, "amount": {"value": "1.00", "currency": "RUB"}}
    assert await payment_service.apply_status(db_session, bad) is None
    assert (await wallet_service.get_wallet(db_session, c.id)).donate_currency == 0


async def test_notification_rechecks_with_api(db_session, make_character, monkeypatch):
    c = await make_character(donate=0)
    await _create(db_session, c, monkeypatch)

    async def fake_get(settings, payment_id):
        # Тело уведомления говорит «оплачено», а ЮKassa - нет: верим ЮKassa.
        return {"id": payment_id, "status": "canceled", "paid": False}

    monkeypatch.setattr(payment_service, "_yk_get", fake_get)
    body = {"event": "payment.succeeded", "object": {"id": "yk-1", "status": "succeeded", "paid": True}}
    assert await payment_service.process_notification(db_session, _settings(), body) is None
    assert (await wallet_service.get_wallet(db_session, c.id)).donate_currency == 0
