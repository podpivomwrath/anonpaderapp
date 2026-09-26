# Промты: пути подкласса, сюжетные акты, враги, рудники и озёра

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

---

# Сюжетные враги

Семь именных врагов, которым не досталось картинки: у них нет ни своей, ни
базового моба, от которого её можно было бы унаследовать. Среди них финальные
боссы трёх регионов, а сражались они до сих пор без портрета, при том что у
любого рядового волка он есть.

**Здесь врага показывать можно и нужно** — в отличие от кадров актов.
Портрет приходит в начале боя, то есть после сцены, где враг уже появился.
Спойлерить уже нечего.

Портрет по пояс, лицом к зрителю, фигура смещена от центра, а за спиной
видно место боя. Лицо врага, в отличие от путей подкласса, открыто: это не
игрок, это противник, и его надо узнать.

Место за спиной у Хелста и Матери Углей совпадает с кадрами их актов,
которые уже нарисованы: кресло на причале и гладкий пепел в сердце Предела.
Так бой читается продолжением той же сцены.

Куда вписывать номера фото: поле `image` у `named_enemy` в
`content/story/<регион>.json`.

## Общий хвост врагов

```
dark fantasy enemy portrait for a turn-based fight, single figure from the
waist up facing the viewer, three-quarter view, figure off-centre with the
place of the fight visible behind, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, hard dramatic side light, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## Надсмотрщик глубин — Кряж, акт 3

Кнут в одной руке, клинок в другой — он привык, что боятся обоих. За спиной
тайная выработка: пленные Меченые в кандалах. Он заметил тебя первым —
поэтому смотрит прямо, без удивления.

```
a broad mine overseer holding a coiled whip in one hand and a short heavy
blade in the other, calm unimpressed stare straight at the viewer, dust and
grit in his beard, behind him a hidden mining pit where shackled prisoners
chip glowing shards out of a rock vein under lantern light, cold grey stone and
steel with bluish shadows, dark fantasy enemy portrait for a turn-based fight,
single figure from the waist up facing the viewer, three-quarter view, figure
off-centre with the place of the fight visible behind, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, hard dramatic side light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## Чужой посредник — Кряж, акт 4

Чужой выговор, чужой герб на плаще — не из Кряжа и не из соседних земель.
Герб не должен совпасть ни с чем в игре: вся суть в том, что его никто не
узнаёт. Сделка оборвана на полуслове — в руке ещё осколок.

```
a well dressed foreign broker in a travelling cloak with an unfamiliar heraldic
emblem that belongs to no known land, one hand still holding a glowing shard
mid deal, the other already reaching for a hidden knife, cold measuring look
of someone who does not leave witnesses, behind him a windswept snowy mountain
pass with a half loaded pack mule, cold grey stone and steel with snow and
bluish shadows, dark fantasy enemy portrait for a turn-based fight, single
figure from the waist up facing the viewer, three-quarter view, figure
off-centre with the place of the fight visible behind, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, hard dramatic side light, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## Магистр-отступник — Кряж, финал

Держит клинок так, будто держал его всю жизнь, а не только годы
предательства. Осколки на броне светятся собственным, неправильным светом.
Спокоен: ждал этого разговора годами. Не злодей в маске — старый солдат,
который давно всё для себя решил.

```
an aging knight commander of a military order in ornate but battle worn plate,
holding a long sword with the easy grip of a lifetime, monolith shards set into
the armour glowing with a wrong unnatural light, completely calm and patient
expression of a man who has long made his decision, grey close cropped hair,
behind him the last bare ridge before the centre of the world with a deep
crimson glow on the horizon, cold grey stone and steel with bluish shadows,
dark fantasy enemy portrait for a turn-based fight, single figure from the
waist up facing the viewer, three-quarter view, figure off-centre with the
place of the fight visible behind, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, hard dramatic side light, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## Тот, что носит её лицо — Пущи, акт 1

Движется слишком плавно для человека и слишком твёрдо для тени. Лицо
травницы сидит на нём, как маска, снятая с ещё тёплого тела. Страшно
именно тем, что лицо обычное и доброе, а всё остальное — нет.

```
a tall wrong shaped figure wearing the ordinary kind face of a village herb
woman like a mask, the face slightly too small for the head and not moving with
the body, the body beneath too smooth and too long limbed to be human, dark
bark like skin at the neck where the face ends, behind it a spilled wicker
basket on wet moss with berries already sprouted, trees standing in the wrong
places, sickly green and wet black bark, dark fantasy enemy portrait for a
turn-based fight, single figure from the waist up facing the viewer,
three-quarter view, figure off-centre with the place of the fight visible
behind, painterly semi-realistic, muted desaturated palette of ash grey, rust
brown and dried blood, hard dramatic side light, no text, no watermark, no logo,
no modern objects, horizontal 3:2 composition
```

## Привитый — Пущи, акт 4

Был друидом. Осколок Монолита растёт в нём, как чужой орган, а он улыбается,
будто это благословение. Свет сквозь ткань идёт неправильный, и от него тянет
жаром — тем же тёплым светом, что на кадре этого акта светил между стволами.

```
a former druid in torn ritual robes with a monolith shard grown into his chest
like a foreign organ, veins of wrong warm orange light spreading under the skin
and glowing through the fabric, serene blissful smile as if it were a blessing,
heat shimmer around him, behind him the bend of a straight cut forest road with
dense trunks, sickly green and wet black bark with a single warm orange light
source, dark fantasy enemy portrait for a turn-based fight, single figure from
the waist up facing the viewer, three-quarter view, figure off-centre with the
place of the fight visible behind, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, hard dramatic side light, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## Барон Хелст — Пристани, финал

Стар, на бойца не похож и **даже не встаёт** — сидит в том самом кресле на
своём ухоженном причале, которое пустым стояло на кадре акта. Опасен не он,
а наёмники за спиной, купленные на деньги с семи потопленных судов.

```
an old wealthy harbour baron seated at ease in a single chair on an immaculate
private pier, not bothering to stand, rings on his fingers, fine but plain
dark coat, amused contemptuous look of a merchant who has already counted the
price, behind him several hired mercenaries in mismatched armour waiting for
his nod, lanterns lit in daylight, rotting shipwrecks visible in the fog beyond
the clean pier, pale salt crust, wet timber and brine green, dark fantasy enemy
portrait for a turn-based fight, figure from the waist up facing the viewer,
three-quarter view, figure off-centre with the place of the fight visible
behind, painterly semi-realistic, muted desaturated palette of ash grey, rust
brown and dried blood, hard dramatic side light, no text, no watermark, no logo,
no modern objects, horizontal 3:2 composition
```

## Мать Углей — Предел, финал

Шрамов не носит: спираль вырезана в ней самой временем и верой десятилетий.
Смотрит не на тебя — на Шрама, своего ученика, стоящего за кадром. Огонь
вокруг неё обжигает только врагов. Место — сердце пепла с кадра акта:
гладкий пепел, жар без пламени.

```
a very old priestess with no visible scars, a deep spiral pattern that seems to
be part of her weathered skin itself rather than cut into it, looking past the
viewer to someone just out of frame with the disappointed tenderness of a
teacher, a slow ring of fire circling her without touching her robes, fierce
heat haze, behind her the dead centre of a burnt land with smooth undisturbed
ash and a crimson glow beneath cracked ground, hot orange embers and black
soot, dark fantasy enemy portrait for a turn-based fight, single figure from
the waist up, three-quarter view, figure off-centre with the place of the fight
visible behind, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, hard dramatic side light, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

---

# Моб с чужой картинкой

«Гулкий латник» и «Кряжевый вопленик» (Кряж, стартовое кольцо) делят одно
фото 457239081, а это явно разные существа — значит, один из них показывает
чужую картинку. Какой именно, видно только глазами: промты есть на обоих,
нужен тот, чья картинка не совпадает.

Стиль подгони под остальных мобов Кряжа: если у них своя манера, бери её, а
не хвост выше.

## Гулкий латник

Пустой доспех солдата Ордена. Когда идёт, внутри гудит, как в колодце.

```
an empty suit of plate armour of an order soldier walking on its own, dark
nothing visible through the visor slit and the gaps at the joints, dented and
frost rimmed, the hollow resonance suggested by faint rings of disturbed snow
and dust around each heavy step, cold grey stone and steel with snow and
bluish shadows, dark fantasy enemy portrait for a turn-based fight, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, hard dramatic side light, no text, no watermark, no logo, horizontal 3:2
composition
```

## Кряжевый вопленик

Кричит на одной ноте и не смолкает. От этого крика ноют зубы и трескается
камень.

```
a gaunt grey mountain creature with its jaw unhinged wide in one endless
scream, the air in front of its mouth visibly rippling, fresh cracks spreading
through the rock under and around it, loose pebbles jumping, cold grey stone
and steel with snow and bluish shadows, dark fantasy enemy portrait for a
turn-based fight, painterly semi-realistic, muted desaturated palette of ash
grey, rust brown and dried blood, hard dramatic side light, no text, no
watermark, no logo, horizontal 3:2 composition
```

---

# Рудники и озёра — по тирам

Десять кадров: пять тиров рудников и пять тиров озёр. Показываются при входе
к жиле или к воде. Номера фото вписываются в `TIER_PHOTO_IDS` в
`bot/mining_texts.py` и `bot/fishing_texts.py`.

**Один кадр на весь тир.** На первом тире двенадцать мест, и картинка у них
общая. Поэтому в кадре не должно быть примет одного конкретного места —
иначе остальные одиннадцать окажутся подписаны чужой картинкой. Промты
собраны из мотивов, общих для тира. Исключение — пятый тир: там место одно,
и кадр рисует именно его.

**Тиры — это лестница к Монолиту**, и кадр обязан её показывать. Чем выше
тир, тем ближе центр мира, тем опаснее: с третьего тира начинается открытое
PvP. Чтобы лестница читалась с одного взгляда, у каждого набора свой
сквозной приём:

- у **озёр** на горизонте стоит Монолит, и от тира к тиру он растёт — от
  едва видной иглы в дымке до стены на полнеба;
- у **рудников** неба нет, поэтому растёт **красное свечение** в породе —
  от ничего на первом тире до камня, который уже наполовину не камень.

Людей в кадрах нет: картинка показывает место, а не того, кто в нём.

## Общий хвост рудников

```
dark fantasy mine, medieval mining with picks, timber props, rope and lanterns
only, no rails, no carts on tracks, no machinery, no people, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, wide establishing shot, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## Рудник, тир 1

Бурое железо и соляной кварц. Выработки у поверхности: вход на брёвнах,
что «держится на честном слове», неглубокий открытый разрез, уступы с
зарубками. Сюда ещё доходит дневной свет. Красного нет совсем — это просто
работа.

```
a shallow surface mine at the foot of a hill, a small adit held up by
weathered timber props at the entrance, a waist deep open cut pit beside it
with a flat bottom, rusty brown iron streaks and pale salt crystals in the
exposed rock, dry dust, plain grey daylight reaching inside, humble worn
human scale, dark fantasy mine, medieval mining with picks, timber props, rope
and lanterns only, no rails, no carts on tracks, no machinery, no people,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, wide establishing shot, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

## Рудник, тир 2

Соляной кварц и скверный колчедан. Уже не яма, а ход в глубь горы: ровная
галерея, крепь через каждый шаг, дневной свет остался у входа. Первые
нездоровые жёлтые прожилки колчедана — пока без свечения.

```
a long straight gallery driven deep into a mountain, timber supports every
single step fading into darkness, lantern light only, daylight left far behind
at the entrance, pale salt quartz in the walls with first sickly yellow veins
of tainted pyrite, orderly but oppressive, dark fantasy mine, medieval mining
with picks, timber props, rope and lanterns only, no rails, no carts on
tracks, no machinery, no people, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, wide establishing shot, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## Рудник, тир 3

Скверный колчедан и пепельное серебро. Тут уже страшно: свод обваливался,
нижние горизонты затоплены, и работают только наверху. Крепь местами не из
брёвен — из того, что нашли здесь же. В глубине породы впервые едва тлеет
красное.

```
a deep mine after a collapse, part of the vault fallen in, lower levels
flooded with still black water and only the top level still worked, some of
the props made not of timber but of large old bones found on site, veins of
dull ash grey silver and tainted yellow pyrite, and deep in the rock the first
faint barely visible red glow, dread and silence, dark fantasy mine, medieval
mining with picks, timber props, rope and lanterns only, no rails, no carts on
tracks, no machinery, no people, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, wide establishing shot, no
text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

## Рудник, тир 4

Пепельное серебро и багряный сросток. Жила светит красным сквозь породу на
всю длину забоя, из стен торчат осколки Монолита — все под одним углом,
как зубья. Красный свет здесь главный, фонари уже почти не нужны.

```
a mine face where a crimson vein glows through the rock along its entire
length, monolith shards jutting out of the walls all at the same angle like
teeth, the red light now brighter than the few lanterns, ash grey silver in
the stone, heavy heat, dark fantasy mine, medieval mining with picks, timber
props, rope and lanterns only, no rails, no carts on tracks, no machinery, no
people, painterly semi-realistic, muted desaturated palette of ash grey, rust
brown and dried blood, wide establishing shot, no text, no watermark, no logo,
no modern objects, horizontal 3:2 composition
```

## Рудник, тир 5 — Подножный забой

Место одно, и кадр рисует его. Копают у самого основания Монолита, порода
здесь уже наполовину не порода. Главное в кадре — этот переход: обычный
камень у края сменяется чем-то гладким, тёплым и неправильным.

```
a dig at the very base of the monolith, the black glossy wall of the monolith
itself filling the top of the frame and rising out of sight, the rock around
the dig half turned into something smooth, warm and wrong, ordinary stone at
the edges of the frame gradually becoming glassy and pulsing with deep crimson
light toward the centre, crimson clusters growing out of it, a few abandoned
picks, dark fantasy mine, medieval mining with picks, timber props, rope and
lanterns only, no rails, no carts on tracks, no machinery, no people, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, wide establishing shot, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## Общий хвост озёр

```
dark fantasy landscape of a lake, the monolith visible on the horizon as a
single tall black spire, no people, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, overcast light,
wide establishing shot, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

## Озеро, тир 1

Пепельная плотва, слепой пескарь, бледный окунь. Тихая мелкая вода: чаши
у родников, гладь, что не рябит на ветру, мелководье, где дно видно насквозь.
Монолит на горизонте — едва заметная игла в дымке.

```
a small calm lake with shallow clear water and the bottom visible through it,
a still surface that does not ripple even in the wind and reflects like dull
tin, a spring welling from stone at the edge into a worn basin, reeds, the
monolith barely visible as a thin faint needle far away in the haze, peaceful
and ordinary, dark fantasy landscape of a lake, the monolith visible on the
horizon as a single tall black spire, no people, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, overcast
light, wide establishing shot, no text, no watermark, no logo, no modern
objects, horizontal 3:2 composition
```

## Озеро, тир 2

Солоноводный лещ, ржавый линь, шепчущий голавль. Вода темнеет и мутнеет:
мутно-голубая чаша со льдом по кромке, чёрная старица цвета крепкого чая.
Из воды торчат ряды старой крепи — сюда уже приходили люди и не справились.
Монолит — маленький, но уже отчётливый.

```
a cold lake in a rocky hollow with murky blue grey water and a rim of old ice
along the shore that never melts, in part of it rows of old mine timbering
sticking out of the water where a flooded working drowned, darker tea coloured
water toward the middle where the bottom cannot be seen, the monolith small
but clearly visible on the horizon, dark fantasy landscape of a lake, the
monolith visible on the horizon as a single tall black spire, no people,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, overcast light, wide establishing shot, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

## Озеро, тир 3

Костяная щука, чёрный сом, скверный угорь. Вода, набравшаяся в провал: земля
ушла вниз разом. Отвесные берега, соль слоями по стенам — и слоёв слишком
много. Мёртвая тишина. Монолит средний и уже заметно тянет взгляд.

```
a deep lake filling a sudden collapse pit with sheer steep walls, layers upon
layers of salt crust on the walls, far too many layers, dark still water with
no bottom in sight, dead unnatural silence, no birds, the monolith of medium
size on the horizon already pulling the eye, dark fantasy landscape of a lake,
the monolith visible on the horizon as a single tall black spire, no people,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, overcast light, wide establishing shot, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition
```

## Озеро, тир 4

Пепельный осётр, утопленничья камбала, багряный налим. Вода отдаёт в красное
— и это не закат, закатов тут не видно. Из воды торчат осколки Монолита,
вросшие в дно под наклоном, и все смотрят в одну сторону — на него. Монолит
большой и главный в кадре.

```
a lake with water tinted dull red that is not a sunset, monolith shards grown
into the lake bottom sticking out of the surface at a slant, all pointing in
the same direction toward the monolith, the monolith large and dominating the
horizon, heavy overcast sky with no sun, dark fantasy landscape of a lake, the
monolith visible on the horizon as a single tall black spire, no people,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, wide establishing shot, no text, no watermark, no logo, no
modern objects, horizontal 3:2 composition
```

## Озеро, тир 5 — Слёзная чаша

Место одно, и кадр рисует его. Монолит стоит вплотную и закрывает полнеба.
Вода под ним тёплая и медленно ходит кругами без всякого ветра — это движение
и должно быть в кадре главным.

```
a round pool at the very foot of the monolith, the black monolith standing
right beside it and filling half of the sky, warm water with faint steam
slowly turning in wide concentric circles although there is no wind at all,
the surface reflecting a deep crimson glow from the monolith, utterly still
air, dark fantasy landscape of a lake, no people, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, wide
establishing shot, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

---

# Мировые боссы (патч 104)

Шесть кадров, по одному на босса. Слот - поле `image` в
`content/world_bosses.json`. Картинка приходит в объявлении о появлении и в
итоге после убийства. Кольца не рисуем: один и тот же босс встаёт в любом
кольце.

Босс огромный, и масштаб в кадре обязан читаться сразу. Поэтому рядом с ним
всегда крошечная фигура человека или привычный предмет (дерево, дом,
телега). Самого игрока в кадре нет. Босс ни на кого не бросается: он занят
своим и не замечает тех, кто бьёт, так и в игре.

## Общий хвост боссов

```
colossal creature dwarfing everything around it, a tiny human silhouette
nearby for scale, dark fantasy, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, overcast light, wide low
angle shot, no text, no watermark, no logo, no modern objects, horizontal
3:2 composition
```

## Жилохват

Рудный червь толщиной со штольню. Прогрызает землю насквозь.

```
a gigantic segmented ore worm as thick as a mine tunnel bursting out of a
rocky hillside, its hide made of cracked stone plates with veins of raw
metal glinting between them, a ring mouth lined with rows of blunt grinding
teeth, broken mine timbers and rails hanging from its body, dust and rubble
pouring down, [общий хвост]
```

## Праматерь корней

Дерево, которое ходит. Корни волочатся за ней на сотню шагов, и в каждом
кто-то застрял.

```
an enormous walking tree with a hunched humanlike posture, dragging a vast
tangle of roots behind it across a dead forest floor, pale human shapes
half swallowed inside the roots and the bark, moss and fungus hanging like
rags, bent old trees reaching only to its knees, [общий хвост]
```

## Утопленный колокол

Колокол размером с дом, весь в соли и ракушках. Внутри что-то ворочается, и
он гудит сам по себе.

```
a church bell the size of a house resting tilted on a salt-crusted
shoreline, its bronze covered in white salt, barnacles and seaweed,
something large and dark shifting in the shadow beneath its rim, faint
ripples in the air around it as if it hums, a wrecked pier and a small
boat beside it for scale, [общий хвост]
```

## Негаснущий костёр

Погребальный костёр, который встал и пошёл. Дождь над ним шипит и не
долетает до земли.

```
a towering funeral pyre shaped like a striding figure, a frame of charred
logs and bones burning with low steady orange fire, heavy rain falling all
around and turning to steam before it can touch the flames, scorched black
ground and ash under its steps, a burnt-out cart beside it for scale,
[общий хвост]
```

## Сшитый великан

Его собирали из многих, и швы видно издалека. Стоит на месте и смотрит в
разные стороны разными глазами.

```
a huge giant stitched together from many different bodies, thick crude
seams and iron staples running across grey mismatched skin, several eyes of
different sizes looking in different directions, standing perfectly still
in a ruined village, the roofs of the houses reaching only to its waist,
[общий хвост]
```

## Безликая процессия

Сотня фигур без лиц идёт за одним штандартом и дышит в такт. Бьёшь одну -
вздрагивают все.

```
a long dense procession of a hundred tall faceless hooded figures walking
in perfect step behind a single tattered standard, their smooth blank faces
without eyes or mouths, all of them moving as one body, the column winding
across a grey plain toward the horizon, a lone signpost beside the road for
scale, [общий хвост]
```
