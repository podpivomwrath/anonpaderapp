"""Готовит иконки из img/ к использованию в мини-аппе (патч 76).

Запуск:  python tools/icon_assets.py

Что делает:
  1. связывает файлы из img/ с предметами игры ПО ИНДЕКСУ (img/manifest.json
     хранит index, tools/icon_prompts.py --keys отдаёт id под тем же
     индексом) — разбирать русские заголовки было бы гаданием;
  2. ужимает 1254x1254 PNG до размера, в котором их реально показывают;
  3. пишет miniapp/src/itemIcons.js — карта «id предмета → картинка».

Про размер. Оригиналы весят 143 МБ: это 79 картинок по ~1.8 МБ. В мини-аппе
они показываются в списках размером 24-64 пикселя, то есть 99% веса ушло бы
в трафик игрока впустую, а репозиторий разбух бы навсегда (git хранит все
версии). Поэтому в сборку идут сжатые производные, а оригиналы остаются
локально и в git не попадают — перегенерировать их из img/ можно в любой
момент этим же скриптом.
"""

import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "img"
OUT = ROOT / "miniapp" / "src" / "assets" / "items"
MAP = ROOT / "miniapp" / "src" / "itemIcons.js"

#: Показываем максимум 64 CSS-пикселя, экраны бывают с двойной плотностью —
#: 128 закрывает это с запасом. Больше смысла нет: разницы не видно, а вес
#: растёт квадратично.
SIZE = 128
QUALITY = 82

#: Имена файлов делаем ASCII: кириллица в пути ассета переживает не каждый
#: сервер и не каждый прокси, а ловить это пришлось бы уже на проде.
TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})


def slug(key: str) -> str:
    out = key.lower().translate(TRANSLIT).replace(":", "_")
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in out)


#: Иконки навигации рисуются контурами прямо в коде (miniapp/src/icons.js) —
#: файлов под них нет.
SKIP_PREFIXES = ("nav:",)

#: Не «потеряно», а сознательно не используется — иначе отчёт каждый раз
#: ругался бы на картинку, которую мы сами решили не подключать.
SKIP_KEYS = {"bg:app"}

#: Фоны обрабатываются отдельно: это не иконки в списке, а подложка на весь
#: экран, и ужимать её до 128 пикселей нельзя. Ключ -> (файл, ширина).
#: Третий элемент - имя исходника. Фоны ищутся не только по промту:
#: телефонный сгенерирован по ПЕРЕПИСАННОМУ тексту («используй landscape как
#: референс»), и по началу строки его не найти. Фонов всего два, имена у них
#: говорящие, поэтому явная привязка честнее любой эвристики.
#: Телефонной картинки здесь НЕТ сознательно (патч 84). На телефоне список
#: занимает почти весь экран, свободного места под фон не остаётся, а сама
#: сцена очень тёмная - разглядеть её было нечего, зато вес и лишний запрос
#: были. На ПК колонка ограничена, по бокам остаются поля, и там фон
#: работает. Промт телефонной версии в документе сохранён: вдруг вернёмся.
BACKGROUNDS = {
    "bg:app_wide": ("bg-wide.webp", 1600, "фон_монолит_пк_16x9.png"),
}
#: Эмблемы подклассов привязаны ПО ИМЕНИ ФАЙЛА, а не по промту.
#: Картинки заказывались не нашим промтом: в описи лежит текст генератора
#: («A polished dark fantasy RPG subclass icon...»), и сравнение по началу
#: строки его не узнает. Имена файлов при этом говорящие и заданы вручную,
#: поэтому явная привязка честнее любой эвристики - тот же случай, что и с
#: телефонным фоном выше.
SUBCLASS_FILES = {
    "subclass:guardian": "путь_01_страж.png",
    "subclass:blood_knight": "путь_02_кровавый_рыцарь.png",
    "subclass:shadow_blade": "путь_03_клинок_теней.png",
    "subclass:poisoner": "путь_04_отравитель.png",
    "subclass:elementalist": "путь_05_элементалист.png",
    "subclass:dark_mystic": "путь_06_тёмный_мистик.png",
}

#: Картинки, которых нет в контенте игры: значки базовых классов и рамки
#: венцов топ-1 (патч 91). Промты для них написаны руками
#: (tools/crown_art_prompts.md), из контента они не выводятся, поэтому и
#: живут отдельным списком, а не в генераторе промтов.
#:
#: Отсутствующий файл - это НЕ ошибка: картинка может быть ещё не нарисована.
#: Мини-апп в таком случае просто не покажет значок (ItemIcon отдаёт null),
#: а отчёт скажет, чего не хватает.
EXTRA_FILES = {
    "class:warrior": "класс_01_воин.png",
    "class:rogue": "класс_02_разбойник.png",
    "class:mage": "класс_03_маг.png",
    "crown:pvp": "венец_01_клинок.png",
    "crown:kills": "венец_02_охотник.png",
    "crown:fishing": "венец_03_мастер_лески.png",
    "crown:fish_weight": "венец_04_трофей.png",
    "crown:mining": "венец_05_жила.png",
}

BG_OUT = ROOT / "miniapp" / "src" / "assets"
BG_CSS = ROOT / "miniapp" / "src" / "background.css"


def load_manifests() -> list[dict]:
    """Все описи в img/: и общая, и отдельные, вроде той, что пришла с фонами."""
    rows: list[dict] = []
    for path in sorted(SRC.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            rows += [row for row in data if isinstance(row, dict) and row.get("filename")]
    return rows


def find(by_prompt: dict[str, dict], prompt: str) -> dict | None:
    """Наш промт либо совпадает целиком, либо является НАЧАЛОМ записанного.

    Генератор дописывает к промту свои требования, и точное сравнение после
    этого не сходится. Сравнение по началу это переживает, а чужую картинку
    всё равно не подставит: начало у каждого предмета своё.
    """
    prompt = prompt.strip()
    exact = by_prompt.get(prompt)
    if exact is not None:
        return exact
    for recorded, row in by_prompt.items():
        if recorded.startswith(prompt):
            return row
    return None


def entries() -> list[dict]:
    """Порядок записей = порядок в img/manifest.json."""
    sys.path.insert(0, str(ROOT / "tools"))
    import icon_prompts

    icon_prompts.QUIET = True
    icon_prompts.ENTRIES.clear()
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        icon_prompts.main()
    return list(icon_prompts.ENTRIES)


def main() -> None:
    manifest = load_manifests()
    # Ключ поиска - ТЕКСТ ПРОМТА. Он выводится из самого предмета, поэтому
    # переживает любую перестановку разделов; индекс не пережил и первой.
    by_prompt = {row.get("prompt", "").strip(): row for row in manifest}

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.webp"):
        stale.unlink()

    mapping: dict[str, str] = {}
    backgrounds: dict[str, str] = {}
    missing: list[str] = []
    total_src = total_out = 0

    for record in entries():
        key = record["key"]
        if key is None or key.startswith(SKIP_PREFIXES) or key in SKIP_KEYS:
            continue
        row = find(by_prompt, record["prompt"])
        if row is None:
            hint = SUBCLASS_FILES.get(key)
            if hint is None and key in BACKGROUNDS:
                hint = BACKGROUNDS[key][2]
            if hint is not None and (SRC / hint).exists():
                row = {"filename": hint}
        if row is None or row.get("status", "generated") != "generated":
            missing.append(f"{key} ({record['label']})")
            continue
        source = SRC / row["filename"]
        if not source.exists():
            missing.append(f"{key} — нет файла {row['filename']}")
            continue

        if key in BACKGROUNDS:
            name, width, _hint = BACKGROUNDS[key]
            with Image.open(source) as image:
                image = image.convert("RGB")
                # Только по ширине: высоту режет CSS (cover), а вот
                # уменьшать фон до иконочных размеров нельзя - он на весь экран.
                if image.width > width:
                    ratio = width / image.width
                    image = image.resize((width, round(image.height * ratio)), Image.LANCZOS)
                image.save(BG_OUT / name, "WEBP", quality=78, method=6)
            backgrounds[key] = name
            total_src += source.stat().st_size
            total_out += (BG_OUT / name).stat().st_size
            continue

        name = slug(key) + ".webp"
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((SIZE, SIZE), Image.LANCZOS)
            image.save(OUT / name, "WEBP", quality=QUALITY, method=6)

        total_src += source.stat().st_size
        total_out += (OUT / name).stat().st_size
        mapping[key] = name

    # Рамки венцов ОСТАЮТСЯ с альфа-каналом: они накладываются поверх значка
    # класса, и залитая середина закрыла бы его целиком. Остальные иконки
    # сводятся в RGB - прозрачность им не нужна, а вес с ней больше.
    not_drawn: list[str] = []
    for key, filename in EXTRA_FILES.items():
        source = SRC / filename
        if not source.exists():
            not_drawn.append(f"{key} ({filename})")
            continue
        name = slug(key) + ".webp"
        keep_alpha = key.startswith("crown:")
        with Image.open(source) as image:
            image = image.convert("RGBA" if keep_alpha else "RGB")
            image.thumbnail((SIZE, SIZE), Image.LANCZOS)
            image.save(OUT / name, "WEBP", quality=QUALITY, method=6)
        total_src += source.stat().st_size
        total_out += (OUT / name).stat().st_size
        mapping[key] = name

    write_map(mapping)
    write_backgrounds(backgrounds)

    print(f"подключено: {len(mapping)} иконок, фонов: {len(backgrounds)}")
    print(f"вес: {total_src / 1e6:.0f} МБ -> {total_out / 1e3:.0f} КБ")
    if not_drawn:
        # Не «потеряно», а «ещё не нарисовано» - отдельной строкой, чтобы
        # не путалось с настоящими промахами привязки.
        print(f"\nещё не нарисованы ({len(not_drawn)}):")
        for item in not_drawn:
            print(f"  {item}")
    if missing:
        print(f"\nбез картинки ({len(missing)}):")
        for item in missing:
            print(f"  {item}")


def write_backgrounds(found: dict[str, str]) -> None:
    """CSS-переменные под фоны. Файл пишется ВСЕГДА, даже пустой.

    Иначе main.jsx импортировал бы то, чего нет, и сборка падала бы до тех
    пор, пока картинки не нарисуют — а до этого момента приложение обязано
    собираться и работать, просто без фона.
    """
    lines = [
        "/* СГЕНЕРИРОВАНО: python tools/icon_assets.py — править нечего. */",
        "",
    ]
    if "bg:app_wide" in found:
        # Только широкий: на телефоне фона нет вовсе (см. BACKGROUNDS).
        lines += [
            "@media (min-width: 720px) {",
            "  :root {",
            f"    --app-bg: url('./assets/{found['bg:app_wide']}');",
            "  }",
            "}",
            "",
        ]
    if not found:
        lines += ["/* Фона пока нет: --app-bg остаётся none, слой невидим. */", ""]
    BG_CSS.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_map(mapping: dict[str, str]) -> None:
    lines = [
        "/**",
        " * Картинки предметов (патч 76) — СГЕНЕРИРОВАНО, править руками нечего:",
        " * `python tools/icon_assets.py`.",
        " *",
        " * Ключ — id предмета в игре, тот же, что в контенте и в БД. Поэтому",
        " * подпись искать не нужно: есть ore_id — есть иконка.",
        " */",
        "",
        "const ICONS = {",
    ]
    for key in sorted(mapping):
        name = mapping[key]
        lines.append(
            f"  '{key}': new URL('./assets/items/{name}', import.meta.url).href,"
        )
    lines += [
        "};",
        "",
        "/** Картинка предмета или null — вызывающий сам решает, чем заменить. */",
        "export function itemIcon(key) {",
        "  return ICONS[key] ?? null;",
        "}",
        "",
    ]
    MAP.write_text("\n".join(lines), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if not SRC.exists():
        raise SystemExit("нет папки img/ — положи туда картинки и manifest.json")
    main()
