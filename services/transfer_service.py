"""Передача предметов и валюты между игроками.

Можно: золото, самоцветы, расходники, руду, экипировку (включая уникальные
боссовые вещи вроде Скальпеля Хирурга). Нельзя: скованную экипировку (она
привязана при ковке), надетое, служебное, трофеи и рыбу.

Все списания - условным запросом в базу («списать, если хватает»), а не
«прочитать -> вычесть -> записать»: события ВК обрабатываются параллельно,
и двойное нажатие «Передать» иначе передало бы вещь дважды (патч 94, та же
история, что с продажами).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import fishing, mining
from models import CharacterConsumable, CharacterOre, Inventory, Item, TransferLog
from services import (
    elixir_service,
    item_service,
    mining_service,
    trophy_service,
    wallet_service,
)

GOLD_WORDS = {"золото", "золота", "зол", "зол.", "золотом", "золотых", "gold"}
GEM_WORDS = {"сам", "сам.", "самоц", "самоцвет", "самоцветы", "самоцветов", "самоцвета",
             "пепельные самоцветы", "gems"}
_GRADE_STEMS = {"обычн": "common", "редк": "rare", "эпич": "epic", "легенд": "legendary"}


@dataclass
class Offer:
    """Что именно передаётся: одна строка выбора."""

    kind: str                # gold | gems | elixir | ore | item
    ref: str | None          # id эликсира, «руда:градация», id предмета
    label: str               # как видит игрок
    available: int           # сколько есть у отправителя
    stackable: bool = True

    @property
    def token(self) -> str:
        return f"{self.kind}:{self.ref or ''}"


@dataclass
class Lookup:
    offers: list[Offer]
    #: почему передать нельзя, если offers пуст (None - просто нет такого)
    refusal: str | None = None


def parse(text: str) -> tuple[str, int | None]:
    """«Малое исцеление 5» -> ("малое исцеление", 5); «золото» -> ("золото", None).
    Число можно ставить и перед названием: «100 зол», «3 малое исцеление».
    Регистр не важен - всё сравнивается в нижнем."""
    text = " ".join(text.split()).strip()
    first = re.match(r"^(\d+)\s+(\D.*)$", text)
    if first:
        return first.group(2).strip().lower(), int(first.group(1))
    match = re.match(r"^(.*?)(?:\s+(\d+))?$", text)
    name, qty = match.group(1), match.group(2)
    return name.strip().lower(), (int(qty) if qty else None)


def _split_grade(name: str) -> tuple[str, str | None]:
    """«бурое железо редкая» -> ("бурое железо", "rare")."""
    words = name.split()
    if len(words) >= 2:
        last = words[-1].strip("()")
        for stem, grade in _GRADE_STEMS.items():
            if last.startswith(stem):
                return " ".join(words[:-1]), grade
    return name, None


def is_transferable(item: Item, equipped: bool) -> str | None:
    """None - можно; иначе причина отказа. Сначала то, что не передать
    никогда: «сначала сними» у служебной вещи обещало бы то, чего нет."""
    if item.admin_only:
        return "Служебные вещи не передаются."
    if item.bound or item.craft_spec is not None:
        return "Скованная экипировка привязана к хозяину - её не передать."
    if equipped:
        return "Надетое не передать - сначала сними."
    return None


def _item_label(item: Item) -> str:
    # Коротко и по-русски (2026-10-13: было «VIT+13»).
    stats = " ".join(
        f"{item_service.STAT_SHORT.get(k, k)}+{v}" for k, v in (item.base_stats or {}).items()
    )
    return f"{item_service.format_item_label(item)} {stats}".strip()


async def find(db: AsyncSession, character_id: int, name: str, number: int | None = None) -> Lookup:
    """Всё, что подходит под название, у отправителя. number - число из
    команды: у стаков это количество, у экипировки - номер вещи."""
    if name in GOLD_WORDS:
        wallet = await wallet_service.get_wallet(db, character_id)
        return Lookup([Offer("gold", None, "💰 Золото", wallet.farm_currency)])
    if name in GEM_WORDS:
        wallet = await wallet_service.get_wallet(db, character_id)
        return Lookup([Offer("gems", None, "💎 Пепельные самоцветы", wallet.donate_currency)])

    for elixir, count in await elixir_service.get_stock(db, character_id):
        if elixir.name.lower() == name:
            return Lookup([Offer("elixir", elixir.id, f"{elixir.emoji} {elixir.name}", count)])

    ore_name, grade = _split_grade(name)
    ore_offers = [
        Offer("ore", f"{definition.id}:{grade_id}",
              f"{definition.emoji} {definition.name} ({mining.grade_name(grade_id)})", count)
        for definition, grade_id, count in await mining_service.get_ore(db, character_id)
        if definition.name.lower() == ore_name and (grade is None or grade_id == grade)
    ]
    if ore_offers:
        return Lookup(ore_offers)

    matches = [(item, equipped) for item, equipped in await item_service.get_inventory(db, character_id)
               if item.name.lower() == name]
    if number is not None:
        # «передать Скальпель Хирурга 1212» - число у экипировки это номер
        # вещи (его копирует кнопка в мини-аппе), а не количество: так
        # передаётся ровно этот экземпляр, без выбора из одноимённых.
        exact = [(item, equipped) for item, equipped in matches if item.id == number]
        if exact:
            refusal = is_transferable(*exact[0])
            if refusal:
                return Lookup([], refusal)
            return Lookup([Offer("item", str(exact[0][0].id), _item_label(exact[0][0]), 1, stackable=False)])
    offers = [Offer("item", str(item.id), _item_label(item), 1, stackable=False)
              for item, equipped in matches if is_transferable(item, equipped) is None]
    if offers:
        return Lookup(offers)
    if matches:
        return Lookup([], is_transferable(*matches[0]))

    if any(t.name.lower() == name for t in trophy_service.trophy_defs_ordered()):
        return Lookup([], "Трофеи не передаются - их можно только продать.")
    if any(f.name.lower() == name for f in fishing.fish_defs_ordered()):
        return Lookup([], "Рыба не передаётся.")
    return Lookup([])


# --- Исполнение -----------------------------------------------------------------


class TransferFailed(Exception):
    pass


async def _credit_stack(db: AsyncSession, model, key: dict, amount: int) -> None:
    """Прибавка получателю одним UPDATE; строки нет - вставка. Если строку
    в ту же секунду вставил параллельный запрос - снова UPDATE."""
    where = [getattr(model, k) == v for k, v in key.items()]
    result = await db.execute(update(model).where(*where).values(count=model.count + amount))
    if result.rowcount:
        return
    try:
        async with db.begin_nested():
            db.add(model(**key, count=amount))
    except IntegrityError:
        await db.execute(update(model).where(*where).values(count=model.count + amount))


async def _take_stack(db: AsyncSession, model, key: dict, amount: int) -> bool:
    where = [getattr(model, k) == v for k, v in key.items()]
    result = await db.execute(
        update(model).where(*where, model.count >= amount).values(count=model.count - amount)
        .execution_options(synchronize_session="fetch")
    )
    return bool(result.rowcount)


#: Из рук в руки (2026-10-19, решение владельца): вещи, зелья и руду - только
#: тому, кто на одной клетке с тобой (город - тоже клетка). Дальше - курьер
#: (services/courier_service.py). Золото и самоцветы - на любое расстояние.
NEEDS_NEAR = ("elixir", "ore", "item")


def same_cell(sender, recipient) -> bool:
    return (sender.pos_x, sender.pos_y) == (recipient.pos_x, recipient.pos_y)


def needs_courier(offer: Offer, sender, recipient) -> bool:
    return offer.kind in NEEDS_NEAR and not same_cell(sender, recipient)


async def take(db: AsyncSession, sender_id: int, offer: Offer, amount: int) -> int:
    """Списать у отправителя (для курьера - сразу при подтверждении, чтобы
    вещь в пути нельзя было продать или передать второй раз). Вещь
    отвязывается от отправителя, но остаётся в базе - её несёт курьер.
    Возвращает количество. TransferFailed - этого уже нет."""
    amount = 1 if not offer.stackable else amount
    if amount <= 0:
        raise TransferFailed("Количество должно быть больше нуля.")
    if offer.kind in ("gold", "gems"):
        from game.economy import faction_config as fc

        if amount < fc.TRANSFER_MIN:
            raise TransferFailed(f"Валюту передают от {fc.TRANSFER_MIN}.")
        currency = "farm" if offer.kind == "gold" else "donate"
        try:
            await wallet_service.charge(db, sender_id, currency, amount)
        except wallet_service.NotEnoughCurrency:
            raise TransferFailed("Столько у тебя нет.") from None
    elif offer.kind == "elixir":
        if not await _take_stack(db, CharacterConsumable, {"character_id": sender_id, "elixir_id": offer.ref}, amount):
            raise TransferFailed("Столько у тебя нет.")
    elif offer.kind == "ore":
        ore_id, grade = offer.ref.split(":", 1)
        key = {"character_id": sender_id, "ore_id": ore_id, "grade": grade}
        if not await _take_stack(db, CharacterOre, key, amount):
            raise TransferFailed("Столько у тебя нет.")
    elif offer.kind == "item":
        item = await db.get(Item, int(offer.ref), with_for_update=True)
        if item is None or item.admin_only or item.bound or item.craft_spec is not None:
            raise TransferFailed("Эту вещь не передать.")
        moved = await db.execute(
            delete(Inventory).where(
                Inventory.item_id == item.id,
                Inventory.character_id == sender_id,
                Inventory.equipped.is_(False),
            ).execution_options(synchronize_session="fetch")
        )
        if not moved.rowcount:
            raise TransferFailed("Этой вещи у тебя уже нет - или она надета.")
    else:
        raise TransferFailed("Это не передаётся.")
    return amount


async def give(db: AsyncSession, recipient_id: int, kind: str, ref: str | None, amount: int) -> int:
    """Выдать получателю то, что списано take. Возвращает, сколько дошло
    (у валюты - за вычетом налога фракции получателя)."""
    if kind in ("gold", "gems"):
        from services import faction_service

        currency = "farm" if kind == "gold" else "donate"
        # Налог фракции получателя (2026-10-15) вместо налога гильдии.
        tax, _city = await faction_service.tax_transfer(db, recipient_id, currency, amount)
        await wallet_service.deposit(db, recipient_id, currency, amount - tax, taxable=False)
        return amount - tax
    if kind == "elixir":
        await _credit_stack(db, CharacterConsumable, {"character_id": recipient_id, "elixir_id": ref}, amount)
    elif kind == "ore":
        ore_id, grade = ref.split(":", 1)
        await _credit_stack(db, CharacterOre, {"character_id": recipient_id, "ore_id": ore_id, "grade": grade}, amount)
    elif kind == "item":
        db.add(Inventory(character_id=recipient_id, item_id=int(ref), equipped=False))
    return amount


def log(db: AsyncSession, sender_id: int, recipient_id: int, kind: str, ref: str | None, label: str, amount: int) -> None:
    db.add(TransferLog(
        from_character_id=sender_id, to_character_id=recipient_id, kind=kind,
        ref=ref, label=label[:160], amount=amount,
    ))


async def execute(
    db: AsyncSession, sender_id: int, recipient_id: int, offer: Offer, amount: int,
) -> int:
    """Передаёт из рук в руки и пишет журнал. Возвращает переданное количество.
    TransferFailed - у отправителя этого уже нет (ушло в параллельном запросе)."""
    if sender_id == recipient_id:
        raise TransferFailed("Самому себе не передать.")
    amount = await take(db, sender_id, offer, amount)
    await give(db, recipient_id, offer.kind, offer.ref, amount)
    log(db, sender_id, recipient_id, offer.kind, offer.ref, offer.label, amount)
    await db.flush()
    return amount


async def recent(db: AsyncSession, character_id: int, limit: int = 20) -> list[TransferLog]:
    """Последние передачи с участием персонажа - для админки и разбора жалоб."""
    rows = await db.execute(
        select(TransferLog).where(
            (TransferLog.from_character_id == character_id) | (TransferLog.to_character_id == character_id)
        ).order_by(TransferLog.id.desc()).limit(limit)
    )
    return list(rows.scalars())


def command_for(item: Item) -> str:
    """«передать Скальпель Хирурга 1212» - команда на ровно этот экземпляр."""
    return f"передать {item.name} {item.id}"
