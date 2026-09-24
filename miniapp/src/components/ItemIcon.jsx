import { itemIcon } from '../itemIcons.js';

/**
 * Картинка предмета в списке (патч 76).
 *
 * Тег <img>, а не CSS-маска, в отличие от иконок навигации: там нужен был
 * цвет темы, здесь — само изображение со своими цветами.
 *
 * Нет картинки — нет и места под неё. Пустой квадрат сдвигал бы текст и
 * выглядел как «иконка не загрузилась», хотя её просто ещё не нарисовали.
 */
export default function ItemIcon({ icon, alt = '', size = 36 }) {
  const src = icon ? itemIcon(icon) : null;
  if (!src) return null;
  return (
    <img
      className="item-icon"
      src={src}
      alt={alt}
      loading="lazy"
      width={size}
      height={size}
    />
  );
}
