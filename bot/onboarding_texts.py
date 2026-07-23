"""Тексты и кнопки сюжетного онбординга (Хранитель Списков).

Сами реплики NPC живут в content/npc/list_keeper.json (дословно из
дизайн-документа) — здесь только загрузка, кнопки и сборка финала.
"""

from config import get_settings
from game.content_loader import load_npc_texts

KEEPER = load_npc_texts("list_keeper")["onboarding"]

# --- Иллюстрации сцен онбординга (фото уже загружены в альбом группы VK) ---

SCENE_PHOTO_IDS = {
    "scene_awakening": "457239017",    # пробуждение / выбор имени
    "scene_blood_test": "457239018",  # проверка крови / выбор класса
    "scene_four_roads": "457239019",  # четыре дороги / выбор региона
}

REGION_PHOTO_IDS = {
    "ridge": "457239020",     # Обетованный Кряж
    "scorched": "457239022",  # Выжженный Предел
    "docks": "457239023",     # Соляные Пристани
    "woods": "457239024",     # Шепчущие Пущи
}


def _photo_attachment(photo_id: str) -> str:
    return f"photo-{get_settings().vk_group_id}_{photo_id}"


def scene_attachment(key: str) -> str | None:
    photo_id = SCENE_PHOTO_IDS.get(key)
    return _photo_attachment(photo_id) if photo_id else None


def region_attachment(region: str) -> str | None:
    photo_id = REGION_PHOTO_IDS.get(region)
    return _photo_attachment(photo_id) if photo_id else None

# --- Кнопки ---

CLASS_BUTTONS = {
    "⚔️ Путь Стали": "warrior",
    "🗡️ Путь Тени": "rogue",
    "🔮 Путь Осколка": "mage",
}
CLASS_TITLES = {v: k for k, v in CLASS_BUTTONS.items()}

REGION_BUTTONS = {
    "🏰 Обетованный Кряж": "ridge",
    "🌲 Шепчущие Пущи": "woods",
    "⚓ Соляные Пристани": "docks",
    "🔥 Выжженный Предел": "scorched",
}
REGION_TITLES = {v: k for k, v in REGION_BUTTONS.items()}
# Имя региона в устной реплике Хранителя — без эмодзи
REGION_SPOKEN = {region: title.split(" ", 1)[1] for title, region in REGION_BUTTONS.items()}

BTN_CHOOSE_PATH = "Выбрать этот путь"
BTN_OTHER_PATHS = "Послушать про другие"
BTN_CONFIRM_PATH = "Да, это мой путь"
BTN_THINK_MORE = "Ещё подумать"
BTN_GO_REGION = "Иду туда"
BTN_OTHER_ROADS = "Расскажи про другие"
BTN_YES = "Да"
BTN_BEGIN = "Ступить на путь →"

# Коды ошибок валидации ника → реплики Хранителя
NICKNAME_ERRORS = {
    "invalid": KEEPER["nickname_invalid"],
    "banned": KEEPER["nickname_banned"],
    "taken": KEEPER["nickname_taken"],
}


def final_message(name: str, base_class: str, region: str, stats) -> str:
    return KEEPER["final"].format(
        nickname=name,
        class_title=CLASS_TITLES[base_class],
        region_title=REGION_TITLES[region],
        region_spoken=REGION_SPOKEN[region],
        str=stats.strength,
        agi=stats.agility,
        int=stats.intellect,
        vit=stats.vitality,
        wil=stats.will,
    )
