"""Тексты и кнопки сюжетного онбординга (Хранитель Списков).

Сами реплики NPC живут в content/npc/list_keeper.json (дословно из
дизайн-документа) — здесь только загрузка, кнопки и сборка финала.
"""

from game.content_loader import load_npc_texts

KEEPER = load_npc_texts("list_keeper")["onboarding"]

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
