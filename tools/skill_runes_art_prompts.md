# Руны-навыки: промты картинок (2026-11-10)

Готовые файлы кладите в `img/` под указанными именами, я подключу. Пока
файла нет, в мини-аппе остаётся эмодзи, так что делать можно частями.

Всего нужно:
- 38 иконок рун-навыков;
- 2 иконки новых огранок;
- 1 гнездо руны-навыка;
- 1 значок пробуждения;
- по желанию новая шапка раздела «Руны».

Нынешние «руны навыков» (сланцевые диски с голубым знаком) становятся
огранками, и их картинки остаются как есть. Гнездо `гнездо_руна_навык.png`
тоже остаётся: теперь это гнездо огранки внутри руны-навыка.

## Как устроены иконки

Те же правила, что у прошлых рун: квадрат 1:1, лучше 1024×1024, один камень
по центру, знак вырезан на камне. **Букв и надписей на камне быть не должно**:
генераторы рисуют их кашей, а знак должен читаться с 40 пикселей.

Руна-навык - четвёртый вид камня, он должен отличаться от трёх прошлых с
первого взгляда:

| Вид | Камень | Свечение знака |
|---|---|---|
| Руны героя | речной голыш | тёплое янтарное |
| Руны экипировки | осколок железняка в скобе | багровое |
| Огранки (бывшие руны навыков) | сланцевый диск | холодное голубое |
| **Руны-навыки** | тяжёлая шестигранная плитка вулканического стекла со сколом на углу | бледное серебристое с фиолетовым отливом |

Редкость рисовать не нужно: её показывает рамка в мини-аппе.

## Хвост рун-навыков

```
a heavy hexagonal tablet of black volcanic glass with one chipped corner and
faint hairline cracks, a simple pictogram carved deep into its face and
glowing with pale silver light with a faint violet tint from inside the
grooves, dark fantasy game item icon, single object centered, slight 3/4
angle, painterly semi-realistic, muted desaturated palette of ash grey,
charcoal and cold violet, glossy chipped edges catching soft rim light from
the upper left, deep neutral background, NO letters, NO text, NO runic
alphabet, no watermark, no border, square 1:1 composition, crisp readable
silhouette at small size
```

Промт иконки = знак из таблицы + хвост. Пример для Кровопуска:

```
carved pictogram: a curved blade with a single drop falling from its tip into
an open palm below, a heavy hexagonal tablet of black volcanic glass with one
chipped corner ... (дальше хвост целиком)
```

## Руны-навыки

### Удары

| Файл | Навык | Знак (carved pictogram: ...) |
|---|---|---|
| `навык_рассекающий_удар.png` | Рассекающий удар | a broad sword swinging in a wide diagonal arc with a long cut trail behind it |
| `навык_двойной_укол.png` | Двойной укол | two short daggers striking forward side by side, points touching one mark |
| `навык_теневой_рывок.png` | Теневой рывок | a dagger thrusting forward with three fading copies of it trailing behind |
| `навык_скользящий_рез.png` | Скользящий рез | a thin curved blade slicing past a small hunting mark shaped like a triangle |
| `навык_жатва_меток.png` | Жатва меток | a sickle gathering three small triangular marks into its curve |
| `навык_казнь.png` | Казнь | a heavy axe blade coming down onto a cracked half-empty heart |
| `навык_удар_щитом.png` | Удар щитом | a round shield thrust forward with short impact lines bursting from its rim |

### Вампиризм

| Файл | Навык | Знак |
|---|---|---|
| `навык_кровопуск.png` | Кровопуск | a curved blade with a single drop falling from its tip into an open palm below |
| `навык_жатва.png` | Жатва | a sickle above a half-filled heart, the heart filling up from the bottom |
| `навык_кровавая_печать.png` | Кровавая печать | a round wax seal stamped with a blood drop, small drips running from its edge |
| `навык_багровый_пир.png` | Багровый пир | a goblet tipped over, a thick stream pouring from it into a heart |
| `навык_иссушение.png` | Иссушение | a withered hand pulling a thin thread of light out of a cracked chain |

### Урон за ход

| Файл | Навык | Знак |
|---|---|---|
| `навык_отравленный_клинок.png` | Отравленный клинок | a narrow blade with three drops hanging along its edge |
| `навык_огненная_плеть.png` | Огненная плеть | a whip curling through the air, its tail turning into a flame |
| `навык_токсический_выброс.png` | Токсический выброс | a round flask bursting apart, drops flying out in every direction |

### Стихии

| Файл | Навык | Знак |
|---|---|---|
| `навык_цепь_молний.png` | Цепь молний | a lightning bolt splitting into three branches, each ending in a small dot |
| `навык_схождение_стихий.png` | Схождение стихий | a flame, a snowflake and a lightning bolt meeting at one bright centre point |

### Контроль и ослабления

| Файл | Навык | Знак |
|---|---|---|
| `навык_оглушающий_натиск.png` | Оглушающий натиск | a heavy mace striking a helmet, three small stars circling above |
| `навык_ледяные_оковы.png` | Ледяные оковы | a pair of shackles made of jagged ice, joined by a short chain |
| `навык_дурманящий_дротик.png` | Дурманящий дротик | a small dart with a spiral of haze trailing behind it |
| `навык_разложение.png` | Разложение | a cracked shield with a spreading stain eating through it |

### Защита и усиления себя

| Файл | Навык | Знак |
|---|---|---|
| `навык_боевой_клич.png` | Боевой клич | an open shouting mouth with three wide sound arcs coming out of it |
| `навык_дымовая_завеса.png` | Дымовая завеса | a curling cloud of smoke with a dagger half hidden inside it |
| `навык_глухая_оборона.png` | Глухая оборона | a tall tower shield planted in the ground with a crouching outline behind it |
| `навык_несокрушимый.png` | Несокрушимый | a standing stone with a sword blade snapped in two against it |

### Поддержка

| Файл | Навык | Знак |
|---|---|---|
| `навык_кровавый_пакт.png` | Кровавый пакт | two hands clasped together with a single drop between the palms |
| `навык_оберег.png` | Оберег | a small amulet hanging over a dome-shaped shield of light |
| `навык_круг_тьмы.png` | Круг тьмы | a dark ring with five small hearts placed evenly around it |

### Новые навыки

| Файл | Навык | Знак |
|---|---|---|
| `навык_чистая_вода.png` | Чистая вода | a cupped hand pouring a clear stream that washes a dark stain away |
| `навык_горькая_рана.png` | Горькая рана | a gash with a crossed-out heart above it |
| `навык_раскол.png` | Раскол | a round shield split in two halves by a single straight crack |
| `навык_немота.png` | Немота | a closed mouth sealed with two crossed stitches |
| `навык_ответный_удар.png` | Ответный удар | an arrow striking a shield and a second arrow flying straight back the way it came |
| `навык_сорвать_покров.png` | Сорвать покров | a hand tearing a veil off a small glowing shape |
| `навык_передышка.png` | Передышка | an hourglass lying on its side with a feather resting on it |
| `навык_прикрыть_собой.png` | Прикрыть собой | a large figure outline stepping in front of a smaller one with an arm raised |

### Мифические

| Файл | Навык | Знак |
|---|---|---|
| `навык_сомкнуть_ряды.png` | Сомкнуть ряды | three tall shields standing edge to edge in a tight wall |
| `навык_расплата.png` | Расплата | a fist made of cracks and scars striking forward, small shards breaking off behind it |

## Новые огранки

Это огранки, им нужен хвост **рун навыков** (сланцевый диск, голубой
знак) из `tools/runes_art_prompts.md`, а не хвост рун-навыков.

| Файл | Огранка | Знак |
|---|---|---|
| `руна_прищур.png` | Прищур | a narrowed eye with a thin crosshair over the pupil |
| `руна_добивание.png` | Добивание | a blade pointing down at a heart that is almost empty |

## Гнездо руны-навыка

Хвост гнёзд - из `tools/runes_art_prompts.md` (пустое круглое гнездо, вид
сверху). Это гнездо для самой руны-навыка, их 3 на персонажа.

| Файл | Что | Промт (+ хвост гнёзд) |
|---|---|---|
| `гнездо_навык.png` | Гнездо руны-навыка | a hexagonal socket with a glossy black volcanic glass rim, chipped at one corner, a faint pale silver-violet line along the rim |

## Значок пробуждения

Маленький значок в углу пробуждённой руны: 1:1, 512×512, читается с 20
пикселей. Видит только сам игрок.

`img/пробуждение.png`
```
a small open eye made of pale silver-violet light with short rays around it,
glowing softly, simple bold shape, dark fantasy game ui badge, painterly,
transparent-looking dark background, NO text, NO letters, no watermark,
square 1:1 composition, readable at tiny size
```

## Шапка раздела «Руны» (по желанию)

Нынешняя шапка показывает три камня. Если хотите, чтобы на ней был и
четвёртый вид, вот замена для `img/шапка_руны.png`. Если нет, оставим старую.

```
a rune carver's workbench in a dark stone room: four rune stones lying on a
leather cloth, a smooth river pebble glowing amber, a black iron shard in a
forged bracket glowing crimson, a thin slate disc glowing pale blue and a
heavy hexagonal tablet of black volcanic glass glowing pale silver-violet in
the middle, a small chisel and a hammer beside them, stone dust on the table,
wide banner composition 3:1, main subject on the right half, the left third
fades into near-black empty darkness, dark fantasy, painterly, ash particles
drifting in the air, low warm light, muted colors with crimson accents, no
text, no letters, no frame, no people in focus
```
