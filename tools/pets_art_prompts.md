# Промты: питомцы и Пепельный дракон

Питомцы встают в новый, шестой слот «Героя» (решения владельца 2026-11-12).
Статов у них нет, только своя механика. Пять питомцев и один маунт:

| Питомец | Механика | Откуда |
|---|---|---|
| Хорёк-сыщик | сам раскапывает горстки пепла | магазин, 500 самоцветов |
| Ворон | сообщает об игроках на соседних клетках | топ-1, 2 и 3 сезона PvP |
| Странная руна | раз в час пишет код, игроку он кажется шуткой | боссы рейдов, 1% |
| Пепельный плетельщик | плетёт сети, приносит мелкую дичь | Обетованный Кряж |
| Призрачная гончая | чует игроков с Кровавым клеймом | разломы или боссы руин |
| Пепельный дракон (маунт) | летит по прямой, ни мобы, ни игроки не нападают | первый, кто введёт код руны у Монолита |

Всего **14 картинок**: 6 иконок и 8 сцен.

## Внешность - одна на все картинки

Каждый питомец во всех кадрах одинаковый, чтобы его узнавали. Описание уже
вписано в каждый промт ниже, здесь - для сверки.

- **Хорёк.** Поджарый серо-бурый хорёк с тёмной «маской» на глазах, в шерсти
  пепел. Под брюхом пристёгнут маленький кожаный рюкзачок на латунных
  пряжках, из него торчат пуговица, гнутый ключ и бусина.
- **Ворон.** Крупный чёрный ворон, по голове, шее и крыльям десятки маленьких
  глаз с бледно-жёлтой радужкой. Часть глаз открыта, часть закрыта, открытые
  смотрят в разные стороны. Жутковатый, но без крови и ран.
- **Странная руна.** Глыба серого камня размером с бочку, вытесанная в один
  кривой угловатый знак, непохожий ни на одну букву. Висит в ладони над
  землёй. Немного нелепая: скособочена, на боку прилипла галька, свет тусклый.
  Для игрока это шуточный питомец, поэтому ни величия, ни связи с Монолитом в
  картинке нет: без багрового света и без чёрного камня.
- **Плетельщик.** Паучок с ладонь, пушистый, серый, как пепел, восемь чёрных
  глазок. Безобидный, почти милый. Сети толстые, серебристые.
- **Гончая.** Тощий полупрозрачный пёс, тело наполовину из пепла и дыма,
  сквозь бока просвечивают рёбра. Глаза холодные, бело-голубые, за лапами и
  хвостом тянется пепел.
- **Дракон.** Огромный, тело из спрессованного серого пепла и угольно-чёрных
  пластин. По телу глубокие трещины, изнутри тлеют рыжим. Крылья - тонкие
  рваные перепонки цвета пепла, на взмахе с них сыплются хлопья. Длинная
  рогатая голова, в глазницах тлеет тот же рыжий огонь.

---

## Иконки (6 штук)

Стиль - как у иконок предметов и маунтов (`tools/icon_prompts.md`).
Квадрат 1:1, один зверь по центру, целиком. Файлы - в `img/` под указанными
именами, подключу через `tools/icon_assets.py`. Иконка встанет в окно слота
питомца на силуэте героя, поэтому зверь должен читаться мелко.

Общий хвост уже есть в каждом промте.

**питомец_хорек.png**

```
a pet called «Хорёк-сыщик»: a lean grey-brown ferret with a dark bandit mask across its eyes and ash dust in its fur, a tiny leather backpack strapped under its belly with small brass buckles, a button, a bent key and a bead poking out of the backpack, standing alert on its hind legs and sniffing the air, single creature centered and fully visible, dark fantasy game item icon, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey, rust brown and dried blood with warm brass highlights, soft rim light from the upper left, deep neutral background, no text, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```

**питомец_ворон.png**

```
a pet called «Ворон»: a large black raven perched on a dead branch, dozens of small eyes scattered over its head, neck and along its folded wings, some eyes open and some closed, the open ones with pale yellow irises staring in different directions, unsettling but clean, no blood, no wounds, single creature centered and fully visible, dark fantasy game item icon, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey, charcoal black and pale sickly yellow, soft rim light from the upper left, deep neutral background, no text, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```

**питомец_странная_руна.png**

```
a pet called «Странная руна»: a barrel-sized chunk of plain grey stone roughly carved into one crooked angular glyph-like shape that resembles no real letter of any alphabet, floating a hand's width above the ground with a small soft shadow under it, slightly lopsided and a little ridiculous, a small pebble stuck to its side, ash dust in the grooves, a dim tired pale glow in the carved lines, unimpressive and harmless looking, single object centered, dark fantasy game item icon, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey and dusty beige, soft rim light from the upper left, deep neutral background, no letters, no text, no runic alphabet, no crimson light, no black stone, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```

**питомец_плетельщик.png**

```
a pet called «Пепельный плетельщик»: a small palm-sized spider covered in soft fuzzy ash-grey hairs, eight small glossy black eyes, harmless and almost cute, sitting in the middle of a thick silvery web net stretched between two mountain rocks, single creature centered and fully visible, dark fantasy game item icon, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey, slate blue and pale silver, soft rim light from the upper left, deep neutral background, no text, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```

**питомец_гончая.png**

```
a pet called «Призрачная гончая»: a gaunt translucent ghostly hound, its body half made of drifting grey ash and smoke, ribs faintly visible through its sides, cold pale blue-white eyes, ash trailing from its paws and tail like smoke, standing with its head low as if catching a scent, single creature centered and fully visible, dark fantasy game item icon, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey, charcoal and cold pale blue, soft rim light from the upper left, deep neutral background, no text, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```

**маунт_пепельный_дракон.png**

```
a legendary mount called «Пепельный дракон»: a huge dragon whose body is made of compacted grey ash and charcoal-black plates, deep cracks across its body glowing with a dim ember orange light from inside, wings of thin torn ash-colored membranes shedding flakes of ash, a long horned head with ember light smouldering in the eye sockets, a worn leather saddle on its back, side view with wings half spread, single creature centered and fully visible, dark fantasy game item icon, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey, charcoal black and ember orange, soft rim light from the upper left, deep neutral background, no text, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```

---

## Сцены для чата (8 штук)

Горизонтально 3:2, как у рейдов и разломов. Лиц нет: люди со спины, в
капюшоне или в тени. Имена файлов - из заголовков (`питомец_<id>.png`).
Загрузить в альбом (`tools/vk_upload.py`) и прислать номера, впишу сам.

Общий хвост уже есть в каждом промте.

### питомец_хорек_покупка.png - хорёк куплен

Сообщение при покупке в магазине. Хорёк сам по себе на пустоши: роет
горстку пепла, рюкзачок оттопырился.

```
a lean grey-brown ferret with a dark bandit mask across its eyes, a tiny leather backpack with brass buckles strapped under its belly, digging energetically into a small mound of grey ash on a wasteland road, ash flying from its front paws, a bent key and a bead already poking out of the backpack, the boots and cloak hem of a traveller standing nearby at the edge of the frame, dark fantasy scene illustration with a touch of humour, painterly semi-realistic, muted desaturated palette of ash grey, rust brown and dried blood with warm brass highlights, drifting ash in the air, moody overcast light, no text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### питомец_ворон_награда.png - ворон за сезон PvP

Сообщение топ-3 после итогов сезона. Ворон садится на плечо, у ног - пустое
ристалище из катсцены сезона.

```
a large black raven with dozens of small eyes over its head, neck and wings, some eyes open with pale yellow irises staring in different directions, landing on the armoured shoulder of a hooded warrior seen from behind, the warrior standing at the edge of an empty stone battle arena covered in grey ash, broken swords in the ash, torn crimson banners on poles, night sky, the raven's wings still half spread, unsettling and quiet, dark fantasy scene illustration, painterly semi-realistic, muted desaturated palette of ash grey, rust brown and dried blood, drifting ash in the air, no faces, no text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### питомец_руна_находка.png - странная руна с босса

Выпала с босса рейда. Кадр нарочно обычный, даже смешной: камень висит над
трофеями, ничего не происходит.

```
a barrel-sized chunk of plain grey stone roughly carved into one crooked angular glyph-like shape that resembles no real letter, floating a hand's width above a heap of ordinary loot after a battle (a dented helmet, a coin pouch, a broken spear), slightly lopsided, a small pebble stuck to its side, a dim tired pale glow in its carved lines, a hooded adventurer seen from behind scratching the back of their head in confusion, dim cave hall of a defeated boss in the background, mundane and slightly comical, dark fantasy scene illustration with a touch of humour, painterly semi-realistic, muted desaturated palette of ash grey and dusty beige, drifting ash in the air, no letters, no text, no runic alphabet, no crimson light, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### питомец_плетельщик_находка.png - плетельщик на Кряже

Скалистый Кряж, редкая трава, между камней натянута толстая сеть. В ней
бьётся горный заяц, паучок сидит рядом.

```
a rocky mountain ridge with sparse dry grass and grey scree, a thick silvery spider web net stretched between two tall rocks, a small mountain hare caught in the net, a small palm-sized fuzzy ash-grey spider with eight glossy black eyes sitting at the edge of the web, harmless and almost cute, a hooded traveller seen from behind crouching to look at it, cold wind, pale sky, dark fantasy scene illustration, painterly semi-realistic, muted desaturated palette of ash grey, slate blue and pale silver, drifting ash in the air, no faces, no text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### питомец_гончая_находка.png - гончая берёт след

Гончая стоит над следами на пепле и смотрит вдаль, куда они ведут. На
горизонте красный отсвет - там тот, у кого клеймо.

```
a gaunt translucent ghostly hound, its body half made of drifting grey ash and smoke, ribs faintly visible, cold pale blue-white eyes, standing over a line of fresh boot prints in grey ash and staring into the distance where the prints lead, a faint dull red glow far away on the horizon, a hooded hunter seen from behind holding a crossbow beside the hound, dusk over an ash wasteland, tense and quiet, dark fantasy scene illustration, painterly semi-realistic, muted desaturated palette of ash grey, charcoal and cold pale blue with one small spot of dull red, drifting ash in the air, no faces, no text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### дракон_пробуждение.png - игрок ввёл код у Монолита

Личное сообщение тому, кто ввёл код. Монолит трескается, из трещин бьёт свет,
из пепла у подножия поднимается голова дракона. Игрок - маленькая фигура
спиной к зрителю.

```
a colossal black monolith in an ash plain at night, deep cracks splitting across its surface with blinding white and crimson light pouring out of them, the ash at its base heaving and pouring upward, the long horned head and neck of a huge dragon made of compacted grey ash and charcoal-black plates rising out of the ash heap, ember orange light glowing in the cracks of its body and in its eye sockets, flakes of ash falling from it, a tiny hooded figure seen from behind standing before the monolith with one hand still raised, awe and scale, cinematic dark fantasy matte painting, painterly semi-realistic, muted desaturated palette of ash grey, charcoal black, crimson and ember orange, drifting ash in the air, no faces, no text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### дракон_объявление.png - объявление всему серверу

Рассылка всем игрокам. Вид издалека, с любого конца мира: Монолит на
горизонте горит, как маяк, над ним в небе развернулся дракон. На переднем
плане люди в городе смотрят туда.

```
a view across a wide ash plain toward a colossal black monolith on the far horizon blazing with white and crimson light like a beacon, the whole overcast sky lit from below, a huge dragon made of grey ash and charcoal-black plates with ember-glowing cracks circling above the monolith with its torn ash-colored wings fully spread, a trail of falling ash behind it, in the foreground the rooftops and wall of a small town with a few silhouetted people seen from behind on the wall pointing and staring at the light, dark fantasy matte painting, painterly semi-realistic, muted desaturated palette of ash grey, rust brown, crimson and ember orange, drifting ash in the air, no faces, no text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```

### дракон_полёт.png - дракон в пути

Для сообщения «в пути» на драконе. Вид сзади и сверху: дракон с всадником
летит над пустошью, внизу на земле мелкие твари задрали головы, но достать не
могут.

```
a huge dragon made of compacted grey ash and charcoal-black plates with ember-glowing cracks flying low over an ash wasteland, seen from behind and slightly above, a hooded rider in a worn leather saddle on its back, torn ash-colored wings in a wide downstroke shedding flakes of ash, far below small dark creatures on the ground lifting their heads and watching it pass out of reach, a straight shadow of the dragon running across the plain, overcast sky, sense of speed and height, dark fantasy scene illustration, painterly semi-realistic, muted desaturated palette of ash grey, charcoal black and ember orange, drifting ash in the air, no faces, no text, no watermark, no logo, no modern objects, horizontal 3:2 composition
```
