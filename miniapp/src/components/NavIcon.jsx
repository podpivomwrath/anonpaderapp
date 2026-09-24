import { SECTION_ICONS } from '../icons.js';

/**
 * Иконка раздела: встроенный SVG, красится currentColor.
 *
 * Именно встроенный, а не <img> и не CSS-маска. Через <img> внешний SVG не
 * видит currentColor и остаётся чёрным в тёмной теме; через маску его
 * ломали одинарные кавычки внутри data-URL, который собирает Vite. Здесь
 * контур - часть разметки, и обе проблемы отпадают.
 */
export default function NavIcon({ id, size = 22 }) {
  const icon = SECTION_ICONS[id];
  if (!icon) return null;
  if (icon.path) {
    return (
      <svg
        className="nav-icon"
        viewBox="0 0 24 24"
        width={size}
        height={size}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d={icon.path} />
      </svg>
    );
  }
  return (
    <span className="nav-icon nav-icon--emoji" style={{ fontSize: size }} aria-hidden="true">
      {icon.emoji}
    </span>
  );
}
