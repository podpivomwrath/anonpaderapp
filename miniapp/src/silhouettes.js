/**
 * Силуэты героя (2026-10-22) - готовит `python tools/silhouette_assets.py`.
 * Ключ - подкласс или базовый класс и пол: blood_knight_f, warrior_m.
 * Сюда попадают только адреса: браузер грузит одну картинку, ту, что видна.
 */
const FILES = import.meta.glob('./assets/silhouettes/*.webp', { eager: true, query: '?url', import: 'default' });

const BY_KEY = Object.fromEntries(
  Object.entries(FILES).map(([path, url]) => [path.split('/').pop().replace('.webp', ''), url]),
);

export function silhouetteUrl(subclass, baseClass, gender) {
  const g = gender === 'f' ? 'f' : 'm';
  return BY_KEY[`${subclass}_${g}`] || BY_KEY[`${baseClass}_${g}`] || BY_KEY[`warrior_${g}`];
}
