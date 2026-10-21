"""Журнал ресурсов игрока (2026-10-21): руда, рыба, травы, еда, зелья,
реликвии и вещи - что пришло и ушло и откуда. Как журнал золота
(services/wallet_service.log_change), чтобы на «пропала руда» отвечать по
записям, а не по номерам строк в базе (жалоба Тихони_Винни).

Пишется сам: перед каждым сохранением сессии (before_flush) смотрим, у каких
строк этих таблиц поменялось количество. Массовые UPDATE/DELETE мимо сессии
этого не видят - там вызывается add() явно. Хранится KEEP_DAYS дней (cleanup).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, event
from sqlalchemy.orm import Session, attributes

from models import (
    CharacterConsumable,
    CharacterFish,
    CharacterFood,
    CharacterHerb,
    CharacterOre,
    CharacterTrophy,
    Inventory,
    ResourceLog,
)

KEEP_DAYS = 7

#: модель -> (вид, поле количества, как собрать ref)
TRACKED = {
    CharacterOre: ("ore", "count", lambda r: f"{r.ore_id}:{r.grade}"),
    CharacterFish: ("fish", "total_grams", lambda r: f"{r.fish_id}:{r.grade}"),
    CharacterHerb: ("herb", "count", lambda r: r.herb_id),
    CharacterFood: ("food", "count", lambda r: f"{r.dish_id}:{r.grade}"),
    CharacterConsumable: ("elixir", "count", lambda r: r.elixir_id),
    CharacterTrophy: ("trophy", "count", lambda r: r.trophy_id),
}

_SKIP_MODULES = ("services.resource_log", "services.db")


def _frames():
    frame = sys._getframe(2)
    while frame is not None:
        yield frame
        frame = frame.f_back
    # Асинхронная сессия сохраняет в отдельном гринлете: вызвавший код - в родительском.
    try:
        import greenlet

        parent = greenlet.getcurrent().parent
        frame = parent.gr_frame if parent is not None else None
    except Exception:  # noqa: BLE001
        frame = None
    while frame is not None:
        yield frame
        frame = frame.f_back


def origin() -> str:
    """«модуль.функция» - первый код игры по стеку, откуда пришло изменение."""
    for frame in _frames():
        module = frame.f_globals.get("__name__", "")
        if module.startswith(("services.", "bot.", "game.")) and not module.startswith(_SKIP_MODULES):
            return f"{module.rsplit('.', 1)[-1]}.{frame.f_code.co_name}"[:80]
    return "?"


def add(db, character_id: int | None, kind: str, ref: str | None, delta: int, reason: str | None = None) -> None:
    """Явная запись - для массовых UPDATE/DELETE мимо сессии."""
    if not delta or character_id is None:
        return
    db.add(ResourceLog(character_id=character_id, kind=kind, ref=(ref or "")[:80], delta=delta,
                       reason=(reason or origin())[:80]))


def _delta(obj, field: str) -> int:
    hist = attributes.get_history(obj, field)
    new = hist.added[0] if hist.added else None
    old = hist.deleted[0] if hist.deleted else None
    if new is None or old is None:
        return 0
    return int(new or 0) - int(old or 0)


@event.listens_for(Session, "before_flush")
def _collect(session, _flush_context, _instances) -> None:
    rows = []
    for obj in session.new:
        spec = TRACKED.get(type(obj))
        if spec is not None:
            rows.append((obj.character_id, spec[0], spec[2](obj), int(getattr(obj, spec[1]) or 0)))
        elif isinstance(obj, Inventory):
            rows.append((obj.character_id, "item", str(obj.item_id), 1))
    for obj in session.dirty:
        spec = TRACKED.get(type(obj))
        if spec is not None and session.is_modified(obj, include_collections=False):
            rows.append((obj.character_id, spec[0], spec[2](obj), _delta(obj, spec[1])))
    for obj in session.deleted:
        spec = TRACKED.get(type(obj))
        if spec is not None:
            rows.append((obj.character_id, spec[0], spec[2](obj), -int(getattr(obj, spec[1]) or 0)))
        elif isinstance(obj, Inventory):
            rows.append((obj.character_id, "item", str(obj.item_id), -1))
    rows = [r for r in rows if r[3] and r[0] is not None]
    if not rows:
        return
    reason = origin()
    for character_id, kind, ref, delta in rows:
        session.add(ResourceLog(character_id=character_id, kind=kind, ref=ref[:80], delta=delta, reason=reason))


async def cleanup(db) -> int:
    """Старше KEEP_DAYS - удалить (раз в час из main)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    result = await db.execute(delete(ResourceLog).where(ResourceLog.created_at < cutoff))
    return result.rowcount or 0
