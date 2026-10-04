# Промты: долгие путешествия и торговля

Картинки в чат для двух новых систем (2026-10): долгих путешествий (AFK) и
караванов торговли. Иконки товаров и повозки - не здесь, а в
`tools/icon_prompts.md`, раздел «Товары торговли» (они идут в мини-апп).

Пропорции **3:2, горизонтально**, как у событий, рейдов и сюжета: вертикальный
кадр чат ВК обрежет.

**Лиц нет.** Люди со спины, в капюшоне, в тени. Игрока в кадре нет.

## Куда вписать готовую картинку

Загрузить в альбом (`tools/vk_upload.py`), полученный id фото:
- **отправление** - полем `image` у путешествия в `VOYAGE_IMAGES`
  (`game/economy/voyage_config.py`), приходит с сообщением «Отряд уходит...»;
- **легендарные события** - в `LEGENDARY_IMAGES` того же файла, ключ
  `(город, номер события)`, приходит с вестью этого часа;
- **караван** - `CARAVAN_PHOTO_ID` в `game/economy/trade_config.py`, приходит,
  когда повозка доехала до каравана.

Пустая строка = картинки ещё нет, сообщение уходит без неё.

---

## Общий хвост

```
dark fantasy scene illustration, no player character in frame, any people
seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting ash in the air, moody overcast light, no text, no watermark,
no logo, no modern objects, horizontal 3:2 composition
```

Хвост уже дописан в каждый промт ниже - копировать целиком.

---

# Отправление (4 картинки)

## ⛵ Пристани - «Плавание за туман» - `docks`

Корабль отходит от причала прямо в стену тумана на краю мира.

```
a weathered single-mast sailing ship leaving a salt-crusted wooden pier at
dusk, heading straight into a towering wall of grey fog that stands on the
sea like a cliff, the faint red glow of a distant monolith behind on the
shore, black still water, a few hooded figures on deck seen from behind,
dark fantasy scene illustration, no player character in frame, any people
seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting ash in the air, moody overcast light, no text, no watermark,
no logo, no modern objects, horizontal 3:2 composition
```

## 🧗 Кряж - «Восхождение к Пустым Вершинам» - `ridge`

Отряд с вьючными козами поднимается по узкой тропе к вершинам в облаках пепла.

```
a small roped party of climbers with laden pack goats ascending a narrow
switchback path on a sheer grey mountainside, the peaks above lost in
churning clouds of ash, a tiny abandoned hermitage clinging to a ledge high
above, iron pitons hammered into the rock, dark fantasy scene illustration,
no player character in frame, any people seen from behind, hooded or in
shadow with faces hidden, painterly semi-realistic, muted desaturated palette
of ash grey, rust brown and dried blood, drifting ash in the air, moody
overcast light, no text, no watermark, no logo, no modern objects, horizontal
3:2 composition
```

## 🛞 Предел - «Переход через Стеклянную пустошь» - `scorched`

Ночь, повозка на широких колёсах уходит по пустоши, где песок спёкся в стекло.

```
a covered wagon with very wide iron-rimmed wheels setting out at night across
an endless desert of fused glass, the glass surface cracked into plates and
faintly reflecting a sky that is not there, heat shimmer still rising, the
smoky silhouette of a fortified border town behind, dark fantasy scene
illustration, no player character in frame, any people seen from behind,
hooded or in shadow with faces hidden, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## 🌲 Пущи - «Тропа в Глубокий лес» - `woods`

Отряд уходит по старой тропе в лес, где деревья стоят слишком тесно.

```
a small hooded party walking single file down an old overgrown path into a
dense ancient forest, the trees leaning close together like a crowd, pale
moss glowing faintly on the roots, the trail vanishing into darkness ahead,
the last light of the forest edge behind them, dark fantasy scene
illustration, no player character in frame, any people seen from behind,
hooded or in shadow with faces hidden, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

---

# Легендарные события (12 картинок)

Выпадают редко (~2% в час), поэтому каждое - со своей картинкой: игрок
должен почувствовать, что это не обычная весть. Номер - позиция события в
списке `legendary` своего путешествия.

## ⛵ Пристани

### `docks`, 0 - Сундук на дне

```
a small rowing boat resting on the sea floor seen through clear dark water
from above, a heavy iron-bound chest sitting in it with a wax seal of a salt
harbour, chains trailing up toward the surface, dark fantasy scene
illustration, no player character in frame, any people seen from behind,
hooded or in shadow with faces hidden, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

### `docks`, 1 - Второй Монолит на дне

```
the sea suddenly perfectly transparent to the bottom, far below a smaller
intact dark monolith standing upright on the seabed, unbroken and faintly
glowing crimson, the ship's hull shadow above it, dark fantasy scene
illustration, no player character in frame, any people seen from behind,
hooded or in shadow with faces hidden, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

### `docks`, 2 - Что-то яркое за туманом

```
a rift tearing open in a wall of grey sea fog, a blinding warm golden light
rising beyond it over the edge of the water like a sunrise, sailors on deck
seen from behind shielding their eyes, dark fantasy scene illustration, no
player character in frame, any people seen from behind, hooded or in shadow
with faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, drifting ash in the air, moody overcast
light, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

## 🧗 Кряж

### `ridge`, 0 - Келья Хранителя

```
a bare stone cell carved into a mountain peak, empty bookshelves on every
wall, a single small casket tied with a grey ribbon on a plain wooden desk,
a narrow window showing clouds of ash below, dark fantasy scene illustration,
no player character in frame, any people seen from behind, hooded or in
shadow with faces hidden, painterly semi-realistic, muted desaturated palette
of ash grey, rust brown and dried blood, drifting ash in the air, moody
overcast light, no text, no watermark, no logo, no modern objects, horizontal
3:2 composition
```

### `ridge`, 1 - Багровая слеза на вершине

```
a single tear-shaped drop of crimson glass lying on bare rock at the very
summit of a mountain, glowing softly, wind-blown ash streaming past it, the
whole world hidden below in cloud, dark fantasy scene illustration, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, drifting ash in the air, moody overcast
light, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### `ridge`, 2 - Звёзды

```
a mountain camp at night above the clouds of ash, a small fire, a sky full of
real stars for the first time, hooded climbers seen from behind staring up, a
mysterious chest standing by the fire that was not there before, dark
fantasy scene illustration, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, drifting
ash in the air, moody overcast light, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

## 🛞 Предел

### `scorched`, 0 - Ларец, вплавленный в стекло

```
a lone ornate chest half fused into the surface of a glass desert, cracks
radiating from it, no tracks anywhere around, a wagon waiting at a distance,
dark fantasy scene illustration, no player character in frame, any people
seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting ash in the air, moody overcast light, no text, no watermark,
no logo, no modern objects, horizontal 3:2 composition
```

### `scorched`, 1 - Капля Монолита прожгла стекло

```
a small glowing crimson droplet sitting at the bottom of a fresh molten crater
burned through a glass desert down to the sand, steam rising, the glass
around it still softly glowing orange, dark fantasy scene illustration, no
player character in frame, any people seen from behind, hooded or in shadow
with faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, drifting ash in the air, moody overcast
light, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### `scorched`, 2 - Застава из миража

```
an old abandoned frontier outpost standing in a glass desert, solid and real
though it shimmers like a mirage, its storeroom door open revealing a locked
chest in the dark, dark fantasy scene illustration, no player character in
frame, any people seen from behind, hooded or in shadow with faces hidden,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, drifting ash in the air, moody overcast light, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

## 🌲 Пущи

### `woods`, 0 - Живое дерево

```
a single tree with fresh living green leaves in the middle of a grey dead
forest, the only colour for miles, a small chest bound in vines nestled among
its roots, dark fantasy scene illustration, no player character in frame,
any people seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting ash in the air, moody overcast light, no text, no watermark,
no logo, no modern objects, horizontal 3:2 composition
```

### `woods`, 1 - Слеза Монолита во мху

```
a forest clearing opening in a perfect circle, in its centre a crimson
tear-shaped crystal half overgrown with soft moss, faint light pulsing from
it, the trees around leaning away, dark fantasy scene illustration, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, drifting ash in the air, moody overcast
light, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### `woods`, 2 - Тот, кто шепчет

```
a tall thin shape made of bark and shadow standing between the trees at the
edge of firelight, barely visible, watching a sleeping camp, a chest left by
the dying fire, dark fantasy scene illustration, no player character in
frame, any people seen from behind, hooded or in shadow with faces hidden,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, drifting ash in the air, moody overcast light, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

---

# Торговля

## 🐪 Караван - `CARAVAN_PHOTO_ID`

Приходит, когда повозка доехала до каравана. Одна картинка на все караваны:
место у каждого своё, кадр задаёт встречу, а не клетку.

```
a resting merchant caravan of several covered wagons drawn in a loose circle
on an ash plain, lanterns lit, crates and bales stacked open for trade,
hooded traders seen from behind, a single banner of patched cloth, dark
fantasy scene illustration, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, drifting
ash in the air, moody overcast light, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```
