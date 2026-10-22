"""Готовит силуэты героя из img/ для вкладки «Герой» мини-аппа (2026-10-22).

Запуск:  python tools/silhouette_assets.py

Исходники - img/силуэт_<класс>[_ж].png, 1024x1536 на чёрном фоне
(промты - tools/silhouette_art_prompts.md). Что делает:
  1. отделяет фон: заливка от краёв по почти чёрным пикселям. Порог яркости
     тут не годится - фигура сама тёмная, и прозрачной стала бы вся броня;
     а заливка останавливается на тлеющей кромке по контуру;
  2. приводит всех к одной высоте и ставит по центру по капюшону, а не по
     рамке фигуры: щит Стража и посох мистика сдвинули бы рамку вбок, и
     окна слотов легли бы мимо тела;
  3. пишет webp с прозрачностью в miniapp/src/assets/silhouettes/.

Оригиналы в git не идут (как иконки, tools/icon_assets.py): по 1-1.5 МБ.
"""

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "img"
OUT = ROOT / "miniapp" / "src" / "assets" / "silhouettes"

#: Холст результата и где на нём стоит фигура (макушка и подошвы).
W, H = 600, 960
TOP, BOTTOM = 36, 924
#: Ниже этой яркости пиксель считается фоном, если до него дотянулась
#: заливка от края.
BG_LEVEL = 5
#: Размер «закрытия» щелей в контуре, пикселей исходника (нечётное).
CLOSE = 9
QUALITY = 84

TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
})

#: Имя файла -> id для мини-аппа (подкласс или базовый класс).
IDS = {
    "кровавый_рыцарь": "blood_knight", "страж": "guardian", "тёмный_мистик": "dark_mystic",
    "элементалист": "elementalist", "клинок_теней": "shadow_blade", "отравитель": "poisoner",
    "воин": "warrior", "разбойник": "rogue", "маг": "mage",
}


def background_mask(img: Image.Image) -> Image.Image:
    """255 - фон, 0 - фигура.

    Тёмная ткань местами так же черна, как фон, и простая заливка от края
    протекала внутрь плаща. Поэтому сначала «закрываем» щели в контуре
    (расширить и сузить обратно), потом заливаем снаружи: всё, до чего
    заливка не дошла, - фигура целиком, со всеми тёмными складками."""
    gray = img.convert("L")
    marks = gray.point(lambda v: 0 if v < BG_LEVEL else 255)
    marks = marks.filter(ImageFilter.MaxFilter(CLOSE)).filter(ImageFilter.MinFilter(CLOSE))
    w, h = marks.size
    for x in range(0, w, 8):
        for y in (0, h - 1):
            if marks.getpixel((x, y)) == 0:
                ImageDraw.floodfill(marks, (x, y), 128)
    for y in range(0, h, 8):
        for x in (0, w - 1):
            if marks.getpixel((x, y)) == 0:
                ImageDraw.floodfill(marks, (x, y), 128)
    return marks.point(lambda v: 255 if v == 128 else 0)


def process(path: Path) -> tuple[str, Image.Image]:
    stem = path.stem.removeprefix("силуэт_")
    female = stem.endswith("_ж")
    key = IDS[stem.removesuffix("_ж")]
    img = Image.open(path).convert("RGB")
    bg = background_mask(img)
    # Мягкий край: без него вырезанная фигура «звенит» лесенкой на кромке.
    alpha = Image.eval(bg, lambda v: 255 - v).filter(ImageFilter.GaussianBlur(1.2))
    rgba = img.convert("RGBA")
    rgba.putalpha(alpha)

    solid = alpha.point(lambda v: 255 if v > 40 else 0)
    x0, y0, x1, y1 = solid.getbbox()
    # Центр по капюшону - медиана непрозрачных x в полосе головы. Медиана, а
    # не среднее: пламя на посохе мистика тянуло среднее вбок, и фигуру
    # обрезало краем холста.
    top, bottom = y0 + int((y1 - y0) * 0.04), y0 + int((y1 - y0) * 0.10)
    xs = sorted(x for y in range(top, bottom, 3) for x in range(solid.width) if solid.getpixel((x, y)))
    hood_x = xs[len(xs) // 2]
    # Высота - от верха капюшона, а не от пламени над посохом: иначе фигура
    # мистика выходила мельче остальных, и окна слотов съезжали.
    y0 = next(y for y in range(y0, y1) if any(solid.getpixel((x, y)) for x in range(hood_x - 25, hood_x + 25)))

    scale = (BOTTOM - TOP) / (y1 - y0)
    fig = rgba.resize((round(rgba.width * scale), round(rgba.height * scale)), Image.LANCZOS)
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dx = round(W / 2 - hood_x * scale)
    dy = round(TOP - y0 * scale)
    canvas.paste(fig, (dx, dy), fig)
    name = f"{key}_{'f' if female else 'm'}"
    return name, canvas


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(SRC.glob("силуэт_*.png"))
    if not files:
        sys.exit("нет img/силуэт_*.png")
    for path in files:
        name, canvas = process(path)
        target = OUT / f"{name}.webp"
        canvas.save(target, "WEBP", quality=QUALITY, method=6)
        print(f"{path.name} -> {target.name} {target.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
