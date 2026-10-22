# Промты: рассказчик подсказок

Тот, кто читает подсказки голосом (озвучка - `miniapp/src/assets/voice/`).
Появляется рядом с карточкой подсказки и «рассказывает» её. Рассудительный
пожилой мужчина, старый проводник по Пепельным Землям: много ходил, много
видел, говорит спокойно и по делу.

Это **не** Хранитель Списков: у того по лору лица не видно - капюшон и два
уголька вместо глаз (`content/npc/list_keeper.json`). Здесь лицо нужно: он
смотрит на игрока и объясняет.

## Важно про внешность

Персонаж - собирательный и свой. В промте нет имён и чужих лиц, только
типаж: пожилой, седые волосы назад, тяжёлые брови, густая седая борода. Фото
реального человека генератору **не подавать** как образец: тогда он
перенесёт лицо почти один в один, а нам нужен оригинальный герой. Чтобы он
сразу был «своим», у него приметы, которых нет у прототипа: старый шрам
через левую бровь и пепел в морщинах и в бороде.

Сначала сгенерируй позу 1. Когда понравится - подавай уже ЕЁ как образец
для поз 2 и 3: так лицо и одежда совпадут во всех трёх.

## Кадр - одинаковый для всех трёх

- По пояс, корпус чуть повёрнут вправо (к тексту подсказки, она будет
  справа от него), взгляд на зрителя.
- Вертикальный 3:4, лучше 1024×1365. Макушка на ~6% от верха, кадр
  обрезан по поясу.
- Фон сплошной чистый чёрный, без тумана и предметов - вырежу сам, как
  силуэты героя (`tools/silhouette_assets.py`).
- Свет: тёплый, как от костра снизу слева, и тлеющая кромка по контуру -
  тот же приём, что у силуэтов.

## Общий хвост

```
waist-up portrait of the same elderly man, body turned slightly to the
right, looking at the viewer, warm low firelight from the lower left and a
faint ember rim light along the outline, dark fantasy, painterly
semi-realistic, muted palette of ash grey, worn leather brown and
smouldering orange, figure centered with a small margin above the head,
cropped at the waist, isolated on a plain pure black background, no fog, no
props behind him, no text, no watermark, no logo, vertical 3:4 composition
```

## Сам персонаж

Повторяется в начале каждого промта слово в слово - так генератор держит
одно лицо.

```
an original character, a wise elderly wanderer of about seventy, lean
weathered face with deep lines, grey hair combed straight back, heavy dark
grey eyebrows, an old pale scar cutting through the left eyebrow, deep-set
calm brown eyes with crow's feet, a full thick grey beard of medium length
grown into a long moustache, fine ash dust caught in the beard and in the
wrinkles, wearing a worn traveller's coat of layered grey wool and cracked
leather with a high collar, a frayed dark red scarf, a leather satchel strap
across the chest with small iron charms and a rolled map tucked in it
```

---

## Поза 1 - рассказывает спокойно

`img/рассказчик_1_1.png` - основная, на ней большая часть подсказок.

```
an original character, a wise elderly wanderer of about seventy, lean
weathered face with deep lines, grey hair combed straight back, heavy dark
grey eyebrows, an old pale scar cutting through the left eyebrow, deep-set
calm brown eyes with crow's feet, a full thick grey beard of medium length
grown into a long moustache, fine ash dust caught in the beard and in the
wrinkles, wearing a worn traveller's coat of layered grey wool and cracked
leather with a high collar, a frayed dark red scarf, a leather satchel strap
across the chest with small iron charms and a rolled map tucked in it, calm
attentive expression with the hint of a kind smile under the beard, both
hands resting on the top of a gnarled wooden walking staff in front of him,
waist-up portrait of the same elderly man, body turned slightly to the
right, looking at the viewer, warm low firelight from the lower left and a
faint ember rim light along the outline, dark fantasy, painterly
semi-realistic, muted palette of ash grey, worn leather brown and
smouldering orange, figure centered with a small margin above the head,
cropped at the waist, isolated on a plain pure black background, no fog, no
props behind him, no text, no watermark, no logo, vertical 3:4 composition
```

## Поза 2 - объясняет

`img/рассказчик_2_1.png` - для шагов, где показывают, что нажимать.

```
an original character, a wise elderly wanderer of about seventy, lean
weathered face with deep lines, grey hair combed straight back, heavy dark
grey eyebrows, an old pale scar cutting through the left eyebrow, deep-set
calm brown eyes with crow's feet, a full thick grey beard of medium length
grown into a long moustache, fine ash dust caught in the beard and in the
wrinkles, wearing a worn traveller's coat of layered grey wool and cracked
leather with a high collar, a frayed dark red scarf, a leather satchel strap
across the chest with small iron charms and a rolled map tucked in it,
explaining something patiently, eyebrows slightly raised, his right hand
raised at chest height with the palm open and the index finger lifted
toward the right as if pointing at something next to him, the other hand
holding the walking staff, waist-up portrait of the same elderly man, body
turned slightly to the right, looking at the viewer, warm low firelight from
the lower left and a faint ember rim light along the outline, dark fantasy,
painterly semi-realistic, muted palette of ash grey, worn leather brown and
smouldering orange, figure centered with a small margin above the head,
cropped at the waist, isolated on a plain pure black background, no fog, no
props behind him, no text, no watermark, no logo, vertical 3:4 composition
```

## Поза 3 - усмехается

`img/рассказчик_3_1.png` - для фраз с усмешкой (курс биржи, «разберёшь по
ходу»).

```
an original character, a wise elderly wanderer of about seventy, lean
weathered face with deep lines, grey hair combed straight back, heavy dark
grey eyebrows, an old pale scar cutting through the left eyebrow, deep-set
calm brown eyes with crow's feet, a full thick grey beard of medium length
grown into a long moustache, fine ash dust caught in the beard and in the
wrinkles, wearing a worn traveller's coat of layered grey wool and cracked
leather with a high collar, a frayed dark red scarf, a leather satchel strap
across the chest with small iron charms and a rolled map tucked in it, a
warm amused chuckle, eyes squinting with laughter lines, one hand stroking
his beard, waist-up portrait of the same elderly man, body turned slightly
to the right, looking at the viewer, warm low firelight from the lower left
and a faint ember rim light along the outline, dark fantasy, painterly
semi-realistic, muted palette of ash grey, worn leather brown and
smouldering orange, figure centered with a small margin above the head,
cropped at the waist, isolated on a plain pure black background, no fog, no
props behind him, no text, no watermark, no logo, vertical 3:4 composition
```

---

## Кадры для движения

Рассказчик шевелится сменой кадров: пока звучит голос, рот открывается в
такт громкости записи; раз в несколько секунд он моргает. На каждую позу -
4 кадра, всего 12 картинок.

**Кадры 2-4 - ПРАВКОЙ готовой позы, не новой генерацией.** Новая генерация
сдвинет лицо, бороду и складки плаща, и при смене кадров он будет дрожать.
Подаёшь готовую позу (кадр 1) и просишь поменять только рот или глаза -
режим правки/редактирования картинки. При обработке я дополнительно беру из
кадров 2-4 только область лица и кладу её на кадр 1, так что всё остальное
не сдвинется даже на пиксель.

Имена: `img/рассказчик_<поза>_<кадр>.png`, например `рассказчик_2_3.png` -
поза 2, рот открыт. Кадр 1 - это и есть готовая поза (`рассказчик_1_1.png` и т.д. выше).

### Кадр 2 - рот приоткрыт

```
edit this exact image: keep everything identical - the face, the beard, the
hair, the eyes, the clothes, the hands, the pose, the lighting and the black
background - and change only the mouth: the lips slightly parted as if in
the middle of a calm word, a thin dark gap between the lips barely visible
under the moustache. Do not move or redraw anything else.
```

### Кадр 3 - рот открыт

```
edit this exact image: keep everything identical - the face, the beard, the
hair, the eyes, the clothes, the hands, the pose, the lighting and the black
background - and change only the mouth: open as if saying the vowel "a"
while speaking calmly, the lower lip and a bit of the lower teeth visible
under the moustache, the jaw lowered only a little. Do not move or redraw
anything else.
```

### Кадр 4 - моргает

```
edit this exact image: keep everything identical - the face, the beard, the
hair, the mouth, the clothes, the hands, the pose, the lighting and the black
background - and change only the eyes: both eyelids fully closed in a
relaxed blink, the eyebrows and the scar unchanged. Do not move or redraw
anything else.
```

Если генератор всё же сдвигает что-то кроме рта и глаз - не страшно, лицо
я вырежу и наложу сам. Страшно, только если поменялось само лицо: другой нос,
другая форма бороды. Такой кадр лучше переделать.

---

## Что проверить, когда будут готовы

1. Во всех трёх позах одно и то же лицо, шрам на левой брови, та же одежда.
   В кадрах одной позы отличаются только рот и глаза.
2. Лицо не похоже на конкретного известного человека. Если похоже -
   перегенерировать: сменить форму носа, сделать лицо уже или шире.
3. Голова на одной высоте во всех трёх: при смене позы он не должен
   прыгать.
4. Фон чисто чёрный, кадр обрезан по поясу.
