"""Картинки рун для мини-аппа (2026-10-31): python tools/rune_assets.py

Берёт из img/ файлы по именам из tools/runes_art_prompts.md (иконка руны -
«руна_<название>.png»), ужимает в webp и пишет miniapp/src/runeIcons.js.
Оригиналы в git не идут, как у остальных иконок (tools/icon_assets.py).
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.economy import runes_config as rc  # noqa: E402

SRC = ROOT / "img"
OUT = ROOT / "miniapp" / "src" / "assets" / "runes"
MAP = ROOT / "miniapp" / "src" / "runeIcons.js"

#: Файл -> (имя в сборке, ширина). Иконки и гнёзда показываются до 64 CSS px.
EXTRA = {
    "гнездо_руна_герой.png": ("socket_hero", 128),
    "гнездо_руна_экипировка.png": ("socket_gear", 128),
    "гнездо_руна_навык.png": ("socket_skill", 128),
    "гнездо_замок.png": ("socket_lock", 128),
    "рунный_круг.png": ("circle", 900),
}

#: Шапка раздела - к остальным шапкам (ui.jsx берёт их по имени файла).
BANNER = ("шапка_руны.png", ROOT / "miniapp" / "src" / "assets" / "sections" / "runes.webp")


def file_for(rune: rc.RuneDef) -> str:
    return "руна_" + rune.name.lower().replace(" ", "_") + ".png"


def save(src: Path, name: str, width: int) -> None:
    image = Image.open(src).convert("RGBA")
    height = round(image.height * width / image.width)
    image.resize((width, height), Image.LANCZOS).save(OUT / f"{name}.webp", "WEBP", quality=82)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines, missing = [], []
    for rune in rc.RUNES:
        src = SRC / file_for(rune)
        if not src.exists():
            missing.append(src.name)
            continue
        save(src, rune.id, 128)
        lines.append(f"  {rune.id}: new URL('./assets/runes/{rune.id}.webp', import.meta.url).href,")
    extra = []
    for file, (name, width) in EXTRA.items():
        if not (SRC / file).exists():
            missing.append(file)
            continue
        save(SRC / file, name, width)
        extra.append(f"  {name}: new URL('./assets/runes/{name}.webp', import.meta.url).href,")
    banner_src, banner_out = BANNER
    if (SRC / banner_src).exists():
        image = Image.open(SRC / banner_src).convert("RGB")
        image.resize((1024, round(image.height * 1024 / image.width)), Image.LANCZOS).save(banner_out, "WEBP", quality=82)
    MAP.write_text(
        "// Сгенерировано tools/rune_assets.py - руками не править.\n"
        "export const RUNE_ICONS = {\n" + "\n".join(lines) + "\n};\n\n"
        "export const RUNE_ART = {\n" + "\n".join(extra) + "\n};\n",
        encoding="utf-8",
    )
    print(f"рун: {len(lines)}, прочего: {len(extra)}, нет файлов: {missing or 'нет'}")


if __name__ == "__main__":
    main()
