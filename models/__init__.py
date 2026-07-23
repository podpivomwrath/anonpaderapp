"""SQLAlchemy-модели. Все импортируются здесь, чтобы Base.metadata была полной
(это важно для Alembic autogenerate)."""

from models.base import Base
from models.character import Character, CharacterBuffPreset, CharacterStats
from models.combat import CombatParticipant, CombatSession
from models.economy import ExchangeOrder, PvpStakeTransfer, Wallet
from models.enums import BaseClass, CombatStatus, CombatType, OrderDirection, QuestStatus, Region
from models.item import Inventory, Item, ItemUpgradeHistory
from models.quest import CharacterQuest, Quest
from models.trophy import CharacterTrophy
from models.user import User

__all__ = [
    "Base",
    "BaseClass",
    "Character",
    "CharacterBuffPreset",
    "CharacterQuest",
    "CharacterStats",
    "CharacterTrophy",
    "CombatParticipant",
    "CombatSession",
    "CombatStatus",
    "CombatType",
    "ExchangeOrder",
    "Inventory",
    "Item",
    "ItemUpgradeHistory",
    "OrderDirection",
    "PvpStakeTransfer",
    "Quest",
    "QuestStatus",
    "Region",
    "User",
    "Wallet",
]
