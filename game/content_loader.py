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
    # Патч 48: честная пометка — бафф реально влияет на бой (True) или ещё
    # заглушка (False, дефолт). Игрок видит "⚙️ в разработке" во вкладке
    # «Испытания», пока флаг не станет True для этого id.
    implemented: bool = False


class MobTraitDef(BaseModel):
    """Одна механика способности моба (патч 103). Смысл полей зависит от kind
    и описан в game/combat/mob_abilities.py - там же список допустимых kind.

    Поля общие, а не отдельный класс на каждый kind: механик под тридцать, и
    контент читается проще, когда у всех одинаковые имена (value/chance/...).
    """

    kind: str
    value: float = 0.0       # основная величина: доля, шанс уворота, % здоровья
    chance: float = 1.0      # шанс срабатывания при ударе
    duration: int = 0        # ходов у наложенного эффекта
    period: int = 0          # раз в сколько ходов
    mult: float = 1.0        # множитель урона
    threshold: float = 0.0   # порог по доле здоровья
    step: float = 0.0        # прирост за ход
    cap: float = 0.0         # потолок прироста
    effect: str = ""         # dot | weaken | vulnerability


class MobAbilityDef(BaseModel):
    """Способность моба (патч 103): чем он отличается от остальных в бою.

    title и hint видит игрок - hint одной строкой перед боем, чтобы моба
    узнавали по поведению, а не угадывали. traits - механики; у мобов
    центра их две, у остальных обычно одна.
    """

    title: str
    hint: str
    traits: list[MobTraitDef]


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
    # Патч 103: способность. None допустим только технически - у каждого
    # моба бестиария она есть, за этим следит тест.
    ability: MobAbilityDef | None = None


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


class SubclassSkillDef(BaseModel):
    """Навык подкласса (content/skills/subclass_skills.json, патч 39, ч.3):
    заменяет базовые навыки класса после выбора подкласса на 30 ур."""

    id: str
    name: str
    subclass_id: str
    multiplier: float
    cd: int
    effect: str | None = None
    effect_value: float = 0.0
    effect_duration: int = 0
    flavor: str = ""


def load_subclass_skills(content_dir: Path = CONTENT_DIR) -> dict[str, list[SubclassSkillDef]]:
    """{subclass_id: [навыки]} из content/skills/subclass_skills.json."""
    with (content_dir / "skills" / "subclass_skills.json").open(encoding="utf-8") as f:
        raw = json.load(f)
    defs = [SubclassSkillDef(**s) for k, s in raw.items() if not k.startswith("_")]
    by_subclass: dict[str, list[SubclassSkillDef]] = {}
    for skill in defs:
        by_subclass.setdefault(skill.subclass_id, []).append(skill)
    return by_subclass


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
    #: Патч 58: исход продаёт садок рыбаку. Множитель цены зависит от
    #: кольца КЛЕТКИ, где выпал ивент (fishing_config.BUYER_EVENT_MARKUP),
    #: и разыгрывается при ПОКАЗЕ события — иначе игрок соглашался бы на
    #: сделку, не зная цены.
    fish_buyer: bool = False


class EventChoiceDef(BaseModel):
    label: str
    outcomes: list[EventOutcome]


class ExplorationEventDef(BaseModel):
    """Событие после исследования с выбором (content/events/exploration.json)."""

    id: str
    title: str
    text: str
    choices: list[EventChoiceDef]
    #: Патч 58: событие торгует рыбой. Раньше оно ещё и не выпадало без рыбы
    #: в садке, но порог оказался ловушкой: на стартовых озёрах рыба мелкая,
    #: и новичок просто никогда не встречал рыбака. Теперь событие выпадает
    #: всегда, а пустой садок — отдельная короткая сцена (empty_text ниже),
    #: которая сразу возвращает игрока к панели локации.
    fish_trade: bool = False
    #: Что рыбак говорит, когда продавать нечего. Выбора в этой сцене нет:
    #: предлагать «продать» с пустым садком было бы издевательством.
    empty_text: str = ""
    #: Патч 59: мелкая рудная жила. Выбора нет и здесь — вместо него приходит
    #: инлайн-кнопка «Добыть», потому что добыча это не мгновенный исход, а
    #: процесс на несколько минут, который блокирует игрока.
    ore_vein: bool = False


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


class FishDef(BaseModel):
    """Вид рыбы (content/fishing/fish.json, патч 58) — каталог: имя/эмодзи/лор.

    Числа (диапазон веса, цена за килограмм, пулы озёр) намеренно НЕ здесь, а
    в game/economy/fishing_config.py: их правит симулятор при калибровке, и
    перезапись контентного файла из тулзы затирала бы лор.
    """

    id: str
    emoji: str
    name: str
    tier: int
    description: str = ""


def load_fish_defs(content_dir: Path = CONTENT_DIR) -> list[FishDef]:
    """Порядок в списке = порядок вывода (от дешёвых к дорогим, как в файле)."""
    return [FishDef(**raw) for raw in _load_json(content_dir / "fishing" / "fish.json")]


class LakeDef(BaseModel):
    """Озеро (content/fishing/lakes.json, патч 58) — клетка с фиксированными
    координатами, а не процедурный тип локации.

    Выбор осознанный: процедурные озёра были бы безликими и взаимозаменяемыми,
    а именованные с постоянными координатами игроки запоминают и передают друг
    другу. `tier` обязан соответствовать кольцу сложности своих координат —
    это проверяет tests/test_fishing_content.py.

    region = None у общих озёр внутренних колец: они не принадлежат ни одной
    фракции, туда ходят все и там встречаются.
    """

    id: str
    x: int
    y: int
    tier: int
    name: str
    descriptions: list[str]
    region: str | None = None
    image: str | None = None


def load_lakes(content_dir: Path = CONTENT_DIR) -> list[LakeDef]:
    return [LakeDef(**raw) for raw in _load_json(content_dir / "fishing" / "lakes.json")]


class WorldBossDef(BaseModel):
    """Мировой босс (content/world_bosses.json, патч 104).

    Только облик: имя, описание, картинка. Сила и награда от босса не
    зависят - их задаёт кольцо, где он появился
    (game/economy/world_boss_config.py). Привязки к региону нет.
    """

    id: str
    name: str
    flavor: str
    image: str = ""


def load_world_bosses(content_dir: Path = CONTENT_DIR) -> list[WorldBossDef]:
    return [WorldBossDef(**raw) for raw in _load_json(content_dir / "world_bosses.json")]


class OreDef(BaseModel):
    """Вид руды (content/mining/ores.json, патч 59) — каталог: имя/эмодзи/лор.

    Числа (пулы рудников, градации, время, опыт) — в
    game/economy/mining_config.py, как и у рыбы.
    """

    id: str
    emoji: str
    name: str
    tier: int
    description: str = ""


def load_ore_defs(content_dir: Path = CONTENT_DIR) -> list[OreDef]:
    return [OreDef(**raw) for raw in _load_json(content_dir / "mining" / "ores.json")]


class MineDef(BaseModel):
    """Рудник (content/mining/mines.json, патч 59) — клетка с фиксированными
    координатами, по той же логике, что озёра, но в других местах.

    Отличие от озера: рудник не бесконечен. Сколько в нём сейчас руды —
    состояние мира (таблица mine_veins), общее для всех игроков, а не
    свойство контента. `tier` обязан совпадать с кольцом своих координат.
    """

    id: str
    x: int
    y: int
    tier: int
    name: str
    descriptions: list[str]
    region: str | None = None
    image: str | None = None


def load_mines(content_dir: Path = CONTENT_DIR) -> list[MineDef]:
    return [MineDef(**raw) for raw in _load_json(content_dir / "mining" / "mines.json")]


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


class UniqueItemDef(BaseModel):
    """Уникальный предмет (патч 53, content/items/unique_items.json) —
    ФИКСИРОВАННЫЕ статы, как AdminWeaponDef: не через item_gen.generate_item,
    только явная выдача по id (services/raid_service.py). power — очки
    основного стата класса получателя (100% в один стат, как у обычного
    оружия) — фактический base_stats собирается в момент выдачи, не здесь."""

    id: str = ""  # проставляется при загрузке (ключ словаря в JSON)
    name: str
    slot: str
    power: int
    flavor: str = ""


def load_unique_items(content_dir: Path = CONTENT_DIR) -> dict[str, UniqueItemDef]:
    raw = _load_json_dict(content_dir / "items" / "unique_items.json")
    return {
        item_id: UniqueItemDef(id=item_id, **data)
        for item_id, data in raw.items()
        if not item_id.startswith("_")
    }


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
    """Акт региональной линии.

    image - иллюстрация акта: показывается ОДИН раз, вместе с выдачей первого
    задания акта. Дальше внутри акта её не повторяют, иначе она перестанет
    что-либо значить.

    У акта 1 картинки нет намеренно: его первое задание выдаёт наставник
    (kind="first_quest", им ведает services/quest_service.py), и к тому
    сообщению уже прикреплён портрет наставника. Две картинки в одном
    сообщении не поместятся, а портрет там уместнее.
    """

    act: int
    title: str
    level_min: int
    level_max: int
    image: str | None = None
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


class CraftOutputDef(BaseModel):
    """Один из трёх результатов перековки (content/crafting/recipes.json)."""

    name: str
    gender: str = "m"
    flavor: str = ""


class CraftRecipeDef(BaseModel):
    """Что получается из предмета-источника (патч 72).

    Ключ рецепта = id уникального предмета из content/items/unique_items.json.
    Числа (бюджет очков, веса специализаций, цена, эффективность) живут в
    game/economy/craft_config.py — здесь только контент, как у рыбы и руды.
    """

    source_name: str
    outputs: dict[str, CraftOutputDef]


def load_craft_recipes(content_dir: Path = CONTENT_DIR) -> dict[str, CraftRecipeDef]:
    raw = _load_json(content_dir / "crafting" / "recipes.json")
    return {
        key: CraftRecipeDef(**value)
        for key, value in raw.items()
        if not key.startswith("_")
    }
