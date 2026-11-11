"""Перевод живых персонажей на руны-навыки (2026-11-11, без вайпа).

Что делает с каждым персонажем, у которого выбран класс и ещё нет ни одной
руны-навыка в слотах (повторный запуск ничего не сломает):

1. Навыки, которые были у него по старой схеме (подкласс - 4 навыка, класс
   или путь - 3), превращаются в руны-навыки. Слитые навыки берут замену
   (MERGED). Три встают в слоты сразу, остальные - в сумку. Сначала ставятся
   навыки, в которые игрок вставлял огранки, потом - по порядку ORDER.
2. Огранки из первого гнезда старого навыка переезжают в гнездо того же
   навыка-руны, если он встал в слот. Второе гнездо теперь открывает
   ступень II - огранки оттуда и с навыков в сумке уходят в сумку.
3. Купленные вторые гнёзда навыков (60 000 золота каждое) возвращаются
   золотом: покупать их больше нечего.
4. За каждый открытый микробафф (пройденное испытание) - руна-награда
   этого испытания, как у тех, кто проходит испытания сейчас.
5. Пресеты с раскладкой рун получают нынешние руны-навыки, огранки в них
   переезжают на новые гнёзда.

Запуск: python tools/migrate_skill_runes.py [--apply]
Без --apply - сухой прогон: что получит каждый, база не меняется.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

import game.classes  # noqa: F401 - регистрирует навыки
from game.combat import skill_catalog
from game.economy import runes_config as rc
from models import Character, CharacterRuneSlot
from models.character import CharacterBuffPreset
from models.subclass_trial import CharacterUnlockedBuff
from services import rune_service, trial_service, wallet_service
from services.db import get_session_factory

#: Старые навыки по пулу (подкласс, иначе базовый класс). Первые три встают в
#: слоты, если игрок не вставлял огранок в другие.
ORDER: dict[str, list[str]] = {
    "warrior": ["warrior_cleave", "warrior_stagger", "warrior_warcry"],
    "rogue": ["rogue_double_stab", "rogue_shadow_dash", "rogue_smoke"],
    "mage": ["mage_shard_volley", "mage_ice_bonds", "mage_blood_seal"],
    "guardian": ["guardian_shield_bash", "guardian_block", "guardian_unbreakable", "guardian_stonegrip"],
    "blood_knight": ["blood_knight_lifesteal_strike", "blood_knight_harvest", "blood_knight_crimson_feast",
                     "blood_knight_blood_seal"],
    "shadow_blade": ["shadow_blade_marked_strike", "shadow_blade_mark_harvest", "shadow_blade_execute",
                     "shadow_blade_shadow_dance"],
    "poisoner": ["poisoner_venom", "poisoner_toxic_burst", "poisoner_disrupt", "poisoner_decay"],
    "elementalist": ["elementalist_fire", "elementalist_ice", "elementalist_lightning", "elementalist_convergence"],
    "dark_mystic": ["dark_mystic_blood_pact", "dark_mystic_drain", "dark_mystic_ward", "dark_mystic_circle"],
}

#: Слитые при переделке навыки -> их замена (этап 1, 2026-11-10).
MERGED: dict[str, str] = {
    "mage_shard_volley": "elementalist_fire",  # маг стартует с Огненной плети (владелец)
    "mage_ice_bonds": "elementalist_ice",
    "mage_blood_seal": "poisoner_decay",  # Стихийная печать - уязвимость цели
    "guardian_stonegrip": "warrior_stagger",  # оглушений два вместо четырёх
    "shadow_blade_shadow_dance": "rogue_smoke",  # уклонение одно
}

OLD_SLOT_PRICE = 60_000
REFUND_REASON = "migrate_skill_runes.refund"


def new_id(old: str) -> str:
    return MERGED.get(old, old)


def plan_skills(pool: str, facet_rows: list) -> tuple[list[str], list[str]]:
    """(в слоты, в сумку) - id рун-навыков."""
    skills: list[str] = []
    for old in ORDER.get(pool, []):
        sid = new_id(old)
        if sid not in skills:
            skills.append(sid)
    assert all(s in skill_catalog.ALL_SKILL_DEFS for s in skills), skills
    faceted = {new_id(r.slot.partition(":")[0]) for r in facet_rows}
    ranked = sorted(skills, key=lambda s: (s not in faceted, skills.index(s)))
    equip = ranked[:rc.ABILITY_SLOTS]
    return [s for s in skills if s in equip], [s for s in skills if s not in equip]


def migrate_preset(runes: list | None, equipped: list[str]) -> list | None:
    if runes is None:
        return None
    out = [{"kind": rc.ABILITY, "slot": str(i), "rune_id": sid} for i, sid in enumerate(equipped)]
    used: set[str] = set()
    for entry in runes:
        if not isinstance(entry, dict) or entry.get("kind") == rc.ABILITY:
            continue
        if entry.get("kind") == rc.SKILL:
            old, _, index = str(entry.get("slot", "")).partition(":")
            sid = new_id(old)
            if index != "0" or sid not in equipped or sid in used:
                continue
            used.add(sid)
            entry = {**entry, "slot": f"{sid}:0"}
        out.append(entry)
    return out


async def migrate_one(db, character: Character, apply: bool) -> dict | None:
    rows = list((await db.execute(
        select(CharacterRuneSlot).where(CharacterRuneSlot.character_id == character.id)
    )).scalars())
    if any(r.kind == rc.ABILITY for r in rows):
        return None
    pool = character.subclass or character.base_class
    facet_rows = [r for r in rows if r.kind == rc.SKILL]
    equip, spare = plan_skills(pool, facet_rows)
    report = {"name": character.name, "pool": pool, "equip": equip, "spare": spare,
              "facets_moved": 0, "facets_bagged": 0, "refund": 0, "trial_runes": Counter()}

    # 2. огранки
    moved: set[str] = set()
    for row in facet_rows:
        old, _, index = row.slot.partition(":")
        sid = new_id(old)
        if index == "0" and sid in equip and sid not in moved:
            moved.add(sid)
            report["facets_moved"] += 1
            if apply:
                row.slot = f"{sid}:0"
        else:
            report["facets_bagged"] += 1
            if apply:
                await rune_service.grant(db, character.id, row.rune_id, 1, reason="migrate")
                await db.delete(row)

    # 1. руны-навыки
    if apply:
        await db.flush()
        for i, sid in enumerate(equip):
            db.add(CharacterRuneSlot(character_id=character.id, kind=rc.ABILITY, slot=str(i), rune_id=sid))
        for sid in spare:
            await rune_service.grant(db, character.id, sid, 1, reason="migrate")

    # 3. купленные вторые гнёзда - золотом
    bought = len(character.rune_skill_slots or [])
    if bought:
        report["refund"] = bought * OLD_SLOT_PRICE
        if apply:
            await wallet_service.deposit(db, character.id, "farm", report["refund"], taxable=False,
                                         reason=REFUND_REASON)
            character.rune_skill_slots = []

    # 4. пройденные испытания - руны-награды
    buffs = (await db.execute(
        select(CharacterUnlockedBuff.buff_id).where(CharacterUnlockedBuff.character_id == character.id)
    )).scalars().all()
    for buff_id in buffs:
        rune_id = trial_service.reward_rune(buff_id)
        report["trial_runes"][rune_id] += 1
    if apply:
        for rune_id, n in report["trial_runes"].items():
            await rune_service.grant(db, character.id, rune_id, n, reason="trial")

    # 5. пресеты
    presets = (await db.execute(
        select(CharacterBuffPreset).where(CharacterBuffPreset.character_id == character.id)
    )).scalars().all()
    report["presets"] = sum(1 for p in presets if p.runes is not None)
    if apply:
        for preset in presets:
            if preset.runes is not None:
                preset.runes = migrate_preset(preset.runes, equip)  # JSON - целиком
        await db.flush()
        await rune_service.recompute(db, character)
    return report


async def main(apply: bool) -> None:
    factory = get_session_factory()
    async with factory() as db:
        ids = (await db.execute(
            select(Character.id).where(Character.base_class.is_not(None)).order_by(Character.id)
        )).scalars().all()
    total = Counter()
    for cid in ids:
        async with factory() as db:
            character = await db.scalar(select(Character).where(Character.id == cid).with_for_update())
            report = await migrate_one(db, character, apply)
            if report is None:
                total["skipped"] += 1
                continue
            if apply:
                await db.commit()
            else:
                await db.rollback()
        total["done"] += 1
        total["refund"] += report["refund"]
        total["trial_runes"] += sum(report["trial_runes"].values())
        total["facets_moved"] += report["facets_moved"]
        total["facets_bagged"] += report["facets_bagged"]
        print(f"{report['name']} [{report['pool']}]: слоты {report['equip']}, сумка {report['spare']}, "
              f"огранки {report['facets_moved']} на месте / {report['facets_bagged']} в сумку, "
              f"возврат {report['refund']}, руны испытаний {dict(report['trial_runes'])}, "
              f"пресетов с рунами {report['presets']}")
    print("ИТОГО", dict(total), "ПРИМЕНЕНО" if apply else "сухой прогон")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
