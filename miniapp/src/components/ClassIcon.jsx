import ItemIcon from './ItemIcon.jsx';
import { itemIcon } from '../itemIcons.js';

/**
 * Значок класса (патч 91), при желании — в рамке венца топ-1.
 *
 * Подкласс есть не у всех: до тридцатого уровня его нет вовсе, и на сервере
 * он сейчас у семи персонажей из восемнадцати. Поэтому показывается эмблема
 * подкласса, а если его нет — значок базового класса. Пустая строка в топе
 * выглядела бы поломкой, а не отсутствием выбора.
 *
 * Рамка накладывается ПОВЕРХ, а не заменяет значок: у рамок прозрачная
 * середина, и класс под ней остаётся виден. Пока рамка не нарисована,
 * itemIcon вернёт undefined, и венца просто не будет — ничего не сломается.
 */
export default function ClassIcon({ subclass, baseClass, crown = null, size = 36 }) {
  const icon = subclass ? `subclass:${subclass}` : baseClass ? `class:${baseClass}` : null;
  if (!icon) return null;

  const frame = crown ? itemIcon(`crown:${crown}`) : null;
  const emblem = <ItemIcon icon={icon} alt={subclass || baseClass || ''} size={size} />;
  if (!frame) return emblem;

  return (
    <span className="class-icon" style={{ width: size, height: size }}>
      {emblem}
      <img className="class-icon__frame" src={frame} alt="" aria-hidden="true" />
    </span>
  );
}
