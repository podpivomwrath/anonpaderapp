# Промты для рейда «Кукольный театр»

Одна картинка на БОЙ, а не на противника: на втором этапе трое именных
кукол, и они должны поместиться в один кадр.

Это не иконки предметов, а сцены для чата ВК — как портреты мобов. Отсюда
и отличия от `tools/icon_prompts.py`: горизонтальный кадр, свет рампы,
несколько фигур в одном кадре.

Промты на английском: модели генерации понимают его точнее. Лор взят из
`bot/raid_texts.py`, поэтому картинка не разойдётся с текстом, который игрок
читает в ту же секунду.

Пропорции: **3:2, горизонтально**. Вертикальный кадр чат ВК обрежет, а на
втором этапе обрезать нечего — трое уже стоят впритык.

---

## Общий стилевой хвост

Дописывается к каждому из трёх промтов. Без него сцены выйдут из разных
миров: театр должен быть один и тот же на всех трёх этапах.

```
dark fantasy scene, old wooden theatre stage seen from the audience, painterly
semi-realistic, muted desaturated palette of ash grey, rust brown and dried
blood, harsh gas footlights from below throwing long shadows upward, dust in the
air, heavy faded curtains at the edges of the frame, worn scuffed floorboards,
no text, no watermark, no logo, no modern objects, horizontal 3:2 composition,
full figures visible and not cropped
```

---

## Этап 1 — Пробные куклы

Три одинаковые куклы, 8 000 HP каждая. По тексту они выходят из-за кулис
рывками, будто их дёргают за нитки не в такт, и каждая кланяется отдельно —
старательно, как ученик на экзамене.

Кадр: черновая работа. Это пробы пера перед настоящими куклами, поэтому они
должны выглядеть грубо и незаконченно — тем страшнее то, что выйдет дальше.
Три одинаковые фигуры, но пойманы в РАЗНЫХ фазах поклона: так читается, что
нитки дёргают не в такт.

```
three identical life-sized wooden marionettes standing in a row at the front of
the stage, crude unfinished carpentry, visible chisel marks and raw pale wood,
mismatched scraps of cloth for clothing, blank sanded faces with only shallow
eye sockets, visible knotted strings running up out of frame into darkness,
each doll caught mid-bow at a different depth so their movement is clearly out
of sync, wooden joints exposed at elbows and knees, one doll's arm hanging
slightly wrong, dark fantasy scene, old wooden theatre stage seen from the
audience, painterly semi-realistic, muted desaturated palette of ash grey, rust
brown and dried blood, harsh gas footlights from below throwing long shadows
upward, dust in the air, heavy faded curtains at the edges of the frame, worn
scuffed floorboards, no text, no watermark, no logo, no modern objects,
horizontal 3:2 composition, full figures visible and not cropped
```

---

## Этап 2 — Семья Вельд

Освальд, Ирма и Литта. По тексту выходят вместе и встают ровно, плечом к
плечу.

Кадр: **композиция не должна подсказывать порядок убийства.** Правильный
порядок — Освальд, Ирма, Литта, то есть ровно от самого заметного к самому
незаметному. Если поставить Освальда в центр и дать ему главный свет, игрок
прочитает «бей самого опасного» и попадёт в верный ответ с первого взгляда,
а этап задуман как загадка. Поэтому вперёд и в свет рампы выведена Литта —
маленькая, последняя по порядку; Освальд отодвинут к краю и частично в тень.
Ростом и массой он всё равно останется крупнейшим, скрывать это не нужно,
но внимание кадра ведёт не к нему.

Приметы каждого из текста: у Освальда правая рука заменена целиком (дерево и
медные шарниры), швы на плечах разошлись от собственной силы, в груди
вырезано отверстие и оттуда тянет жаром. У Ирмы половина лица фарфоровая, и
эта половина улыбается всегда, а живая половина просто устала. Литте
заменили только глаза — стеклянные и слишком большие для такого лица.

```
three figures of one family standing shoulder to shoulder on a theatre stage,
part human and part doll. Centre foreground and lit brightest: a small girl,
her own living face, but her eyes replaced with oversized glass doll eyes far
too large for her face, plain dress, calm and polite expression. Beside her: a
woman whose left half of the face is smooth white porcelain fixed in a permanent
smile, while the living right half looks merely tired, fine seam running down
the middle of her face. Pushed toward the edge of the frame and half in shadow
despite being the tallest and heaviest: a broad man in a torn shirt, his entire
right arm replaced with dark carved wood and copper hinges, burst stitching
across both shoulders where the seams tore open, a rectangular hole cut into his
chest with furnace heat and dull orange light spilling out of it. Dark fantasy
scene, old wooden theatre stage seen from the audience, painterly semi-realistic,
muted desaturated palette of ash grey, rust brown and dried blood, harsh gas
footlights from below throwing long shadows upward, dust in the air, heavy faded
curtains at the edges of the frame, worn scuffed floorboards, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition, full figures
visible and not cropped
```

---

## Этап 3 — Хирург

Один, 45 000 HP. По тексту выкатывает стол сам, инструменты разложены ровными
рядами по размеру, пахнет спиртом и горячим железом. Сутулый, в переднике,
который давно не отстирывается, руки заканчиваются латунными сочленениями,
шестерни в локтях проворачиваются на каждом шаге.

Кадр: он не смотрит на зрителя — по тексту он говорит «Новый материал», не
поднимая головы. Это страшнее прямого взгляда: игрок для него не противник,
а работа. Инструменты на виду и разложены аккуратно, потому что вся механика
этапа — про то, что он готовит инструмент, и это надо успеть сбить.

```
a stooped surgeon standing behind a wheeled metal instrument table on a theatre
stage, not looking at the viewer, head down and absorbed in his work, wearing a
heavy leather apron stained dark and long past washing, his arms ending in
brass mechanical joints with exposed gears at the elbows, surgical instruments
laid out on the table in neat rows sorted by size and catching the light, small
brazier heat haze and the sheen of spirits on steel, single gaunt figure
dominating the frame, quiet and unhurried and businesslike, dark fantasy scene,
old wooden theatre stage seen from the audience, painterly semi-realistic, muted
desaturated palette of ash grey, rust brown and dried blood, harsh gas
footlights from below throwing long shadows upward, dust in the air, heavy faded
curtains at the edges of the frame, worn scuffed floorboards, no text, no
watermark, no logo, no modern objects, horizontal 3:2 composition, full figure
visible and not cropped
```

---

## Необязательный четвёртый кадр — пролог

Не бой, поэтому в тройку не входит. Но пролог — единственное место рейда, где
игрок видит ЗАЛ, а не сцену, и текст там сильный: кресла заняты, никто не
оборачивается, видны только затылки и пыльные плечи, занавес уже поднят.

```
view from the stage looking out into a packed old theatre auditorium, every seat
taken by a motionless seated audience seen from behind, only the backs of heads
and dust-covered shoulders visible, nobody turning around, thick dust over
everything, raised curtain framing the top of the frame, faint smell-of-glue
warmth suggested by sickly amber light, deeply unsettling stillness, dark
fantasy scene, painterly semi-realistic, muted desaturated palette of ash grey,
rust brown and dried blood, harsh gas footlights from below throwing long
shadows upward, no text, no watermark, no logo, no modern objects, horizontal
3:2 composition
```
