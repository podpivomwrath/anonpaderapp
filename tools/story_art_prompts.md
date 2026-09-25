# Промты: пути подкласса и сюжетные акты

Продолжение `tools/raid_art_prompts.md`. Там три кадра рейда, здесь шесть
путей и шестнадцать актов. Слоты под всё это уже есть в коде (патч 88):
`path_images` в `content/npc/list_keeper.json` и `image` у акта в
`content/story/<регион>.json`.

Пропорции везде **3:2, горизонтально** — как у рейда и у мобов. Вертикальный
кадр чат ВК обрежет.

Лор взят из самой игры: описания путей — из реплик Хранителя Списков, акты —
из заданий, которые игрок читает в ту же секунду.

---

# Пути подкласса

Шесть кадров. Показываются в тот момент, когда игрок читает про путь целиком
и ещё может передумать.

**Лицо у фигуры скрыто везде.** Игрок выбирает не персонажа со стороны, а
себя: любое конкретное лицо будет спорить с тем, кого он уже придумал.
Поэтому фигура со спины или в три четверти, лицо в тени. По той же причине
нигде нет пола и возраста — читается роль, а не человек.

Фигура смещена от центра, рядом пустое место: так кадр не спорит с текстом,
который идёт тем же сообщением.

## Общий хвост путей

```
dark fantasy character card, single figure, face hidden in shadow or turned
away, three-quarter back view, plain dark backdrop with heavy vignette,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown and
dried blood, figure off-centre with empty space beside it, no text, no
watermark, no logo, horizontal 3:2 composition
```

## Страж — несокрушимая защита

«Не бежит от удара, а встречает его». Щит развёрнут к зрителю, ноги в упоре,
корпус развёрнут навстречу — вся поза про движение НАВСТРЕЧУ, а не в укрытие.

```
a heavily armoured figure braced behind a huge battered tower shield, feet set
wide and weight forward, leaning into an incoming blow rather than away from
it, shield face scarred with countless impacts and hasty field repairs, plate
dented but whole, dark fantasy character card, single figure, face hidden in
shadow or turned away, three-quarter back view, plain dark backdrop with heavy
vignette, painterly semi-realistic, muted desaturated palette of ash grey, rust
brown and dried blood, figure off-centre with empty space beside it, no text,
no watermark, no logo, horizontal 3:2 composition
```

## Кровавый рыцарь — сила через кровь врагов

«Платит за чужую кровь своей». Собственные раны открыты и не перевязаны, и
чем их больше, тем увереннее стойка — это и есть механика, показанная телом.

```
a warrior in torn heavy armour standing straighter the more wounded he is, deep
unbandaged cuts across arms and side, blood running down the armour and along
the blade and beading at its tip, gauntlet gripping the hilt hard enough to
shake, posture growing more confident rather than failing, dark fantasy
character card, single figure, face hidden in shadow or turned away,
three-quarter back view, plain dark backdrop with heavy vignette, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, figure off-centre with empty space beside it, no text, no watermark, no
logo, horizontal 3:2 composition
```

## Клинок теней — смертельная точность

«Решает исход одним ударом раньше, чем противник поймёт, что бой начался».
Поэтому в кадре не удар, а момент ПЕРЕД ним: клинок ещё опущен, фигура уже на
расстоянии вытянутой руки от цели.

```
a lean figure in dark close-fitting leathers standing already within arm's
reach of an unaware target, blade still lowered and not yet raised, absolute
stillness a heartbeat before the strike, soft edges dissolving into the shadow
behind, no struggle and no motion blur anywhere in frame, dark fantasy
character card, single figure, face hidden in shadow or turned away,
three-quarter back view, plain dark backdrop with heavy vignette, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, figure off-centre with empty space beside it, no text, no watermark, no
logo, horizontal 3:2 composition
```

## Отравитель — яды и увядание

«Враг проигрывает медленно и не понимает, когда это началось». Значит, в
кадре ничего не происходит: спокойная фигура, закрытые склянки, и только
пожухшая трава под ногами выдаёт, что уже началось.

```
a hooded figure standing calmly and doing nothing threatening, rows of small
stoppered glass vials on a bandolier across the chest, a thin blade held loosely
point-down, the grass and moss directly underfoot withered brown in a spreading
circle while everything further away is still alive, quiet and patient posture,
dark fantasy character card, single figure, face hidden in shadow or turned
away, three-quarter back view, plain dark backdrop with heavy vignette,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown and
dried blood, figure off-centre with empty space beside it, no text, no
watermark, no logo, horizontal 3:2 composition
```

## Элементалист — ярость стихий

«Повелевает тем, что этот мир предпочёл бы забыть: огнём, льдом, бурей». Три
стихии в одном кадре, и все три неуправляемы: пламя по одной руке, иней по
другой, ветер рвёт плащ в третью сторону.

```
a robed figure with three elements at once and none of them obedient, fire
crawling up one sleeve, frost creeping down the other arm and over the fingers,
storm wind tearing the cloak sideways against the direction of both, ash and
sparks and ice crystals caught together in the air, the one accent of colour in
the frame, dark fantasy character card, single figure, face hidden in shadow or
turned away, three-quarter back view, plain dark backdrop with heavy vignette,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown and
dried blood, figure off-centre with empty space beside it, no text, no
watermark, no logo, horizontal 3:2 composition
```

## Тёмный мистик — кровавые пакты

«Обращает чужую боль в чужое спасение». Единственный путь, где в кадре двое:
иначе пакт не показать. Вторая фигура — лежащая, и нить крови идёт ОТ мистика
к ней, а не наоборот.

```
a hooded figure kneeling beside a wounded body lying on the ground, one palm
cut open and held out, a thin thread of blood running from the kneeling figure
toward the wounded one rather than away from it, faint sigils drawn in blood on
the ground between them, the wounded body's colour returning while the kneeling
figure's hand shakes, dark fantasy character card, face hidden in shadow or
turned away, plain dark backdrop with heavy vignette, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, figures
off-centre with empty space beside them, no text, no watermark, no logo,
horizontal 3:2 composition
```

---

# Сюжетные акты

Шестнадцать кадров: четыре региона по четыре акта. Акт 1 не входит — его
первое задание выдаёт наставник, и к тому сообщению уже прикреплён его
портрет.

**Главное правило: кадр не должен спойлерить акт.** Картинка приходит вместе
с ВЫДАЧЕЙ первого задания, то есть до того, как игрок узнает, чем акт
кончится. Поэтому нигде не нарисован тот, чьё имя откроется в конце: ни
Магистр, ни Ольхвейн, ни Хелст, ни Мать Углей. Кадр показывает МЕСТО, куда
игрока отправляют, и ровно ту улику, ради которой он идёт.

Людей в кадре либо нет, либо одна мелкая фигура для масштаба — читается
место, а не сцена.

У каждого региона свой акцент, иначе четыре линии сольются в одну серую кашу.

## Обетованный Кряж — камень, снег, устав Ордена

Акцент: холодный серый камень и сталь, снег, синеватые тени.

### Акт 2 «Гнилое снабжение» — забытый редут

Склад в редуте, который по бумагам пуст с самого раскола. Осколки разложены и
пересчитаны, как обычный товар, — страшно именно от бухгалтерской
аккуратности.

```
a collapsed stone redoubt interior lit by a single shaft of daylight through
the broken vault, crates of glowing monolith shards stacked in tidy counted
rows with inventory tags, everything neatly ordered and accounted for, rust and
dry dust, no people, dark fantasy landscape, cold grey stone and steel with
snow and bluish shadows, painterly semi-realistic, muted desaturated palette of
ash grey, rust brown and dried blood, overcast light, fine ash in the air, wide
establishing shot, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

### Акт 3 «Клинок Ордена» — рудничные провалы

Тайная выработка. Осколки не покупают — их ДОБЫВАЮТ руками пленных, которых
Орден не считает даже пропавшими.

```
a hidden mining pit sunk into a cliff of broken rock, raw monolith shards being
cut straight out of a glowing vein in the pit wall, abandoned picks and lengths
of heavy shackle chain lying where they were dropped, scaffolding and ore
baskets, seen from above and far off with only tiny distant figures for scale,
dark fantasy landscape, cold grey stone and steel with snow and bluish shadows,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown and
dried blood, overcast light, fine ash in the air, wide establishing shot, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### Акт 4 «Имя в Совете» — ветреный перевал

«Снег на перевале чистый и скрипит под сапогом». Чистота снега тут и есть
тревога: по нему сразу видно, что следов больше, чем должно быть.

```
a high narrow mountain pass under a pale sky, clean untouched snow between
black rocks, a single line of bootprints entering the frame and several more
sets of prints waiting behind the rocks on both sides, wind lifting loose snow,
no visible people, dark fantasy landscape, cold grey stone and steel with snow
and bluish shadows, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, overcast light, fine ash in the air, wide
establishing shot, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

### Акт 5 «Дорога к сердцу» — край пятого кольца

Ближе к сердцу, чем положено кому-либо из Ордена. На горизонте багровеет
зарево центра — единственное цветное пятно в кадре.

```
the last ridge before the centre of the world, bare scoured stone and no snow
left, a deep crimson glow burning on the horizon as the only colour in the
frame, the air itself shimmering with heat and ash, a narrow path running
straight toward the glow, no people, dark fantasy landscape, cold grey stone
and steel with bluish shadows, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, fine ash in the air, wide
establishing shot, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

## Шепчущие Пущи — корень, гниль, менгиры

Акцент: болезненная зелень и мокрая чёрная кора.

### Акт 2 «Гниль в корнях» — багровые топи

Осколки в воде вбиты ровным рядом — «не украдены, воткнуты». Ровность ряда и
есть улика: это не грабёж, а пытка.

```
a stagnant swamp hollow where the water stands dark red and smells of iron,
monolith shards driven into the mud in one deliberate straight evenly spaced
row beneath the shallow water, tree roots around them blackened and twisted as
if in pain, mist low over the surface, no people, dark fantasy landscape,
sickly green and wet black bark, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, overcast light, wide
establishing shot, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

### Акт 3 «Отступник» — просека, которой не должно быть

«Прорублена ровно, без топора лесорубов». Осколки вдоль неё — разметка. Это
не вырубка, это дорога, и ведёт она к центру.

```
an unnaturally straight clearing cut through dense old forest, edges sheared
smooth rather than chopped, monolith shards driven into the ground along both
sides at regular intervals like survey markers, the cut line running dead
straight to a distant crimson glow on the horizon, unnatural stillness and not
a single bird, no people, dark fantasy landscape, sickly green and wet black
bark, painterly semi-realistic, muted desaturated palette of ash grey, rust
brown and dried blood, overcast light, wide establishing shot, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

### Акт 4 «Голос из глубины» — поворот просеки

Там, где просека поворачивает, ждёт засада. В кадре её ещё не видно — только
неправильный свет между стволами, тёплый там, где ничего тёплого быть не
должно.

```
the point where a straight cut forest road bends out of sight, dense trunks
crowding both sides, a wrong warm orange light leaking faintly from between the
trees where no fire or sun could be, everything else cold and damp and green,
fallen druid robes and a broken staff at the roadside, no visible people, dark
fantasy landscape, sickly green and wet black bark, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, overcast
light, wide establishing shot, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

### Акт 5 «Договор расторгнут» — глубина, где лес почти мёртв

Тишина здесь не пустая, а выжатая: деревья стоят, но уже ничего не значат.

```
the deepest part of the forest where the trees are still standing but entirely
dead, grey bark stripped bare and no leaves and no undergrowth at all, the
ground covered in fine pale ash instead of moss, monolith shards embedded in
every visible trunk, a crimson glow filtering through from far ahead, absolute
silence implied, no people, dark fantasy landscape, dead grey wood, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, wide establishing shot, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## Соляные Пристани — соль, туман, остовы

Акцент: белёсая соль, мокрое дерево, зелень рассола.

### Акт 2 «Чужие деньги» — свалка остовов

В трюме ящики с осколками, уложенные под опись. Груз шёл транзитом, не
задерживаясь: Пристани — всего лишь перевалочный пункт.

```
a graveyard of beached rotting ship hulls half sunk in salt flats, the split
open hold of one hull exposed to view with crates of glowing shards stacked in
counted rows inside, water dripping steadily from the ribs of the hull, waxed
shipping seals and waterlogged ledgers scattered on the boards, no people, dark
fantasy landscape, pale salt crust, wet timber and brine green, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, heavy fog, wide establishing shot, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

### Акт 3 «Тот, кто платит» — причалы без фрахта

«Днём там подозрительно пусто». Суда без опознавательных знаков уходят не в
море, а вглубь, по соляным руслам.

```
a row of long empty wooden piers in thick fog, unmarked ships with no flags and
no names moored along them, their bows all turned inland toward a salt channel
leading away from the sea, cargo hooks swinging in the damp with nobody working
them, gulls absent, no people, dark fantasy landscape, pale salt crust, wet
timber and brine green, painterly semi-realistic, muted desaturated palette of
ash grey, rust brown and dried blood, heavy fog, wide establishing shot, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### Акт 4 «Списанные» — затопленные склады

Замки на дверях изнутри. Это не убийство, а уборка — и кадр должен читаться
именно так: спокойно, без следов борьбы.

```
a flooded stone warehouse interior with knee deep still black water, heavy iron
padlocks hanging on the inside faces of the doors, crates floating undisturbed,
no signs of struggle anywhere, cold light through a high barred window, the
water perfectly flat, no people, dark fantasy landscape, pale salt crust, wet
timber and brine green, painterly semi-realistic, muted desaturated palette of
ash grey, rust brown and dried blood, wide establishing shot, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

### Акт 5 «Расчёт» — личный причал барона

Он сидит там, «будто ничего не боится». Кадр — про эту спокойную уверенность:
причал ухоженный, чистый, единственное целое место во всех Пристанях.

```
a private deep water pier in immaculate repair, fresh paint and polished
brasswork and swept boards, sharply out of place among the rotting wrecks
visible behind it in the fog, lanterns already lit in daylight, one empty chair
set facing the water, no people, dark fantasy landscape, pale salt crust, wet
timber and brine green, painterly semi-realistic, muted desaturated palette of
ash grey, rust brown and dried blood, heavy fog, wide establishing shot, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## Выжженный Предел — пепел, угли, обряд

Акцент: горячий оранжевый уголь и чёрная сажа. Единственный регион, где есть
живой огонь.

### Акт 2 «Те, кто не ждут» — кострища не по обряду

«Горят там, где обрядов не назначали. Слишком ярко для обычного пепла». В
золе кости, и не звериные.

```
several large bonfires still burning on an open ash plain at dusk, burning far
brighter and hotter than the scattered ceremonial fire circles nearby, pale
bones visible half buried in the ash around them, no ritual markings or
offerings anywhere, thick smoke going straight up in dead air, no people, dark
fantasy landscape, hot orange embers and black soot, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, fine ash in
the air, wide establishing shot, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

### Акт 3 «Голос из пепла» — подвал Старого квартала

Осколки в стенах сложены в спираль. Ту же спираль игрок уже видел на лице
Шрама — поэтому её нужно нарисовать читаемо, это опознавательный знак.

```
an underground stone cellar hall with no wind and stale heavy air, monolith
shards driven into the walls arranged in one clear large spiral pattern, the
spiral distinct and readable as a deliberate symbol, chalk marks and burnt out
candle stubs on the floor beneath it, faint light from a stairway behind, no
people, dark fantasy interior, hot orange embers and black soot, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, wide establishing shot, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

### Акт 4 «Топливо» — вихрь против ветра

«Плохой знак даже для Предела». В вихре мелькают лица, и все со шрамами —
жгут своих, самых верных.

```
a towering column of whirling ash moving visibly against the direction of the
wind across a burnt plain, faint human faces suggested and half dissolved
within the swirling ash, ritual scar spirals just readable on those faces,
everything else in frame bending the other way in the true wind, no people on
the ground, dark fantasy landscape, hot orange embers and black soot, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, wide establishing shot, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

### Акт 5 «Второй раскол» — сердце пепла

«Вокруг неё сухо и очень жарко». Ни дыма, ни пламени — только жар, от
которого дрожит воздух.

```
the dead centre of a burnt land where the ash lies undisturbed and perfectly
smooth, no smoke and no visible flame at all, only fierce heat distorting and
rippling the air, the ground cracked into pale dry plates, a crimson glow
beneath the cracks, absolute stillness, no people, dark fantasy landscape, hot
orange embers and black soot, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, wide establishing shot, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```
