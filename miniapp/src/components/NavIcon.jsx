import { SECTION_ICONS } from '../icons.js';

/**
 * Иконка раздела. Пока в манифесте нет файла - рисуется эмодзи.
 *
 * Файл подставляется CSS-маской, а не тегом <img>: в <img> внешний SVG не
 * видит currentColor и остаётся того цвета, каким его сохранили - в тёмной
 * теме иконки были бы чёрными пятнами. Маска же красится background-ом,
 * то есть наследует цвет текста и активного пункта сама.
 */
export default function NavIcon({ id, size = 22 }) {
  const icon = SECTION_ICONS[id];
  if (!icon) return null;
  if (icon.src) {
    return (
      <span
        className="nav-icon nav-icon--mask"
        aria-hidden="true"
        style={{
          width: size,
          height: size,
          flexBasis: size,
          maskImage: `url(${icon.src})`,
          WebkitMaskImage: `url(${icon.src})`,
        }}
      />
    );
  }
  return (
    <span className="nav-icon nav-icon--emoji" style={{ fontSize: size }} aria-hidden="true">
      {icon.emoji}
    </span>
  );
}
