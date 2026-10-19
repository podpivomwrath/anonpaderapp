# Промты: картинки к тому, что добавили в октябре без арта

Сцены - **3:2, горизонтально** (как мобы, рейды, события). Карточки магазина -
**1:1, квадрат** (как иконки предметов). Лиц нет: люди со спины, в капюшоне или в тени.
Промты на английском, стилевой хвост уже дописан - копировать целиком.

Уже готовый промт, который ещё не нарисован: **Пепельный меняла** -
`tools/event_art_prompts.md`, раздел «💰 Пепельный меняла» (сейчас временно
стоит картинка скупщика Иргала).

---

# Сцены (бот, 3:2)

Готовую картинку загрузить в альбом (`tools/vk_upload.py`) и прислать номер фото -
впишу в код.

## 🏟 Арена - вход из таверны

Тренировочная яма при таверне: никто не умирает, но бьются всерьёз. Кадр - место,
а не бой.

```
an underground sparring pit behind a tavern, a round sand-covered arena ringed
by a low wooden fence, wooden practice weapons and scarred training dummies
along the walls, lanterns and candles hanging from the beams, a few hooded
spectators leaning on the fence seen from behind, a chalk tally of wins
scratched on a wooden board, dark fantasy scene illustration, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting ash in the air, warm lantern light against cold shadows, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## 🛡 Страж гильдии - бой со Стражем базы

Древний страж, которого гильдия будит на своей земле. Огромный, неподвижный, из
камня и пепла.

```
a colossal ancient guardian statue awakening on a ruined stone platform, cracked
ashen stone body with glowing ember seams, a broken banner pole beside it, a
guild camp with tents and palisade in the background, small hooded figures
seen from behind facing it with raised weapons, dark fantasy scene
illustration, painterly semi-realistic, muted desaturated palette of ash grey,
rust brown and dried blood, drifting ash in the air, moody overcast light, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## ⚔ Осада - начало осадного боя

Две гильдии сходятся у частокола базы. Кадр про натиск, без лиц и без победителя.

```
a siege at dawn on a wooden palisade fort in an ashen wasteland, attackers with
shields and ladders rushing the gate seen from behind, defenders silhouetted on
the wall against smoke, torn guild banners of two colours, burning arrows
arcing through grey sky, dark fantasy scene illustration, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting ash and embers in the air, moody overcast light, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

---

# Карточки магазина (мини-апп, 1:1)

Готовую картинку сохранить в **`miniapp/src/assets/shop/<имя файла>.webp`** -
карточка подхватит её сама, без правки кода (пока файла нет, на карточке эмодзи).
Размер хватит 256×256.

Общий хвост:

```
dark fantasy game item icon, single object centered, slight 3/4 angle,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown and
dried blood, weathered and worn surfaces, soft rim light from the upper left,
deep neutral background, no text, no watermark, no border, square 1:1
composition, crisp readable silhouette at small size
```

## 💎 Самоцветы - 6 пакетов

Один и тот же камень, «Пепельный самоцвет», в нарастающем количестве и таре -
чтобы ряд читался как лестница от меньшего к большему. Камень везде одинаковый:
холодно-голубой кристалл с пепельной дымкой внутри.

**Горсть** - `handful.webp`
```
a small handful of three cold pale-blue faceted crystals with grey ash swirling
inside them, resting on an open weathered palm-shaped leather glove, dark
fantasy game item icon, single object centered, slight 3/4 angle, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, weathered and worn surfaces, soft rim light from the upper left, deep
neutral background, no text, no watermark, no border, square 1:1 composition,
crisp readable silhouette at small size
```

**Мешочек** - `pouch.webp`
```
a small drawstring leather pouch spilling a few cold pale-blue faceted crystals
with grey ash swirling inside them, dark fantasy game item icon, single object
centered, slight 3/4 angle, painterly semi-realistic, muted desaturated palette
of ash grey, rust brown and dried blood, weathered and worn surfaces, soft rim
light from the upper left, deep neutral background, no text, no watermark, no
border, square 1:1 composition, crisp readable silhouette at small size
```

**Кошель** - `purse.webp`
```
a heavy stitched coin purse with a brass clasp, bulging and half open, a dozen
cold pale-blue faceted crystals with grey ash inside visible at the mouth, dark
fantasy game item icon, single object centered, slight 3/4 angle, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, weathered and worn surfaces, soft rim light from the upper left, deep
neutral background, no text, no watermark, no border, square 1:1 composition,
crisp readable silhouette at small size
```

**Ларец** - `casket.webp`
```
a small iron-bound wooden casket with its lid open, filled with cold pale-blue
faceted crystals with grey ash swirling inside, faint blue glow rising from it,
dark fantasy game item icon, single object centered, slight 3/4 angle,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown and
dried blood, weathered and worn surfaces, soft rim light from the upper left,
deep neutral background, no text, no watermark, no border, square 1:1
composition, crisp readable silhouette at small size
```

**Сундук** - `chest.webp`
```
a large reinforced treasure chest with heavy iron bands, lid thrown open and
overflowing with cold pale-blue faceted crystals with grey ash inside, strong
blue glow spilling out, dark fantasy game item icon, single object centered,
slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, weathered and worn surfaces, soft rim light
from the upper left, deep neutral background, no text, no watermark, no border,
square 1:1 composition, crisp readable silhouette at small size
```

**Казна** - `treasury.webp`
```
a heap of cold pale-blue faceted crystals with grey ash inside piled around an
open ancient vault chest and a toppled stone pedestal, crystals spilling onto
the floor, intense blue glow, the richest and largest pile, dark fantasy game
item icon, single object centered, slight 3/4 angle, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, weathered
and worn surfaces, soft rim light from the upper left, deep neutral background,
no text, no watermark, no border, square 1:1 composition, crisp readable
silhouette at small size
```

## 💠 Метка Хранителя - `premium.webp`

Знак, который Хранитель Списков ставит на избранных: светящаяся печать-руна.

```
a glowing ethereal sigil burned into an old parchment page of a ledger, the
mark shaped like a diamond with an eye-like rune inside, faint pale-blue light
and drifting ash around it, a quill resting beside it, dark fantasy game item
icon, single object centered, slight 3/4 angle, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, weathered and worn
surfaces, soft rim light from the upper left, deep neutral background, no text,
no watermark, no border, square 1:1 composition, crisp readable silhouette at
small size
```

## ✏️ Смена ника - `rename.webp`

```
an old leather-bound name ledger lying open, one line of handwriting being
scraped away with a small knife and a fresh quill dipped in ink waiting beside
it, dark fantasy game item icon, single object centered, slight 3/4 angle,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown and
dried blood, weathered and worn surfaces, soft rim light from the upper left,
deep neutral background, no text, no watermark, no border, square 1:1
composition, crisp readable silhouette at small size
```

## 🏛 Смена названия фирмы - `firm_rename.webp`

```
a weathered wooden merchant shop sign hanging on iron chains, the old carved
lettering painted over and a fresh blank plank nailed across it, a paint brush
and hammer resting below, dark fantasy game item icon, single object centered,
slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, weathered and worn surfaces, soft rim light
from the upper left, deep neutral background, no text, no watermark, no border,
square 1:1 composition, crisp readable silhouette at small size
```

## 🧪 Набор зелий - `elixir_pack.webp`

Походный набор алхимика: десяток крупных зелий лечения и по паре боевых, уложенные
в открытый ящик. Должен читаться как «много разных склянок сразу».

```
an open wooden apothecary crate with straw padding, packed with ten large red
healing potion flasks in a row and smaller vials of different colours beside
them - ember orange, black, blood red, pale blue, misty grey and violet - a
leather strap and a wax-sealed label on the lid, dark fantasy game item icon,
single object centered, slight 3/4 angle, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, weathered and worn
surfaces, soft rim light from the upper left, deep neutral background, no text,
no watermark, no border, square 1:1 composition, crisp readable silhouette at
small size
```
