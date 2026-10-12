"""Полное обнуление персонажа: игрок начинает заново (онбординг с нуля).

Используется админ-панелью мини-аппа (bot/miniapp_admin_api.py, действие
«reset_character») и скриптом scripts/delete_character.py - один код на оба
пути, чтобы они не разошлись.

Запись users (vk_id) остаётся: следующее сообщение игрока автоматически
запускает онбординг (bot/handlers/fallback.py), как после вайпа.

Не полагаемся на ON DELETE CASCADE: зависимые строки удаляются ЯВНО, поэтому
результат одинаков на PostgreSQL и на SQLite без включённых внешних ключей.
  - CASCADE и NO ACTION (combat_participants, exchange_orders) - строки удаляются;
  - SET NULL (журналы админки, переводы, гильдейские поля) - обнуляются: аудит
    переживает удаление, как и при вайпе;
  - предметы из инвентаря удаляются целиком, история апгрейдов остаётся.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

import models  # noqa: F401  (регистрирует все таблицы в Base.metadata)
from game.economy import guild_config as gc
from models import Base, Character, GuildMember, Inventory, Item, User, Wallet
from services import admin_service


class ResetBlocked(Exception):
    """Обнулять нельзя. code - машинный код для API, message - текст админу."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Ref:
    table_name: str
    column_name: str
    ondelete: str | None
    table: object
    column: object


@dataclass
class Summary:
    character_id: int
    name: str
    vk_id: int | None
    level: int
    farm_currency: int
    donate_currency: int
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def character_refs() -> list[Ref]:
    """Все внешние ключи на characters.id по метаданным моделей."""
    refs: list[Ref] = []
    for table in Base.metadata.sorted_tables:
        if table.name == "characters":
            continue
        for fk in table.foreign_keys:
            if fk.column.table.name == "characters" and fk.column.name == "id":
                refs.append(Ref(
                    table_name=table.name, column_name=fk.parent.name,
                    ondelete=(fk.ondelete or "").upper() or None,
                    table=table, column=fk.parent,
                ))
    return refs


async def find_by_name(db: AsyncSession, name: str) -> list[Character]:
    # Регистр сравниваем в Python, а не SQL-функцией lower(): SQLite понижает
    # регистр только у латиницы, и кириллица не находилась бы без учёта регистра.
    wanted = name.strip().casefold()
    rows = (await db.execute(select(Character.id, Character.name))).all()
    ids = [cid for cid, cname in rows if cname.strip().casefold() == wanted]
    if not ids:
        return []
    return list(await db.scalars(select(Character).where(Character.id.in_(ids))))


async def summarize(db: AsyncSession, character_id: int) -> Summary:
    character = await db.get(Character, character_id)
    if character is None:
        raise LookupError(f"Персонаж {character_id} не найден")
    user = await db.get(User, character.user_id)
    wallet = await db.get(Wallet, character_id)
    summary = Summary(
        character_id=character_id, name=character.name,
        vk_id=user.vk_id if user is not None else None, level=character.level,
        farm_currency=wallet.farm_currency if wallet is not None else 0,
        donate_currency=wallet.donate_currency if wallet is not None else 0,
    )
    for ref in character_refs():
        n = await db.scalar(select(func.count()).select_from(ref.table).where(ref.column == character_id))
        if n:
            summary.counts[f"{ref.table_name}.{ref.column_name} [{ref.ondelete or 'NO ACTION'}]"] = n
    if any(key.startswith("combat_participants.") for key in summary.counts):
        summary.warnings.append("Игрок числится в бою: перед удалением дождитесь конца боя.")
    for key in summary.counts:
        if key.startswith("raid_lobbies.leader_character_id"):
            summary.warnings.append("Игрок - лидер лобби рейда: лобби удалится вместе с ним.")
    if summary.donate_currency:
        summary.warnings.append(f"На счету донатной валюты: {summary.donate_currency}. Она пропадёт.")
    return summary


async def purge(db: AsyncSession, character_id: int) -> dict[str, int]:
    """Удаляет персонажа и всё его. Коммит делает вызывающий."""
    removed: dict[str, int] = {}
    item_ids = list(await db.scalars(select(Inventory.item_id).where(Inventory.character_id == character_id)))

    for ref in character_refs():
        if ref.ondelete == "SET NULL":
            result = await db.execute(
                update(ref.table).where(ref.column == character_id).values({ref.column_name: None})
            )
        else:
            result = await db.execute(delete(ref.table).where(ref.column == character_id))
        if result.rowcount:
            removed[f"{ref.table_name}.{ref.column_name}"] = result.rowcount

    if item_ids:
        # Записи о предметах, которые на них ссылаются без каскада (история
        # апгрейдов), обнуляются, а не удаляются.
        for table in Base.metadata.sorted_tables:
            for fk in table.foreign_keys:
                if fk.column.table.name == "items" and fk.column.name == "id" and table.name != "inventory":
                    if (fk.ondelete or "").upper() == "SET NULL":
                        await db.execute(
                            update(table).where(fk.parent.in_(item_ids)).values({fk.parent.name: None})
                        )
                    else:
                        await db.execute(delete(table).where(fk.parent.in_(item_ids)))
        result = await db.execute(delete(Item).where(Item.id.in_(item_ids)))
        removed["items"] = result.rowcount

    result = await db.execute(delete(Character).where(Character.id == character_id))
    removed["characters"] = result.rowcount
    await db.flush()
    return removed


async def reset_character(db: AsyncSession, admin_vk_id: int, character_id: int) -> dict:
    """Обнуляет персонажа с записью в журнал админ-действий. Коммит - у вызывающего.

    ResetBlocked - нельзя обнулять (глава гильдии: гильдия осталась бы без
    главы). Активности (бой, путь) снимает вызывающий ДО этого вызова: сервисный
    слой не знает про память бота (см. докстринг admin_service)."""
    summary = await summarize(db, character_id)
    member = await db.scalar(select(GuildMember).where(GuildMember.character_id == character_id))
    if member is not None and member.rank == gc.RANK_LEADER:
        raise ResetBlocked(
            "guild_leader",
            "Игрок - глава гильдии. Сначала передайте главу другому или распустите гильдию.",
        )
    # Журнал пишем ДО удаления: после него target_character_id обнулится (SET NULL),
    # а имя и vk_id сохранятся в самой записи.
    await admin_service.log_action(
        db, admin_vk_id, "reset_character", character_id,
        old_value={
            "name": summary.name, "vk_id": summary.vk_id, "level": summary.level,
            "farm_currency": summary.farm_currency, "donate_currency": summary.donate_currency,
        },
        note=f"Персонаж {summary.name!r} обнулён, vk_id {summary.vk_id} начнёт заново",
    )
    removed = await purge(db, character_id)
    return {
        "name": summary.name, "vk_id": summary.vk_id, "level": summary.level,
        "donate_currency": summary.donate_currency, "removed": removed,
    }
