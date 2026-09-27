/**
 * Чистая геометрия карты - воспроизводит серверные формулы
 * (game/world/grid.py, game/world/location_types.py) на клиенте, чтобы НЕ
 * ходить на сервер при каждом движении/зуме карты. Каталог (города, кольца,
 * типы локаций, озёра, рудники) приходит с сервера ОДИН раз при открытии
 * вкладки (GET /api/miniapp/map/state), дальше всё считается тут.
 *
 * Патч 108: мир - круг радиуса world_radius вокруг Монолита, регионы - секторы
 * по сторонам света. Карта - картинка (assets/world-map-3072.webp), клетки
 * на неё накладываются по радиальной калибровке (см. ниже).
 */

// Портирован из game/world/location_types.py::_type_index - тот же 32-битный
// хеш координат, побитово идентичный результат.
export function locationTypeIndex(x, y, count) {
  let h = (x * 374761393 + y * 668265263) >>> 0;
  h = (h ^ (h >>> 13)) >>> 0;
  h = Math.imul(h, 1274126177) >>> 0;
  h = (h ^ (h >>> 16)) >>> 0;
  return h % count;
}

// game/world/location_types.py::region_for - сектор вокруг стороны света,
// клетка на диагонали отходит к северу/югу.
export function regionFor(x, y) {
  if (Math.abs(y) >= Math.abs(x)) return y >= 0 ? 'ridge' : 'scorched';
  return x > 0 ? 'docks' : 'woods';
}

// game/world/grid.py::monolith_distance. Ничьих при округлении не бывает:
// x²+y² целое, а (k+0.5)² - нет, поэтому Math.round совпадает с Python round.
export function monolithDistance(x, y) {
  return Math.round(Math.hypot(x, y));
}

// game/world/grid.py::cells_between - путь маунта в клетках.
export function cellsBetween(x1, y1, x2, y2) {
  return Math.max(Math.abs(x2 - x1), Math.abs(y2 - y1));
}

export function inBounds(catalog, x, y) {
  return monolithDistance(x, y) <= catalog.world_radius;
}

/** catalog.zone_table: [[distMin, distMax, [levelMin, levelMax]], ...] */
export function zoneLevelRange(catalog, dist) {
  for (const [lo, hi, levels] of catalog.zone_table) {
    if (dist >= lo && dist <= hi) return levels;
  }
  return catalog.zone_table[0][2];
}

/** catalog.city_coords: {region: [x, y]} - возвращает region или null. */
export function cityRegionAt(catalog, x, y) {
  for (const [region, [cx, cy]] of Object.entries(catalog.city_coords)) {
    if (cx === x && cy === y) return region;
  }
  return null;
}

export function locationTypeAt(catalog, x, y) {
  const region = regionFor(x, y);
  const types = catalog.location_types[region];
  return types[locationTypeIndex(x, y, types.length)];
}

export const REGION_TITLES = {
  ridge: '🏰 Обетованный Кряж',
  woods: '🌲 Шепчущие Пущи',
  docks: '⚓ Соляные Пристани',
  scorched: '🔥 Выжженный Предел',
};

/** Полная инфо-карточка клетки - координаты, регион, тип, зона, расстояние. */
export function cellInfo(catalog, x, y, playerPos, questTarget, worldBoss) {
  const cityRegion = cityRegionAt(catalog, x, y);
  const dist = monolithDistance(x, y);
  const isMonolith = x === 0 && y === 0;
  const isQuestTarget = Boolean(questTarget && questTarget.x === x && questTarget.y === y);
  return {
    lake: (catalog.lakes || []).find((l) => l.x === x && l.y === y) || null,
    mine: (catalog.mines || []).find((m) => m.x === x && m.y === y) || null,
    boss: worldBoss && worldBoss.x === x && worldBoss.y === y ? worldBoss : null,
    x, y, dist,
    region: regionFor(x, y),
    regionTitle: REGION_TITLES[regionFor(x, y)],
    isCity: cityRegion !== null,
    cityRegion,
    isMonolith,
    isPlayer: Boolean(playerPos && playerPos.x === x && playerPos.y === y),
    isQuestTarget,
    questLabel: isQuestTarget ? questTarget.label : null,
    levelRange: zoneLevelRange(catalog, dist),
    typeName: isMonolith ? 'Багряный Монолит' : locationTypeAt(catalog, x, y).name,
  };
}

// --- Картинка карты: калибровка (tools/map_art_prompt.md) --------------------
//
// Координаты на картинке - доли её ширины (u вправо, v вниз), от 0 до 1.
// Центр Монолита замерен по готовому арту. Радиус - кусочно-линейная функция
// расстояния в клетках: узлы стоят на границах колец (dist+0.5), как они
// нарисованы. Поэтому клетки ложатся на нарисованные кольца, даже если
// художник сделал одно кольцо чуть шире другого.

// Патч 112: рисованная карта картографа (img/карта_мира_чб_картограф_
// поселения). Кольца на ней нарисованы пунктиром - радиусы замерены по
// ним (tools/map_art_prompt.md), поэтому свои линии колец поверх не нужны.
export const MAP_CENTER = { u: 620 / 1254, v: 612 / 1254 };

const WARP = [
  [0, 0],
  [1.5, 0.036],     // кратер у обелиска
  [6.5, 0.1049],    // первый пунктир
  [14.5, 0.2053],   // второй пунктир
  [23.5, 0.3142],   // третий пунктир
  [30, 0.4374],     // внешний круг - города стоят на нём
  [30.5, 0.445],    // край мира
];

/** Рисовать ли свои линии колец: на рисованной карте они уже есть. */
export const DRAW_RINGS = false;

function interpolate(table, value, from, to) {
  if (value <= table[0][from]) return table[0][to];
  for (let i = 1; i < table.length; i++) {
    const a = table[i - 1];
    const b = table[i];
    if (value <= b[from]) {
      const t = (value - a[from]) / (b[from] - a[from]);
      return a[to] + t * (b[to] - a[to]);
    }
  }
  const a = table[table.length - 2];
  const b = table[table.length - 1];
  return b[to] + (value - b[from]) * ((b[to] - a[to]) / (b[from] - a[from]));
}

/** Радиус на картинке (доля ширины) для расстояния в клетках. */
export function warpRadius(dist) {
  return interpolate(WARP, dist, 0, 1);
}

function unwarpRadius(radius) {
  return interpolate(WARP, radius, 1, 0);
}

/** Размер клетки на картинке у этого расстояния (доля ширины). */
export function cellSizeAt(dist) {
  return warpRadius(dist + 0.5) - warpRadius(Math.max(dist - 0.5, 0));
}

/** Клетка -> точка на картинке (u, v). +y - север, т.е. вверх. */
export function cellToMap(x, y) {
  const r = Math.hypot(x, y);
  if (r === 0) return { u: MAP_CENTER.u, v: MAP_CENTER.v };
  const radius = warpRadius(r);
  return { u: MAP_CENTER.u + (radius * x) / r, v: MAP_CENTER.v - (radius * y) / r };
}

/** Точка на картинке -> ближайшая клетка мира (или null за краем). */
export function mapToCell(catalog, u, v) {
  const du = u - MAP_CENTER.u;
  const dv = MAP_CENTER.v - v;
  const radius = Math.hypot(du, dv);
  const r = unwarpRadius(radius);
  const scale = radius === 0 ? 0 : r / radius;
  const gx = Math.round(du * scale);
  const gy = Math.round(dv * scale);
  // Округление по осям в искривлённом пространстве может промахнуться на
  // клетку - выбираем среди соседей ту, чей центр ближе к точке нажатия.
  let best = null;
  for (let x = gx - 1; x <= gx + 1; x++) {
    for (let y = gy - 1; y <= gy + 1; y++) {
      if (!inBounds(catalog, x, y)) continue;
      const p = cellToMap(x, y);
      const d = Math.hypot(p.u - u, p.v - v);
      if (!best || d < best.d) best = { x, y, d };
    }
  }
  if (!best || best.d > cellSizeAt(monolithDistance(best.x, best.y)) * 1.2) return null;
  return { x: best.x, y: best.y };
}

/** Границы колец на картинке (доли ширины) - для обводки поверх арта. */
export function ringBorders(catalog) {
  return catalog.zone_table.map(([, hi]) => warpRadius(hi + 0.5));
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
