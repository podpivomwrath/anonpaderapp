"""SQLAlchemy-модели. Все импортируются здесь, чтобы Base.metadata была полной
(это важно для Alembic autogenerate)."""

from models.admin import AdminAction, BugReport, CharacterDeath
from models.base import Base
from models.character import Character, CharacterBuffPreset, CharacterStats
from models.combat import CombatParticipant, CombatSession
from models.consumable import CharacterConsumable
from models.dailies import CharacterDaily, CharacterTitle
from models.economy import ExchangeOrder, PvpStakeTransfer, Wallet
from models.enums import BaseClass, CombatStatus, CombatType, OrderDirection, QuestStatus, Region
from models.group import Group, GroupInvite, GroupMember
from models.item import Inventory, Item, ItemUpgradeHistory
from models.lootbox import CharacterLootbox
from models.mount import CharacterMount, MountTravel
from models.promo import PromoActivation, PromoCode
from models.pvp import PvpBattle
from models.quest import CharacterQuest, Quest
from models.song import CharacterSongFragment
from models.story import CharacterStoryProgress
from models.subclass_trial import CharacterTrialProgress, CharacterUnlockedBuff
from models.trophy import CharacterTrophy
from models.user import User

__all__ = [
    "AdminAction",
    "Base",
    "BaseClass",
    "BugReport",
    "Character",
    "CharacterBuffPreset",
    "CharacterConsumable",
    "CharacterDaily",
    "CharacterDeath",
    "CharacterLootbox",
    "CharacterMount",
    "CharacterQuest",
    "CharacterSongFragment",
    "CharacterStats",
    "CharacterStoryProgress",
    "CharacterTitle",
    "CharacterTrialProgress",
    "CharacterTrophy",
    "CharacterUnlockedBuff",
    "CombatParticipant",
    "CombatSession",
    "CombatStatus",
    "CombatType",
    "ExchangeOrder",
    "Group",
    "GroupInvite",
    "GroupMember",
    "Inventory",
    "Item",
    "ItemUpgradeHistory",
    "MountTravel",
    "OrderDirection",
    "PromoActivation",
    "PromoCode",
    "PvpBattle",
    "PvpStakeTransfer",
    "Quest",
    "QuestStatus",
    "Region",
    "User",
    "Wallet",
]
