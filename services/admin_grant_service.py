"""Выдача любого предмета игры из админки (патч 107).

Каталог строится из тех же источников, что и сама игра (контентные файлы и
конфиги), поэтому новая руда, рыба или реликвия появляется в админке без
правки этого модуля. Выдача идёт теми же функциями, что и игровой лут, чтобы
выданное ничем не отличалось от выпавшего.

Ключ позиции каталога - строка "вид:id[:градация]": её мини-апп и присылает
обратно, других параметров, кроме количества и уровня, нет.
"""

import random

from sqlalchemy import select

from game.combat import balance_config as bc
from game.content_loader import load_admin_weapons
from game.economy import craft_config as cc
from game.economy import crafting, fishing, item_gen, mining
from game.economy import fishing_config as fc
from game.economy import mining_config as ore_cfg
from game.economy import mount_config as mount_cfg
from game.economy.item_config import SLOTS
from models import Character, CharacterFish, CharacterLootbox, Inventory, Item
from models.mining import CharacterCraftTool
from services import (
    elixir_service,
    item_service,
    lootbox_service,
    mining_service,
    mount_service,
    trophy_service,
    wallet_service,
)
from services.admin_service import _require_self, log_action

#: Потолки за одну выдачу. Защита от лишнего нуля в поле: тысяча штук
#: экипировки положила бы и инвентарь, и мини-апп.
MAX_STACK = 1_000_000
MAX_PIECES = 50

SLOT_TITLES = {
    "weapon": "Оружие", "helmet": "Шлем", "armor": "Броня", "legs": "Поножи", "boots": "Сапоги",
}
GEAR_RARITIES = ("common", "uncommon", "rare", "epic", "legendary")


class GrantError(Exception):
    """Ключ не из каталога или количество вне пределов."""


def _entry(key: str, label: str, amount: str = "count", **extra) -> dict:
    """amount: count - стакается; pieces - отдельные экземпляры (каждый со
    своим роллом); one - только одна штука (маунт).

    variants - градации одного вида (редкость экипировки, градация руды и
    рыбы): в каталоге это одна строка, градация выбирается при выдаче, и
    прислать обратно надо ключ варианта."""
    return {"key": key, "label": label, "amount": amount, **extra}


def _grade_suffix(emoji: str | None) -> str:
    return f" {emoji}" if emoji else ""


def catalog() -> list[dict]:
    rarities = item_service.rarities()
    gear = [
        _entry(
            f"gear:{slot}", f"🗡 {SLOT_TITLES.get(slot, slot)}", "pieces", ilvl=True,
            variants=[
                {"key": f"gear:{slot}:{r}", "label": f"{rarities[r].emoji} {rarities[r].name}"}
                for r in GEAR_RARITIES
            ],
        )
        for slot in SLOTS
    ]
    unique = [
        _entry(f"unique:{uid}", f"⭐ {u.name}", "pieces")
        for uid, u in item_service.unique_items().items()
    ]
    crafted = []
    for uid in item_service.unique_items():
        recipe = crafting.recipe_for(uid)
        if recipe is None:
            continue
        for spec in cc.SPECS:
            if spec in recipe.outputs:
                crafted.append(_entry(
                    f"crafted:{uid}:{spec}",
                    f"⚒ {recipe.outputs[spec].name} ({cc.SPEC_TITLES[spec].lower()})",
                    "pieces",
                ))
    tools = [
        _entry(f"tool:{ceiling}", f"🔧 Инструмент до {ceiling}%")
        for ceiling in sorted(set(cc.TOOL_CEILING_BY_ORE_TIER.values()))
    ]
    ores = [
        _entry(f"ore:{ore.id}", f"{ore.emoji} {ore.name}", variants=[
            {"key": f"ore:{ore.id}:{grade}", "label": f"{name}{_grade_suffix(ore_cfg.GRADE_EMOJI.get(grade))}"}
            for _t, grade, name in ore_cfg.GRADES
        ])
        for ore in mining.ore_defs_ordered()
    ]
    fish = [
        _entry(f"fish:{f.id}", f"{f.emoji} {f.name}", variants=[
            {"key": f"fish:{f.id}:{grade}", "label": f"{name}{_grade_suffix(fc.GRADE_EMOJI.get(grade))}"}
            for _t, grade, name, _m in fc.GRADES
        ])
        for f in fishing.fish_defs_ordered()
    ]
    mounts = [
        _entry(
            f"mount:{m.id}",
            f"{mount_cfg.RARITY_EMOJI.get(m.rarity, '')} {m.name}"
            + (" (только себе)" if m.id == mount_cfg.ADMIN_MOUNT_ID else ""),
            "one",
        )
        for m in mount_service._defs().values()
    ]
    service = [
        _entry(f"admin_weapon:{w.id}", f"🛠 {w.name} (только себе)", "pieces")
        for w in load_admin_weapons()
    ]
    return [
        {"id": "currency", "title": "💰 Валюта и ключи", "entries": [
            _entry("gold", "💰 Золото"),
            _entry("gems", "💎 Самоцветы"),
            _entry("raid_keys", "🗝 Ключи Монолита"),
        ]},
        {"id": "gear", "title": "🗡 Экипировка", "entries": gear},
        {"id": "unique", "title": "⭐ Уникальные", "entries": unique},
        {"id": "crafted", "title": "⚒ Кованое оружие", "entries": crafted},
        {"id": "rarities", "title": "🗃️ Редкости", "entries": [
            _entry("chest", f"🗃️ {lootbox_service.CHEST_NAME}"),
        ]},
        {"id": "relics", "title": "💀 Реликвии", "entries": [
            _entry(f"trophy:{t.id}", f"{t.emoji} {t.name}") for t in trophy_service.trophy_defs_ordered()
        ]},
        {"id": "consumables", "title": "🧪 Расходники", "entries": [
            _entry(f"elixir:{e.id}", f"{e.emoji} {e.name}") for e in elixir_service.elixir_defs_ordered()
        ]},
        {"id": "ore", "title": "⛏ Руда", "entries": ores},
        {"id": "tools", "title": "🔧 Инструменты", "entries": tools},
        {"id": "fish", "title": "🐟 Рыба", "entries": fish},
        {"id": "mounts", "title": "🐎 Маунты", "entries": mounts},
        {"id": "service", "title": "🛠 Служебное", "entries": service},
    ]


def _find_entry(key: str) -> dict:
    for group in catalog():
        for entry in group["entries"]:
            keys = [v["key"] for v in entry.get("variants", ())] or [entry["key"]]
            if key in keys:
                return entry
    raise GrantError("Такого предмета нет в каталоге.")


def _primary_stat(character: Character) -> str:
    return bc.PRIMARY_STAT_BY_CLASS[character.base_class]


async def _add_item(db, character: Character, item: Item) -> Item:
    db.add(item)
    await db.flush()
    db.add(Inventory(character_id=character.id, item_id=item.id, equipped=False))
    await db.flush()
    return item


def _fish_grams(fish_id: str, grade: str) -> int:
    """Вес одной рыбы заданной градации - середина её диапазона долей."""
    lo, hi, _price = fc.FISH_STATS[fish_id]
    bounds = [g[0] for g in fc.GRADES] + [1.0]
    index = next(i for i, g in enumerate(fc.GRADES) if g[1] == grade)
    fraction = (bounds[index] + bounds[index + 1]) / 2
    return max(1, round(lo + (hi - lo) * fraction))


def _gear_level(character: Character, ilvl: int | None) -> int:
    return max(1, min(ilvl or character.level, bc.MAX_LEVEL))


async def grant(
    db, admin_vk_id: int, character: Character, key: str, amount: int,
    ilvl: int | None, rng: random.Random,
) -> str:
    """Выдаёт позицию каталога. Возвращает строку для журнала и ответа."""
    entry = _find_entry(key)
    kind, *rest = key.split(":")
    if entry["amount"] == "one":
        amount = 1
    limit = {"count": MAX_STACK, "pieces": MAX_PIECES, "one": 1}[entry["amount"]]
    if not 1 <= amount <= limit:
        raise GrantError(f"Количество - от 1 до {limit}.")

    if kind in ("gold", "gems"):
        wallet = await wallet_service.get_wallet(db, character.id)
        field = "farm_currency" if kind == "gold" else "donate_currency"
        setattr(wallet, field, getattr(wallet, field) + amount)
    elif kind == "raid_keys":
        character.raid_keys += amount
    elif kind == "gear":
        slot, rarity = rest
        for _ in range(amount):
            generated = item_gen.generate_item(
                rng, ilvl=_gear_level(character, ilvl), slot=slot, rarity_id=rarity,
                primary_stat=_primary_stat(character),
                bases=item_service.bases(), rarities=item_service.rarities(),
            )
            await _add_item(db, character, Item(
                name=generated.name, slot=generated.slot, base_stats=generated.base_stats,
                rarity=generated.rarity, ilvl=generated.ilvl,
            ))
    elif kind == "unique":
        for _ in range(amount):
            await item_service.grant_unique_item(db, character, rest[0], rng)
    elif kind == "crafted":
        source_id, spec = rest
        source = item_service.unique_items()[source_id]
        recipe = crafting.recipe_for(source_id)
        for _ in range(amount):
            # Как после первой ковки лучшей допустимой рудой обычной
            # градации; дальше - обычная прокачка инструментами.
            base, efficiency = crafting.roll_crafted_stats(
                rng, spec, source.power, _primary_stat(character), cc.CRAFT_MAX_ORE_TIER, "common",
                weights=crafting.spec_weights(source_id, spec),
            )
            await _add_item(db, character, Item(
                name=recipe.outputs[spec].name, slot=source.slot,
                base_stats=crafting.stats_at_efficiency(base, efficiency),
                rarity=item_service.UNIQUE_RARITY_ID, ilvl=None,
                craft_source_id=source_id, craft_spec=spec, craft_efficiency=efficiency,
                craft_base_stats=base, bound=True,
            ))
    elif kind == "chest":
        for _ in range(amount):
            db.add(CharacterLootbox(character_id=character.id, status="closed", streak=character.daily_streak))
    elif kind == "trophy":
        await trophy_service.grant_specific(db, character.id, rest[0], amount)
    elif kind == "elixir":
        await elixir_service.grant(db, character.id, rest[0], amount)
    elif kind == "ore":
        await mining_service.add_ore(db, character.id, rest[0], rest[1], amount)
    elif kind == "tool":
        ceiling = int(rest[0])
        row = await db.scalar(select(CharacterCraftTool).where(
            CharacterCraftTool.character_id == character.id, CharacterCraftTool.ceiling == ceiling,
        ))
        if row is None:
            row = CharacterCraftTool(character_id=character.id, ceiling=ceiling, count=0)
            db.add(row)
        row.count += amount
    elif kind == "fish":
        fish_id, grade = rest
        # Садок хранит суммарный вес по виду и градации - кладём N рыб
        # среднего для градации веса. Вместимость садка не проверяем:
        # админская выдача, как и промокод, идёт мимо игровых лимитов.
        row = await db.scalar(select(CharacterFish).where(
            CharacterFish.character_id == character.id, CharacterFish.fish_id == fish_id,
            CharacterFish.grade == grade,
        ))
        if row is None:
            row = CharacterFish(character_id=character.id, fish_id=fish_id, grade=grade, total_grams=0)
            db.add(row)
        row.total_grams += _fish_grams(fish_id, grade) * amount
    elif kind == "mount":
        if rest[0] == mount_cfg.ADMIN_MOUNT_ID:
            await _require_self(db, admin_vk_id, character)
        if not await mount_service.grant(db, character, rest[0]):
            raise GrantError("Этот маунт у игрока уже есть.")
    elif kind == "admin_weapon":
        await _require_self(db, admin_vk_id, character)
        weapon = next(w for w in load_admin_weapons() if w.id == rest[0])
        for _ in range(amount):
            await _add_item(db, character, Item(
                name=weapon.name, slot=weapon.slot, base_stats=dict(weapon.stats),
                rarity=weapon.rarity, ilvl=None, admin_only=True,
            ))
    else:
        raise GrantError("Такого предмета нет в каталоге.")

    await db.flush()
    label = entry["label"]
    variant = next((v for v in entry.get("variants", ()) if v["key"] == key), None)
    if variant is not None:
        label += f" ({variant['label']})"
    if kind == "gear":
        label += f", ур. {_gear_level(character, ilvl)}"
    note = f"{label} ×{amount}"
    await log_action(
        db, admin_vk_id, "grant_any", character.id,
        new_value={"key": key, "amount": amount}, note=note,
    )
    return note


def player_notice(note: str) -> str:
    """Сообщение игроку о выдаче. note - то, что вернул grant()."""
    label, _, amount = note.rpartition(" ×")
    return f"🎁 Вы получили: {label} - {amount} шт."
