/**
 * Иконки разделов (патч 72).
 *
 * Пока каждый раздел рисуется эмодзи, но место под настоящие картинки уже
 * заготовлено: как только файл появится, достаточно положить его в
 * src/assets/icons/ и вписать путь в `src` — ничего больше править не надо,
 * NavIcon сам переключится с эмодзи на картинку.
 *
 * Почему манифест, а не импорт в каждом компоненте: иконка раздела нужна и в
 * шторке, и в шапке, и (потом) в подсказках. Разъезд между этими местами —
 * вопрос времени, если у каждого свой источник.
 */

// Чтобы добавить иконку:
//   1. положить файл в miniapp/src/assets/icons/<id>.svg (или .png)
//   2. заменить здесь  src: null  на  src: new URL('./assets/icons/<id>.svg', import.meta.url).href
// Эмодзи оставляем как запасной вариант: он же виден, пока картинка грузится.
export const SECTION_ICONS = {
  character: { emoji: '🎭', src: new URL('./assets/icons/character.svg', import.meta.url).href },
  dailies: { emoji: '📜', src: new URL('./assets/icons/dailies.svg', import.meta.url).href },
  inventory: { emoji: '🎒', src: new URL('./assets/icons/inventory.svg', import.meta.url).href },
  craft: { emoji: '🔨', src: new URL('./assets/icons/craft.svg', import.meta.url).href },
  map: { emoji: '🗺️', src: new URL('./assets/icons/map.svg', import.meta.url).href },
  tops: { emoji: '🏆', src: new URL('./assets/icons/tops.svg', import.meta.url).href },
  exchange: { emoji: '💱', src: new URL('./assets/icons/exchange.svg', import.meta.url).href },
  admin: { emoji: '🛡️', src: new URL('./assets/icons/admin.svg', import.meta.url).href },
};
