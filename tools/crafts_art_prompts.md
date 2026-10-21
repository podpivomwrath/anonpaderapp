# Ремесла: дом, травы, блюда - промты картинок

Сцены дома - горизонтальные 3:2, как картинки локаций и NPC в чате.
Иконки трав и блюд - квадрат 1:1, как иконки рыбы и руды в мини-аппе.
Готовые файлы класть в `img/` под указанными именами - подключу и выкачу.

Дом - не дворец: комната в каменном доме посреди обнищавшего города под
пепельным небом. Тепло только от печи.

## Общий стилевой хвост сцен

```
dark fantasy interior scene, painterly semi-realistic, muted desaturated
palette of ash grey, soot black, warm ember orange and faded wood, a single
warm light source, drifting ash dust in the light, lived-in and worn, no
people, no readable text, no watermark, no logo, no modern objects,
horizontal 3:2 composition
```

## Дом

`img/дом.png`

```
a small room inside an old stone townhouse, thick walls with patched plaster,
a low wooden ceiling with blackened beams, a squat clay stove glowing in one
corner, a heavy workbench with glass flasks and bundles of drying herbs in the
other, a narrow window with grey ash falling outside, a straw mattress and a
chest by the wall, + общий хвост
```

## Печь

`img/дом_печь.png`

```
close view of a squat clay and brick stove with an open iron door and glowing
coals inside, a blackened iron pot and a long-handled pan on top, smoked fish
hanging on a cord above, a wooden board with a knife, onions and a bowl of
salt beside it, + общий хвост
```

## Алхимический стол

`img/дом_стол.png`

```
close view of a heavy scarred wooden workbench crowded with glass retorts,
corked vials of red and grey liquids, a stone mortar and pestle, a small brass
burner with a blue flame under a flask, bundles of dried herbs hanging from a
beam above, stains and burn marks on the wood, + общий хвост
```

## Общий стилевой хвост иконок

```
dark fantasy game item icon, single object centered, slight 3/4 angle,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood with one accent colour, weathered and natural, soft rim light
from the upper left, deep neutral background, no text, no watermark, no
border, square 1:1 composition, crisp readable silhouette at small size
```

## Травы (10)

Одна иконка на вид: пучок или одно растение, без горшка и без рук.

| Файл | Трава | Промт (+ хвост иконок) |
|---|---|---|
| `img/трава_полынь.png` | Горькая полынь | a bundle of silvery grey wormwood stems with narrow feathery leaves, tied with a strand of grass |
| `img/трава_подорожник.png` | Пепельный подорожник | a rosette of broad ribbed plantain leaves dusted with fine grey ash, a single seed spike rising from the centre |
| `img/трава_лебеда.png` | Солончаковая лебеда | a sprig of pale orache with fleshy silvery leaves crusted with white salt crystals |
| `img/трава_чертополох.png` | Ржавый чертополох | a thistle stem with spiky leaves and a single flower head, the spines rust orange like old nails |
| `img/трава_кровохлебка.png` | Кровохлебка | slender stems topped with small oval dark red flower heads, a few drops of red sap on the leaves |
| `img/трава_болиголов.png` | Сизый болиголов | a hemlock stem with bluish grey speckled stalk and flat umbels of tiny white flowers |
| `img/трава_мак.png` | Пепельный мак | an ash grey poppy flower with a black centre and a dry seed pod beside it, faint smoke curling from the pod |
| `img/трава_вереск.png` | Тлеющий вереск | a sprig of heather with tiny bell flowers glowing faint ember orange from inside, like smouldering coals |
| `img/трава_корень.png` | Багряный корень | a gnarled root that is deep crimson all the way through, a cut end showing red pulsing veins, a few torn rootlets |
| `img/трава_каменный_цвет.png` | Каменный цвет | a flower with petals of thin polished grey stone growing straight out of a small rock, a faint light in its centre |

## Блюда (10)

Одно блюдо в простой посуде: глиняная миска, деревянная доска или сковорода.
Еда бедная, но горячая - пар над ней.

| Файл | Блюдо | Промт (+ хвост иконок) |
|---|---|---|
| `img/еда_уха.png` | Уха с полынью | a clay bowl of clear fish soup with chunks of pale fish and a sprig of grey wormwood, steam rising |
| `img/еда_пескарь.png` | Печеный пескарь | a few small whole baked fish on a wooden board, crisp blackened skin, a pinch of coarse salt |
| `img/еда_похлебка.png` | Похлебка с лебедой | a clay bowl of thick fish stew with silvery orache leaves floating on top, a wooden spoon |
| `img/еда_линь.png` | Копченый линь | a whole smoked tench, golden brown skin, hanging from a cord by its tail |
| `img/еда_пирог.png` | Пирог с чертополохом | a round rustic pie with a cracked golden crust, one slice cut to show fish and rust-coloured greens inside |
| `img/еда_угорь.png` | Угорь в кровохлебке | slices of dark eel in a shallow pan with a deep red herb sauce |
| `img/еда_жаркое.png` | Жаркое из осетра | thick chunks of sturgeon roasted in a black iron pan with grey poppy seeds, steam and glistening fat |
| `img/еда_камбала.png` | Камбала на углях | a whole flat flounder grilled over glowing coals on an iron grate, faint ember glow from heather sprigs under it |
| `img/еда_слеза.png` | Слеза глубины в корне | a pale translucent deep sea fish fillet laid on slices of crimson root, served on a dark stone plate |
| `img/еда_пир.png` | Пир у Монолита | a heavy wooden platter with a whole roasted large fish, crimson roots and a single stone flower in the centre, a dark red glow in the background |

## Карточка магазина - `img/магазин_дом.png` (1:1)

Готово (2026-10-21), подключено как miniapp/src/assets/shop/house.webp. Иконка -
снаружи: небольшой каменный дом в городе, свет в окне и дым из трубы,
чтобы читалось «свой угол» даже на маленькой карточке.

```
a small narrow two-storey stone townhouse squeezed between darker buildings,
a warm orange light in one window, thin smoke rising from a crooked chimney,
a heavy wooden door with an iron ring, grey ash falling on the roof tiles,
dark fantasy game item icon, single building centered, slight 3/4 angle,
painterly semi-realistic, muted desaturated palette of ash grey, rust brown
and dried blood with a warm ember accent, weathered and worn surfaces, soft
rim light from the upper left, deep neutral background, no text, no
watermark, no border, square 1:1 composition, crisp readable silhouette at
small size
```
