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
    """

    id: str
    name: str
    flavor: str
    region: str
    zone_min: int
    zone_max: int


def load_starter_ring(content_dir: Path = CONTENT_DIR) -> dict[str, list[StarterRingMob]]:
    """Возвращает {region: [мобы]} из content/mobs/starter_ring.json."""
    with (content_dir / "mobs" / "starter_ring.json").open(encoding="utf-8") as f:
        raw = json.load(f)
    result: dict[str, list[StarterRingMob]] = {}
    for region, mobs in raw.items():
        if region.startswith("_"):
            continue
        result[region] = [StarterRingMob(region=region, **m) for m in mobs]
    return result


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


class EventOutcome(BaseModel):
    """Исход выбора в событии исследования (патч 9, блок 1). Эффекты
    комбинируемы: напр. trophy=True И damage_max_pct>0 одновременно
    (Пепельный алтарь: "трофей гарантированно + урон")."""

    weight: float
    text: str = ""
    trophy: bool = False
    xp: bool = False
    song: bool = False  # гарантированный обрывок Песни (не 50/50 с замечанием)
    flavor: bool = False  # гарантированный обрывок Песни ИЛИ замечание (50/50)
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
