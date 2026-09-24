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


#: Иконки навигации уже лежат отдельно (assets/icons) и подключены маской —
#: здесь они не нужны.
SKIP_PREFIXES = ("nav:",)


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
    manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    by_index = {row["index"]: row for row in manifest}

    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*.webp"):
        stale.unlink()

    mapping: dict[str, str] = {}
    missing: list[str] = []
    total_src = total_out = 0

    for record in entries():
        key = record["key"]
        if key is None or key.startswith(SKIP_PREFIXES):
            continue
        row = by_index.get(record["index"])
        if row is None or row.get("status") != "generated":
            missing.append(f"{key} ({record['label']})")
            continue
        source = SRC / row["filename"]
        if not source.exists():
            missing.append(f"{key} — нет файла {row['filename']}")
            continue

        name = slug(key) + ".webp"
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((SIZE, SIZE), Image.LANCZOS)
            image.save(OUT / name, "WEBP", quality=QUALITY, method=6)

        total_src += source.stat().st_size
        total_out += (OUT / name).stat().st_size
        mapping[key] = name

    write_map(mapping)

    print(f"подключено: {len(mapping)}")
    print(f"вес: {total_src / 1e6:.0f} МБ -> {total_out / 1e3:.0f} КБ")
    if missing:
        print(f"\nбез картинки ({len(missing)}):")
        for item in missing:
            print(f"  {item}")


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
