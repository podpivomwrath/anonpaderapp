"""Готовит кадры рассказчика подсказок из img/ для мини-аппа (2026-10-22).

Запуск:  python tools/narrator_assets.py

Исходники - img/рассказчик_<поза>_<кадр>.png, 3 позы по 4 кадра (промты -
tools/narrator_art_prompts.md): 1 - рот закрыт, 2 - приоткрыт, 3 - открыт,
4 - моргает. Что делает:
  1. из кадров 2-4 берёт только лицо и кладёт на кадр 1 с мягким краем:
     правка картинки генератором шевелит шум по всему кадру, и при смене
     кадров плащ и руки мелко дрожали бы; тон лица подгоняет под кадр 1;
  2. вырезает чёрный фон - одна маска на позу, по кадру 1 (у всех кадров
     позы один контур): фигура непрозрачна, тёплый ореол вокруг -
     полупрозрачен по своей яркости, без рваного края;
  3. отражает зеркально: на картинках он смотрит и показывает влево, а в
     мини-аппе стоит слева от текста подсказки и должен смотреть на него;
  4. пишет webp в miniapp/src/assets/narrator/<поза>_<кадр>.webp; в кадрах
     2-4 только овал лица - мини-апп кладёт их поверх кадра 1.

Оригиналы в git не идут (по 2.3 МБ).
"""

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageMath, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "img"
OUT = ROOT / "miniapp" / "src" / "assets" / "narrator"

#: Ширина результата: показываем до ~200 CSS-пикселей, экраны двойной плотности.
WIDTH = 420
QUALITY = 84
BG_LEVEL = 12
CLOSE = 9
#: Свечение вокруг фигуры (тёплый ореол на чёрном) - полупрозрачное по своей
#: яркости: при такой яркости и выше оно уже непрозрачное.
GLOW_FULL = 70


def background_mask(img: Image.Image) -> Image.Image:
    """255 - фон. Как в tools/silhouette_assets.py: закрыть щели в контуре и
    залить фон снаружи; заливка не заходит в тёмные складки плаща."""
    marks = img.convert("L").point(lambda v: 0 if v < BG_LEVEL else 255)
    marks = marks.filter(ImageFilter.MaxFilter(CLOSE)).filter(ImageFilter.MinFilter(CLOSE))
    w, h = marks.size
    # Снизу кадр обрезан по поясу - фигура касается нижнего края, заливку
    # начинаем только с верха и боков.
    seeds = [(x, 0) for x in range(0, w, 8)] + [(x, y) for y in range(0, h, 8) for x in (0, w - 1)]
    for seed in seeds:
        if marks.getpixel(seed) == 0:
            ImageDraw.floodfill(marks, seed, 128)
    return marks.point(lambda v: 255 if v == 128 else 0)


def face_mask(base: Image.Image, frames: list[Image.Image]) -> Image.Image:
    """Где кадры 2-4 по-настоящему отличаются от кадра 1 (рот, веки) - только
    в верхней половине, с запасом и мягким краем."""
    w, h = base.size
    box = None
    for frame in frames:
        diff = ImageChops.difference(base, frame).convert("L").filter(ImageFilter.GaussianBlur(4))
        diff = diff.crop((0, 0, w, h // 2)).point(lambda v: 255 if v > 18 else 0)
        b = diff.getbbox()
        if b:
            box = b if box is None else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
    if box is None:
        sys.exit("кадры позы не отличаются от первого")
    # Генератор при правке рта задевал и шарф с плечами - берём только овал
    # головы с бородой: центр - по верху фигуры, где кроме головы ничего нет.
    alpha = Image.eval(background_mask(base), lambda v: 255 - v)
    top = alpha.getbbox()[1]
    band = alpha.crop((0, top + int(h * 0.02), w, top + int(h * 0.06)))
    xs = sorted(x for y in range(0, band.height, 4) for x in range(0, band.width, 2) if band.getpixel((x, y)))
    cx = xs[len(xs) // 2]
    rx, ry = w * 0.17, h * 0.2
    cy = top + ry
    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    return mask.filter(ImageFilter.GaussianBlur(18))


def match_tone(frame: Image.Image, base: Image.Image, mask: Image.Image) -> Image.Image:
    """Тон лица кадра - как у основного: правка генератором чуть сдвигает
    цвет, и при смене кадров лицо вспыхивало (2026-10-22, «мерцает»)."""
    a = ImageStat.Stat(frame, mask).mean
    b = ImageStat.Stat(base, mask).mean
    bands = [band.point(lambda v, d=b[i] - a[i]: max(0, min(255, round(v + d))))
             for i, band in enumerate(frame.split())]
    return Image.merge("RGB", bands)


def soft_alpha(img: Image.Image) -> Image.Image:
    """Прозрачность: фигура целиком непрозрачна, а свечение вокруг -
    полупрозрачно по своей яркости. Раньше резали по порогу, и ореол
    обрывался рваным краем (2026-10-22, «свечение плохо вырезано»)."""
    hard = Image.eval(background_mask(img), lambda v: 255 - v).filter(ImageFilter.GaussianBlur(1.2))
    glow = img.convert("L").point(lambda v: min(255, round(v * 255 / GLOW_FULL)))
    return ImageChops.lighter(hard, glow)


def unpremultiply(img: Image.Image, alpha: Image.Image) -> Image.Image:
    """Фон был чёрным, значит цвет полупрозрачного ореола на картинке уже
    затемнён на его прозрачность - возвращаем настоящий цвет, иначе ореол
    поверх карточки выйдет грязно-тёмным."""
    bands = []
    for band in img.split():
        out = ImageMath.lambda_eval(
            lambda a: a["c"] * 255 / (a["a"] + (a["a"] == 0)), c=band, a=alpha,
        )
        bands.append(out.convert("L"))  # из целых в 0-255: лишнее срезается
    return Image.merge("RGB", bands)


def process_pose(pose: int) -> None:
    frames = [Image.open(SRC / f"рассказчик_{pose}_{k}.png").convert("RGB") for k in (1, 2, 3, 4)]
    base = frames[0]
    mask = face_mask(base, frames[1:])
    alpha = soft_alpha(base)
    height = round(WIDTH * base.height / base.width)
    for k, frame in enumerate(frames, start=1):
        merged = base if k == 1 else Image.composite(match_tone(frame, base, mask), base, mask)
        rgba = unpremultiply(merged, alpha).convert("RGBA")
        # Кадры 2-4 в мини-аппе лежат ПОВЕРХ кадра 1 - в них только лицо, иначе
        # полупрозрачный ореол сложился бы дважды и пульсировал при смене кадров.
        rgba.putalpha(alpha if k == 1 else ImageChops.multiply(alpha, mask))
        out = ImageOps.mirror(rgba).resize((WIDTH, height), Image.LANCZOS)
        target = OUT / f"{pose}_{k}.webp"
        out.save(target, "WEBP", quality=QUALITY, method=6)
        print(f"рассказчик_{pose}_{k}.png -> {target.name} {target.stat().st_size // 1024} КБ")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for pose in (1, 2, 3):
        process_pose(pose)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
