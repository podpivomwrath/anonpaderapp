"""Тексты мира: наставники городов (content/npc/mentors.json)."""

from bot.vk_media import photo_attachment
from game.content_loader import load_npc_texts

MENTORS = load_npc_texts("mentors")


def mentor_intro(region: str) -> str:
    return MENTORS[region]["intro"]


def mentor_praise(region: str) -> str:
    return MENTORS[region]["praise"]


def mentor_name(region: str) -> str:
    return MENTORS[region]["name"]


def mentor_attachment(region: str) -> str | None:
    photo_id = MENTORS[region].get("image")
    return photo_attachment(photo_id) if photo_id else None


# --- Патч 26: чужие города — доступен только скупщик, PvP разрешено ---


def foreign_city_entry_text(region_title: str) -> str:
    return (
        f"🚪 {region_title}\n\n"
        "Ты входишь в чужие ворота. Разговоры стихают, взгляды провожают тебя вдоль улицы. "
        "Здесь тебя не ждали — и не защитят.\n\n"
        "⚠️ Это чужой город. Здесь на тебя могут напасть."
    )


FOREIGN_NPC_REJECTION = "— Ты не отсюда. — Тебя окидывают взглядом и отворачиваются. — Иди к своим."

FOREIGN_APPRAISER_INTRO_SUFFIX = (
    "\n\nТорговец оглядывает тебя, потом твою добычу, потом снова тебя.\n"
    "— Беру. Но по своей цене, чужак. Не нравится — неси домой.\n\n"
    "⚠️ Цены чужака: −30%"
)

# --- Патч 39: кварталы города — атмосферный текст на вход в каждый. Таверна в
# чужом городе НЕДОСТУПНА вовсе (в отличие от торгового квартала, где скупщик
# работает с наценкой) — там используется тот же FOREIGN_NPC_REJECTION.

CITY_SQUARE_TEXTS = {
    "ridge": "Каменные стены Кряжа держат небо на копьях. Патрули Ордена проходят мимо, "
             "не глядя — здесь свои, и это давно не вопрос доверия, а привычка.",
    "woods": "Пущи смыкаются над самой площадью — ветви сплетаются в подобие крыши. Пахнет "
             "мхом и дымом костров; кто-то тихо напевает на языке, которого ты ещё не выучил.",
    "docks": "Солёный ветер несёт крики чаек и торговцев вперемешку. Доски площади скрипят "
             "под ногами — здесь всё временное, кроме самой воды.",
    "scorched": "Пепел здесь не грязь, а почва — по нему ходят, как по брусчатке. Спирали "
                "шрамов мелькают на лицах прохожих; никто не смотрит на них дважды.",
}

TAVERN_TEXTS = {
    "ridge": "В таверне пахнет элем и полировкой для доспехов. Разговоры здесь тише, чем в "
             "других городах — Кряж не любит трепаться о делах Ордена.",
    "woods": "Здесь пьют настой из коры, а не эль, и молчат больше, чем говорят. Огонь в "
             "очаге горит зелёным — Пущи умеют удивлять даже своих.",
    "docks": "Пол шатается в такт волнам, будто таверна сама на плаву. Моряки делят стол с "
             "контрабандистами — здесь это не считается странным.",
    "scorched": "Пепельная пыль оседает даже на кружках. Разговор стихает, стоит кому-то "
                "упомянуть раскол — старая рана, которую в Пределе не любят трогать.",
}

MARKET_QUARTER_TEXTS = {
    "ridge": "Ряды лотков тянутся вдоль стены — оружие, броня, слухи, всё по одной цене, "
             "если знать, с кем говорить.",
    "woods": "Торговцы Пущи держат товар под навесами из живых веток — здесь редко продают "
             "то, что не выросло само.",
    "docks": "Здесь торгуют всем, что прибило волной или украли с чужого корабля — вопросов "
             "лучше не задавать.",
    "scorched": "Прилавки закопчены не хуже самих торговцев. Каждая сделка здесь — маленький "
                "договор с Пеплом, шутят местные.",
}


def city_square_text(region: str) -> str:
    return CITY_SQUARE_TEXTS.get(region, "Ты на главной площади.")


def tavern_text(region: str) -> str:
    return f"🍺 Таверна\n\n{TAVERN_TEXTS.get(region, '')}".rstrip()


def market_quarter_text(region: str, is_foreign: bool = False) -> str:
    base = f"🏬 Торговый квартал\n\n{MARKET_QUARTER_TEXTS.get(region, '')}".rstrip()
    if is_foreign:
        base += "\n\n⚠️ Чужой квартал — только скупщик, и тот с наценкой."
    return base


# --- Иллюстрации: хаб города + события исследования (фото в альбоме группы VK) ---

HUB_PHOTO_IDS = {
    "ridge": "457239028",     # Обетованный Кряж
    "woods": "457239026",     # Шепчущие Пущи
    "docks": "457239025",     # Соляные Пристани
    "scorched": "457239027",  # Выжженный Предел
}

EVENT_PHOTO_IDS = {
    "dead_box": "457239029",          # Шкатулка мертвеца
    "monolith_shard": "457239034",    # Пульсирующий осколок
    "wounded_wanderer": "457239031",  # Раненый путник
    "ash_altar": "457239030",         # Пепельный алтарь
}


def hub_attachment(region: str) -> str | None:
    photo_id = HUB_PHOTO_IDS.get(region)
    return photo_attachment(photo_id) if photo_id else None


def event_attachment(event_id: str) -> str | None:
    photo_id = EVENT_PHOTO_IDS.get(event_id)
    return photo_attachment(photo_id) if photo_id else None
