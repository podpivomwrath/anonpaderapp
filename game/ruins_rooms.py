"""Руины культа: особые комнаты и сценки - что выбирает лидер и чем это
кончается. Чистая логика: здесь только «что произойдёт» (эффекты), применяет
их services/ruins_service.py, тексты - bot/ruins_texts.py.

Эффект - словарь:
  {"heal": доля}        лечит живых на долю здоровья;
  {"hurt": доля}        бьёт живых на долю здоровья (вне боя не убивает: до 1 HP);
  {"offer": уровни}     лидер выбирает дар из трёх этих уровней;
  {"loot": бросков}     каждому живому реликвии в мешок;
  {"fight": тип}        бой прямо здесь (тип для этапа и добычи);
  {"after": эффект}     что будет после выигранного боя;
  {"curse": True}       случайный проклятый дар на этаж;
  {"raise": доля}       павшие встают с долей здоровья;
  {"pay": реликвий}     каждый живой отдаёт из мешка столько реликвий;
  {"line": ключ}        строка исхода (bot/ruins_texts.OUTCOME).
"""

from __future__ import annotations

import random

from game import ruins as rules
from game import ruins_gifts as gifts_mod
from game.economy import ruins_config as rc

ANY = (gifts_mod.COMMON, gifts_mod.RARE, gifts_mod.CURSED)
GOOD = (gifts_mod.COMMON, gifts_mod.RARE)
RARE_ONLY = (gifts_mod.RARE,)

#: Сценки (комната «Событие»): id -> варианты (ключ кнопки).
EVENTS: dict[str, tuple[str, ...]] = {
    "candles": ("grab", "leave"),
    "hermit": ("listen", "chase"),
    "sealed": ("break", "leave"),
    "writing": ("read", "leave"),
}

#: Что лидер может выбрать в комнате (кроме сценок и колодца).
CHOICES: dict[str, tuple[str, ...]] = {
    rules.SPRING: ("drink", "gift"),
    rules.ALTAR: ("blood", "leave"),
    rules.CRYPT: ("raise", "leave"),
    rules.CAVEIN: ("squeeze", "detour"),
    rules.PRISONER: ("free", "leave"),
    rules.STOREROOM: ("take", "leave"),
    rules.CHAPEL: ("pray", "leave"),
    rules.TREASURE: ("open", "leave"),
}


def event_for(rng: random.Random) -> str:
    return rng.choice(sorted(EVENTS))


def choices(kind: str, event: str | None = None) -> tuple[str, ...]:
    if kind == rules.EVENT:
        return EVENTS.get(event or "", ())
    return CHOICES.get(kind, ())


def outcome(kind: str, choice: str, rng: random.Random, event: str | None = None) -> list[dict]:
    """Эффекты выбора. Пустой список - ничего не случилось (ушли)."""
    if kind == rules.SPRING:
        return [{"heal": rc.SPRING_HEAL, "line": "spring_drink"}] if choice == "drink" else \
            [{"offer": GOOD, "line": "spring_gift"}]
    if kind == rules.ALTAR and choice == "blood":
        return [{"hurt": rc.ALTAR_BLOOD, "line": "altar_blood"}, {"offer": RARE_ONLY}]
    if kind == rules.CRYPT and choice == "raise":
        return [{"hurt": rc.CRYPT_COST, "raise": rc.CRYPT_RAISE, "line": "crypt_raise"}]
    if kind == rules.CAVEIN:
        if choice == "squeeze":
            return [{"hurt": rc.CAVEIN_HIT, "line": "cavein_squeeze"}]
        return [{"fight": rules.FIGHT, "line": "cavein_detour"}]
    if kind == rules.PRISONER and choice == "free":
        return [{"fight": rules.FIGHT, "after": {"offer": RARE_ONLY}, "line": "prisoner_free"}]
    if kind == rules.STOREROOM and choice == "take":
        return [{"loot": rc.STOREROOM_ROLLS, "curse": True, "line": "storeroom_take"}]
    if kind == rules.CHAPEL and choice == "pray":
        return [{"pay": rc.CHAPEL_PRICE, "line": "chapel_pray"}, {"offer": RARE_ONLY}]
    if kind == rules.TREASURE and choice == "open":
        if rng.random() < rc.TREASURE_MIMIC:
            return [{"fight": rules.TREASURE, "line": "treasure_mimic"}]
        return [{"loot": 2, "line": "treasure_open"}]
    if kind == rules.EVENT:
        return _event(event or "", choice, rng)
    return []


def _event(event: str, choice: str, rng: random.Random) -> list[dict]:
    if event == "candles" and choice == "grab":
        return [{"offer": GOOD, "line": "candles_ok"}] if rng.random() < 0.6 else \
            [{"hurt": 0.15, "line": "candles_fire"}]
    if event == "hermit":
        if choice == "listen":
            return [{"offer": GOOD, "line": "hermit_listen"}]
        return [{"loot": 1, "line": "hermit_chase"}]
    if event == "sealed" and choice == "break":
        return [{"loot": 2, "line": "sealed_ok"}] if rng.random() < 0.5 else \
            [{"hurt": 0.20, "line": "sealed_trap"}]
    if event == "writing" and choice == "read":
        return [{"offer": ANY, "line": "writing_ok"}] if rng.random() < 0.7 else \
            [{"hurt": 0.10, "line": "writing_bad"}]
    return []


def dodge_chance(agility: int) -> float:
    """Ловушка: шанс увернуться от ловкости."""
    return min(rc.TRAP_MAX, rc.TRAP_BASE + 0.5 * agility / (agility + rc.TRAP_AGI_SCALE))
