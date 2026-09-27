# Промт: карта мира (круглая)

## Вариант «рисованная карта» (на оценку игрокам, 2026-09-28)

Живописная карта при приближении мылится. Рисованная (тушь, штриховка,
акварель на пергаменте) держит зум лучше: линии чёткие, а мягкость читается
как стиль. Геометрия та же - шаблон `tools/map_template.png` как основа,
круг, пять колец, города по сторонам света, Монолит в центре. Квадрат 1:1,
2048+.

**А - светлый пергамент, тушь и акварель:**

```
hand-drawn fantasy world map on aged parchment, ink linework with watercolor
washes, top-down cartographic view, square 1:1, follow the reference layout
exactly: one circular landmass centred on the canvas, five concentric zones
around the exact centre marked by thin dashed ink circles,
at the exact centre a small black obelisk drawn in ink with a red crack,
red-brown ink stains spreading from it in rings, the inner zones washed in
dried-blood red, the outer zones in pale ash grey,
four regions around the circle: north - hatched ink mountain ranges in cold
blue-grey wash with a tiny fortress on the northern rim; east - stippled salt
flats and a coastline with wave lines and a tiny harbour on the eastern rim;
south - scorched land with small ink volcanoes and red lava lines, a tiny
burnt fort on the southern rim; west - dense little ink tree symbols in muted
green wash, a tiny settlement on the western rim,
classic cartographer's style, crisp confident pen strokes, cross-hatching,
subtle paper texture, coffee stains and worn edges outside the circle, dark
fantasy mood, no text, no letters, no labels, no compass rose, no legend
```

**Б - тёмный пергамент, сепия (ближе к палитре игры):**

```
hand-drawn dark fantasy world map on dark smoke-stained parchment, sepia and
black ink linework with muted watercolor, top-down cartographic view, square
1:1, follow the reference layout exactly: one circular landmass centred on
the canvas, five concentric zones around the exact centre marked by thin
dashed ink circles,
at the exact centre a small black ink obelisk with a glowing crimson crack,
crimson ink bleeding outward in rings, inner zones in deep blood red wash,
outer zones in faded ash grey,
four regions around the circle: north - cross-hatched mountain ranges in cold
slate wash with a tiny fortress on the northern rim; east - stippled white
salt flats and an inked coastline with a tiny harbour on the eastern rim;
south - charred land, small inked volcanoes and thin red lava lines, a tiny
burnt fort on the southern rim; west - clusters of small ink tree symbols in
dark moss green, a tiny settlement on the western rim,
old cartographer's hand, crisp pen strokes, hatching instead of gradients,
ember-singed edges outside the circle, grim atmosphere, no text, no letters,
no labels, no compass rose, no legend
```

Если генератор тянет надписи - дописать в конец `absolutely no writing of
any kind`. После выбора варианта: замерить центр и кольца заново
(как для v2 ниже) и подставить калибровку в miniapp/src/mapCatalog.js.

---


Картинка-основа для карты мини-аппа. Клетки на ней не рисуются: код ставит их
поверх, подогнав разметку под нарисованное (центр и радиусы границ колец
замеряются по готовой картинке). Поэтому от арта нужна не точность до
пикселя, а читаемые концентрические пояса вокруг одного центра.

Шаблон геометрии - `tools/map_template.png`: отдать генератору как
референс/основу («нарисуй поверх этой схемы»), а не как стиль.

- Квадрат, **1:1**, не меньше 2048×2048, лучше 4096.
- Вид строго сверху, без наклона и перспективы: иначе круги станут
  эллипсами и разметка поплывёт.
- Без надписей, рамки, розы ветров и легенды - всё это делает код.
- Рудники, озёра, дороги не рисовать как отдельные значки: их ставит код.
  Фактура (скалы, вода у берега, лес) - можно и нужно.

Регионы - секторы по 90° вокруг сторон света, города на краю круга:

| Сторона | Регион | Город |
|---|---|---|
| Север | Обетованный Кряж - холодный камень, горы | 🏰 крепость в скале |
| Восток | Соляные Пристани - белёсый солёный берег, море за краем | ⚓ пристань |
| Юг | Выжженный Предел - угольная, спёкшаяся земля | 🔥 выжженный форт |
| Запад | Шепчущие Пущи - больной тёмно-зелёный лес | 🌲 поселение в чаще |

Пять поясов от края к центру (пропорции как в шаблоне): серый холодный пепел,
пепел с тёплой примесью, тускло-багровый, насыщенный багровый, у самого
центра почти чёрный. Регион виден сильнее у края и растворяется к центру:
чем ближе к Монолиту, тем меньше остаётся от родной земли.

```
top-down orthographic fantasy world map painted as a single circular land
seen from directly above, no perspective tilt, square 1:1 canvas, the
circular world fills the frame and fades into black void at the edges,
follow the reference layout exactly: five concentric rings around one
exact center point,
at the exact center a tiny black obelisk seen from above with a thin
glowing crimson crack, from which a corrupted crimson blight spreads
outward in rings,
the rings change from the edge to the center: outer ring of cold grey ash
wasteland, then ash with warm rusty tint, then dull crimson scorched
earth, then saturated blood-red cracked ground with faint glowing veins,
the innermost small ring almost black,
the land is divided into four regions by direction, each strongest near
the rim and dissolving into the blight toward the center:
north - cold bluish stone ridges and jagged mountains, a small fortress
carved into the rock on the northern rim;
east - pale white salt flats and a bleached shoreline with a dark sea
beyond the rim, a small wooden harbor on the eastern rim;
south - charred black cinder plains and cooled lava, a small burnt fort on
the southern rim;
west - dense sickly dark-green forest, a small settlement hidden among the
trees on the western rim,
the ring borders are soft painted transitions but clearly readable as
circles around the center,
dark fantasy, painterly hand-drawn map texture, muted desaturated palette
with crimson accents, subtle fog drifting across the land, grim and
desolate, high detail,
no text, no labels, no letters, no compass rose, no frame, no border, no
legend, no icons, no people
```

Если генератор тянет весь кадр в красное - добавь в конец
`the outer rings are mostly grey and cold, red only closer to the center`.
Если центр вышел не в центре кадра - не страшно, разметка его найдёт, но
пусть он будет один и отчётливо виден.

## Замер готовой картинки (img/карта_мира_пять_колец.png, 1254×1254)

- Центр Монолита: (625.5; 618) - на 2 px левее и 9 px выше центра кадра.
- Центральный диск: r ≈ 31 px (2.5% ширины), по шаблону 2.2%.
- Яркий багровый диск: r ≈ 122 px (9.8%), по шаблону 10%.
- Тусклый багровый пояс: граница ≈ 270 px (21.5%) - совпадает.
- Граница 35% (серый пепел / рыжий пепел) на арте не читается: регионы её
  перекрывают. Рисовать её тонкой линией поверх - кодом.
- Города: север ≈ 578 px, восток ≈ 570, юг ≈ 562, запад ≈ 555 от центра.
  Край игрового мира ставить по ним (~565 px), земля за ними - просто фон.
- Разрешение мало: ~11 px на клетку при радиусе 50, ~19 px при 30. Нужен
  апскейл ×3-4 перед использованием.

## v2 (img/карта_мира_пять_колец_v2.png) - ретушь

Геометрия не сдвинулась ни на пиксель (сверка со смещением - 0; 0), центр
тот же (625.5; 618). Швы убраны, диск у Монолита мягкий. Новая тёмная
полоса пепла легла на ~23-26% (сразу за тусклым багровым поясом), а не на
35%: читается как кромка багровой зоны. Границу 35% по-прежнему рисует код.
Основа для карты - v2.
