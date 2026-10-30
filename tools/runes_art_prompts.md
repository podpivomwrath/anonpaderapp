# Руны: промты картинок (2026-10-31)

Готовые файлы клади в `img/` под указанными именами - подключу. Нет файла -
в мини-аппе остаётся эмодзи, так что делать можно частями.

Всего: 49 иконок рун, 3 пустых гнезда, замок, рунный круг под ногами героя и
шапка раздела.

## Как устроены иконки

Квадрат 1:1, лучше 1024×1024. Один камень по центру, на нём вырезан
знак-рисунок. **Букв и надписей на камне быть не должно** - генераторы рисуют
их кашей, а знак должен читаться с 40 пикселей.

Вид руны узнаётся по камню, а сама руна - по знаку:

| Вид | Камень | Свечение знака |
|---|---|---|
| Руны героя | гладкий округлый речной голыш, тёмно-серый | тёплое янтарное |
| Руны экипировки | осколок чёрного железняка, оправленный в кованую скобу | багровое |
| Руны навыков | тонкий диск сланца с трещинками по краю | холодное голубое |

Редкость руны рисовать не нужно - её показывает рамка в мини-аппе.

## Общие хвосты

Руны героя:
```
a smooth rounded dark grey river pebble rune stone, a simple pictogram carved
deep into its face and glowing with warm amber light from inside the grooves,
dark fantasy game item icon, single object centered, slight 3/4 angle,
painterly semi-realistic, muted desaturated palette of ash grey and charcoal,
weathered stone surface with small chips, soft rim light from the upper left,
deep neutral background, NO letters, NO text, NO runic alphabet, no watermark,
no border, square 1:1 composition, crisp readable silhouette at small size
```

Руны экипировки:
```
a jagged shard of black ironstone held in a crude forged iron bracket with
rivets, a simple pictogram carved deep into its face and glowing with dull
crimson light from inside the grooves, dark fantasy game item icon, single
object centered, slight 3/4 angle, painterly semi-realistic, muted desaturated
palette of ash grey, rust and charcoal, soft rim light from the upper left,
deep neutral background, NO letters, NO text, NO runic alphabet, no watermark,
no border, square 1:1 composition, crisp readable silhouette at small size
```

Руны навыков:
```
a thin round disc of dark slate with hairline cracks along the rim, a simple
pictogram carved deep into its face and glowing with cold pale blue light from
inside the grooves, dark fantasy game item icon, single object centered,
slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash
grey and slate blue, soft rim light from the upper left, deep neutral
background, NO letters, NO text, NO runic alphabet, no watermark, no border,
square 1:1 composition, crisp readable silhouette at small size
```

Промт иконки = знак из таблицы + хвост своего вида. Пример:
`carved pictogram: a tied coin pouch, ` + хвост рун героя.

## Руны героя (янтарь, речной голыш)

| Файл | Руна | Знак (carved pictogram: ...) |
|---|---|---|
| `руна_пепельная_кожа.png` | Пепельная кожа | a heart covered with overlapping scales |
| `руна_рывок_с_порога.png` | Рывок с порога | an arrow bursting forward through a doorway arch |
| `руна_запас_дыхания.png` | Запас дыхания | two leaves shaped like lungs with a thin wisp rising between them |
| `руна_упрямый_лоб.png` | Упрямый лоб | a ram's head with heavy curled horns, seen from the front |
| `руна_горькая_кровь.png` | Горькая кровь | a single blood drop inside a closed ring |
| `руна_тяжёлый_взгляд.png` | Тяжёлый взгляд | an open eye with three heavy lines pressing down from above |
| `руна_цепкие_пальцы.png` | Цепкие пальцы | a clawed hand closing around a small bone |
| `руна_нюх_старьёвщика.png` | Нюх старьёвщика | a hound's head with its nose down to a small old amulet |
| `руна_намётанный_глаз.png` | Намётанный глаз | an eye with a cut gem in place of the pupil |
| `руна_тугой_кошель.png` | Тугой кошель | a coin pouch tied tight with a cord |
| `руна_битый_опыт.png` | Битый опыт | a round shield with a long healed scar across it |
| `руна_кривая_тропа.png` | Кривая тропа | a winding path with one footprint on it |
| `руна_сон_на_камне.png` | Сон на камне | a crescent moon above a flat stone |
| `руна_живучий.png` | Живучий | a small sprout growing out of a cracked skull |
| `руна_лёгкое_седло.png` | Лёгкое седло | a saddle with a single feather above it |
| `руна_чутьё_забойщика.png` | Чутьё забойщика | a pickaxe striking a spark from a rock |
| `руна_тяжёлый_улов.png` | Тяжёлый улов | a fish hanging from a hook with a weight beneath it |
| `руна_зелёные_пальцы.png` | Зелёные пальцы | an open palm with a leaf sprouting from it |
| `руна_чистая_перегонка.png` | Чистая перегонка | a round flask with one clear drop falling from its neck |
| `руна_сытый_живот.png` | Сытый живот | a bowl with three lines of steam above it |
| `руна_мозоли.png` | Мозоли | a hammer and an awl crossed |
| `руна_метка_монолита.png` | Метка Монолита | a tall narrow standing stone with a handprint on it |
| `руна_язык_без_костей.png` | Язык без костей | a set of balance scales with a coin on one pan |

## Руны экипировки (багрянец, осколок в скобе)

| Файл | Руна | Знак (carved pictogram: ...) |
|---|---|---|
| `руна_молот_по_лежачему.png` | Молот по лежачему | a war hammer above three small stars |
| `руна_красная_жажда.png` | Красная жажда | two fangs with a drop of blood between them |
| `руна_злоба.png` | Злоба | a clenched fist with cracks running across it |
| `руна_колючая_броня.png` | Колючая броня | a breastplate with thorns sticking out of it |
| `руна_глухой_щит.png` | Глухой щит | a solid round shield with no openings and a heavy rim |
| `руна_тонкое_жало.png` | Тонкое жало | a long thin needle blade |
| `руна_последний_надрез.png` | Последний надрез | a blade cutting through a half-empty heart |
| `руна_ответный_выпад.png` | Ответный выпад | two curved arrows, the second one turning back |
| `руна_гнилая_рана.png` | Гнилая рана | a gash with drops oozing from it |
| `руна_лёгкий_шаг.png` | Лёгкий шаг | a footprint with a feather lying across it |
| `руна_отзвук.png` | Отзвук | a dot with three concentric rings around it |
| `руна_жар_и_иней.png` | Жар и иней | a sign split in half, a flame on the left and a snowflake on the right |
| `руна_излишек.png` | Излишек | an overflowing cup, the spill forming a small shield below |
| `руна_обратная_молитва.png` | Обратная молитва | two praying hands turned upside down with a spike between them |
| `руна_свежая_броня.png` | Свежая броня | a breastplate with short rays shining around it |
| `руна_литая_кираса.png` | Литая кираса | a solid cuirass with a round seal stamped on its chest |
| `руна_не_сегодня.png` | Не сегодня | an hourglass with a crack across it and the sand stopped |

## Руны навыков (голубой лёд, сланцевый диск)

| Файл | Руна | Знак (carved pictogram: ...) |
|---|---|---|
| `руна_холодный_счёт.png` | Холодный счёт | an hourglass covered in frost |
| `руна_нажим.png` | Нажим | an open palm pressing down on a blade |
| `руна_кровяная_кромка.png` | Кровяная кромка | a blade edge with drops falling from it |
| `руна_отскок.png` | Отскок | an arrow bouncing off one mark into a second mark |
| `руна_хватка.png` | Хватка | a short chain closed around a wrist |
| `руна_едкость.png` | Едкость | a fang with a long drip hanging from it |
| `руна_тягучесть.png` | Тягучесть | a long stretched drop pulled into a thread |
| `руна_короткий_взмах.png` | Короткий взмах | a short sharp arc next to a half-empty hourglass |
| `руна_подпорка.png` | Подпорка | a stone pillar propping up a cracked shield |

## Гнёзда слотов

Квадрат 1:1, фон тот же. Это пустое гнездо, в которое мини-апп кладёт
иконку руны, - поэтому середина гнезда пустая и тёмная.

Хвост гнёзд:
```
top-down view, an empty round socket carved into a dark stone surface, the
centre of the socket is empty and dark, dark fantasy game ui element,
painterly semi-realistic, muted palette of ash grey and charcoal, soft light
from the upper left, deep neutral background, NO text, no watermark, square
1:1 composition
```

| Файл | Что | Промт (+ хвост гнёзд) |
|---|---|---|
| `гнездо_руна_герой.png` | Гнездо руны героя | a smooth shallow round hollow with a thin worn amber line around the rim |
| `гнездо_руна_экипировка.png` | Гнездо руны экипировки | a socket ringed by a forged iron collar with four rivets, a faint crimson line on the rim |
| `гнездо_руна_навык.png` | Гнездо руны навыка | a shallow socket with a cracked slate rim and a faint cold blue line |
| `гнездо_замок.png` | Закрытое гнездо | the socket is sealed by a rusty iron plate with a heavy old padlock hanging on a chain across it |

## Рунный круг под ногами героя

Подложка под силуэтом героя на вкладке «Герой». Формат широкий 2:1
(2048×1024), вид чуть сверху. **Гнёзд и камней на круге быть не должно**:
12 гнёзд мини-апп ставит сам по окружности, иначе нарисованные разъедутся с
нажимаемыми.

`img/рунный_круг.png`
```
a wide flat ring carved into dark ash-covered ground, seen from a low
three-quarter angle above, a clean empty circular groove with faint worn amber
lines along it, thin cracks radiating outwards, ash drifting over it, the
centre of the circle is empty where a figure would stand, NO stones, NO
sockets, NO symbols on the ring, dark fantasy, painterly, muted palette of
ash grey and charcoal with a faint amber glow, transparent-looking dark
surroundings fading to black at the edges, no text, no watermark, wide 2:1
composition
```

## Шапка раздела «Руны»

Как шапки разделов: полоса 3:1 (1536×512), левая треть тёмная и пустая,
сюжет справа.

`img/шапка_руны.png`
```
a rune carver's workbench in a dark stone room: three rune stones lying on a
leather cloth, a smooth river pebble glowing amber, a black iron shard in a
forged bracket glowing crimson and a thin slate disc glowing pale blue, a
small chisel and a hammer beside them, stone dust on the table, wide banner
composition 3:1, main subject on the right half, the left third fades into
near-black empty darkness, dark fantasy, painterly, ash particles drifting in
the air, low warm light, muted colors with crimson accents, no text, no
letters, no frame, no people in focus
```
