/**
 * Чистые геометрические вычисления карты (патч 29) — воспроизводят
 * серверные формулы (game/world/grid.py, game/world/location_types.py) на
 * клиенте, чтобы НЕ ходить на сервер при каждом движении/зуме карты.
 * Каталог (города/зоны/типы локаций) приходит с сервера ОДИН раз при
 * открытии вкладки (GET /api/miniapp/map/state) — дальше всё считается тут.
 */

// Портирован из game/world/location_types.py::_type_index — тот же 32-битный
// хеш координат, побитово идентичный результат для любых x,y в -50..50
// (проверено на живых значениях из Python при разработке патча).
export function locationTypeIndex(x, y, count) {
  let h = (x * 374761393 + y * 668265263) >>> 0;
  h = (h ^ (h >>> 13)) >>> 0;
  h = Math.imul(h, 1274126177) >>> 0;
  h = (h ^ (h >>> 16)) >>> 0;
  return h % count;
}

// game/world/location_types.py::region_for
export function regionFor(x, y) {
  if (x >= 0 && y >= 0) return 'ridge';
  if (x < 0 && y >= 0) return 'woods';
  if (x >= 0 && y < 0) return 'docks';
  return 'scorched';
}

// game/world/grid.py::chebyshev_distance
export function chebyshevDistance(x, y) {
  return Math.max(Math.abs(x), Math.abs(y));
}

/** catalog.zone_table: [[distMin, distMax, [levelMin, levelMax]], ...] */
export function zoneLevelRange(catalog, dist) {
  for (const [lo, hi, levels] of catalog.zone_table) {
    if (dist >= lo && dist <= hi) return levels;
  }
  return catalog.zone_table[catalog.zone_table.length - 1][2];
}

/** catalog.city_coords: {region: [x, y]} — возвращает region или null. */
export function cityRegionAt(catalog, x, y) {
  for (const [region, [cx, cy]] of Object.entries(catalog.city_coords)) {
    if (cx === x && cy === y) return region;
  }
  return null;
}

export function locationTypeAt(catalog, x, y) {
  const region = regionFor(x, y);
  const types = catalog.location_types[region];
  const idx = locationTypeIndex(x, y, types.length);
  return types[idx];
}

const REGION_TITLES = {
  ridge: '🏰 Обетованный Кряж',
  woods: '🌲 Шепчущие Пущи',
  docks: '⚓ Соляные Пристани',
  scorched: '🔥 Выжженный Предел',
};

/** Полная инфо-карточка клетки — координаты, регион, тип, зона, расстояние. */
export function cellInfo(catalog, x, y, playerPos, questTarget) {
  const cityRegion = cityRegionAt(catalog, x, y);
  const dist = chebyshevDistance(x, y);
  const levels = zoneLevelRange(catalog, dist);
  const isMonolith = x === 0 && y === 0;
  const isPlayer = playerPos && playerPos.x === x && playerPos.y === y;
  const isQuestTarget = questTarget && questTarget.x === x && questTarget.y === y;

  return {
    x, y, dist,
    region: regionFor(x, y),
    regionTitle: REGION_TITLES[regionFor(x, y)],
    isCity: cityRegion !== null,
    cityRegion,
    isMonolith,
    isPlayer,
    isQuestTarget,
    questLabel: isQuestTarget ? questTarget.label : null,
    levelRange: levels,
    typeName: isMonolith ? 'Багряный Монолит' : locationTypeAt(catalog, x, y).name,
  };
}

// --- Цвет клетки: градиент заражения (dist) + слабый региональный оттенок ---

// Патч 29, §5: пять ступеней от края (холодный пепел) к центру (тёмно-багровый).
const INFECTION_STOPS = [
  { maxDist: 50, color: [58, 56, 54] },   // 40-50: холодный серо-пепельный
  { maxDist: 39, color: [72, 52, 46] },   // 25-39: пепельный с тёплой примесью
  { maxDist: 24, color: [92, 40, 38] },   // 12-24: тускло-багровый
  { maxDist: 11, color: [126, 30, 34] },  // 3-11: насыщенный багровый
  { maxDist: 2, color: [74, 10, 16] },    // 0-2: тёмно-багровый, почти чёрный
];

// Едва заметный оттенок по четверти карты (10-15% интенсивности).
const REGION_TINTS = {
  ridge: [40, 70, 120],      // холодный каменно-синий
  woods: [40, 110, 60],      // болезненно-зелёный
  docks: [200, 190, 160],    // белёсо-соляной
  scorched: [10, 10, 10],    // угольно-чёрный
};

function mix(base, tint, amount) {
  return base.map((c, i) => Math.round(c * (1 - amount) + tint[i] * amount));
}

export function cellColor(x, y, dist) {
  const stop = INFECTION_STOPS.find((s) => dist <= s.maxDist) || INFECTION_STOPS[0];
  const tinted = mix(stop.color, REGION_TINTS[regionFor(x, y)], 0.12);
  return `rgb(${tinted[0]}, ${tinted[1]}, ${tinted[2]})`;
}

// --- Проекция мир <-> экран (камера — центр видимой области в игровых
// координатах; +y вверх/север, как на обычной карте). ---

export function worldToScreen(camera, cellPx, viewport, gx, gy) {
  return {
    x: (gx - camera.cx) * cellPx + viewport.width / 2,
    y: (camera.cy - gy) * cellPx + viewport.height / 2,
  };
}

export function screenToWorld(camera, cellPx, viewport, sx, sy) {
  return {
    x: camera.cx + (sx - viewport.width / 2) / cellPx,
    y: camera.cy - (sy - viewport.height / 2) / cellPx,
  };
}

export function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
