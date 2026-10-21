"""Алхимия (2026-10-21, решения владельца).

Варят те же зелья, что в лавке, и они ничем от купленных не отличаются.
Варить выгоднее лавки: лечебные выходят по 10 штук, боевые по 3, а платишь
травами и немного золотом за склянки (оно списывается само). Варка идёт
BREW_SECONDS и не выпускает из дома; отменить можно, но травы и золото
пропадают. Рецепт открывается уровнем, провала нет.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    elixir_id: str
    level: int
    herbs: dict[str, int]
    gold: int
    out: int


RECIPES: list[Recipe] = [
    Recipe("heal_small", 1, {"bitter_wormwood": 2}, 40, 10),
    Recipe("ashen_fever", 8, {"ash_plantain": 2, "bitter_wormwood": 1}, 70, 3),
    Recipe("heal_medium", 12, {"salt_orache": 2, "bitter_wormwood": 1}, 120, 10),
    Recipe("blood_for_blood", 18, {"rusty_thistle": 2, "ash_plantain": 1}, 70, 3),
    Recipe("ashen_haze", 24, {"grey_hemlock": 2, "salt_orache": 1}, 80, 3),
    Recipe("shard_blood", 30, {"bloodwort": 2, "rusty_thistle": 1}, 90, 3),
    Recipe("blood_clarity", 35, {"ash_poppy": 2, "grey_hemlock": 1}, 100, 3),
    Recipe("second_heart", 40, {"smoldering_heather": 2, "bloodwort": 1}, 110, 3),
    Recipe("last_breath", 45, {"crimson_root": 2, "ash_poppy": 1}, 130, 3),
    Recipe("heal_large", 50, {"stone_bloom": 2, "smoldering_heather": 1}, 350, 10),
]
RECIPES_BY_ID = {r.elixir_id: r for r in RECIPES}

BREW_SECONDS = 30

# --- Уровень ------------------------------------------------------------------
MAX_LEVEL = 50
#: Та же кривая, что у травничества: до 50-го ~5400 опыта.
XP_BASE = 10
XP_PER_LEVEL = 4
#: Опыт за варку: BREW_XP_BASE + BREW_XP_PER_LEVEL * уровень рецепта.
BREW_XP_BASE = 20
BREW_XP_PER_LEVEL = 2

#: Каждые 10 уровней: склянки на 10% дешевле и +10% к шансу лишней порции
#: (+1 боевое зелье или +3 лечебных).
GOLD_DISCOUNT_PER_10 = 0.10
BONUS_CHANCE_PER_10 = 0.10
BONUS_HEAL = 3
BONUS_COMBAT = 1
