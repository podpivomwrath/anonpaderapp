"""Припасы на складе гильдии (2026-10-23, владелец: «складывать все новые
вещи в склад»): травы, рыба, блюда, зелья. Руда и снаряжение - как раньше,
в services/guild_service.py.

Сдать может любой участник, выдать - глава и казначеи (как руду). Место -
своё, того же размера, что у руды, по счёту «штук»: рыба - килограммами с округлением
вверх. Ремесленные инструменты привязаны - на склад не идут.
"""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import cooking, fishing, herbalism
from models import Character, CharacterConsumable, CharacterFish, CharacterFood, CharacterHerb, GuildStock
from services import guild_service
from services.guild_service import GuildError

KINDS = ("herb", "fish", "food", "elixir")
#: Место под припасы - своё, того же размера, что под руду (capacity().ore).

KIND_TITLES = {"herb": "🌿 Травы", "fish": "🐟 Рыба", "food": "🍲 Еда", "elixir": "🧪 Зелья и расходники"}


def _units(kind: str, count: int) -> int:
    """Сколько места занимает: рыба - килограммы вверх, остальное - штуки."""
    return -(-count // 1000) if kind == "fish" else count


async def goods_units(db: AsyncSession, guild_id: int) -> int:
    rows = (await db.execute(
        select(GuildStock.kind, func.sum(GuildStock.count)).where(GuildStock.guild_id == guild_id)
        .group_by(GuildStock.kind)
    )).all()
    return sum(_units(kind, int(total or 0)) for kind, total in rows)


async def stock(db: AsyncSession, guild_id: int) -> list[GuildStock]:
    return list((await db.scalars(select(GuildStock).where(
        GuildStock.guild_id == guild_id, GuildStock.count > 0,
    ))).all())


@dataclass
class Line:
    kind: str
    ref: str
    grade: str
    count: int
    name: str
    emoji: str
    grade_name: str


def describe(kind: str, ref: str, grade: str, count: int) -> Line:
    if kind == "herb":
        h = herbalism.herb_def(ref)
        return Line(kind, ref, grade, count, h.name if h else ref, h.emoji if h else "🌿", "")
    if kind == "fish":
        f = fishing.fish_def(ref)
        return Line(kind, ref, grade, count, f.name if f else ref, f.emoji if f else "🐟", fishing.grade_name(grade))
    if kind == "food":
        d = cooking.dish_def(ref)
        return Line(kind, ref, grade, count, d.name if d else ref, d.emoji if d else "🍲",
                    f"рыба {fishing.grade_name(grade)}")
    from services import elixir_service

    e = elixir_service.elixir_def(ref)
    return Line(kind, ref, grade, count, e.name if e else ref, e.emoji if e else "🧪", "")


async def mine(db: AsyncSession, character_id: int) -> list[Line]:
    """Что игрок может сдать."""
    out: list[Line] = []
    for r in (await db.scalars(select(CharacterHerb).where(
            CharacterHerb.character_id == character_id, CharacterHerb.count > 0))).all():
        out.append(describe("herb", r.herb_id, "", r.count))
    for r in (await db.scalars(select(CharacterFish).where(
            CharacterFish.character_id == character_id, CharacterFish.total_grams > 0))).all():
        out.append(describe("fish", r.fish_id, r.grade, r.total_grams))
    for r in (await db.scalars(select(CharacterFood).where(
            CharacterFood.character_id == character_id, CharacterFood.count > 0))).all():
        out.append(describe("food", r.dish_id, r.grade, r.count))
    for r in (await db.scalars(select(CharacterConsumable).where(
            CharacterConsumable.character_id == character_id, CharacterConsumable.count > 0))).all():
        out.append(describe("elixir", r.elixir_id, "", r.count))
    return out


async def _own_row(db: AsyncSession, character_id: int, kind: str, ref: str, grade: str):
    """(строка, имя поля счётчика) у персонажа; FOR UPDATE."""
    model, ref_col, field = {
        "herb": (CharacterHerb, CharacterHerb.herb_id, "count"),
        "fish": (CharacterFish, CharacterFish.fish_id, "total_grams"),
        "food": (CharacterFood, CharacterFood.dish_id, "count"),
        "elixir": (CharacterConsumable, CharacterConsumable.elixir_id, "count"),
    }[kind]
    query = select(model).where(model.character_id == character_id, ref_col == ref)
    if kind in ("fish", "food"):
        query = query.where(model.grade == grade)
    row = await db.scalar(query.with_for_update().execution_options(populate_existing=True))
    return row, field


async def _give_to(db: AsyncSession, character_id: int, kind: str, ref: str, grade: str, count: int) -> None:
    row, field = await _own_row(db, character_id, kind, ref, grade)
    if row is None:
        if kind == "herb":
            row = CharacterHerb(character_id=character_id, herb_id=ref, count=0)
        elif kind == "fish":
            row = CharacterFish(character_id=character_id, fish_id=ref, grade=grade, total_grams=0)
        elif kind == "food":
            row = CharacterFood(character_id=character_id, dish_id=ref, grade=grade, count=0)
        else:
            row = CharacterConsumable(character_id=character_id, elixir_id=ref, count=0)
        db.add(row)
    setattr(row, field, (getattr(row, field) or 0) + count)
    await db.flush()


async def _stock_row(db: AsyncSession, guild_id: int, kind: str, ref: str, grade: str) -> GuildStock | None:
    return await db.scalar(select(GuildStock).where(
        GuildStock.guild_id == guild_id, GuildStock.kind == kind, GuildStock.ref == ref, GuildStock.grade == grade,
    ).with_for_update().execution_options(populate_existing=True))


def _check(kind: str, count: int) -> None:
    if kind not in KINDS:
        raise GuildError("Такое на склад не кладут.")
    if count <= 0:
        raise GuildError("Неверное количество.")


async def deposit(db: AsyncSession, character: Character, kind: str, ref: str, grade: str, count: int) -> Line:
    """Сдать на склад. У рыбы count - граммы (сдаётся стак целиком)."""
    _check(kind, count)
    guild, _member = await guild_service._require_member(db, character)
    grade = grade or ""
    row, field = await _own_row(db, character.id, kind, ref, grade)
    if row is None or getattr(row, field) < count:
        raise GuildError("Столько у тебя нет.")
    cap = await guild_service.capacity(db, guild)
    if await goods_units(db, guild.id) + _units(kind, count) > cap.ore:
        raise GuildError(f"Склад полон: припасов помещается {cap.ore}.")
    setattr(row, field, getattr(row, field) - count)
    stored = await _stock_row(db, guild.id, kind, ref, grade)
    if stored is None:
        stored = GuildStock(guild_id=guild.id, kind=kind, ref=ref, grade=grade, count=0)
        db.add(stored)
    stored.count += count
    line = describe(kind, ref, grade, count)
    await guild_service.log(db, guild.id, "stock", f"{character.name} сдаёт на склад: {amount_text(line)}.", character.id)
    await db.flush()
    return line


async def withdraw(
    db: AsyncSession, actor: Character, kind: str, ref: str, grade: str, count: int,
    to_character_id: int | None = None,
) -> tuple[Character, Line]:
    _check(kind, count)
    guild, _member = await guild_service.require_treasurer(db, actor)
    receiver = actor
    if to_character_id is not None and to_character_id != actor.id:
        target = await guild_service.membership(db, to_character_id)
        if target is None or target.guild_id != guild.id:
            raise GuildError("Выдавать со склада можно только своим.")
        receiver = await db.get(Character, to_character_id)
    grade = grade or ""
    stored = await _stock_row(db, guild.id, kind, ref, grade)
    if stored is None or stored.count < count:
        raise GuildError("Столько на складе нет.")
    stored.count -= count
    await _give_to(db, receiver.id, kind, ref, grade, count)
    line = describe(kind, ref, grade, count)
    await guild_service.log(
        db, guild.id, "stock", f"{actor.name} выдаёт со склада {amount_text(line)}: {receiver.name}.", actor.id,
    )
    await db.flush()
    return receiver, line


def amount_text(line: Line) -> str:
    grade = f" ({line.grade_name})" if line.grade_name else ""
    if line.kind == "fish":
        return f"{line.emoji} {line.name}{grade}, {fishing.format_kg(line.count)}"
    return f"{line.emoji} {line.name}{grade} ×{line.count}"
