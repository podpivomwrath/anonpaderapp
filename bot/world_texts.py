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
