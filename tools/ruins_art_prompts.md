# Промты: Древние руины культа

Руины - бесконечный подземный рогалик под Подножным забоем у Монолита
(дизайн - `tools/ruins_design.md`). Культ молился Монолиту, его разогнали,
а храм ушёл под землю: тёсаный камень, копоть, свечи, знаки культа,
осколки Монолита в стенах.

**Сцены** - 3:2, горизонтально, как у рейдов и разломов. Лиц нет, игрока в
кадре нет. Имена файлов - `руины_<id>.png` из заголовков. Номера фото
после загрузки в альбом впишу сам (`ruins_config`), пока картинки нет,
сообщение уходит без неё.

**Иконка** ларца рун - в конце, в стиле иконок предметов, кладётся в `img/`
и подключается через `tools/icon_assets.py`.

Всего: 2 входа, 10 комнат с мобами (5 видов × обычные и элита), 16 особых
комнат и сценок, 6 боссов, 3 перехода, 1 иконка - **38 картинок**.

## Общий хвост сцен

Уже дописан в каждый промт ниже - копировать промт целиком.

```
dark fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash grey,
soot black, rust brown and dried blood, warm candle light against cold stone,
drifting ash and dust in the air, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

---

## Вход

### Завал в забое - `руины_вход.png`

Приходит на клетке Подножного забоя (-1; 0) вместе с кнопкой спуска.

```
the far end of a mining tunnel at the foot of a colossal black monolith,
miners' timber props and abandoned pickaxes, a collapsed rock wall cleared
away to reveal old carved stone steps going down into darkness, faded cult
symbols chiselled around the opening, a single lantern left on the top step,
dark fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash grey,
soot black, rust brown and dried blood, warm candle light against cold stone,
drifting ash and dust in the air, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

### Зал у лестницы (пролог) - `руины_пролог.png`

Первое сообщение после спуска.

```
a low-ceilinged underground hall at the bottom of a worn stone staircase,
black soot stains from old campfires on the floor, walls covered with carved
cult symbols around a faint outline of a monolith, three dark archways leading
off in different directions, a few melted candle stubs on stone ledges, dark
fantasy scene illustration, underground cult temple ruins, no player character
in frame, any people seen from behind, hooded or in shadow with faces hidden,
painterly semi-realistic, muted desaturated palette of ash grey, soot black,
rust brown and dried blood, warm candle light against cold stone, drifting ash
and dust in the air, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

---

## Комнаты с мобами

На этаж выпадает один вид мобов. Две картинки на вид: **обычные** (бой и
засада) и **элита** (элита со свитой и хозяин этажа на некратных 5).

### Послушники культа - `руины_послушники.png`

```
a group of gaunt cult novices in grey hooded robes stepping out of the
darkness of a stone corridor, wooden staves in their hands, hoods low over
their faces, prayer beads of monolith shards around their necks, candlelight
behind them, dark fantasy scene illustration, underground cult temple ruins,
no player character in frame, any people seen from behind, hooded or in shadow
with faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, soot black, rust brown and dried blood, warm candle light against cold
stone, drifting ash and dust in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### Старший послушник - `руины_послушники_элита.png`

```
a tall elder cult novice in a heavy ash-grey robe with a red-stained hem,
iron-shod staff topped with a monolith shard, standing in the middle of a
pillared chamber, two hooded novices behind him, hood hiding the face, dark
fantasy scene illustration, underground cult temple ruins, no player character
in frame, any people seen from behind, hooded or in shadow with faces hidden,
painterly semi-realistic, muted desaturated palette of ash grey, soot black,
rust brown and dried blood, warm candle light against cold stone, drifting ash
and dust in the air, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

### Забойщики в масках - `руины_забойщики.png`

```
miners who joined the cult, wearing crude clay masks without eye holes,
leather aprons and pickaxes, coming out of a half-dug side tunnel in an
underground temple, lamps hanging from their belts, rock dust in the air,
dark fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash grey,
soot black, rust brown and dried blood, warm candle light against cold stone,
drifting ash and dust in the air, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

### Бригадир забоя - `руины_забойщики_элита.png`

```
a huge broad-shouldered mine foreman in a cracked clay mask and a chain of
iron keys, a two-handed pickaxe with a stone-crusher head over his shoulder,
standing on a heap of broken rock in a temple hall, masked miners at his
sides, dark fantasy scene illustration, underground cult temple ruins, no
player character in frame, any people seen from behind, hooded or in shadow
with faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, soot black, rust brown and dried blood, warm candle light against cold
stone, drifting ash and dust in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### Свечные служки - `руины_служки.png`

```
thin cult acolytes in wax-stained robes carrying iron pots of boiling candle
wax, lit candles fixed on their shoulders and hoods, molten wax dripping on
the stone floor, a corridor lined with burning candles, faces hidden in
shadow, dark fantasy scene illustration, underground cult temple ruins, no
player character in frame, any people seen from behind, hooded or in shadow
with faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, soot black, rust brown and dried blood, warm candle light against cold
stone, drifting ash and dust in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### Свечной смотритель - `руины_служки_элита.png`

```
a tall candle warden in a robe crusted with layers of old wax, a crown of
dozens of burning candles on the head, holding a long iron ladle of molten
wax, standing among wax pillars in a dim chapel hall, two acolytes beside
him, face lost in shadow and dripping wax, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### Ползуны из завала - `руины_ползуны.png`

```
pale blind cave crawlers the size of large dogs pouring out of a pile of
fallen rubble, long jointed limbs, chitin plates dusted with stone grit, no
eyes, wide toothy mouths, crawling over broken temple columns, dark fantasy
scene illustration, underground cult temple ruins, no player character in
frame, any people seen from behind, hooded or in shadow with faces hidden,
painterly semi-realistic, muted desaturated palette of ash grey, soot black,
rust brown and dried blood, warm candle light against cold stone, drifting
ash and dust in the air, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

### Матёрый ползун - `руины_ползуны_элита.png`

```
an old giant blind cave crawler the size of a cart, chitin overgrown with
stone and monolith shards, scarred jaws, coiled around a broken altar in a
collapsed temple hall, smaller crawlers swarming at its legs, dark fantasy
scene illustration, underground cult temple ruins, no player character in
frame, any people seen from behind, hooded or in shadow with faces hidden,
painterly semi-realistic, muted desaturated palette of ash grey, soot black,
rust brown and dried blood, warm candle light against cold stone, drifting
ash and dust in the air, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

### Безглазые стражи - `руины_стражи.png`

```
temple guards in rusted scale armour and closed helmets with no eye slits,
heavy round shields painted with a faded monolith sign, marching in a line
down a pillared corridor, spears lowered, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### Страж ворот - `руины_стражи_элита.png`

```
a giant gate guardian in blackened plate armour and a smooth eyeless helm,
a tower shield as tall as a door, standing in front of massive bronze temple
gates, eyeless guards flanking him, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

---

## Особые комнаты

### 🗡 Засада - `руины_засада.png`

```
a narrow temple corridor with deep wall niches, hooded cultists stepping out
of every niche at once with knives drawn, a dropped travel bag on the floor
in the foreground, sense of being surrounded, dark fantasy scene
illustration, underground cult temple ruins, no player character in frame,
any people seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, soot black, rust brown
and dried blood, warm candle light against cold stone, drifting ash and dust
in the air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### ⛲ Источник - `руины_источник.png`

```
a clear cold spring bursting from a crack in a carved temple wall and
filling a shallow stone basin shaped like a bowl, moss around the edges, the
water faintly glowing, a calm quiet chamber, dark fantasy scene
illustration, underground cult temple ruins, no player character in frame,
any people seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, soot black, rust brown
and dried blood, warm candle light against cold stone, drifting ash and dust
in the air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### 🩸 Алтарь - `руины_алтарь.png`

```
a heavy black stone altar crusted with old brown blood, a ritual knife lying
on it, grooves in the stone leading down to a bowl, a small monolith shard
embedded in the altar glowing dull red, candles burned to stumps around it,
dark fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, soot black, rust brown and dried blood, warm candle light against cold
stone, drifting ash and dust in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### 🪤 Ловушка - `руины_ловушка.png`

```
a temple corridor floor of square stone plates, one plate pressed down,
rows of rusted iron spikes shooting out of holes in both walls, dust bursting
from the gaps, motion and danger, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### ⚰️ Склеп - `руины_склеп.png`

```
a cult crypt with burial niches cut into the walls, bones of novices laid in
rows, stone lids carved with lines of ritual words, one lid pushed aside, a
pale greenish glow from the words, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### 🔁 Колодец - `руины_колодец.png`

```
a dry stone well in the centre of a round chamber, offerings piled on its
rim - old rings, belt buckles, teeth, small carved figures, a faint glow
rising from the dark bottom of the well, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### ⛏ Обвал - `руины_обвал.png`

```
a temple passage half blocked by a fresh rockfall, a narrow gap under a
cracked stone beam with sharp edges, broken timber props, and to the side a
dark wall niche where hooded shapes stir, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### ⛓ Пленник - `руины_пленник.png`

Тот самый второй забойщик из рассказа наставника.

```
an exhausted miner in torn work clothes chained to a temple wall, head
hanging down so the face is hidden, an empty water bowl beside him, two
cult guards asleep against pillars nearby with spears across their knees,
dark fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, soot black, rust brown and dried blood, warm candle light against cold
stone, drifting ash and dust in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### 🏺 Кладовая - `руины_кладовая.png`

```
a cult storeroom crammed with clay jugs, wrapped bundles and wooden crates
under wax seals, a heavy door with a warning scratched into it, a faint red
curse glow seeping from under the seals, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### 📿 Молельня - `руины_молельня.png`

```
a small prayer chamber with a kneeling bench before a carved monolith relief,
rows of copper offering bowls on the floor filled with relics - bone charms,
shards, dark crystals, prayer beads hanging from hooks, dark fantasy scene
illustration, underground cult temple ruins, no player character in frame,
any people seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, soot black, rust brown
and dried blood, warm candle light against cold stone, drifting ash and dust
in the air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### 💰 Тайник - `руины_тайник.png`

```
an old iron-bound chest in the corner of a dusty temple chamber, its lock
smashed off, the lid slightly open with a glint of old offerings inside,
cobwebs and fallen plaster around, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### 💰 Мимик - `руины_мимик.png`

```
the same iron-bound chest come alive, its lid gaping open as a huge mouth
full of jagged teeth and a long grey tongue, splintered planks for legs,
lunging forward from the corner of a temple chamber, coins and relics spilling
out, dark fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash grey,
soot black, rust brown and dried blood, warm candle light against cold stone,
drifting ash and dust in the air, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

---

## Сценки (комната «❓ Событие»)

### Склад свечей - `руины_сценка_свечи.png`

```
a storeroom piled to the ceiling with thousands of melted candle stubs, some
with rings, beads and small bones melted into the wax, a few still burning,
dark fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, soot black, rust brown and dried blood, warm candle light against cold
stone, drifting ash and dust in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### Старый сектант - `руины_сценка_отшельник.png`

```
a very old cult member sitting cross-legged in a wall niche, wrapped in a
rotten grey robe, long white beard visible below the hood, a patched bag and
a clay cup beside him, one bony hand raised as if beginning a long story,
dark fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, soot black, rust brown and dried blood, warm candle light against cold
stone, drifting ash and dust in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### Сундук с печатью - `руины_сценка_печать.png`

```
a small dark wooden chest on a stone pedestal, sealed with a large red wax
seal pressed with the monolith sign, thin wisps of warm vapour rising from
under the seal, dark fantasy scene illustration, underground cult temple
ruins, no player character in frame, any people seen from behind, hooded or
in shadow with faces hidden, painterly semi-realistic, muted desaturated
palette of ash grey, soot black, rust brown and dried blood, warm candle
light against cold stone, drifting ash and dust in the air, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

### Надпись на стене - `руины_сценка_надпись.png`

```
a temple wall with old carved cult symbols, and on top of them fresh dark red
paint in the same strange symbols but in a different order, paint still
dripping, a brush and a paint pot left on the floor, dark fantasy scene
illustration, underground cult temple ruins, no player character in frame,
any people seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, soot black, rust brown
and dried blood, warm candle light against cold stone, drifting ash and dust
in the air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

---

## Уникальные боссы (этажи 5, 10, 15, 20, 25, 30)

### Привратник завала - `руины_босс_привратник.png`

Засыпает игроков камнями, своды над ним дрожат.

```
a massive hulking golem of piled boulders and broken temple masonry rising
out of a rockfall, long arms ending in stone slabs, a dull red glow between
the stones of its chest, cracks spreading across the vaulted ceiling above
it, small rocks raining down, dark fantasy scene illustration, underground
cult temple ruins, no player character in frame, any people seen from
behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### Счетовод культа - `руины_босс_счетовод.png`

Записывает долги, на третьей записи взыскивает.

```
a gaunt hooded cult accountant hunched at a huge stone desk piled with
ledgers and debt books, a quill dipped in dark red ink in one bony hand,
heavy iron abacus beside him with beads of monolith shards, long scrolls of
names hanging from the desk to the floor, face hidden under the hood, dark
fantasy scene illustration, underground cult temple ruins, no player
character in frame, any people seen from behind, hooded or in shadow with
faces hidden, painterly semi-realistic, muted desaturated palette of ash
grey, soot black, rust brown and dried blood, warm candle light against cold
stone, drifting ash and dust in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### Свечница - `руины_босс_свечница.png`

Лечится, пока горят свечи вокруг.

```
a tall female cult figure in a long gown made of layered dripping wax,
standing in a ring of tall burning candles on iron stands, threads of warm
light flowing from the candle flames into her body, her face hidden behind a
veil of melted wax, a hall full of candlelight and smoke, dark fantasy scene
illustration, underground cult temple ruins, no player character in frame,
any people seen from behind, hooded or in shadow with faces hidden, painterly
semi-realistic, muted desaturated palette of ash grey, soot black, rust brown
and dried blood, warm candle light against cold stone, drifting ash and dust
in the air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### Глашатай - `руины_босс_глашатай.png`

Заранее кричит, какой удар отразит.

```
a cult herald in a torn ceremonial chasuble standing on a raised stone
pulpit, blowing a long curved horn made of bone, a heavy iron sceptre in the
other hand, a faint shimmering mirror-like barrier in front of him, face
hidden in the shadow of a tall mitre, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### Братья-копатели - `руины_босс_братья.png`

Два тела, дерутся спина к спине.

```
two huge cult gravedigger brothers standing back to back in a hall of open
graves, one with a broad shovel and one with a pickaxe, matching leather
masks and patched aprons, the same build like twins, piles of fresh earth
around them, dark fantasy scene illustration, underground cult temple ruins,
no player character in frame, any people seen from behind, hooded or in
shadow with faces hidden, painterly semi-realistic, muted desaturated palette
of ash grey, soot black, rust brown and dried blood, warm candle light against
cold stone, drifting ash and dust in the air, no text, no watermark, no logo,
no modern objects, horizontal 3:2 composition
```

### Настоятель - `руины_босс_настоятель.png`

Объявляет обеты, нарушение карает всех.

```
the cult abbot in a long black robe with a high collar, swinging a smoking
iron censer on a chain, standing before a great carved monolith relief at
the end of a cathedral-like underground hall, rows of empty stone pews, the
censer smoke forming faint ritual symbols in the air, face hidden in deep
shadow, dark fantasy scene illustration, underground cult temple ruins, no
player character in frame, any people seen from behind, hooded or in shadow
with faces hidden, painterly semi-realistic, muted desaturated palette of
ash grey, soot black, rust brown and dried blood, warm candle light against
cold stone, drifting ash and dust in the air, no text, no watermark, no logo,
no modern objects, horizontal 3:2 composition
```

---

## Переходы

### Хозяин повержен, спуск ниже - `руины_спуск.png`

```
a defeated stone throne in an empty hall, behind it a newly opened
staircase leading further down into deeper red darkness, and on the other
side a faint daylight falling down an old stairway going up, a choice
between two ways, dark fantasy scene illustration, underground cult temple
ruins, no player character in frame, any people seen from behind, hooded or
in shadow with faces hidden, painterly semi-realistic, muted desaturated
palette of ash grey, soot black, rust brown and dried blood, warm candle
light against cold stone, drifting ash and dust in the air, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

### Выход наверх - `руины_выход.png`

```
a small group of tired adventurers seen from behind climbing worn stone
steps up out of the ruins into a mining tunnel, heavy sacks on their
shoulders, lantern light from the miners waiting above, the black monolith
visible through the tunnel mouth, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

### Группа легла - `руины_гибель.png`

```
an empty temple hall after a lost battle, abandoned travel sacks and broken
weapons scattered on the floor, candles going out one by one, cult shadows
gathering up the sacks in the background, dark fantasy scene illustration,
underground cult temple ruins, no player character in frame, any people seen
from behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, soot black, rust brown and dried
blood, warm candle light against cold stone, drifting ash and dust in the
air, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

---

## Иконка: 🔮 Ларец рун - `ларец_рун.png`

Одна серия с Пепельным ларцом и ларцами разлома: тот же размер и ракурс.
Картинку положить в `img/` и запустить `python tools/icon_assets.py`.

```
a small heavy stone chest carved with cult runes and the sign of the
monolith, lid slightly open, soft orange, violet and golden rune light
glowing from inside, small runestones visible at the rim, dark fantasy game
item icon, single object centered, slight 3/4 angle, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, weathered and worn surfaces, soft rim light from the upper left, deep
neutral background, no text, no watermark, no border, square 1:1
composition, crisp readable silhouette at small size
```
