"""Кулинария (2026-10-21, решения владельца).

Блюдо готовят в печи дома из рыбы (и иногда травы); соль и специи
подтягиваются сами за золото. Вес рыбы задаёт число порций, градация рыбы -
силу блюда. Съеденное блюдо даёт бафф на FOOD_MINUTES (с уровнем дольше),
действует одно блюдо - новое заменяет старое, бафф переживает смерть.
Есть можно только вне боя. Готовка идёт COOK_SECONDS и не выпускает из дома;
отмена - без возврата. Каталог (названия, лор) - content/cooking/dishes.json.

Ключи баффа:
  max_hp_bonus             - доля к максимуму здоровья
  xp_bonus                 - доля к опыту за мобов (соло и группа)
  damage_bonus             - доля к урону (тот же ключ, что у пресетов)
  incoming_damage_reduction - доля снижения входящего урона
  relic_bonus              - шанс дополнительного броска реликвий с моба (соло)
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Dish:
    dish_id: str
    level: int
    fish_tier: int
    herb: str | None
    gold: int
    buff: dict[str, float] = field(default_factory=dict)


DISHES: list[Dish] = [
    Dish("wormwood_soup", 1, 1, "bitter_wormwood", 20, {"max_hp_bonus": 0.10}),
    Dish("baked_gudgeon", 6, 1, None, 25, {"xp_bonus": 0.08}),
    Dish("orache_stew", 12, 2, "salt_orache", 40, {"damage_bonus": 0.05}),
    Dish("smoked_tench", 18, 2, None, 50, {"relic_bonus": 0.10}),
    Dish("thistle_pie", 24, 3, "rusty_thistle", 70, {"incoming_damage_reduction": 0.08}),
    Dish("bloodwort_eel", 30, 3, "bloodwort", 90, {"xp_bonus": 0.12}),
    Dish("sturgeon_roast", 36, 4, "ash_poppy", 110, {"damage_bonus": 0.08}),
    Dish("coal_flounder", 42, 4, "smoldering_heather", 130, {"relic_bonus": 0.15}),
    Dish("deep_tear_root", 48, 5, "crimson_root", 160, {"max_hp_bonus": 0.15, "damage_bonus": 0.05}),
    Dish("monolith_feast", 50, 5, "stone_bloom", 200,
         {"damage_bonus": 0.10, "incoming_damage_reduction": 0.10, "max_hp_bonus": 0.10}),
]
DISHES_BY_ID = {d.dish_id: d for d in DISHES}

BUFF_TITLES = {
    "max_hp_bonus": "здоровья",
    "xp_bonus": "опыта с мобов",
    "damage_bonus": "урона",
    "incoming_damage_reduction": "защиты",
    "relic_bonus": "к шансу дополнительной реликвии с моба",
}

#: Сила блюда от градации рыбы (градации - fishing_config.GRADES).
GRADE_MULT = {"small": 0.75, "common": 1.0, "big": 1.25, "trophy": 1.5, "legendary": 2.0}
#: Лучшие градации - первыми в списках.
GRADE_ORDER = ("legendary", "trophy", "big", "common", "small")

#: Граммов рыбы на порцию по тиру; за одну готовку - не больше MAX_PORTIONS.
PORTION_GRAMS = {1: 500, 2: 1200, 3: 3000, 4: 6000, 5: 2000}
MAX_PORTIONS = 3

COOK_SECONDS = 30
FOOD_MINUTES = 30
#: С 10, 20, 30, 40, 50 уровня бафф длится дольше на столько минут.
EXTRA_MINUTES = {10: 5, 20: 10, 30: 15, 40: 20, 50: 30}

# --- Уровень (та же кривая, что у травничества и алхимии) --------------------
MAX_LEVEL = 50
#: Кривая та же, что у травничества. Опыт до следующего уровня: XP_BASE + XP_PER_LEVEL * уровень ** XP_EXP.
#: 2026-10-21, владелец: «качается слишком быстро, ещё медленнее» - было
#: 10 + 4*L (до 50-го 5 390 опыта, уровень за 1-2 варки). Теперь до 50-го
#: ~19 000: ~850 пучков травы или ~260 варок, на старте 4 пучка/2 варки за
#: уровень, к концу 27 пучков/7 варок. Круче нельзя: трав на карте мало.
XP_BASE = 35
XP_PER_LEVEL = 6
XP_EXP = 1.25
COOK_XP_BASE = 20
COOK_XP_PER_LEVEL = 2
