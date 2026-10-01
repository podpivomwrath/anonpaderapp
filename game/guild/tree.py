"""Древо гильдии: три ветви (Война, Промысел, Братство), в каждой 51 малый
узел, 10 средних и 3 ключевых.

Древо строится КОДОМ, детерминированно, а не лежит контентным файлом: узлов
почти двести, и у каждого координаты для мини-аппа и связи с соседями.
Руками такой файл не правят, а сгенерированный рядом с генератором однажды
разошёлся бы с ним. Id узлов стабильны (ветвь, рука, позиция), поэтому
взятые узлы в базе переживают любые правки текстов и чисел.

Устройство ветви: корень (берётся бесплатно), от него три руки. Рука - цепь
из 21 узла: малые, средние на 6-й, 13-й и 19-й позиции и ключевой в конце.
Соседние руки сшиты перемычками у средних узлов, а между руками стоит ещё
по одному среднему узлу - так у древа есть развилки, как в Path of Exile,
а не три прямые дорожки.

Брать можно узел, соседний с уже взятым (или с корнем ветви).
"""

import math
from dataclasses import dataclass, field
from functools import lru_cache

# --- Эффекты -------------------------------------------------------------------
# key -> (подпись с {v}, единица: "%" | "ч" | "" , значение малого узла)
EFFECTS: dict[str, tuple[str, str, float]] = {
    # Война
    "garrison_power_pct": ("+{v}% к характеристикам стражей гарнизона в осаде", "%", 1.5),
    "siege_damage_pct": ("+{v}% к основной характеристике участников в осадном бою", "%", 0.5),
    "siege_defense_pct": ("-{v}% к урону, который участники получают в осадном бою", "%", 0.5),
    "siege_cost_pct": ("-{v}% к цене объявления осады", "%", 1.0),
    "claim_speed_pct": ("-{v}% к числу исследований, нужных для закладки знамени", "%", 1.0),
    "pvp_damage_pct": ("+{v}% к основной характеристике участников в любом PvP", "%", 0.2),
    "shield_hours": ("+{v} ч к щиту на клетке, взятой осадой", "ч", 1.0),
    "garrison_size": ("+{v} страж в гарнизоне каждой базы с казармами", "", 1.0),
    # Промысел
    "build_cost_pct": ("-{v}% к цене построек и перестройки баз в золоте", "%", 0.5),
    "build_time_pct": ("-{v}% ко времени стройки и перестройки баз", "%", 1.0),
    "shaft_speed_pct": ("+{v}% к скорости шахт на рудниках гильдии", "%", 2.0),
    "warehouse_pct": ("+{v}% к вместимости склада (руда и вещи)", "%", 2.0),
    "tithe_pct": ("+{v}% к десятине - золоту в казну за каждое исследование на землях гильдии", "%", 2.0),
    "sell_pct": ("+{v}% к выручке участников за реликвии у скупщика", "%", 0.3),
    "prayer_cost_pct": ("-{v}% к цене молитвы в часовне", "%", 1.0),
    "totem_drop_pct": ("+{v}% к шансу тотема удвоить трофеи с моба в своей ауре 3x3", "%", 0.1),
    "mining_speed_pct": ("-{v}% ко времени добычи руды участниками", "%", 0.3),
    # Братство
    "xp_pct": ("+{v}% опыта участникам (до 60 уровня)", "%", 0.3),
    "fame_pct": ("+{v}% славы гильдии с заданий и Стража", "%", 0.5),
    "daily_gold_pct": ("+{v}% золота за гильдейские ежедневки", "%", 2.0),
    "stat_pct": ("+{v}% ко всем характеристикам участников", "%", 0.05),
    "respawn_pct": ("-{v}% ко времени возрождения участников", "%", 0.5),
    "trophy_pct": ("+{v}% шанс на лишний бросок трофеев после победы над мобом", "%", 0.3),
    "key_chance_pct": ("+{v}% к шансу Ключа Монолита (от обычного шанса)", "%", 1.0),
}

#: Потолки суммарных эффектов - на случай будущих правок чисел древа.
EFFECT_CAPS: dict[str, float] = {
    "siege_defense_pct": 40, "siege_cost_pct": 60, "claim_speed_pct": 60,
    "build_cost_pct": 50, "build_time_pct": 60, "prayer_cost_pct": 60,
    "mining_speed_pct": 30, "respawn_pct": 50,
}


def effect_text(key: str, value: float) -> str:
    label, _unit, _small = EFFECTS[key]
    shown = f"{value:g}" if value != int(value) else str(int(value))
    return label.format(v=shown)


# --- Ветви ----------------------------------------------------------------------
BRANCHES = ["war", "craft", "kin"]
BRANCH_TITLES = {"war": "Война", "craft": "Промысел", "kin": "Братство"}

#: Темы рук: малые узлы руки чередуют эти эффекты.
ARM_THEMES: dict[str, list[list[str]]] = {
    "war": [
        ["garrison_power_pct", "siege_defense_pct", "shield_hours"],
        ["siege_damage_pct", "pvp_damage_pct", "siege_cost_pct"],
        ["claim_speed_pct", "siege_cost_pct", "garrison_power_pct"],
    ],
    "craft": [
        ["shaft_speed_pct", "warehouse_pct", "mining_speed_pct"],
        ["tithe_pct", "sell_pct", "prayer_cost_pct"],
        ["build_cost_pct", "build_time_pct", "totem_drop_pct"],
    ],
    "kin": [
        ["xp_pct", "fame_pct", "daily_gold_pct"],
        ["stat_pct", "respawn_pct", "trophy_pct"],
        ["key_chance_pct", "trophy_pct", "xp_pct"],
    ],
}

#: Имена малых узлов по эффекту - берутся по кругу.
SMALL_NAMES: dict[str, list[str]] = {
    "garrison_power_pct": ["Выучка", "Строевой шаг", "Тяжёлые щиты", "Сторожевой паёк"],
    "siege_damage_pct": ["Таран", "Штурмовой клин", "Горячая смола"],
    "siege_defense_pct": ["Зубцы", "Двойная кладка", "Мокрые шкуры"],
    "siege_cost_pct": ["Свои подводы", "Наёмный обоз", "Трофейные лестницы"],
    "claim_speed_pct": ["Межевые камни", "Быстрые колья", "Разметка"],
    "pvp_damage_pct": ["Жажда схватки", "Злость", "Короткий клинок"],
    "shield_hours": ["Ночной караул", "Засека", "Рвы"],
    "build_cost_pct": ["Свой кирпич", "Бережливость", "Старые балки"],
    "build_time_pct": ["Артель", "Леса", "Ранний подъём"],
    "shaft_speed_pct": ["Крепь", "Водоотлив", "Вагонетки"],
    "warehouse_pct": ["Подвалы", "Стеллажи", "Опись"],
    "tithe_pct": ["Мытари", "Межевая пошлина", "Сборщики"],
    "sell_pct": ["Свой человек у скупщика", "Торговая хватка", "Весы без обмана"],
    "prayer_cost_pct": ["Свечной двор", "Певчие", "Ладан"],
    "totem_drop_pct": ["Резьба по кости", "Подношения", "Старые знаки"],
    "mining_speed_pct": ["Заточенные кайла", "Рудознатцы", "Чутьё на жилу"],
    "xp_pct": ["Наука старших", "Байки у костра", "Разбор боя"],
    "fame_pct": ["Глашатаи", "Слухи", "Песни о гильдии"],
    "daily_gold_pct": ["Жалованье", "Общий котёл", "Премия"],
    "stat_pct": ["Закалка", "Братская кровь", "Общая клятва"],
    "respawn_pct": ["Лекари", "Обереги", "Зов дома"],
    "trophy_pct": ["Зоркий глаз", "Мешки побольше", "Добытчики"],
    "key_chance_pct": ["Шёпот Монолита", "Ключники", "Счастливая монета"],
}

#: Средние узлы: (имя, {эффект: значение}). По 10 на ветвь: 9 на руках
#: (по три на руку) и 1 между руками.
NOTABLES: dict[str, list[tuple[str, dict[str, float]]]] = {
    "war": [
        ("Кованые ворота", {"garrison_power_pct": 6, "siege_defense_pct": 2}),
        ("Стража без сна", {"shield_hours": 4, "garrison_power_pct": 4}),
        ("Последний рубеж", {"siege_defense_pct": 4, "shield_hours": 3}),
        ("Боевой рог", {"siege_damage_pct": 3, "pvp_damage_pct": 1}),
        ("Знамёна вперёд", {"siege_damage_pct": 2, "siege_cost_pct": 5}),
        ("Кровавая жатва", {"pvp_damage_pct": 1.5, "siege_damage_pct": 2}),
        ("Землемеры", {"claim_speed_pct": 6, "siege_cost_pct": 3}),
        ("Обоз войны", {"siege_cost_pct": 6, "garrison_power_pct": 3}),
        ("Прирезанная земля", {"claim_speed_pct": 8}),
        ("Военный совет", {"siege_damage_pct": 1.5, "siege_defense_pct": 1.5, "garrison_power_pct": 3}),
    ],
    "craft": [
        ("Глубокий забой", {"shaft_speed_pct": 10, "mining_speed_pct": 1}),
        ("Амбары", {"warehouse_pct": 12, "shaft_speed_pct": 4}),
        ("Горная артель", {"mining_speed_pct": 2, "warehouse_pct": 6}),
        ("Дорожная пошлина", {"tithe_pct": 10, "sell_pct": 0.5}),
        ("Лавка при гильдии", {"sell_pct": 1.5, "tithe_pct": 4}),
        ("Свой приход", {"prayer_cost_pct": 6, "sell_pct": 0.5}),
        ("Зодческий цех", {"build_cost_pct": 3, "build_time_pct": 4}),
        ("Леса до неба", {"build_time_pct": 6, "build_cost_pct": 1}),
        ("Священная роща", {"totem_drop_pct": 0.6, "build_cost_pct": 1}),
        ("Гильдейская палата", {"tithe_pct": 5, "build_cost_pct": 1.5, "shaft_speed_pct": 4}),
    ],
    "kin": [
        ("Школа гильдии", {"xp_pct": 1.5, "fame_pct": 2}),
        ("Летописец", {"fame_pct": 4, "daily_gold_pct": 5}),
        ("Щедрая казна", {"daily_gold_pct": 10, "xp_pct": 0.5}),
        ("Плечом к плечу", {"stat_pct": 0.3, "respawn_pct": 2}),
        ("Знахарка", {"respawn_pct": 4, "trophy_pct": 0.5}),
        ("Удачливые руки", {"trophy_pct": 1.5, "stat_pct": 0.1}),
        ("Хранители ключей", {"key_chance_pct": 5, "trophy_pct": 0.5}),
        ("Добыча на всех", {"trophy_pct": 1.5, "xp_pct": 0.5}),
        ("Путь к Монолиту", {"key_chance_pct": 4, "xp_pct": 1}),
        ("Общий очаг", {"stat_pct": 0.2, "fame_pct": 2, "xp_pct": 0.5}),
    ],
}

#: Ключевые узлы: по одному в конце каждой руки.
KEYSTONES: dict[str, list[tuple[str, str, dict[str, float]]]] = {
    "war": [
        ("Железный гарнизон",
         "Для гильдии, которая держит землю. Каждая база с казармами выставляет при осаде на одного "
         "стража больше, а все стражи заметно крепче. Отбиться можно даже тогда, когда своих онлайн нет.",
         {"garrison_size": 1, "garrison_power_pct": 10}),
        ("Натиск",
         "Для гильдии, которая берёт чужое. Осады объявляются заметно дешевле, а участники под стенами "
         "бьют сильнее - выгодно осаждать часто.",
         {"siege_damage_pct": 5, "siege_cost_pct": 15}),
        ("Вечная стража",
         "Для гильдии, которой нужно удержать взятое. Захваченная клетка на сутки дольше закрыта щитом "
         "от ответной осады, а в осадном бою участники получают меньше урона.",
         {"shield_hours": 24, "siege_defense_pct": 5}),
    ],
    "craft": [
        ("Глубокие штольни",
         "Для гильдии с рудником. Шахта копает почти на треть быстрее, а склад вмещает в полтора раза "
         "больше руды и вещей - руда копится, пока вы заняты другим.",
         {"shaft_speed_pct": 30, "warehouse_pct": 50}),
        ("Десятина Монолита",
         "Для гильдии с большой землёй, по которой много ходят. Каждое исследование на ваших клетках - "
         "чьё угодно - приносит казне в полтора раза больше золота. Участники вдобавок дороже продают реликвии.",
         {"tithe_pct": 50, "sell_pct": 1}),
        ("Зодчие",
         "Для гильдии, которая строится. Постройки и перестройка баз дешевле в золоте и идут на четверть "
         "быстрее - базы растут к цитадели заметно скорее.",
         {"build_cost_pct": 10, "build_time_pct": 25}),
    ],
    "kin": [
        ("Наставничество",
         "Для гильдии, где много тех, кто ещё качается. Все участники получают больше опыта, а гильдия - "
         "больше славы с заданий и Стража, то есть быстрее растёт в уровне и очках древа.",
         {"xp_pct": 5, "fame_pct": 10}),
        ("Кровные узы",
         "Для всех. Каждый участник становится сильнее по всем характеристикам - в любом бою, PvE и PvP, - "
         "и быстрее возвращается после смерти.",
         {"stat_pct": 2, "respawn_pct": 10}),
        ("Вечное возвращение",
         "Для гильдии, которая ходит в рейды. Ключи Монолита выпадают у участников заметно чаще, "
         "а после победы над мобом чаще выпадают лишние трофеи.",
         {"key_chance_pct": 15, "trophy_pct": 3}),
    ],
}

KIND_SMALL = "small"
KIND_NOTABLE = "notable"
KIND_KEYSTONE = "keystone"
KIND_ROOT = "root"
POINTS = {KIND_SMALL: 1, KIND_NOTABLE: 2, KIND_KEYSTONE: 3, KIND_ROOT: 0}

ARM_LENGTH = 21
NOTABLE_POSITIONS = (6, 13, 19)


@dataclass
class TreeNode:
    id: str
    branch: str
    kind: str
    name: str
    effects: dict[str, float]
    x: float
    y: float
    description: str = ""
    links: set[str] = field(default_factory=set)


def _link(nodes: dict[str, TreeNode], a: str, b: str) -> None:
    nodes[a].links.add(b)
    nodes[b].links.add(a)


#: Раскладка: ветви растут СНИЗУ ВВЕРХ. Корни стоят рядом внизу, руки
#: тянутся вверх и расходятся веером, крайние - сильнее (крона).
ROOT_SPACING = 400
BRANCH_TILT = {"war": -26.0, "craft": 0.0, "kin": 26.0}
ARM_SPREAD = 22.0
#: Насколько руки раскидываются к концу: угол растёт на эту долю к вершине.
ARM_FAN = 0.45


def _grow(root_x: float, angle_deg: float, length: float) -> tuple[float, float]:
    """Точка на руке: угол от вертикали (минус - влево), y растёт вниз,
    поэтому вверх - отрицательные y."""
    rad = math.radians(angle_deg)
    return round(root_x + length * math.sin(rad), 1), round(-length * math.cos(rad), 1)


@lru_cache(maxsize=1)
def build() -> dict[str, TreeNode]:
    nodes: dict[str, TreeNode] = {}
    for b_index, branch in enumerate(BRANCHES):
        root_x = (b_index - 1) * ROOT_SPACING
        root_id = f"{branch}:root"
        rx, ry = root_x, 0.0
        nodes[root_id] = TreeNode(
            root_id, branch, KIND_ROOT, BRANCH_TITLES[branch], {}, rx, ry,
            description="Начало ветви. Берётся бесплатно.",
        )
        name_cursor: dict[str, int] = {}
        notable_iter = iter(NOTABLES[branch])
        for arm in range(3):
            arm_angle = BRANCH_TILT[branch] + (arm - 1) * ARM_SPREAD
            theme = ARM_THEMES[branch][arm]
            previous = root_id
            small_index = 0
            for pos in range(ARM_LENGTH):
                node_id = f"{branch}:{arm}:{pos}"
                # Лёгкий изгиб: руки расходятся веером, а не лучами.
                angle = arm_angle * (1 + ARM_FAN * pos / (ARM_LENGTH - 1))
                # Ключевой узел крупный - на вершине руки ему нужно больше места.
                tip = 16 if pos == ARM_LENGTH - 1 else 0
                x, y = _grow(root_x, angle, 70 + 34 * pos + tip)
                if pos == ARM_LENGTH - 1:
                    name, desc, effects = KEYSTONES[branch][arm]
                    node = TreeNode(node_id, branch, KIND_KEYSTONE, name, dict(effects), x, y, desc)
                elif pos in NOTABLE_POSITIONS:
                    name, effects = next(notable_iter)
                    node = TreeNode(node_id, branch, KIND_NOTABLE, name, dict(effects), x, y)
                else:
                    key = theme[small_index % len(theme)]
                    small_index += 1
                    names = SMALL_NAMES[key]
                    n = name_cursor.get(key, 0)
                    name_cursor[key] = n + 1
                    node = TreeNode(
                        node_id, branch, KIND_SMALL, names[n % len(names)],
                        {key: EFFECTS[key][2]}, x, y,
                    )
                nodes[node_id] = node
                _link(nodes, previous, node_id)
                previous = node_id
        # Перемычки между соседними руками у средних узлов: обход вокруг.
        for arm in range(2):
            for pos in (6, 13):
                _link(nodes, f"{branch}:{arm}:{pos}", f"{branch}:{arm + 1}:{pos - 1}")
        # Десятый средний узел - между руками 0 и 1 на середине пути.
        bridge_id = f"{branch}:bridge"
        name, effects = next(notable_iter)
        a, c = nodes[f"{branch}:0:9"], nodes[f"{branch}:1:9"]
        nodes[bridge_id] = TreeNode(
            bridge_id, branch, KIND_NOTABLE, name, dict(effects),
            round((a.x + c.x) / 2, 1), round((a.y + c.y) / 2, 1),
        )
        _link(nodes, bridge_id, a.id)
        _link(nodes, bridge_id, c.id)
    for node in nodes.values():
        if node.kind == KIND_ROOT:
            continue
        lines = "\n".join(f"• {effect_text(k, v)}" for k, v in node.effects.items())
        # У ключевых узлов сначала - для кого он и что даёт в игре, потом
        # точные числа; у остальных - только числа.
        node.description = f"{node.description}\n\n{lines}" if node.description else lines
    return nodes


def node(node_id: str) -> TreeNode | None:
    return build().get(node_id)


def roots() -> set[str]:
    return {f"{b}:root" for b in BRANCHES}


def can_allocate(node_id: str, allocated: set[str]) -> bool:
    """Узел соседствует с уже взятым или с корнем ветви."""
    target = node(node_id)
    if target is None or target.kind == KIND_ROOT or node_id in allocated:
        return False
    reachable = allocated | roots()
    return bool(target.links & reachable)


def total_effects(allocated: set[str]) -> dict[str, float]:
    total: dict[str, float] = {}
    for node_id in allocated:
        n = node(node_id)
        if n is None:
            continue
        for key, value in n.effects.items():
            total[key] = total.get(key, 0.0) + value
    for key, cap in EFFECT_CAPS.items():
        if key in total:
            total[key] = min(total[key], cap)
    return {k: round(v, 3) for k, v in total.items()}


def points_total() -> int:
    return sum(POINTS[n.kind] for n in build().values())
