# Промты: силуэты героя для снаряжения

Вкладка «Снаряжение» в профиле мини-аппа (2026-10-22): по центру силуэт
героя, на нём пять окон слотов - шлем, нагрудник, штаны, сапоги, оружие.
Нажал окно - снизу список подходящих вещей.

Всего **18 картинок**: шесть подклассов и три базовых класса, каждый в
мужском и женском варианте (выбор пола персонажа, 2026-10-22). Подкласс есть
не у всех: до 30 уровня его нет, и такой игрок видит силуэт своего базового
класса.

## Главное для всех восемнадцати

- **Без лица.** Как и с эмблемами (`tools/crown_art_prompts.md`): игрок видит
  себя, и чужое лицо спорило бы с тем, кого он себе представляет. Голова в
  капюшоне, шлеме или в тени - черт не видно.
- **Тёмная фигура, а не броня в деталях.** Поверх силуэта встанут иконки
  надетых вещей, поэтому сама фигура тёмная, почти чёрная, с тлеющей
  кромкой света по контуру. Подкласс узнаётся по очертаниям: мантия, плащ,
  щит, наплечники.
- **Одна поза и одна рамка на все восемнадцать** - иначе окна слотов пришлось бы
  двигать под каждую картинку:
  - фигура в полный рост, анфас, стоит прямо, ноги чуть шире плеч;
  - руки немного отведены от тела, кисти видны - у правой руки (слева для
    зрителя) встанет окно оружия;
  - макушка - на 6% от верха кадра, ступни - на 6% от низа;
  - фигура по центру по горизонтали.
- **Формат.** Вертикальный 2:3, лучше 1024×1536.
- **Фон.** Сплошной чистый чёрный, без пола, тени и тумана. Вырежу его сам.
  Если генератор умеет прозрачный фон, ещё лучше.

Готовые файлы класть в `img/` под указанными именами - подключу и подгоню
окна слотов.

## Общий хвост

Дописывается в конец каждого промта.

```
full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

---

# Мужские силуэты

# Подклассы

## Кровавый рыцарь

`img/силуэт_кровавый_рыцарь.png`

Воин, живёт чужой кровью. Тяжёлый и широкоплечий, но не крепость, как Страж:
плащ в клочьях и длинный меч опущен остриём к земле.

```
a broad-shouldered male knight with heavy angular pauldrons and a tattered cloak
hanging in torn strips behind him, a long straight greatsword held low in the
right hand with the point toward the ground, thin trails of dark red glow
running along the blade edge, the rim light along his outline has a faint
blood red tint, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Страж

`img/силуэт_страж.png`

Воин, танк. Самый массивный из девяти: большой щит на левой руке, крепкая
стойка. Щит не закрывает туловище целиком, нагрудник должен остаться виден.

```
a massive heavily built male guardian in thick layered plate, a large rounded
tower shield strapped to the left forearm and held slightly out to the side
so the chest stays visible, a short heavy mace in the right hand, wide firm
stance, the rim light along his outline is steady and pale like cooling iron,
full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Тёмный мистик

`img/силуэт_тёмный_мистик.png`

Маг, единственный лекарь. Высокий, в длинной мантии до земли, посох с
бледным огнём на навершии. Ноги под мантией читаются - на них встанут штаны и
сапоги, поэтому мантия расходится спереди.

```
a tall thin male mystic in a long hooded robe that parts at the front to show the
legs and boots underneath, a tall gnarled staff in the right hand topped with
a small pale violet flame, the left hand open and raised slightly with a faint
violet glow in the palm, the rim light along the outline has a cold violet
tint, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Элементалист

`img/силуэт_элементалист.png`

Маг, стихии. Короче мантия, больше движения: вокруг рук три искры - огонь,
лёд и молния. Без посоха, оружие - в правой руке короткий жезл.

```
a lean male mage in a hooded knee-length coat with loose sleeves, a short rod in
the right hand, three small floating motes around the left hand, one of
flickering fire, one of pale blue ice, one of crackling white lightning, the
coat edges lifted slightly as if by a hot draft, the rim light along the
outline shifts from orange to icy blue, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Клинок теней

`img/силуэт_клинок_теней.png`

Разбойник, убийца. Самый узкий и лёгкий силуэт: облегающая одежда, короткий
плащ, кинжал обратным хватом. Тень вокруг него гуще, чем у остальных.

```
a slim agile male assassin in close fitting dark leathers with a short hooded
half cape over the shoulders, a long dagger held in a reverse grip in the
right hand, a second dagger sheathed at the hip, wisps of black shadow
curling off the shoulders and heels, the rim light along the outline is thin
and sharp like a knife edge, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Отравитель

`img/силуэт_отравитель.png`

Разбойник, яды. Ниже и сутулее Клинка, длиннее плащ, на поясе склянки.
Тусклое зелёное свечение - единственный холодный цвет у разбойников.

```
a hunched male poisoner in a long ragged hooded cloak, a belt hung with small
glass vials and pouches, a short curved blade in the right hand with a drop
of sickly green liquid on its tip, a faint green haze rising from the vials,
the rim light along the outline has a dull toxic green tint, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

---

# Базовые классы (до 30 уровня)

Те же позы, но проще: без особых примет подкласса, обычное снаряжение
путника. Игрок ещё не выбрал путь.

## Воин

`img/силуэт_воин.png`

```
a sturdy plain male warrior in simple worn mail and a short cloak, a plain
straight sword in the right hand pointing down, a small round buckler on the
left arm held to the side, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Разбойник

`img/силуэт_разбойник.png`

```
a light wiry male rogue in a simple hooded jacket and soft boots, a plain short
knife in the right hand, a coil of rope at the belt, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Маг

`img/силуэт_маг.png`

```
a young male mage in a plain hooded travelling robe that parts at the front, a
simple wooden staff in the right hand, a small faint ember glowing above the
open left palm, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

---

# Женские силуэты

Та же поза, рамка, фон и тлеющая кромка, что у мужских: окна слотов общие
для обоих. Без лица - так же.

**Броня полная и практичная, как у мужских.** Без открытого тела, без
«бронелифчиков» и подчёркнутых форм: это тот же боец того же подкласса,
женский силуэт читается по пропорциям (уже плечи и талия, другая посадка),
а не по открытости брони. Если генератор всё равно открывает тело - добавь
в конец `modest, fully covered`.

# Подклассы

## Кровавый рыцарь

`img/силуэт_кровавый_рыцарь_ж.png`

Та же тяжесть и те же наплечники, что у мужского: рыцарь, а не украшение. Волосы, если видны, убраны под капюшон или шлем.

```
a tall broad-shouldered female knight in heavy angular plate with large pauldrons, a tattered cloak hanging in torn strips behind her, a long straight greatsword held low in the right hand with the point toward the ground, thin trails of dark red glow running along the blade edge, practical full armor with no exposed skin, the rim light along her outline has a faint blood red tint, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Страж

`img/силуэт_страж_ж.png`

Такая же массивная, как мужской Страж: толстая броня, большой щит, крепкая стойка. Женский силуэт читается по более узкой талии и посадке плеч, не по открытой броне.

```
a powerfully built female guardian in thick layered plate, a large rounded tower shield strapped to the left forearm and held slightly out to the side so the chest stays visible, a short heavy mace in the right hand, wide firm stance, practical full armor with no exposed skin, the rim light along her outline is steady and pale like cooling iron, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Тёмный мистик

`img/силуэт_тёмный_мистик_ж.png`

Высокая, в длинной мантии с капюшоном, мантия расходится спереди - ноги видны под слоты штанов и сапог.

```
a tall slender female mystic in a long hooded robe that parts at the front to show the legs and boots underneath, a tall gnarled staff in the right hand topped with a small pale violet flame, the left hand open and raised slightly with a faint violet glow in the palm, the rim light along her outline has a cold violet tint, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Элементалист

`img/силуэт_элементалист_ж.png`

Плащ до колен, короткий жезл, три стихийные искры у левой руки - как у мужского.

```
a lean female mage in a hooded knee-length coat with loose sleeves, a short rod in the right hand, three small floating motes around the left hand, one of flickering fire, one of pale blue ice, one of crackling white lightning, the coat edges lifted slightly as if by a hot draft, the rim light along her outline shifts from orange to icy blue, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Клинок теней

`img/силуэт_клинок_теней_ж.png`

Узкая и лёгкая, облегающая кожаная одежда закрывает тело полностью - ловкость, а не открытость.

```
a slim agile female assassin in close fitting dark leathers that cover the whole body, a short hooded half cape over the shoulders, a long dagger held in a reverse grip in the right hand, a second dagger sheathed at the hip, wisps of black shadow curling off the shoulders and heels, the rim light along her outline is thin and sharp like a knife edge, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Отравитель

`img/силуэт_отравитель_ж.png`

Сутулая, в длинном рваном плаще со склянками на поясе - травница с дурной славой.

```
a hunched female poisoner in a long ragged hooded cloak, a belt hung with small glass vials and pouches, a short curved blade in the right hand with a drop of sickly green liquid on its tip, a faint green haze rising from the vials, the rim light along her outline has a dull toxic green tint, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

# Базовые классы (до 30 уровня)

## Воин

`img/силуэт_воин_ж.png`

```
a sturdy plain female warrior in simple worn mail and a short cloak, a plain straight sword in the right hand pointing down, a small round buckler on the left arm held to the side, practical armor with no exposed skin, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Разбойник

`img/силуэт_разбойник_ж.png`

```
a light wiry female rogue in a simple hooded jacket and soft boots, a plain short knife in the right hand, a coil of rope at the belt, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

## Маг

`img/силуэт_маг_ж.png`

```
a young female mage in a plain hooded travelling robe that parts at the front, a simple wooden staff in the right hand, a small faint ember glowing above the open left palm, full body figure standing upright facing the viewer, symmetrical front view,
feet slightly apart, arms held a little away from the body with both hands
visible, the head hidden in deep shadow with no visible face or features,
the whole figure is a near-black silhouette with only a faint ember rim light
glowing along its outline, subtle drifting ash sparks around the edges, dark
fantasy, painterly semi-realistic, muted palette of ash grey and smouldering
orange, figure centered with small even margins above the head and below the
feet, isolated on a plain pure black background, no ground, no floor shadow,
no fog, no text, no watermark, no logo, vertical 2:3 composition
```

---

## Что проверить, когда картинки будут готовы


1. Положи все восемнадцать рядом, мужской и женский вариант одного класса
   особенно. Макушки и ступни на одной высоте, руки
   примерно в одном месте. Если какая-то выбилась, лучше перегенерировать:
   иначе окна слотов поедут на этом подклассе.
2. Лица нет ни у одного.
3. Фон чисто чёрный, без тумана у ног: его я вырезаю.
4. Нагрудник, штаны и сапоги ничем не закрыты: ни щитом, ни мантией.
