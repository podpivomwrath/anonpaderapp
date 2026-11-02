# Сопротивления: промты картинок (2026-11-02)

Готовые файлы клади в `img/` под указанными именами. Руны подключает
`python tools/rune_assets.py`, перстень - `python tools/icon_assets.py`.
Нет файла - в мини-аппе остаётся заглушка, игре это не мешает.

Всего три картинки: две руны героя и перстень.

## Руны героя

Камень и свечение - как у остальных рун героя (`tools/runes_art_prompts.md`):
гладкий тёмно-серый голыш, знак светится янтарём. Хвост промта тот же:

```
a smooth rounded dark grey river pebble rune stone, a simple pictogram carved
deep into its face and glowing with warm amber light from inside the grooves,
dark fantasy game item icon, single object centered, slight 3/4 angle,
painterly semi-realistic, muted desaturated palette of ash grey and charcoal,
weathered stone surface with small chips, soft rim light from the upper left,
deep neutral background, NO letters, NO text, NO runic alphabet, no watermark,
no border, square 1:1 composition, crisp readable silhouette at small size
```

Перед хвостом - знак:

| Файл | Руна | Знак |
|---|---|---|
| `руна_закалка.png` | Закалка - шанс крита по тебе ниже | a blacksmith's anvil with a short blade lying flat on it, three small sparks bouncing off the blade |
| `руна_верный_глаз.png` | Верный глаз - уворот цели ниже | an open eye with a straight arrow passing through the pupil and out the other side |

## Перстень Несгоревшего

Самая редкая вещь в игре: 15 п.п. всех сопротивлений, шанс 0.01% с моба.
Встаёт вторым кольцом в силуэт героя, справа. Иконка 1:1, читается с 40
пикселей, фон тёмный и ровный, как у `особое_кольцо.png`.

Предание (видно в окне перстня): его сняли с паломника, который прошёл
Пепельный круг босиком. Ступни у него были в волдырях, а под кольцом кожа
осталась чистой.

Файл: `особое_перстень_несгоревшего.png`

```
a heavy old signet ring of dark blackened iron, the band worn thin and
pitted, its flat face set with a single small oval stone of pale grey ash
glass with a faint cold blue ember glowing deep inside it, a thin line of
fine white ash still caught in the engraving around the stone while the
metal itself is perfectly clean and unscorched, tiny flakes of grey ash
drifting around the ring, dark fantasy game item icon, legendary relic,
single object centered, slight 3/4 angle, painterly semi-realistic, muted
palette of charcoal, ash grey and a single accent of cold blue, soft rim
light from the upper left, deep neutral dark background, NO letters, NO
text, no watermark, no border, square 1:1 composition, crisp readable
silhouette at small size
```

Если генератор упрямо делает перстень золотым или гладким, добавь в конец:
`not gold, not shiny, old iron, hand forged`.
