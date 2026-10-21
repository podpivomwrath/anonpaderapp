"""Журнал золота и самоцветов (2026-10-21): жалоба «пропало 20 000 ночью»
разбиралась догадками - журнала не было."""

import ast
from pathlib import Path

from sqlalchemy import select

from models import WalletLog
from services import admin_service, wallet_service

ROOT = Path(__file__).resolve().parent.parent


async def _log(db, cid):
    return (await db.scalars(select(WalletLog).where(WalletLog.character_id == cid).order_by(WalletLog.id))).all()


async def test_charge_and_deposit_are_logged_with_caller(db_session, make_character) -> None:
    c = await make_character(farm=1000)
    await wallet_service.charge(db_session, c.id, "farm", 300)
    await wallet_service.deposit(db_session, c.id, "donate", 50, reason="promo_service._apply_reward")
    rows = await _log(db_session, c.id)
    assert [(r.currency, r.delta, r.balance) for r in rows] == [("farm", -300, 700), ("donate", 50, 50)]
    # Причина по умолчанию - откуда позвали (здесь - сам тест).
    assert rows[0].reason == "test_wallet_log.test_charge_and_deposit_are_logged_with_caller"
    assert rows[1].reason == "promo_service._apply_reward"
    journal = await admin_service.wallet_journal(db_session, c.id)
    assert journal[0]["reason"] == "Промокод" and journal[0]["delta"] == 50  # новые сверху


async def test_keeps_only_last_twenty(db_session, make_character) -> None:
    c = await make_character(farm=0)
    for i in range(25):
        await wallet_service.deposit(db_session, c.id, "farm", i + 1)
    rows = await _log(db_session, c.id)
    assert len(rows) == wallet_service.WALLET_LOG_KEEP == 20
    assert rows[0].delta == 6 and rows[-1].delta == 25


def test_every_money_call_has_a_russian_reason() -> None:
    """Сверка: каждое место, которое списывает или начисляет валюту, подписано
    в журнале админки. Новое место без подписи покажется как «модуль.функция»
    - не беда, но лучше подписать сразу."""
    callers = set()
    for path in list((ROOT / "services").rglob("*.py")) + list((ROOT / "bot").rglob("*.py")) \
            + list((ROOT / "game").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    f = node.func
                    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    if name in ("charge", "deposit") and path.stem != "wallet_service":
                        callers.add(f"{path.stem}.{fn.name}")
    assert len(callers) > 40
    missing = sorted(callers - set(admin_service.WALLET_REASONS))
    assert not missing, f"нет подписи в admin_service.WALLET_REASONS: {missing}"
