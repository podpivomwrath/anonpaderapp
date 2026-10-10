# Иконки на замену (2026-10-11)

Проверка всех иконок мини-аппа на смысл. Три не подходят предмету: две
рисуют обувь вместо штанов, одна - узнаваемую христианскую икону.

Сохранить под указанным именем в `img/` - иконка подключится сама по
имени файла (`OVERRIDE_FILES` в `tools/icon_assets.py`), старая перестанет
показываться. Промты в общем генераторе не трогаем: по их тексту находятся
все остальные иконки.

Главное в промтах штанов - **без ступней и без обуви**: в слоте «сапоги»
своя вещь, и штаны со ступнями читаются как она.

---

## Обмотки (штаны) - `предмет_обмотки.png`

Сейчас: обмотанные сапоги со ступнями - читается как обувь.

```
leg armour called «Обмотки»: a pair of trouser legs made entirely of long strips of cloth and leather wound tightly around from hip to ankle, laid out flat like empty leggings, the strips ending at the ankle cuffs with loose trailing ends, no feet, no shoes, no boots, battered and field-repaired, scavenged look, cold off-white accents, dark fantasy game item icon, single object centered, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey, rust brown and dried blood, weathered and worn surfaces, soft rim light from the upper left, deep neutral background, no text, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```

## Поножи (штаны) - `предмет_поножи.png`

Сейчас: латные голенища со ступнями - путаются с сабатонами из сапог.

```
leg armour called «Поножи»: a full pair of iron leg plates from hip to ankle - thigh plates, round knee cops and shin greaves joined by leather straps, shown as empty leg armour standing upright, open at the ankle, no feet, no shoes, no sabatons, battered and field-repaired, scavenged look, cold off-white accents, dark fantasy game item icon, single object centered, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey, rust brown and dried blood, weathered and worn surfaces, soft rim light from the upper left, deep neutral background, no text, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```

## Храмовые образа (товар) - `товар_храмовые_образа_2.png`

Сейчас: узнаваемая икона Богородицы с младенцем - мир игры свой, без
христианских образов.

```
a trade good called «Храмовые образа»: a folded wooden triptych of faded temple paintings showing a red monolith and hooded faceless pilgrims kneeling before it, chipped gilt edges, no christian imagery, no saints, no halos, burnt amber accents, merchant's wares ready for the road, dark fantasy game item icon, single object centered, slight 3/4 angle, painterly semi-realistic, muted desaturated palette of ash grey, rust brown and dried blood, weathered and worn surfaces, soft rim light from the upper left, deep neutral background, no text, no watermark, no border, square 1:1 composition, crisp readable silhouette at small size
```
