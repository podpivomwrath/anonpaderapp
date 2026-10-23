"""Готовит картинки шапок разделов мини-аппа из img/ (2026-10-22).

Запуск:  python tools/section_assets.py

Исходники - img/шапка_<раздел>.png (промты - tools/section_art_prompts.md).
Ужимает до ширины 960 и пишет miniapp/src/assets/sections/<раздел>.webp.
Мини-апп подхватывает файл сам (components/ui.jsx, SectionHead): есть
картинка - она под шапкой раздела, нет - шапка остаётся градиентом.

Оригиналы в git не идут.
"""

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "img"
OUT = ROOT / "miniapp" / "src" / "assets" / "sections"

#: Шапка - до ~560 CSS-пикселей в ширину, экраны двойной плотности.
WIDTH = 960
QUALITY = 78

#: Разделы, у которых есть шапка: ключ - имя файла, как в SectionHead kind.
KINDS = (
    "dailies", "login", "inventory", "craft", "crafts", "tops", "board",
    "guild", "trade", "exchange", "shop", "trials",
)

#: Шапки страниц ремёсел на вкладке «Герой» (2026-10-23, CraftGear.jsx):
#: имя файла на выходе -> имя исходника img/шапка_<...>.png.
GEAR_KINDS = {
    "gear_herbalism": "ремесло_травник", "gear_alchemy": "ремесло_алхимик", "gear_mining": "ремесло_горняк",
    "gear_cooking": "ремесло_кулинар", "gear_fishing": "ремесло_рыбак",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    done = 0
    sources = {kind: kind for kind in KINDS} | GEAR_KINDS
    for kind, name in sources.items():
        src = SRC / f"шапка_{name}.png"
        if not src.exists():
            continue
        img = Image.open(src).convert("RGB")
        height = round(WIDTH * img.height / img.width)
        target = OUT / f"{kind}.webp"
        img.resize((WIDTH, height), Image.LANCZOS).save(target, "WEBP", quality=QUALITY, method=6)
        print(f"{src.name} -> {target.name} {target.stat().st_size // 1024} КБ")
        done += 1
    missing = [n for n in sources.values() if not (SRC / f"шапка_{n}.png").exists()]
    if missing:
        print("нет исходников:", ", ".join(missing))
    print(f"готово: {done}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
