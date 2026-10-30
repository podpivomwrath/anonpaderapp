# Синематик «Подорожник»: маскоты и раскадровка

Ролик на 14 секунд: рыцарь осторожно рвёт пепельный подорожник, слышит
мотор, и его сносит Турбоишак. Финал - рыцарь сидит в пепле и смотрит
ишаку вслед.

Формат: **9:16** (ВК Клипы, сторис) - основной. Кадры собраны так, что из них
же режется 16:9: главное по центру, по бокам запас.

---

## Маскоты

### Турбоишак

То же, что в игре (`content/mounts/mounts.json`): пепельный ишак, в которого
жестянщик с Пристаней вкрутил паровой котёл.

- **Силуэт:** серый лохматый ишак с медным котлом на спине. Из котла торчит
  кривая выхлопная труба, из неё летят чёрный дым и искры.
- **Узнаётся по:** огромным ушам, которые на бегу ложатся назад, лётным очкам
  на морде (стёкла в саже), заплатам на котле и болтам вместо пряжек.
- **Характер:** ему всё равно. Он не злой, просто несётся, и остановить его
  нельзя. Морда довольная, язык набок.
- **Звук:** тарахтение котла, как у старого мотоцикла, и ослиный крик сквозь
  рёв.

### Рыцарь - вечный неудачник

Рабочее имя - **сэр Шишка**: шишка на лбу и шишка как прозвище. Запасные
варианты: «сэр Ушиб», «брат Пластырь».

- **Силуэт:** большой шлем и маленькое тело. Доспех ему велик, наплечники
  разные, один погнут. Плащ в заплатах.
- **Лица не видно** - только щель забрала. Всё играется позой, забралом и
  пером на шлеме: перо торчит, когда он насторожен, и обвисает, когда ему
  плохо. Генераторам так проще держать персонажа одинаковым от кадра к
  кадру.
- **Узнаётся по:** бинту на левой руке, пластырю крест-накрест на шлеме и
  листу подорожника, приклеенному к наплечнику.
- **Характер:** старательный и аккуратный, всё делает бережно и всё равно
  попадает под раздачу. Подорожник он рвёт себе на ушибы. Это и есть шутка
  сцены: шёл лечить синяки, получил новые.

### Стиль

Мир игры тёмный и пепельный, маскоты - чуть мультяшнее мира: крупные головы,
читаемые силуэты, но те же краски (пепел, ржавчина, засохшая кровь) и
тёплый свет котла как единственное яркое пятно.

---

## Раскадровка (14 с)

| # | Время | План | Что происходит | Звук |
|---|---|---|---|---|
| 1 | 0:00-0:03 | Макро, низко над землёй | Лист подорожника в серой пыли. Пепел медленно падает. В кадр входят пальцы латной перчатки, медленно, с дрожью. | Ветер, тихое дыхание под шлемом |
| 2 | 0:03-0:05 | Средний сбоку | Рыцарь стоит на коленях, наклонился к земле, забрало почти касается листа. Двумя пальцами тянет стебель. Лист вот-вот поддастся. | Скрип доспеха, натянутый стебель |
| 3 | 0:05-0:07 | Крупный, шлем | Издалека нарастает «тр-тр-тр». Рыцарь замирает. Перо на шлеме встаёт торчком. Шлем со скрипом поворачивается влево, потом вправо. | Мотор вдалеке, скрип забрала |
| 4 | 0:07-0:08 | Общий из-за пригорка | Пустая равнина, над холмом поднимается столб чёрного дыма. Через гребень прыгает Турбоишак: уши назад, очки блестят, из трубы огонь. | Рёв котла, ослиный крик |
| 5 | 0:08-0:09 | Удар, на полсекунды замедление | Ишак сносит рыцаря. Шлем слетает и крутится в воздухе, рядом крутится лист подорожника. Потом снова обычная скорость: рыцарь кувыркается по пеплу. | «Бам», звон железа, тишина на замедлении |
| 6 | 0:09-0:13 | Средний, со спины рыцаря | Рыцарь сидит в воронке из пепла, доспех дымится, шлем набекрень. Вдали ишак уменьшается до точки и оставляет полосу сажи. Пепел оседает. | Мотор затихает вдали |
| 7 | 0:13-0:14 | Крупный, шлем | Сверху медленно опускается лист подорожника и ложится ему на шлем. Перо обвисает. Пауза, затем затемнение. | Одна тихая нота, потом тишина |

В кадре 7 можно дать титр. Варианты (выбрать один):
- «Пепельный подорожник. Помогает от ушибов.»
- «Турбоишак. На дороге не стой.»

Если «секунд на 10-15» - это длина одного финала, а не всего ролика, кадр
6 растягивается: рыцарь пытается встать, шлем съезжает ему на нос, он садится
обратно и машет вслед кулаком.

---

## Промты: листы персонажей

Сначала генерируются эти два листа. Потом их подают референсом в каждый
кадр, иначе рыцарь и ишак будут разными от кадра к кадру.

Общий хвост уже в каждом промте.

### Турбоишак - лист персонажа

```
character reference sheet of a scrappy grey donkey with a battered copper steam boiler strapped to its back, a crooked exhaust pipe sticking up from the boiler puffing black smoke and sparks, huge floppy ears, round aviator goggles with soot-stained lenses on its muzzle, bolts and rivets instead of buckles on the harness, patched boiler, goofy happy expression with tongue out, front view, side view, three-quarter view, running pose, plain dark grey background, stylized 3D animated character, chunky readable silhouette, dark fantasy world palette of ash grey, rust brown and dried blood with the warm orange glow of the boiler as the only bright accent, no text, no watermark, no logo
```

### Рыцарь - лист персонажа

```
character reference sheet of a small clumsy knight in oversized dented armor, huge bucket helmet with a narrow eye slit and no visible face, mismatched pauldrons with one bent, patched tattered cloak, a bandage wrapped around the left arm, a cross-shaped plaster stuck on the helmet, a broad grey plantain leaf stuck to the shoulder pad, a tall feather plume on the helmet, big helmet small body proportions, front view, side view, three-quarter view, kneeling pose, plain dark grey background, stylized 3D animated character, chunky readable silhouette, dark fantasy world palette of ash grey, rust brown and dried blood, no text, no watermark, no logo
```

---

## Промты: ключевые кадры

Каждый кадр - стартовая картинка (по листу персонажа) плюс короткий
промт движения для генератора видео.

### 1 - Лист в пыли

Картинка:
```
extreme macro close-up at ground level of a single broad grey plantain leaf growing in grey ash dust, ash flakes slowly falling, a steel gauntlet with trembling fingers slowly reaching in from the top of the frame, shallow depth of field, soft dim light, stylized 3D animated short, dark fantasy palette of ash grey, rust brown and dried blood, vertical 9:16, subject centered, no text, no watermark
```
Движение: `the gauntlet fingers move in very slowly and carefully, trembling slightly, ash flakes drift down, slow camera push in`

### 2 - Тянет стебель

Картинка:
```
side view medium shot of the small clumsy knight from the reference kneeling in grey ash, bent low over the ground with the helmet almost touching a plantain leaf, pinching the stem between two armored fingers with exaggerated care, empty ashen plain in the background, stylized 3D animated short, dark fantasy palette, vertical 9:16, subject centered, no text, no watermark
```
Движение: `the knight slowly pulls the stem, the leaf stretches and is about to come loose, the knight holds still in total concentration`

### 3 - Слышит мотор

Картинка:
```
close-up of the knight's big bucket helmet, the feather plume suddenly standing straight up, the helmet turning to look to the side, empty grey plain behind, stylized 3D animated short, dark fantasy palette, vertical 9:16, subject centered, no text, no watermark
```
Движение: `the knight freezes, the plume springs upright, the helmet slowly turns left, then right, puzzled`

### 4 - Ишак через гребень

Картинка:
```
wide low-angle shot of a grey ash hill under a dark sky, a column of black smoke rising from behind the ridge, the turbo donkey from the reference leaping over the crest mid-air, boiler blazing, flames from the exhaust pipe, ears flying back, goggles glinting, stylized 3D animated short, dark fantasy palette with the warm orange boiler glow, vertical 9:16, subject centered, no text, no watermark
```
Движение: `the donkey bursts over the ridge at full speed toward the camera, smoke and sparks trailing, ash spraying from its hooves`

### 5 - Удар

Картинка:
```
dynamic action shot, the turbo donkey ramming into the small knight, the knight lifted off his feet, the bucket helmet flying off spinning in the air next to a spinning plantain leaf, ash exploding around them, motion blur, stylized 3D animated short, dark fantasy palette, vertical 9:16, subject centered, no text, no watermark
```
Движение: `half a second of slow motion on impact, the helmet and the leaf spin in the air, then normal speed as the knight tumbles head over heels across the ash`

### 6 - Смотрит вслед

Картинка:
```
medium shot from behind the small knight sitting in a shallow crater of grey ash, armor smoking, helmet crooked on his head, looking at the horizon where a tiny donkey with a smoking boiler disappears leaving a long trail of black soot, ash slowly settling, stylized 3D animated short, dark fantasy palette, vertical 9:16, subject centered, no text, no watermark
```
Движение: `the knight sits motionless, the donkey shrinks into a dot on the horizon, the soot trail drifts, ash slowly settles around the knight`

### 7 - Лист на шлем

Картинка:
```
close-up of the small knight's crooked bucket helmet, a broad grey plantain leaf slowly floating down and landing on top of the helmet, the feather plume drooping, dim ashen light, stylized 3D animated short, dark fantasy palette, vertical 9:16, subject centered, empty space at the bottom for a caption, no text, no watermark
```
Движение: `the plantain leaf flutters down and settles on the helmet, the plume slowly droops, hold, fade to black`

---

## Звук

- Ветер и тихое дыхание под шлемом - весь кадр 1-2.
- Тарахтение котла: появляется в кадре 3, растёт до рёва в 4, обрывается
  на ударе.
- Удар - звон доспеха, на замедлении тишина.
- Мотор затихает в кадре 6.
- Финал - одна тихая нота.
- Музыки нет до удара: тишина делает удар смешнее.
