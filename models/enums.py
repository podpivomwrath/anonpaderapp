"""Строковые enum'ы предметной области.

Хранятся в БД как обычные VARCHAR (StrEnum), чтобы миграции оставались простыми —
схема будет часто меняться, PG native enum'ы при этом только мешают.
"""

from enum import StrEnum


class BaseClass(StrEnum):
    WARRIOR = "warrior"  # Воин
    ROGUE = "rogue"      # Разбойник
    MAGE = "mage"        # Маг


class Region(StrEnum):
    RIDGE = "ridge"        # 🏰 Обетованный Кряж
    WOODS = "woods"        # 🌲 Шепчущие Пущи
    DOCKS = "docks"        # ⚓ Соляные Пристани
    SCORCHED = "scorched"  # 🔥 Выжженный Предел


class OrderDirection(StrEnum):
    BUY = "buy"
    SELL = "sell"


class QuestStatus(StrEnum):
    ACTIVE = "active"        # прогресс идёт
    READY = "ready"          # цель достигнута, награда не выдана
    COMPLETED = "completed"  # выдана у наставника


class CombatType(StrEnum):
    PVE = "pve"              # соло/группа против мобов
    PVP_GROUP = "pvp_group"  # групповой PvP (тиковый движок)
    DUEL = "duel"            # 1×1, последовательные ходы (duel_engine)


class CombatStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    FINISHED = "finished"
