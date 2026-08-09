"""Загрузка и Pydantic-валидация игрового контента из content/*.json."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

CONTENT_DIR = Path(__file__).resolve().parent.parent / "content"


class MobDef(BaseModel):
    id: str
    name: str
    level: int = 1
    stats: dict[str, int] = Field(default_factory=dict)  # str/agi/int/vit/wil


class ItemDef(BaseModel):
    id: str
    name: str
    slot: str
    tier: str = "gray"
    base_stats: dict[str, int] = Field(default_factory=dict)


BUFF_CATEGORIES = {"damage", "defense", "control_utility", "group_support"}


class BuffDef(BaseModel):
    """Микробафф (п.7 дизайна): пул 12-15 на подкласс, категории обязательны
    к разнообразию при сборке пресета. Конкретные значения — TODO: content."""

    id: str
    name: str
    subclass: str | None = None  # id подкласса-владельца пула; None — общий
    category: str = "damage"     # damage | defense | control_utility | group_support
    description: str = ""
    stat_modifiers: dict[str, float] = Field(default_factory=dict)
    duration_ticks: int = 1


class StarterRingMob(BaseModel):
    """Моб стартового кольца (content/mobs/starter_ring.json).

    Флейвор-текст показывается игроку при встрече ПЕРЕД боем. zone_min/max —
    диапазон уровней зоны, в который клампится уровень моба под игрока.
    primary_stat (патч 26) — основной боевой стат по теме моба (str/agi/int),
    определяет и специализацию распределения статов, и формулу урона;
    по умолчанию str, если не задан в контенте.
    """

    id: str
    name: str
    flavor: str
    region: str
    zone_min: int
    zone_max: int
    primary_stat: str = "str"
    # ID фото альбома сообщества ВК (без owner_id) — см. bot/vk_media.py::photo_attachment.
    # None — картинки для этого моба ещё нет, показываем бой без вложения.
    image: str | None = None


def _load_mob_file(filename: str, content_dir: Path) -> dict[str, list[StarterRingMob]]:
    with (content_dir / "mobs" / filename).open(encoding="utf-8") as f:
        raw = json.load(f)
    result: dict[str, list[StarterRingMob]] = {}
    for region, mobs in raw.items():
        if region.startswith("_"):
            continue
        result[region] = [StarterRingMob(region=region, **m) for m in mobs]
    return result


def load_starter_ring(content_dir: Path = CONTENT_DIR) -> dict[str, list[StarterRingMob]]:
    """Возвращает {region: [мобы]} из content/mobs/starter_ring.json (кольцо 1-15)."""
    return _load_mob_file("starter_ring.json", content_dir)


_MOB_FILES = (
    "starter_ring.json", "ring_16_30.json", "ring_31_45.json", "ring_46_60.json", "ring_center.json",
)


def load_bestiary(content_dir: Path = CONTENT_DIR) -> dict[str, list[StarterRingMob]]:
    """Все кольца карты (патч 15): мержит мобов всех content/mobs/*.json по
    региону (+ отдельный ключ "any" для общих мобов центра)."""
    merged: dict[str, list[StarterRingMob]] = {}
    for filename in _MOB_FILES:
        for region, mobs in _load_mob_file(filename, content_dir).items():
            merged.setdefault(region, []).extend(mobs)
    return merged


class QuestDef(BaseModel):
    """Определение квеста (content/quests.json) — единственный источник правды
    и для сида миграции, и для тестов (никакого дублирования чисел)."""

    code: str
    region: str
    title: str
    progress_label: str
    target_count: int
    xp_reward: int
    gold_reward: int


def load_quest_defs(content_dir: Path = CONTENT_DIR) -> list[QuestDef]:
    return [QuestDef(**raw) for raw in _load_json(content_dir / "quests.json")]


class BaseSkillDef(BaseModel):
    """Базовый навык класса (content/skills/base_skills.json)."""

    id: str
    name: str
    multiplier: float
    cd: int
    effect: str | None = None
    effect_value: float = 0.0
    effect_duration: int = 0
    flavor: str = ""


def load_base_skills(content_dir: Path = CONTENT_DIR) -> dict[str, list[BaseSkillDef]]:
    """{base_class: [навыки]} из content/skills/base_skills.json."""
    with (content_dir / "skills" / "base_skills.json").open(encoding="utf-8") as f:
        raw = json.load(f)
    return {
        cls: [BaseSkillDef(**s) for s in skills]
        for cls, skills in raw.items()
        if not cls.startswith("_")
    }


class TrophyDef(BaseModel):
    """Градация трофея (content/trophies.json, патч 9) — стакающийся ресурс,
    не отдельные предметы."""

    id: str
    emoji: str
    name: str
    sell_price: int
    description: str = ""


def load_trophy_defs(content_dir: Path = CONTENT_DIR) -> list[TrophyDef]:
    """Порядок в списке = порядок вывода (от дешёвых к дорогим, как в файле)."""
    return [TrophyDef(**raw) for raw in _load_json(content_dir / "trophies.json")]


class ElixirDef(BaseModel):
    """Зелье/эликсир (content/items/elixirs.json, патч 16) — каталог (имя/эмодзи/
    описание); цены и числовые эффекты — в game/economy/elixir_config.py."""

    id: str
    name: str
    emoji: str
    category: str  # "heal" | "combat"
    description: str = ""


def load_elixirs(content_dir: Path = CONTENT_DIR) -> dict[str, ElixirDef]:
    return {
        raw["id"]: ElixirDef(**raw)
        for raw in _load_json(content_dir / "items" / "elixirs.json")
    }


class EventOutcome(BaseModel):
    """Исход выбора в событии исследования (патч 9 блок 1, патч 10 блок 3).
    Эффекты комбинируемы: напр. trophy=True И damage_max_pct>0 одновременно
    (Пепельный алтарь: "трофей гарантированно + урон"). Пустых исходов
    ("ничего не произошло") с патча 10 не бывает — только trophy/xp/damage/combat."""

    weight: float
    text: str = ""
    trophy: bool = False
    xp: bool = False
    xp_big: bool = False  # "крупнее обычного" опыт — рискованный выбор (EVENT_XP_RISKY)
    damage_min_pct: float = 0.0
    damage_max_pct: float = 0.0
    combat: bool = False  # засада — переход в бой


class EventChoiceDef(BaseModel):
    label: str
    outcomes: list[EventOutcome]


class ExplorationEventDef(BaseModel):
    """Событие после исследования с выбором (content/events/exploration.json)."""

    id: str
    title: str
    text: str
    choices: list[EventChoiceDef]


def load_exploration_events(content_dir: Path = CONTENT_DIR) -> list[ExplorationEventDef]:
    return [
        ExplorationEventDef(**raw)
        for raw in _load_json(content_dir / "events" / "exploration.json")
    ]


class LocationTypeDef(BaseModel):
    """Тип локации (content/locations/types.json, патч 10, блок 4) — 4 на регион.
    Тип клетки детерминирован по координатам (см. game/world/location_types.py):
    одна и та же клетка всегда одного типа. `image` — задел под картинки, пока
    всегда пусто."""

    id: str
    region: str
    name: str
    descriptions: list[str]
    image: str | None = None


def load_location_types(content_dir: Path = CONTENT_DIR) -> list[LocationTypeDef]:
    return [LocationTypeDef(**raw) for raw in _load_json(content_dir / "locations" / "types.json")]


class ItemBaseDef(BaseModel):
    """Базовое название экипировки по слоту (content/items/bases.json,
    патч 11). gender согласует суффикс редкости: m|f|pl."""

    name: str
    gender: str


class ItemRaritySuffix(BaseModel):
    m: str | None = None
    f: str | None = None
    pl: str | None = None
    invariant: str | None = None  # легендарная: родительный падеж, ставится ПОСЛЕ базы


class ItemRarityDef(BaseModel):
    """Редкость базовой экипировки (content/items/rarities.json, патч 11) —
    id ключом в JSON, тот же порядок градаций, что у трофеев (патч 9)."""

    id: str = ""  # проставляется при загрузке (ключ словаря в JSON)
    emoji: str
    name: str
    mult: float
    suffix: ItemRaritySuffix


def _load_json_dict(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_item_bases(content_dir: Path = CONTENT_DIR) -> dict[str, list[ItemBaseDef]]:
    """{slot: [базы]} из content/items/bases.json."""
    raw = _load_json_dict(content_dir / "items" / "bases.json")
    return {
        slot: [ItemBaseDef(**b) for b in bases]
        for slot, bases in raw.items()
        if not slot.startswith("_")
    }


def load_item_rarities(content_dir: Path = CONTENT_DIR) -> dict[str, ItemRarityDef]:
    """{rarity_id: определение} из content/items/rarities.json, в порядке файла
    (от обычной к легендарной — важно для сортировки инвентаря/скупщика)."""
    raw = _load_json_dict(content_dir / "items" / "rarities.json")
    return {
        rarity_id: ItemRarityDef(id=rarity_id, **data)
        for rarity_id, data in raw.items()
        if not rarity_id.startswith("_")
    }


class AdminWeaponDef(BaseModel):
    """Тестовый предмет админки (патч 34, ч.3, content/items/admin_items.json)
    — ФИКСИРОВАННЫЕ статы, не через item_gen.generate_item (та процедурная
    система про него ничего не знает — только так и гарантируется, что он
    не может выпасть из обычного дропа)."""

    id: str
    name: str
    slot: str
    rarity: str
    stats: dict[str, int]
    flavor: str


def load_admin_weapons(content_dir: Path = CONTENT_DIR) -> list[AdminWeaponDef]:
    raw = _load_json_dict(content_dir / "items" / "admin_items.json")
    return [AdminWeaponDef(**w) for w in raw.get("weapons", [])]


class ClassTrialDef(BaseModel):
    """Классовое испытание (content/quests/class_trials.json, патч 12):
    условие открытия одного микробаффа подкласса. id испытания == id баффа
    (связь 1:1 — каждое испытание открывает ровно один бафф).
    condition_type/params — параметры для services/trial_service.py."""

    id: str
    buff_id: str
    subclass: str
    condition_type: str
    params: dict = Field(default_factory=dict)
    text: str = ""


def load_class_trials(content_dir: Path = CONTENT_DIR) -> list[ClassTrialDef]:
    return [
        ClassTrialDef(**raw)
        for raw in _load_json(content_dir / "quests" / "class_trials.json")
    ]


class StoryNamedEnemyDef(BaseModel):
    """Named-враг сюжетной сцены (патч 18) — обычный моб по формуле силы,
    но с уникальным именем/флейвором и множителем к статам (не босс).

    Патч 36: картинка — сначала своя (image), иначе унаследованная от
    базового моба бестиария (base_mob_id). Общее правило: любая производная
    сущность (усиленный моб, сюжетная версия, будущие элиты/боссы) наследует
    визуал и флейвор базовой, если своих не задано — не требовать картинку
    для каждого варианта контента вручную."""

    name: str
    flavor: str = ""
    stat_mult: float | None = None  # None → game.economy.story_config.NAMED_ENEMY_STAT_MULT_DEFAULT
    image: str | None = None
    base_mob_id: str | None = None  # id из content/mobs/*.json — источник картинки, если своей нет


class StoryQuestDef(BaseModel):
    """Шаг региональной сюжетной линии (content/story/<region>.json).

    kind:
      - "first_quest"   — существующий квест «убей 10» (services/quest_service.py),
                          встроенный в сюжет как квест 1.1; transition_text
                          добавляется к похвале наставника при завершении.
      - "travel_combat" — зона-цель на карте (target_x/y + radius из конфига);
                          по прибытии — arrival_text (+ бой с named_enemy, если
                          задан); chain_length>1 — серия боёв подряд (патч 18,
                          квест 2.2 «Свидетель»), без города между ними;
                          return_text — при возврате к наставнику после победы.
      - "city_scene"    — разрешается сразу в разговоре с наставником, без
                          похода на карту (assign_text — цельная сцена).
      - "subclass_gate" — сюжет ставится на паузу до выбора подкласса
                          (патч 12); продолжается автоматически хуком в
                          bot/handlers/list_keeper.py после выбора пути.
    """

    id: str
    kind: str
    title: str
    assign_text: str = ""
    target_x: int | None = None
    target_y: int | None = None
    target_label: str = ""
    direction_hint: str = ""
    arrival_text: str = ""
    named_enemy: StoryNamedEnemyDef | None = None
    chain_length: int = 1
    return_text: str = ""
    transition_text: str = ""
    xp_reward: int = 0
    gold_reward: int = 0


class StoryActDef(BaseModel):
    act: int
    title: str
    level_min: int
    level_max: int
    quests: list[StoryQuestDef]


class StoryLineDef(BaseModel):
    """Региональная сюжетная линия целиком (content/story/<region>.json)."""

    region: str
    acts: list[StoryActDef]


def load_story_line(region: str, content_dir: Path = CONTENT_DIR) -> StoryLineDef:
    raw = _load_json_dict(content_dir / "story" / f"{region}.json")
    return StoryLineDef(**raw)


class DailyQuestDef(BaseModel):
    """Ежедневное задание (content/quests/dailies.json, патч 23) — пул, из
    которого каждый день выбираются 3 случайных. base_target масштабируется
    по уровню игрока (game.economy.dailies_config.scaled_target); условие
    прогресса — services/daily_service.py (condition_type/params)."""

    id: str
    title: str
    progress_label: str
    condition_type: str
    base_target: int
    min_level: int = 1
    params: dict = Field(default_factory=dict)


def load_daily_quests(content_dir: Path = CONTENT_DIR) -> list[DailyQuestDef]:
    return [
        DailyQuestDef(**raw)
        for raw in _load_json(content_dir / "quests" / "dailies.json")
    ]


class LootboxRewardPart(BaseModel):
    """Один компонент награды Пепельного ларца (патч 24). Варианты внутри
    градации — список СПИСКОВ частей: обычно 1 часть, иногда комбо (напр.
    трофей + эликсир у 🟠). type: gold|gems|elixir|elixir_random_combat|trophy."""

    type: str
    trophy_id: str | None = None
    elixir_id: str | None = None
    min: int = 0
    max: int = 0


class LootboxGradeDef(BaseModel):
    """Градация Пепельного ларца (content/lootbox/ashen_chest.json, патч 24).
    chance — базовая вероятность (сумма по всем градациям = 1.0); буст от
    длины стрика — game.economy.lootbox_config."""

    id: str
    emoji: str
    name: str
    chance: float
    options: list[list[LootboxRewardPart]]


def load_lootbox_grades(content_dir: Path = CONTENT_DIR) -> list[LootboxGradeDef]:
    return [
        LootboxGradeDef(**raw)
        for raw in _load_json(content_dir / "lootbox" / "ashen_chest.json")
    ]


class MountDef(BaseModel):
    """Маунт (content/mounts/mounts.json, патч 25, п.7). rarity — ключ в
    game.economy.mount_config (сек/клетка, шанс нападения)."""

    id: str
    name: str
    rarity: str
    flavor: str = ""


def load_mounts(content_dir: Path = CONTENT_DIR) -> dict[str, MountDef]:
    return {
        raw["id"]: MountDef(**raw)
        for raw in _load_json(content_dir / "mounts" / "mounts.json")
    }


class GameContent(BaseModel):
    mobs: dict[str, MobDef]
    items: dict[str, ItemDef]
    buffs: dict[str, BuffDef]


def _load_json(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_npc_texts(npc_id: str, content_dir: Path = CONTENT_DIR) -> dict:
    """Реплики системного NPC из content/npc/<npc_id>.json.

    Тексты NPC хранятся контентом, а не хардкодом в хендлерах —
    Хранитель Списков будет появляться и вне онбординга (подкласс,
    ресет класса, смерть), файл будет пополняться.
    """
    path = content_dir / "npc" / f"{npc_id}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_content(content_dir: Path = CONTENT_DIR) -> GameContent:
    mobs = [MobDef(**raw) for raw in _load_json(content_dir / "mobs.json")]
    items = [ItemDef(**raw) for raw in _load_json(content_dir / "items.json")]
    buffs = [BuffDef(**raw) for raw in _load_json(content_dir / "buffs.json")]
    return GameContent(
        mobs={m.id: m for m in mobs},
        items={i.id: i for i in items},
        buffs={b.id: b for b in buffs},
    )
