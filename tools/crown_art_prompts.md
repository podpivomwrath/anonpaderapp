# Промты: базовые классы и рамки топ-1

Два набора под «венец топа»: три иконки базовых классов и пять рамок,
по одной на доску.

Стиль общий с эмблемами подклассов (`tools/icon_prompts.py`, раздел «Эмблемы
подклассов»): это **эмблемы, а не персонажи**. В топе и в шапке игрок видит
себя, и чужое лицо спорило бы с тем, кого он себе представляет.

---

# Базовые классы — 3 иконки

Нужны потому, что подкласс есть не у всех: на сервере он у семи персонажей
из восемнадцати, остальные не дошли до тридцатого уровня. Без этих трёх
иконок половина строк топа поедет без значка.

Работают они и как запасной вариант: подкласса нет — показываем базовый
класс.

Размер и вид — ровно как у эмблем подклассов, они встанут в тот же ряд.

## Общий хвост

```
dark fantasy game item icon, single object centered, slight 3/4 angle,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood, weathered and worn surfaces, soft rim light from the upper
left, deep neutral background, an emblem rather than a character, no text, no
watermark, no border, square 1:1 composition, crisp readable silhouette at
small size
```

## Воин — Путь Стали

Прямой клинок и щит: единственный из трёх, кто встречает удар. Композиция
симметричная и тяжёлая — класс читается устойчивостью.

```
a straight heavy sword crossed over a small round shield, both dented from
use, symmetrical and solid composition, burnt amber accents, dark fantasy game
item icon, single object centered, slight 3/4 angle, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, weathered
and worn surfaces, soft rim light from the upper left, deep neutral
background, an emblem rather than a character, no text, no watermark, no
border, square 1:1 composition, crisp readable silhouette at small size
```

## Разбойник

Два коротких клинка накрест, один наполовину в тени: композиция намеренно
несимметричная, чтобы рядом с воином читалась с одного взгляда.

```
two short curved daggers crossed at an angle, one blade half swallowed by
shadow, deliberately asymmetric composition, pale steel-blue accents, dark
fantasy game item icon, single object centered, slight 3/4 angle, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, weathered and worn surfaces, soft rim light from the upper left, deep
neutral background, an emblem rather than a character, no text, no watermark,
no border, square 1:1 composition, crisp readable silhouette at small size
```

## Маг

Навершие посоха с осколком Монолита. Единственная из трёх иконок со
свечением — по нему класс и опознают в мелком размере.

```
the head of a gnarled wooden staff holding a shard of glowing stone in its
claw, faint inner light spilling from the shard, the only glow among the class
emblems, muted violet accents, dark fantasy game item icon, single object
centered, slight 3/4 angle, painterly semi-realistic, muted desaturated
palette of ash grey, rust brown and dried blood, weathered and worn surfaces,
soft rim light from the upper left, deep neutral background, an emblem rather
than a character, no text, no watermark, no border, square 1:1 composition,
crisp readable silhouette at small size
```

---

# Рамки топ-1 — 5 штук

По одной на доску. Рамку носит только первое место: сместили — забрали.

**Середина обязана быть полностью прозрачной.** Рамка накладывается поверх
эмблемы класса, а не заменяет её. У существующих рамок редкости это сделано
верно (альфа в центре 0), их и берём за образец формы.

**Толщина умеренная.** В шапке мини-аппа эмблема 44 пикселя, в топах ещё
меньше: рамка толще четверти стороны съест саму картинку.

**Чем рамка отличается от рамок редкости.** Те говорили «насколько ценная
вещь» и были ровными. Эти говорят «кто первый», поэтому у каждой свой мотив
от своей доски — рамка должна читаться даже без подписи.

## Общий хвост

```
ornate square frame border only, completely empty and fully transparent in the
centre, thin to medium border thickness no more than one sixth of the side,
symmetrical, dark fantasy, painterly semi-realistic, muted desaturated palette
of ash grey and rust brown with a single accent colour, weathered metal, soft
inner rim light, no text, no watermark, no background, transparent PNG, square
1:1 composition, readable silhouette at 64 pixels
```

## ⚔️ PvP — «Клинок»

Мотив: скрещённые клинки в верхнем и нижнем углах, по сторонам — гладкий
металл с зарубками.

```
a square frame of crossed blades at top and bottom corners with plain nicked
steel along the sides, deep crimson accent, ornate square frame border only,
completely empty and fully transparent in the centre, thin to medium border
thickness no more than one sixth of the side, symmetrical, dark fantasy,
painterly semi-realistic, muted desaturated palette of ash grey and rust
brown, weathered metal, soft inner rim light, no text, no watermark, no
background, transparent PNG, square 1:1 composition, readable silhouette at 64
pixels
```

## 💀 Убийства — «Охотник»

Мотив: мелкие звериные клыки и позвонки, уложенные по периметру плотно и
аккуратно — счёт, а не трофей.

```
a square frame made of small animal fangs and vertebrae laid tightly and
evenly around the perimeter like tally marks, bone white and dried blood
accent, ornate square frame border only, completely empty and fully
transparent in the centre, thin to medium border thickness no more than one
sixth of the side, symmetrical, dark fantasy, painterly semi-realistic, muted
desaturated palette of ash grey and rust brown, weathered surfaces, soft inner
rim light, no text, no watermark, no background, transparent PNG, square 1:1
composition, readable silhouette at 64 pixels
```

## 🎣 Рыбалка — «Мастер лески»

Мотив: витая леска и мелкие крючки по углам. Самая лёгкая рамка из пяти.

```
a square frame of twisted fishing line with small hooks at the corners, thin
and light, brine green accent, ornate square frame border only, completely
empty and fully transparent in the centre, thin border thickness no more than
one eighth of the side, symmetrical, dark fantasy, painterly semi-realistic,
muted desaturated palette of ash grey and rust brown, wet rope and tarnished
metal, soft inner rim light, no text, no watermark, no background, transparent
PNG, square 1:1 composition, readable silhouette at 64 pixels
```

## 🐟 Рекорды по рыбе — «Трофей»

Мотив: чешуя и плавники. Тяжелее предыдущей намеренно — это не про ремесло,
а про пойманную громадину.

```
a square frame of overlapping large fish scales with fins at the corners,
heavy and thick compared to a line frame, pale steel-blue accent, ornate
square frame border only, completely empty and fully transparent in the
centre, medium border thickness no more than one sixth of the side,
symmetrical, dark fantasy, painterly semi-realistic, muted desaturated palette
of ash grey and rust brown, wet iridescent surfaces, soft inner rim light, no
text, no watermark, no background, transparent PNG, square 1:1 composition,
readable silhouette at 64 pixels
```

## ⛏ Горное дело — «Жила»

Мотив: грубый камень с прожилкой руды, идущей по периметру не прерываясь.

```
a square frame carved from rough dark stone with a single unbroken vein of
glowing ore running all the way around the perimeter, burnt amber accent,
ornate square frame border only, completely empty and fully transparent in the
centre, medium border thickness no more than one sixth of the side,
symmetrical, dark fantasy, painterly semi-realistic, muted desaturated palette
of ash grey and rust brown, rough stone and metal, soft inner rim light, no
text, no watermark, no background, transparent PNG, square 1:1 composition,
readable silhouette at 64 pixels
```
