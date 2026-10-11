import { itemIcon } from '../itemIcons.js';

/**
 * Картинка предмета (патч 76) со свечением редкости (патч 79).
 *
 * Редкость показывает СВЕЧЕНИЕ РАМКИ, а не цвет подписи. Цветной текст в
 * списке заставляет читать не слово, а оттенок, и на тёмном фоне половина
 * градаций выцветает до нечитаемых. Цвет на объекте работает иначе: имя
 * остаётся обычным, а взгляд всё равно цепляется за нужную строку.
 *
 * У обычных вещей свечения нет вовсе - это не потеря, а смысл: обычное и
 * должно выглядеть обычным.
 */
// Новой боссовой вещи картинку рисуют позже, чем выходит сам рейд - до
// тех пор вместо пустого места знак уникальной редкости.
//
// Пустая рамка вместо вещи выглядела как ошибка (Панцирь Тавра, 2026-10-11),
// поэтому сначала - базовая вещь того же вида: панцирь для Панциря Тавра и
// его ковки, маска для Маски Архивариуса. Рамка - если и этого нет.
const UNIQUE_STAND_IN = {
  general_cuirass: 'base:armor:Панцирь',
  archivist_mask: 'base:helmet:Маска',
};

function fallbackFor(icon) {
  if (!icon.startsWith('unique:') && !icon.startsWith('craft:')) return null;
  const source = icon.split(':')[1];
  const standIn = UNIQUE_STAND_IN[source];
  return (standIn && itemIcon(standIn)) || itemIcon('rarity:unique');
}

export default function ItemIcon({ icon, rarity, alt = '', size = 36 }) {
  const src = icon ? itemIcon(icon) ?? fallbackFor(icon) : null;
  if (!src) return null;
  const className = rarity ? `item-icon item-icon--${rarity}` : 'item-icon';
  return (
    <img
      className={className}
      src={src}
      alt={alt}
      loading="lazy"
      width={size}
      height={size}
    />
  );
}
