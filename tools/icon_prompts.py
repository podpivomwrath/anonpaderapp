"""Промты для генерации иконок — СОБИРАЮТСЯ ИЗ КОНТЕНТА (патч 75).

Запуск:  python tools/icon_prompts.py > tools/icon_prompts.md

Зачем генератор, а не написанный руками список: предметы добавляются каждый
патч (шесть руд, восемнадцать рыб, три результата крафта — и это за последний
месяц). Список, набранный вручную, разошёлся бы с игрой на первой же новой
рыбе, и заметили бы это только по пропавшей иконке.

Лор берётся из самого контента: у руды и уникальных вещей есть описания, и
они дают художнику куда больше, чем название. Где описания нет, подставляется
короткая формулировка по типу предмета.

Промты на английском: модели генерации изображений понимают его заметно
точнее. Названия в заголовках оставлены русскими, чтобы список было удобно
листать.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"

# Общий стилевой хвост. Дописывается к КАЖДОМУ промту — иначе иконки выйдут
# из разных миров: одна мультяшная, другая фотографическая. Мир игры —
# пепел, ржавчина, кровь и Монолит, поэтому палитра приглушённая.
STYLE = (
    "dark fantasy game item icon, single object centered, slight 3/4 angle, "
    "painterly semi-realistic, muted desaturated palette of ash grey, rust brown "
    "and dried blood, weathered and worn surfaces, soft rim light from the upper "
    "left, deep neutral background, no text, no watermark, no border, "
    "square 1:1 composition, crisp readable silhouette at small size"
)

# Акцентный цвет по редкости/тиру. Один и тот же язык цвета во всей игре:
# эмодзи в чате, полоски в мини-аппе и иконки должны совпадать.
ACCENT = {
    1: "cold off-white accents",
    2: "pale steel-blue accents",
    3: "muted violet accents",
    4: "burnt amber accents",
    5: "deep crimson accents, faint inner glow",
    6: "deep crimson accents, unsettling inner glow",
}

RARITY_ACCENT = {
    "common": ACCENT[1],
    "uncommon": ACCENT[2],
    "rare": ACCENT[3],
    "epic": ACCENT[4],
    "legendary": "pale gold accents, faint inner glow",
    "unique": "deep crimson accents, strong inner glow",
    "admin": "flat neutral grey, deliberately plain",
}

SLOT_HINT = {
    "weapon": "a weapon held by an adventurer",
    "helmet": "a piece of head armour",
    "armor": "a torso armour piece",
    "legs": "leg armour",
    "boots": "footwear",
}


def load(name: str):
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


def clean(node: dict) -> dict:
    return {k: v for k, v in node.items() if not k.startswith("_")}


def prompt(subject: str, accent: str, extra: str = "") -> str:
    parts = [subject.rstrip(". "), accent]
    if extra:
        parts.append(extra.rstrip(". "))
    parts.append(STYLE)
    return ", ".join(parts)


QUIET = False


def section(title: str, note: str = "") -> None:
    if QUIET:
        return
    print(f"\n## {title}\n")
    if note:
        print(f"{note}\n")


#: Все записи по порядку. Индекс в этом списке = index в img/manifest.json,
#: по нему картинка и связывается с предметом.
ENTRIES: list[dict] = []


def entry(label: str, text: str, key: str | None = None) -> None:
    # text нужен не только для печати: по нему tools/icon_assets.py находит
    # картинку в манифесте. Индекс для этого не годится - он съезжает от
    # любой вставки раздела в середину.
    ENTRIES.append({"index": len(ENTRIES), "key": key, "label": label, "prompt": text})
    if QUIET:
        return
    print(f"**{label}**\n")
    print("```")
    print(text)
    print("```\n")


def first_sentence(text: str, limit: int = 160) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:limit]


# --- Разделы --------------------------------------------------------------------


def equipment() -> None:
    section(
        "Экипировка — базы по слотам",
        "На каждую базу нужна одна иконка. Редкость поверх неё даётся цветом "
        "рамки или свечения (см. раздел «Редкости»), перерисовывать предмет "
        "под каждую из пяти редкостей не нужно.",
    )
    bases = clean(load("items/bases.json"))
    for slot, rows in bases.items():
        for row in rows:
            entry(
                f"{row['name']} ({slot})",
                prompt(
                    f"{SLOT_HINT.get(slot, 'a piece of equipment')} called «{row['name']}», "
                    "battered and field-repaired, scavenged look",
                    ACCENT[1],
                ),
                key=f"base:{slot}:{row['name']}",
            )


def rarities() -> None:
    section(
        "Редкости — рамки",
        "Рисуются один раз и накладываются на любую иконку предмета. "
        "Тот же язык цвета, что у эмодзи в чате.",
    )
    for rarity_id, row in clean(load("items/rarities.json")).items():
        entry(
            f"{row['emoji']} {row['name']}",
            prompt(
                "empty square item frame for an inventory slot, ornate but restrained "
                "metal edging, hollow centre",
                RARITY_ACCENT.get(rarity_id, ACCENT[1]),
                "the frame is the only subject, nothing inside it",
            ),
            key=f"rarity:{rarity_id}",
        )


def elixirs() -> None:
    section(
        "Эликсиры",
        "Общая форма склянки должна читаться как одна серия: различаются "
        "содержимым, пробкой и цветом.",
    )
    for row in load("items/elixirs.json"):
        entry(
            f"{row['emoji']} {row['name']}",
            prompt(
                f"small glass vial of an alchemical draught called «{row['name']}», "
                f"hand-blown uneven glass, wax-sealed stopper, cloth label. "
                f"Effect: {first_sentence(row['description'])}",
                ACCENT[3],
                "the liquid inside visually hints at the effect",
            ),
            key=f"elixir:{row['id']}",
        )


def trophies() -> None:
    section("Трофеи", "Выпадают с мобов, копятся стаками — читаемость в мелком размере важнее детализации.")
    rows = load("trophies.json")
    rows = rows if isinstance(rows, list) else list(clean(rows).values())
    for i, row in enumerate(rows, start=1):
        entry(
            f"{row.get('emoji','')} {row['name']}",
            prompt(
                f"a grim trophy called «{row['name']}», a small organic-mineral fragment "
                "taken from a slain creature, resting on nothing",
                ACCENT.get(min(i, 5), ACCENT[1]),
            ),
            key=f"trophy:{row.get('id')}",
        )


def ores() -> None:
    section("Руда", "У каждой породы есть описание в контенте — оно и задаёт вид.")
    for row in load("mining/ores.json"):
        entry(
            f"{row['emoji']} {row['name']} (тир {row['tier']})",
            prompt(
                f"a raw ore chunk called «{row['name']}». {first_sentence(row.get('description'))}",
                ACCENT.get(row["tier"], ACCENT[1]),
                "rough unworked mineral, freshly broken facets",
            ),
            key=f"ore:{row['id']}",
        )


def fish() -> None:
    section(
        "Рыба",
        "Вид сбоку, как в определителе: так силуэты не сливаются между собой.",
    )
    for row in load("fishing/fish.json"):
        entry(
            f"{row.get('emoji','')} {row['name']} (тир {row['tier']})",
            prompt(
                f"a freshwater fish called «{row['name']}», full body side view, "
                "wet scales, caught and lifeless",
                ACCENT.get(row["tier"], ACCENT[1]),
                "anatomically plausible but subtly wrong, as if the water it came from is sick",
            ),
            key=f"fish:{row['id']}",
        )


def uniques_and_craft() -> None:
    section(
        "Рейдовые и крафченые",
        "Три результата ковки должны читаться как переделки ОДНОГО скальпеля: "
        "общая рукоять, разное полотно.",
    )
    for unique_id, row in clean(load("items/unique_items.json")).items():
        row = {**row, "id_key": unique_id}
        entry(
            row["name"],
            prompt(
                f"a unique surgical weapon called «{row['name']}». {first_sentence(row.get('flavor'))}",
                RARITY_ACCENT["unique"],
                "clearly a medical instrument repurposed as a weapon",
            ),
            key=f"unique:{row['id_key']}",
        )
    for recipe in clean(load("crafting/recipes.json")).values():
        for spec, out in recipe["outputs"].items():
            entry(
                f"{out['name']} ({spec}, из «{recipe['source_name']}»)",
                prompt(
                    f"a reforged surgical weapon called «{out['name']}». "
                    f"{first_sentence(out.get('flavor'))}",
                    RARITY_ACCENT["unique"],
                    f"visibly reforged from «{recipe['source_name']}» — same handle wrapping, "
                    "different blade",
                ),
                key=f"craft:{spec}",
            )


def tools() -> None:
    section(
        "Инструменты мастерской",
        "Расходник, поднимающий эффективность на ступень. Отличаются только "
        "потолком, поэтому различать их стоит материалом и числом клейм.",
    )
    sys.path.insert(0, str(ROOT))
    from game.economy import craft_config as cc

    ladder = sorted(set(cc.TOOL_CEILING_BY_ORE_TIER.values()))
    for i, ceiling in enumerate(ladder, start=1):
        entry(
            f"Инструмент до {ceiling}%",
            prompt(
                "a blacksmith's finishing tool: a hand punch and file bound together, "
                f"single-use, stamped with {i} mark(s)",
                ACCENT.get(min(i + 1, 5), ACCENT[2]),
                "clearly consumable — already half worn out",
            ),
            key=f"tool:{ceiling}",
        )


def misc() -> None:
    section("Прочее")
    entry(
        "🗝 Ключ Монолита",
        prompt(
            "an ancient key to a sealed place called the Monolith, oversized and heavy, "
            "cast from dark stone rather than metal, warm to the touch",
            ACCENT[5],
        ),
        key="misc:raid_key",
    )
    chest = load("lootbox/ashen_chest.json")
    for row in chest:
        entry(
            f"{row.get('emoji','')} Пепельный сундук — {row['name']}",
            prompt(
                f"a small looted chest, «{row['name']}» grade, lid ajar, ash spilling out",
                ACCENT.get(min(chest.index(row) + 1, 5), ACCENT[1]),
            ),
            key=f"chest:{row['id']}",
        )
    for path in sorted((CONTENT / "mounts").glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))
        rows = rows if isinstance(rows, list) else list(clean(rows).values())
        for row in rows:
            entry(
                f"Маунт — {row['name']}",
                prompt(
                    f"a mount called «{row['name']}», gaunt and ash-covered riding beast, "
                    "side view, saddled",
                    ACCENT[4],
                    "ridden hard for a long time",
                ),
                key=f"mount:{row['id']}",
            )


def background() -> None:
    section(
        "Фон приложения",
        "ДВЕ картинки: соотношение сторон телефона около 0.46, окна на ПК - "
        "за единицу, и одну композицию cover обрезал бы до неузнаваемости. "
        "Сцена и палитра общие, различается только компоновка. Требования к "
        "обеим необычные: их видно каждую секунду, и они НЕ должны спорить с "
        "текстом - контраст низкий, в середине пусто, детали по краям.",
    )
    entry(
        "Фон — Монолит, широкий экран (ПК)",
        "a wide horizontal wallpaper for a dark fantasy game: a colossal black "
        "monolith standing far away in an ash plain under a heavy overcast sky. "
        "Same scene and palette as the portrait version, recomposed for width: "
        "the monolith sits off-centre, the rest is empty ash plain and haze, so "
        "that a narrow centred column of interface panels can sit over the "
        "middle without covering anything important. Very low contrast, muted "
        "ash grey and rust brown with a single faint crimson glow at the "
        "monolith's base. Painterly, atmospheric, no characters, no text, "
        "no watermark, landscape 16:9",
        key="bg:app_wide",
    )
    entry(
        "Фон — Монолит, телефон",
        "a wide vertical wallpaper for a dark fantasy game: a colossal black "
        "monolith standing far away in an ash plain under a heavy overcast sky, "
        "seen from below. Composition deliberately sparse: detail concentrated "
        "in the upper third, the lower two thirds are near-empty ash and haze so "
        "that interface panels can sit over them. Very low contrast, no focal "
        "point in the centre, muted palette of ash grey, rust brown and a single "
        "faint crimson glow at the monolith's base. Painterly, atmospheric, "
        "no characters, no text, no watermark, portrait 9:16",
        key="bg:app",
    )


def sections_ui() -> None:
    section(
        "Иконки разделов мини-аппа",
        "Не предметы, а навигация — поэтому плоские и монохромные, иначе "
        "перетянут внимание с содержимого. Кладутся в miniapp/src/assets/icons/.",
    )
    sys.path.insert(0, str(ROOT))
    titles = {
        "character": "a masked face in profile",
        "dailies": "a rolled parchment with a wax seal",
        "inventory": "a worn travel satchel",
        "craft": "a smith's hammer crossed with tongs",
        "map": "a folded map with a route drawn on it",
        "tops": "a simple laurel wreath around a numeral one",
        "exchange": "two arrows curving into each other",
        "admin": "a plain shield",
    }
    for key, subject in titles.items():
        entry(
            f"{key}.svg",
            f"{subject}, flat monochrome UI icon, single weight line art, "
            "no fill, no gradient, no text, square 1:1, centred with even padding, "
            "legible at 22x22 pixels",
            key=f"nav:{key}",
        )


def subclasses() -> None:
    section(
        "Эмблемы подклассов",
        "Показываются в мини-аппе рядом с названием пути. Это ЭМБЛЕМА, а не "
        "персонаж: игрок смотрит на свой подкласс, и чужое лицо спорило бы с "
        "тем, кого он себе представляет. Промты для картинок в чат отдельные, "
        "там как раз фигура (tools/story_art_prompts.md).",
    )
    sys.path.insert(0, str(ROOT))
    from game.classes import REGISTRY

    subjects = {
        "guardian": "a battered tower shield seen head on, dented but whole",
        "blood_knight": "a straight blade held point down with blood running along the fuller",
        "shadow_blade": "a slim dagger half dissolving into shadow",
        "poisoner": "a stoppered glass vial of dark liquid beside a withered leaf",
        "elementalist": "a sphere split into flame, frost and storm wind",
        "dark_mystic": "an open palm cut across the centre with a blood sigil beneath it",
    }
    for subclass in REGISTRY.values():
        entry(
            f"{subclass.title} ({subclass.id})",
            prompt(subjects[subclass.id], ACCENT[4], "an emblem rather than a character"),
            key=f"subclass:{subclass.id}",
        )


def main() -> None:
    print("# Промты для генерации иконок\n")
    print(
        "Собрано из контента игры: `python tools/icon_prompts.py > tools/icon_prompts.md`.\n"
        "После добавления предметов перегенерировать — руками список разойдётся "
        "с игрой на первой же новой вещи.\n"
    )
    print(
        "Промты на английском: модели генерации понимают его точнее. "
        "Общий стилевой хвост дописан к каждому — без него набор выйдет "
        "из разных миров.\n"
    )
    equipment()
    rarities()
    elixirs()
    trophies()
    ores()
    fish()
    uniques_and_craft()
    tools()
    misc()
    background()
    subclasses()
    sections_ui()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--keys" in sys.argv:
        # Машинный вывод для tools/icon_assets.py: какой предмет под каким
        # индексом. Сам документ при этом глушится целиком - main() печатает
        # ещё и шапку, мимо section()/entry().
        import contextlib
        import io as _io

        QUIET = True
        with contextlib.redirect_stdout(_io.StringIO()):
            main()
        print(json.dumps(ENTRIES, ensure_ascii=False, indent=2))
    else:
        main()
