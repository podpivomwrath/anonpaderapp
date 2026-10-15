"""Покупка самоцветов за рубли через ЮKassa (2026-10-15).

Поток:
1. create_payment - строка GemPayment и платёж в ЮKassa (API v3) с
   переадресацией на её страницу оплаты; в ответ ссылка для игрока.
2. ЮKassa присылает уведомление на /api/yookassa/notify. Телу уведомления
   не верим: process_notification сам запрашивает платёж у ЮKassa по id и
   смотрит его настоящий статус.
3. Оплата подтверждена - самоцветы начисляются ровно один раз (credited под
   блокировкой строки), повторные уведомления ничего не меняют.

Чек самозанятого («Мой налог») ЮKassa формирует сама по описанию платежа.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import aiohttp
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from game.economy import gem_packs
from models import Character, GemPayment
from services import wallet_service

API = "https://api.yookassa.ru/v3/payments"


class PaymentError(Exception):
    pass


def enabled(settings: Settings) -> bool:
    return bool(settings.yookassa_shop_id and settings.yookassa_secret_key)


def _auth(settings: Settings) -> aiohttp.BasicAuth:
    return aiohttp.BasicAuth(settings.yookassa_shop_id, settings.yookassa_secret_key)


async def _yk_post(settings: Settings, body: dict, idempotence_key: str) -> dict:
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, auth=_auth(settings)) as http:
        async with http.post(API, json=body, headers={"Idempotence-Key": idempotence_key}) as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 300:
                raise PaymentError(f"YooKassa {resp.status}: {data}")
            return data


async def _yk_get(settings: Settings, payment_id: str) -> dict:
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, auth=_auth(settings)) as http:
        async with http.get(f"{API}/{payment_id}") as resp:
            data = await resp.json(content_type=None)
            if resp.status >= 300:
                raise PaymentError(f"YooKassa {resp.status}: {data}")
            return data


async def create_payment(
    db: AsyncSession, settings: Settings, character: Character, vk_id: int, pack_id: str, return_url: str,
) -> str:
    """Новый платёж; возвращает ссылку на оплату."""
    if not enabled(settings):
        raise PaymentError("Оплата пока не подключена.")
    pack = gem_packs.BY_ID.get(pack_id)
    if pack is None:
        raise PaymentError("Такого пакета нет.")
    row = GemPayment(
        character_id=character.id, vk_id=vk_id, pack_id=pack.id, gems=pack.gems, amount_rub=pack.rub,
        status="pending",
    )
    db.add(row)
    await db.flush()
    body = {
        "amount": {"value": f"{pack.rub}.00", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": f"Пепельные самоцветы: {pack.name} ({pack.gems} шт.) - {character.name}",
        "metadata": {"payment_row": str(row.id), "character_id": str(character.id), "vk_id": str(vk_id)},
    }
    data = await _yk_post(settings, body, idempotence_key=f"gem-{row.id}-{uuid.uuid4()}")
    row.yk_payment_id = data["id"]
    await db.flush()
    url = (data.get("confirmation") or {}).get("confirmation_url")
    if not url:
        raise PaymentError("Платёжный сервис не дал ссылку на оплату.")
    return url


@dataclass
class Credited:
    vk_id: int
    gems: int
    pack_name: str


async def apply_status(db: AsyncSession, payment: dict) -> Credited | None:
    """Применить проверенный ответ ЮKassa о платеже. Credited - если
    самоцветы начислены именно сейчас."""
    row = await db.scalar(
        select(GemPayment).where(GemPayment.yk_payment_id == payment.get("id")).with_for_update()
    )
    if row is None:
        logger.warning("YooKassa: неизвестный платёж {}", payment.get("id"))
        return None
    status = payment.get("status")
    if status == "canceled" and row.status == "pending":
        row.status = "canceled"
        await db.flush()
        return None
    if status != "succeeded" or not payment.get("paid"):
        return None
    amount = payment.get("amount") or {}
    if amount.get("currency") != "RUB" or round(float(amount.get("value", 0))) != row.amount_rub:
        logger.error("YooKassa: сумма платежа {} не совпала: {}", row.id, amount)
        return None
    row.status = "succeeded"
    if row.credited or row.character_id is None:
        await db.flush()
        return None
    await wallet_service.deposit(db, row.character_id, "donate", row.gems, taxable=False)
    row.credited = True
    row.paid_at = datetime.now(timezone.utc)
    await db.flush()
    # Учёт донатов (2026-10-16): кто и сколько - для выдачи после вайпа.
    from services import donation_service

    await donation_service.record_payment(
        db, row.vk_id, row.character_id, row.amount_rub, row.gems, str(row.yk_payment_id),
    )
    logger.info("YooKassa: платёж {} - начислено {} самоцветов персонажу {}", row.id, row.gems, row.character_id)
    pack = gem_packs.BY_ID.get(row.pack_id)
    return Credited(vk_id=row.vk_id, gems=row.gems, pack_name=pack.name if pack else row.pack_id)


async def process_notification(db: AsyncSession, settings: Settings, body: dict) -> Credited | None:
    """Уведомление ЮKassa: перепроверяем платёж запросом к API."""
    obj = body.get("object") if isinstance(body, dict) else None
    payment_id = obj.get("id") if isinstance(obj, dict) else None
    if not payment_id or not enabled(settings):
        return None
    payment = await _yk_get(settings, payment_id)
    return await apply_status(db, payment)


async def history(db: AsyncSession, character_id: int, limit: int = 20) -> list[GemPayment]:
    return list((await db.scalars(
        select(GemPayment).where(GemPayment.character_id == character_id, GemPayment.status != "pending")
        .order_by(GemPayment.id.desc()).limit(limit)
    )).all())


def packs_payload() -> list[dict]:
    return [{"id": p.id, "name": p.name, "gems": p.gems, "rub": p.rub} for p in gem_packs.PACKS]
