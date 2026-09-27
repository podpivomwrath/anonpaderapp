"""События исследования со сценами (патч 110): чистая логика без БД.

Событие - граф сцен (content/events/scenes.json). Сцена бывает:
- choice - обычный выбор; у выбора могут быть требование, цена, проверка
  характеристики или взвешенные исходы;
- push   - «ещё чуть-чуть»: тянешь добычу шаг за шагом, риск растёт;
- timer  - реакция: успеть нажать кнопку за несколько секунд;
- riddle - загадка, ответ пишется текстом;
- dice   - ставка в кости на золото или самоцветы.

Исход (SceneResult) либо ведёт в следующую сцену (next), либо завершает
событие наградой/уроном/боем/эффектом/следом. Награды - в «мобах»: 1.0 =
столько же опыта и трофеев, сколько даёт обычный моб этой клетки. Так
события автоматически масштабируются под кольцо и уровень, а контент не
держит ни одного абсолютного числа.

Здесь - модели контента и расчёты (шанс проверки, риск шага, бросок костей,
сверка ответа, выбор клетки следа). Запись в БД - services/scene_event_service.py,
показ и кнопки - bot/handlers/scene_events.py.
"""

import random
import re
from pathlib import Path

from pydantic import BaseModel, Field

from game.content_loader import CONTENT_DIR, _load_json_dict
from game.world import grid
from game.world import world_config as wc

TIERS = ("medium", "deep")

#: Доли слоёв среди событий исследования. «Лёгкие» - старые одноэкранные
#: события (content/events/exploration.json).
TIER_WEIGHTS = {"light": 0.65, "medium": 0.30, "deep": 0.05}

STATS = ("str", "agi", "int", "vit", "wil")
STAT_EMOJI = {"str": "💪", "agi": "🏃", "int": "🧠", "vit": "❤️", "wil": "✨"}

#: Шанс проверки = база сложности + наклон * (доля стата в сумме статов - 0.2).
#: Доля, а не абсолютное значение: так проверка отражает сборку персонажа
#: (воин силён в силе, маг - в интеллекте) и не зависит от уровня.
CHECK_BASE = {"easy": 0.65, "normal": 0.50, "hard": 0.35}
CHECK_SLOPE = 1.6
CHECK_MIN, CHECK_MAX = 0.10, 0.90
#: Классовая кнопка без проверки - почти наверняка, но не всегда.
CLASS_OPTION_CHANCE = 0.85


class SceneResult(BaseModel):
    """Исход выбора. Эффекты комбинируются."""

    weight: float = 1.0
    text: str = ""
    next: str | None = None
    reward: float = 0.0          # опыт + трофеи, в мобах
    xp: float = 0.0              # только опыт, в мобах
    gold: float = 0.0            # золото, в «мобах» золота
    elixir: str | None = None    # id зелья или "heal" - случайное лечебное
    item: bool = False           # вещь уровня зоны
    ore: int = 0                 # кусков руды кольца
    damage: list[float] | None = None  # [мин, макс] % макс. HP; не убивает
    ruin: bool = False           # HP до 1% и потеря части трофеев
    combat: str | None = None    # "ambush" - обычная засада, "elite" - матёрая тварь
    bonus: float = 0.0           # награда за победу над элитой, в мобах
    effect: str | None = None    # id эффекта на N боёв
    trail: str | None = None     # id следа


class Requirement(BaseModel):
    """Требование к выбору или его цена (одни и те же поля)."""

    base_class: str | None = None
    subclass: str | None = None
    gold: float = 0.0            # в «мобах» золота
    gems: int = 0
    elixir: str | None = None    # id или "heal"
    trophy: bool = False         # любой один трофей


class Check(BaseModel):
    stat: str
    difficulty: str = "normal"


class Choice(BaseModel):
    label: str
    requires: Requirement | None = None
    cost: Requirement | None = None
    check: Check | None = None
    #: Без проверки: один исход или взвешенный список.
    result: SceneResult | None = None
    outcomes: list[SceneResult] = Field(default_factory=list)
    #: С проверкой (или классовой кнопкой): успех/провал.
    success: SceneResult | None = None
    failure: SceneResult | None = None


class Riddle(BaseModel):
    q: str
    a: list[str]


class Scene(BaseModel):
    type: str = "choice"
    text: str = ""
    choices: list[Choice] = Field(default_factory=list)
    # push
    loot: str = "trophy"               # trophy | gold | ore
    step_reward: float = 0.5
    risks: list[float] = Field(default_factory=list)
    pull_label: str = "Ещё"
    stop_label: str = "Хватит"
    pull_texts: list[str] = Field(default_factory=list)
    stop_text: str = ""
    fail_light: str = ""
    fail_heavy: str = ""
    fail_ruin: str = ""
    # timer
    seconds: int = 8
    button: str = "Действовать!"
    success: SceneResult | None = None
    timeout: SceneResult | None = None
    # riddle
    riddles: list[Riddle] = Field(default_factory=list)
    failure: SceneResult | None = None
    giveup_label: str = "Сдаться"
    # dice
    currency: str = "gold"             # gold | gems
    stakes: list[float] = Field(default_factory=list)
    win_chance: float = 0.47
    rounds: int = 3
    leave_label: str = "Уйти"
    win_text: str = ""
    lose_text: str = ""
    leave_text: str = ""


class SceneEvent(BaseModel):
    id: str
    title: str
    tier: str                          # medium | deep | finale
    weight: float = 1.0
    rings: list[int] | None = None
    regions: list[str] | None = None
    min_level: int = 1
    start: str = "start"
    scenes: dict[str, Scene]


class TrailDef(BaseModel):
    title: str
    emoji: str = "🐾"
    hint: str
    minutes: int = 25
    finale: str
    #: Ложный след: финал ведёт к новому следу, до stages отрезков.
    stages: int = 1
    cold_text: str = "След остыл."


class EffectDef(BaseModel):
    name: str
    emoji: str = "✨"
    fights: int
    modifiers: dict[str, float] = Field(default_factory=dict)
    trophy_bonus: float = 0.0          # +доля бросков трофеев с мобов
    text: str = ""


class SceneContent(BaseModel):
    events: list[SceneEvent]
    trails: dict[str, TrailDef]
    effects: dict[str, EffectDef]


_content: SceneContent | None = None


def load(content_dir: Path = CONTENT_DIR) -> SceneContent:
    return SceneContent(**_load_json_dict(content_dir / "events" / "scenes.json"))


def content() -> SceneContent:
    global _content
    if _content is None:
        _content = load()
    return _content


def event_by_id(event_id: str) -> SceneEvent | None:
    return next((e for e in content().events if e.id == event_id), None)


# --- Выбор события ----------------------------------------------------------------


def roll_tier(rng: random.Random) -> str:
    tiers = list(TIER_WEIGHTS)
    return rng.choices(tiers, weights=[TIER_WEIGHTS[t] for t in tiers])[0]


def eligible(event: SceneEvent, ring: int, region: str, level: int) -> bool:
    return (
        (event.rings is None or ring in event.rings)
        and (event.regions is None or region in event.regions)
        and level >= event.min_level
    )


def pick_event(rng: random.Random, tier: str, ring: int, region: str, level: int) -> SceneEvent | None:
    pool = [e for e in content().events if e.tier == tier and eligible(e, ring, region, level)]
    if not pool:
        return None
    return rng.choices(pool, weights=[e.weight for e in pool])[0]


def pick_result(rng: random.Random, outcomes: list[SceneResult]) -> SceneResult:
    return rng.choices(outcomes, weights=[o.weight for o in outcomes])[0]


# --- Проверки ---------------------------------------------------------------------


def check_chance(stat: str, stats: dict[str, int], difficulty: str = "normal") -> float:
    """stats - итоговые статы с экипировкой: {"str": .., "agi": .., ...}."""
    total = sum(max(v, 0) for v in stats.values()) or 1
    share = max(stats.get(stat, 0), 0) / total
    chance = CHECK_BASE.get(difficulty, CHECK_BASE["normal"]) + CHECK_SLOPE * (share - 0.2)
    return max(CHECK_MIN, min(CHECK_MAX, chance))


def meets(req: Requirement | None, base_class: str, subclass: str | None) -> bool:
    """Классовая часть требования. Ресурсы (золото/зелье/трофей) проверяет сервис."""
    if req is None:
        return True
    return not (
        (req.base_class and req.base_class != base_class)
        or (req.subclass and req.subclass != subclass)
    )


# --- «Ещё чуть-чуть» ---------------------------------------------------------------


def push_risk(scene: Scene, step: int) -> float:
    """Риск шага step (1 - первый рывок)."""
    if not scene.risks:
        return 0.5
    return scene.risks[min(step, len(scene.risks)) - 1]


def push_penalty(step: int) -> str:
    """Чем обернулся срыв на шаге step: light - теряешь только этот рывок,
    heavy - всё накопленное и урон, ruin - HP до 1% и часть трофеев."""
    if step <= 2:
        return "light"
    if step <= 4:
        return "heavy"
    return "ruin"


# --- Кости ------------------------------------------------------------------------


def roll_dice(rng: random.Random, win_chance: float) -> tuple[bool, tuple[int, int], tuple[int, int]]:
    """(выиграл ли, кости игрока, кости соперника). Исход решает win_chance;
    кости подбираются под исход, чтобы картинка не спорила с результатом."""
    won = rng.random() < win_chance
    while True:
        mine = (rng.randint(1, 6), rng.randint(1, 6))
        theirs = (rng.randint(1, 6), rng.randint(1, 6))
        if (sum(mine) > sum(theirs)) == won and sum(mine) != sum(theirs):
            return won, mine, theirs


# --- Загадки ----------------------------------------------------------------------


def normalize_answer(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s-]", " ", text)
    return " ".join(text.split())


def answer_matches(text: str, answers: list[str]) -> bool:
    """Ответ засчитан, если одно из верных слов встречается в ответе целиком:
    «это тень» и «Тень!» - верно, «тенёк» - нет."""
    words = set(normalize_answer(text).split())
    given = normalize_answer(text)
    for answer in answers:
        norm = normalize_answer(answer)
        if " " in norm:
            if norm in given:
                return True
        elif norm in words:
            return True
    return False


# --- Следы ------------------------------------------------------------------------

TRAIL_MIN_CELLS = 3
TRAIL_MAX_CELLS = 7


def pick_trail_cell(rng: random.Random, x: int, y: int) -> tuple[int, int] | None:
    """Клетка следа: 3-7 клеток пути, в том же кольце или ближе к центру,
    не город и не Монолит."""
    ring = grid.ring_tier(x, y)
    options = [
        (cx, cy)
        for cx in range(x - TRAIL_MAX_CELLS, x + TRAIL_MAX_CELLS + 1)
        for cy in range(y - TRAIL_MAX_CELLS, y + TRAIL_MAX_CELLS + 1)
        if TRAIL_MIN_CELLS <= grid.cells_between(x, y, cx, cy) <= TRAIL_MAX_CELLS
        and grid.in_bounds(cx, cy)
        and grid.ring_tier(cx, cy) >= ring
        and grid.city_region_at(cx, cy) is None
        and (cx, cy) != (0, 0)
    ]
    return rng.choice(options) if options else None


def ring_rolls(x: int, y: int) -> int:
    """Бросков трофеев у моба этой клетки (для награды «в мобах»)."""
    from game.economy import loot_config as lc

    return lc.ROLLS_BY_RING[wc.ring_tier_for_dist(grid.monolith_distance(x, y))]
