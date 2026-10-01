# Промты: события исследования

Картинки к событиям исследования — и к новым со сценами (патч 110,
`content/events/scenes.json`), и к двум старым, у которых картинки до сих
пор нет (рыбак у воды, обнажённая жила).

Картинка приходит **с первой сценой** события, одна на всё событие. Дальше
игрок читает сцены уже без картинок, так что кадр должен задавать место и
настроение, а не показывать исход: исход игрок выберет сам.

Пропорции **3:2, горизонтально**, как у мобов, рейда и сюжета: вертикальный
кадр чат ВК обрежет.

**Лиц нет.** Люди в кадре со спины, в капюшоне, в тени или в профиль против
света. Игрок — никогда не в кадре: он смотрит на сцену своими глазами.

**Куда вписать готовую картинку.** Загрузить в альбом (tools/vk_upload.py),
полученный id фото:
- для нового события — полем `"image": "4572xxxxx"` в
  `content/events/scenes.json` у нужного события;
- для рыбака и жилы — в `EVENT_PHOTO_IDS` в `bot/world_texts.py`.

---

## Общий хвост

```
dark fantasy scene illustration, first-person view of a traveller who has
just stopped on the road, no player character in frame, any people seen from
behind, hooded or in shadow with faces hidden, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, drifting
ash in the air, moody overcast light, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

Хвост уже дописан в каждый промт ниже — копировать целиком.

---

# Средние события

## 🪨 Завал на тропе — `rockfall`

Тропа перегорожена плитой, из-под неё торчит край чужой сумки. Кадр про
выбор: плита тяжёлая, но сумка манит.

```
a narrow mountain path blocked by a huge fallen stone slab, the strap and
corner of a leather satchel sticking out from under the slab, loose scree and
dust still settling, a steep rock wall on one side, dark fantasy scene
illustration, first-person view of a traveller who has just stopped on the
road, no player character in frame, any people seen from behind, hooded or in
shadow with faces hidden, painterly semi-realistic, muted desaturated palette
of ash grey, rust brown and dried blood, drifting ash in the air, moody
overcast light, no text, no watermark, no logo, no modern objects, horizontal
3:2 composition
```

## 🩸 Путник без сил — `thirsty_wanderer`

Раненый путник сидит у камня, повязка на боку промокла. Он не просит — просто
смотрит, и это хуже.

```
an exhausted wounded traveller slumped against a large stone at the roadside,
hood down over the face, one hand pressed to a blood-soaked bandage on the
side, an empty waterskin at his feet, a walking staff dropped in the ash,
dark fantasy scene illustration, first-person view of a traveller who has just
stopped on the road, no player character in frame, any people seen from
behind, hooded or in shadow with faces hidden, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## 💥 Земля уходит из-под ног — `crumbling_ledge`

Край обрыва ползёт вниз прямо сейчас. Кадр должен давить: трещина у самых
ног, камни уже летят.

```
the edge of a cliff crumbling away right beneath the viewer's feet, a fresh
crack racing through the ground, chunks of rock and ash falling into a misty
drop below, dynamic tilted angle, sense of sudden danger, dark fantasy scene
illustration, first-person view of a traveller who has just stopped on the
road, no player character in frame, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## 🎲 Игрок в кости — `dice_player`

Человек у костра лениво подбрасывает кости. Расслаблен, как тот, кто редко
проигрывает.

```
a lone man in a worn travelling coat sitting cross-legged by a small campfire
at night, face hidden under a wide-brimmed hat, two bone dice resting on a
flat stone in front of him, a small pile of coins beside the stone, one hand
lazily tossing a third die, relaxed confident posture, dark fantasy scene
illustration, first-person view of a traveller who has just stopped on the
road, no player character in frame, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, warm firelight
against the cold dark, drifting ash in the air, no text, no watermark, no
logo, no modern objects, horizontal 3:2 composition
```

## 🎲 Шулер в капюшоне — `hooded_cheat`

Фигура в глубоком капюшоне расстилает тряпицу с костями и самоцветами. В
отличие от игрока у костра — от него тянет опасностью.

```
a figure in a deep dark hood kneeling on a worn cloth spread over the ash,
face completely lost in the shadow of the hood, pale thin fingers arranging
bone dice and a few glittering crimson gemstones on the cloth, long sleeves
hiding something, unsettling stillness, dark fantasy scene illustration,
first-person view of a traveller who has just stopped on the road, no player
character in frame, painterly semi-realistic, muted desaturated palette of
ash grey, rust brown and dried blood, drifting ash in the air, moody overcast
light, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

## 🐾 Кровь на камнях — `blood_on_stones`

Тёмная полоса крови уходит по камням вдаль. Что-то крупное ранено и уползло
— и оно ещё живо.

```
a trail of dark blood smeared across grey rocks and ash, leading away into
the fog, deep claw marks and a broken arrow shaft beside the trail, the
trail disappearing between boulders in the distance, tense quiet mood, dark
fantasy scene illustration, first-person view of a traveller who has just
stopped on the road, no player character in frame, no creature visible,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, drifting ash in the air, moody overcast light, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

## 🗺 Обрывок карты — `torn_map`

Клочок пергамента прибит ветром к ногам: грубые ориентиры и печать.

```
a torn scrap of old parchment caught against a stone at the viewer's feet,
crude hand-drawn landmarks, a dotted route and a wax seal stamp on it,
edges burnt and ragged, ash drifting over it in the wind, close-up at ground
level with the wasteland blurred behind, dark fantasy scene illustration,
first-person view of a traveller who has just stopped on the road, no player
character in frame, painterly semi-realistic, muted desaturated palette of
ash grey, rust brown and dried blood, moody overcast light, no readable text
on the map, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

## 🔥 Огни на горизонте — `distant_fires`

Вдалеке, где никто не живёт, горят три костра — ровно в ряд. Слишком ровно.

```
three small campfires burning far away on a dark ash plain at dusk, placed
in a perfectly straight line, thin columns of smoke rising in the still air,
no people visible, vast empty wasteland between the viewer and the fires,
ominous calm, dark fantasy scene illustration, first-person view of a
traveller who has just stopped on the road, no player character in frame,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, drifting ash in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

## 🦉 Зарубки на дереве — `carved_marks`

На мёртвом дереве свежая зарубка: стрелка и число шагов. Кто-то приглашает.

```
a dead grey tree trunk with a fresh knife carving, an arrow pointing
sideways and a row of tally notches beneath it, pale wood showing through
the cut bark, wood shavings on the ash at the roots, the rest of the dead
forest fading into fog, dark fantasy scene illustration, first-person view of
a traveller who has just stopped on the road, no player character in frame,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, drifting ash in the air, moody overcast light, no letters or
numbers, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## 🦴 Разбитый алтарь — `broken_altar`

Алтарь расколот надвое, на нём ещё лежат подношения — кости, бусины,
огарки. Одного места явно не хватает.

```
a small roadside stone altar split in two by a deep crack, old offerings
still lying on it: small bones, clay beads, burnt candle stubs and a dried
flower, one empty hollow in the centre where something is missing, dark
fantasy scene illustration, first-person view of a traveller who has just
stopped on the road, no player character in frame, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, drifting
ash in the air, moody overcast light, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

## 🪞 Неподвижная вода — `mirror_marsh`

Лужа среди пепла гладкая, как зеркало. Отражение в ней чуть-чуть не
совпадает с миром — это и есть главное.

```
a perfectly still black pool of water in a hollow among ash and dead reeds,
mirror-smooth surface reflecting the grey sky, the reflection subtly wrong:
the reflected dead tree has leaves while the real one is bare, eerie silence,
dark fantasy scene illustration, first-person view of a traveller who has
just stopped on the road, no player character in frame, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting ash in the air, moody overcast light, no text, no watermark,
no logo, no modern objects, horizontal 3:2 composition
```

---

# Глубокие события

## 🕳 Колодец — `old_well`

Старый колодец, цепь уходит в темноту, снизу тянет холодом. Кадр сверху
вниз — взгляд в провал.

```
an old ruined stone well in a deserted yard, a rusted iron chain hanging
down into complete darkness, looking down over the rim into the shaft, damp
moss on the stones, cold mist rising from below, dark fantasy scene
illustration, first-person view of a traveller who has just stopped on the
road, no player character in frame, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## 💎 Трещина с осколками — `shard_crack`

В скале трещина, набитая багровыми светящимися осколками. Видно, что вся
порода вокруг держится еле-еле.

```
a deep crack in a grey rock face packed with glowing blood-red crystal
shards, faint crimson light spilling out of the crack, hairline fractures
spreading across the surrounding stone, small pebbles trickling down,
tempting and unstable, dark fantasy scene illustration, first-person view of
a traveller who has just stopped on the road, no player character in frame,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood with a crimson glow accent, drifting ash in the air, no text,
no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## 🔥 Безглазый у костра — `campfire_riddle`

Старик без глаз у костра. Он смотрит прямо на тебя — хотя смотреть нечем.
Глаза закрыты повязкой, лицо в тени — видно только рот в усмешке.

```
an old blind man sitting by a campfire at night, a dirty cloth tied over his
eyes, face mostly in shadow with only a thin knowing smile lit by the fire,
wrapped in a patched grey cloak, a small leather pouch on the ground beside
him, head turned toward the viewer as if he sees, dark fantasy scene
illustration, first-person view of a traveller who has just stopped on the
road, no player character in frame, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, warm firelight
against the cold dark, drifting ash in the air, no text, no watermark, no
logo, no modern objects, horizontal 3:2 composition
```

---

# Финалы следов

Финал приходит, когда игрок дошёл по следу до конца. Кадр — награда за
дорогу: здесь должно ощущаться «я нашёл».

## 🐾 Логово — `trail_blood_finale`

След крови обрывается у расщелины. Внутри в темноте — что-то большое и
тяжело дышащее: видны только очертания и отсвет глаз.

```
a dark rocky cleft at the end of a blood trail, the blood leading straight
into the opening, inside the darkness the huge silhouette of a wounded
beast barely visible, two faint glints of eyes, steam of breath in the cold
air, bones scattered at the entrance, dark fantasy scene illustration,
first-person view of a traveller who has just stopped on the road, no player
character in frame, painterly semi-realistic, muted desaturated palette of
ash grey, rust brown and dried blood, drifting ash in the air, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

## 🛒 Брошенная телега — `trail_cart_finale`

Колея приводит к опрокинутой телеге. Груз цел. У колеса дремлет сторож с
тесаком на коленях.

```
an overturned wooden cart on a muddy ash road, crates and sacks of cargo
spilled but intact, a broken wheel, a hooded guard dozing against the other
wheel with a heavy cleaver resting across his knees, face hidden under the
hood, dark fantasy scene illustration, first-person view of a traveller who
has just stopped on the road, no player character in frame, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting ash in the air, moody overcast light, no text, no watermark,
no logo, no modern objects, horizontal 3:2 composition
```

## 🗺 Печать на камне — `trail_map_finale`

Метка с карты — плоский камень с печатью. Под печатью выбиты строки загадки,
которые не прочесть на картинке, — только ощущение надписи.

```
a large flat stone slab half buried in ash, a carved circular seal in the
centre of it, several lines of worn chiselled runes beneath the seal, the
same seal as on an old map, a faint gap under the edge of the slab hinting
at a hidden cache, dark fantasy scene illustration, first-person view of a
traveller who has just stopped on the road, no player character in frame,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, drifting ash in the air, moody overcast light, no readable
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## 🔥 Стоянка культа — `trail_fires_finale`

Трое в серых робах поют над котлом. Пожитки сложены в стороне — близко, но
не настолько, чтобы взять незаметно.

```
three cultists in grey hooded robes standing around a smoking iron cauldron
at a night camp, seen from behind and in profile with faces hidden by hoods,
chanting with raised hands, their bags and bundles piled a few steps away in
the foreground, three campfires in a straight line behind them, dark fantasy
scene illustration, first-person view of a traveller hiding at the edge of
the camp, no player character in frame, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, firelight
against the dark, drifting ash in the air, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

## 🦉 Пустой тайник — `trail_false_1`, `trail_false_2`

Одна картинка на оба пустых тайника ложного следа. Тайник вскрыт — и пуст,
только на дне новая зарубка-стрелка.

```
a small hidden cache dug under the roots of a dead tree, the wooden lid
pulled aside, the pit completely empty, a fresh carved arrow and tally
notches on the inner wall of the pit pointing onward, dark fantasy scene
illustration, first-person view of a traveller who has just stopped on the
road, no player character in frame, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no letters or numbers, no watermark, no logo,
no modern objects, horizontal 3:2 composition
```

## 🦉 Конец пути — `trail_false_3`

Под последней зарубкой — сундук, замок открыт. На крышке нацарапано
«Дошедшему» — на картинке без букв, просто царапины.

```
an old iron-bound chest resting at the foot of a dead tree marked with many
carved arrows, the padlock hanging open, the lid slightly ajar with a warm
glint of treasure inside, scratches on the lid like a short carved
dedication, a sense of reward after a long search, dark fantasy scene
illustration, first-person view of a traveller who has just stopped on the
road, no player character in frame, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no readable text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

---

# Старые события без картинки

## 🎣 Рыбак у воды — `lakeside_fisher`

Человек с двумя вёдрами у кромки воды. Торгуется — значит, смотрит оценивающе,
но лица не видно.

```
a stocky fisherman sitting on an upturned bucket at the edge of a grey lake,
two wooden buckets of fish beside him, a rolled net and a rod laid on the
shore, hood and scarf hiding his face, leaning forward as if sizing up a
deal, mist over the still water, dark fantasy scene illustration, first-person
view of a traveller who has just stopped on the road, no player character in
frame, painterly semi-realistic, muted desaturated palette of ash grey, rust
brown and dried blood, drifting ash in the air, moody overcast light, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## ⛏ Обнажённая жила — `ore_vein`

Осыпь вскрыла породу, в ней тускло блестит рудная прожилка — немного, на
один заход кирки.

```
a fresh rockslide that has torn open a hillside, a thin vein of dull
metallic ore glinting in the exposed rock, loose scree and dust at the foot,
an old abandoned pickaxe lying nearby, small and modest find, dark fantasy
scene illustration, first-person view of a traveller who has just stopped on
the road, no player character in frame, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, drifting ash in
the air, moody overcast light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

---

# Групповые события

`content/events/group_scenes.json`. Картинка приходит всем участникам с
первой сценой. Отличие от соло: в кадре место для **нескольких** путников -
со спины или в тени, лиц нет, как везде. Готовый id - полем `"image"` у
события в `content/events/group_scenes.json`.

## 📦 Схрон дезертиров — `g_deserters_cache`

```
an opened wooden chest wrapped in oiled leather lying under the roots of an
uprooted tree, coins, a few small vials and a heavy wrapped bundle inside,
several hooded travellers crouching around it seen from behind, hands
hovering over the chest but nobody touching it yet, tense stillness, dark
fantasy scene illustration, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, drifting ash in the air,
moody overcast light, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

## 🗳 Развилка над оврагом — `g_ravine_fork`

```
a path ending at the edge of a deep ravine, a rickety bridge of lashed poles
spanning it, the black mouth of a tunnel far below, a narrow trail winding
away along the ridge, a small group of hooded travellers standing at the edge
seen from behind, each looking a different way, dark fantasy scene
illustration, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, drifting ash in the air, moody overcast
light, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```

## 🪨 Завал — `g_rockfall`

```
inside an old collapsed mine gallery, cracked timber beams bowing under the
weight of the ceiling, dust raining down, the exit buried under a pile of
rocks with a thin line of grey daylight above it, silhouettes of several
travellers bracing the beams with their shoulders while another pulls stones
away, faces hidden in shadow, dark fantasy scene illustration, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, drifting dust in the air, dim light from above, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

## 🌫 Трясина — `g_bog`

```
a fog-covered bog at dusk, a hooded traveller sunk to the waist in black mud
reaching out with one hand, two or three other hooded figures at the edge of
firm ground seen from behind, one stepping forward with a rope, one turning
away toward abandoned bags lying on a hummock, dark fantasy scene
illustration, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, drifting ash in the air, moody overcast
light, no text, no watermark, no logo, no modern objects, horizontal 3:2
composition
```
