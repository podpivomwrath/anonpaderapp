import { SECTION_ICONS } from '../icons.js';

/**
 * Слот под иконку раздела. Пока рисует эмодзи, но переключится на
 * картинку сам, как только в src/icons.js появится путь - размер
 * зарезервирован заранее, чтобы список не дёрнулся при подмене.
 */
export default function NavIcon({ id, size = 22 }) {
  const icon = SECTION_ICONS[id];
  if (!icon) return null;
  if (icon.src) {
    return (
      <img
        className="nav-icon"
        src={icon.src}
        alt=""
        aria-hidden="true"
        width={size}
        height={size}
      />
    );
  }
  return (
    <span className="nav-icon nav-icon--emoji" style={{ fontSize: size }} aria-hidden="true">
      {icon.emoji}
    </span>
  );
}
