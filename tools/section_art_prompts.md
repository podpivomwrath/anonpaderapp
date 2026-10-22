# Промты: шапки разделов мини-аппа

Широкая полоса над каждым разделом (`SectionHead` в `miniapp/src/components/ui.jsx`).
Поверх картинки слева лежат значок и главная цифра раздела, поэтому **левая треть
кадра должна быть тёмной и пустой**, а сюжет - справа. Слева код ещё и
затемняет картинку градиентом.

Готовые файлы клади в `img/шапка_<раздел>.png` и запускай
`python tools/section_assets.py` - он ужмёт их в `miniapp/src/assets/sections/`.
Нет файла - шапка остаётся цветным градиентом, так что делать можно по одной.

## Кадр - одинаковый для всех

- Горизонтальный 3:1, лучше 1536×512.
- Главный предмет - в правой половине, по центру по высоте. Левая треть -
  почти чёрная, без деталей.
- Тёмная гамма, низкий тёплый свет, пепел в воздухе. Без текста, букв,
  рамок и людей в кадре (руки и силуэты вдали - можно).

## Общий хвост (добавляй в конец каждого промта)

```
wide banner composition 3:1, main subject on the right half, the left third
fades into near-black empty darkness, dark fantasy, painterly, ash particles
drifting in the air, low warm light, muted colors with crimson accents,
no text, no letters, no frame, no people in focus
```

## Разделы

| Файл | Раздел | Промт |
|---|---|---|
| `шапка_dailies.png` | Задания, ежедневные | an old notice board nailed to a charred wooden post, a few torn parchment task notes pinned with rusty nails, a small campfire glowing below it |
| `шапка_login.png` | Задания, вход | a wall calendar carved into dark stone, fourteen notches, several of them filled with glowing embers, a candle burning on a ledge beneath |
| `шапка_inventory.png` | Инвентарь | an open worn leather backpack spilling its contents on a dark wooden table: a rusty sword hilt, small potion vials, a pouch of coins, a small iron-bound chest |
| `шапка_craft.png` | Мастерская | a blacksmith anvil with a red-hot blade on it, a hammer mid-strike, bright sparks flying, a glowing forge behind |
| `шапка_crafts.png` | Ремёсла | a craftsman's shelf: a fishing rod, a mining pick, bundles of dried herbs, an alchemist flask and a cooking pot, lit by a lantern |
| `шапка_tops.png` | Топы | a stone pedestal with three steps, a battered golden crown resting on the top step, ash falling like snow, a faint beam of light from above |
| `шапка_board.png` | Доска PvP | a weathered wooden wall covered in old wanted posters with blood-red seals, one poster half torn, a dagger stuck into the wood |
| `шапка_guild.png` | Гильдия | a long dark hall with a heavy oak table, several tattered guild banners hanging from the beams, a fireplace burning at the far end |
| `шапка_trade.png` | Фракция, торговля | an ox-drawn covered cargo cart on a dusty road at dusk, wooden crates stacked in it, a distant walled town on the horizon |
| `шапка_exchange.png` | Биржа | a merchant's scale on a counter, one pan heavy with gold coins, the other with deep blue glowing gems, a ledger and a quill nearby |
| `шапка_shop.png` | Магазин | a dim merchant stall with shelves of glowing blue gems, small potions and a mysterious sealed book with a silver emblem, warm lantern light |
| `шапка_trials.png` | Испытания и пресеты | a stone altar with carved runes, several runes glowing pale blue, an old sword lying across it, faint mist |

## Ещё, если захочешь

- **Плакат розыска** (Доска → Розыск): сейчас бумага нарисована градиентом и
  смотрится прилично. Картинка не обязательна.
- **Гербы городов** (Фракция → Фракции): сейчас у ступени процветания эмодзи.
  Можно нарисовать 4 герба городов, квадрат 512×512, щит на чёрном фоне - скажи,
  и я напишу промты под каждый город.
