import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Div, Spinner, Placeholder, Button, IconButton } from '@vkontakte/vkui';
import { getMapRoute, getMapState, saveUi, sendMountFromMap, stopTravel } from '../api.js';
import mapBase from '../assets/world-map-drawn-2048.webp';
import { Sheet } from './ui.jsx';
import {
  DRAW_RINGS, MAP_CENTER, REGION_TITLES, cellInfo, cellSizeAt, cellToMap, cellsBetween, clamp, mapToCell,
  monolithDistance, ringBorders,
} from '../mapCatalog.js';

/**
 * Карта мира (патч 108): нарисованная карта, клетки поверх.
 *
 * Камера - точка картинки в центре окна (cu, cv - доли ширины картинки) и
 * масштаб scale - сколько пикселей экрана занимает вся картинка по ширине.
 * Клетки не рисуются все сразу: сетка проступает только при приближении, а
 * клетку определяет нажатие (mapToCell). Метки - обычные элементы поверх,
 * их размер не зависит от зума.
 *
 * Патч 112: рисованная карта. 2026-10-15: линзу убрали (работала плохо) -
 * карта обычная: перетаскивание, колесо мыши и щипок приближают. Картинка
 * одна (2048): детальную 4096 для линзы тоже убрали, чтобы карта грузилась быстрее.
 */

const DRAG_THRESHOLD_PX = 5;
const MAX_SCALE = 4400;          // щипком на телефоне - клетка до ~60 px
const CELL_K = 0.0143;           // средний размер клетки на картинке (доля ширины)

//: Шаг приближения колесом мыши.
const WHEEL_ZOOM = 1.15;

const ERROR_MESSAGES = {
  dead: 'Сначала очнись.',
  in_pvp: 'Сначала разберись с открытым боем.',
  in_combat: 'В бою не до маунта.',
  busy: 'Сначала закончи то, что начал.',
  mining: 'Ты в забое - сначала закончи или брось добычу.',
  fishing: 'Снасть в воде - сначала дождись поклёвки или отмени заброс.',
  in_event: 'Сначала закончи событие в чате - потом в седло.',
  house_work: 'Идет варка в доме - дождись ее или брось.',
  traveling_on_foot: 'Ты уже в пути пешком.',
  already_on_mount: 'Ты уже в пути на маунте.',
  out_of_bounds: 'Это за краем мира.',
  already_there: 'Ты уже здесь.',
  mount_not_owned: 'Этого маунта у тебя нет.',
  bad_request: 'Что-то пошло не так.',
};

function cellsWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'клетка';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'клетки';
  return 'клеток';
}

function formatSeconds(seconds) {
  if (seconds >= 60) return `~${(seconds / 60).toFixed(1)} мин.`;
  return `~${Math.round(seconds)} сек.`;
}

/**
 * Где значок в пути верхом прямо сейчас. Сервер присылает путь (со стартовой
 * клеткой), номер клетки, на которой персонаж стоит, и сколько секунд до
 * следующего шага - на момент опроса. Между опросами шаги досчитываются
 * здесь же, а внутри шага значок едет к следующей клетке плавно.
 * rest - клетки впереди, для пунктира. null - не верхом.
 */
function ridePos(travel, fetchedAt) {
  if (!travel?.path?.length) return null;
  const { path, step_seconds: step } = travel;
  let idx = Math.min(travel.cell_index, path.length - 1);
  let progress = 0;
  if (!travel.paused && travel.next_cell_in != null && step > 0) {
    let left = travel.next_cell_in - (performance.now() - fetchedAt) / 1000;
    while (left < 0 && idx < path.length - 1) {
      idx += 1;
      left += step;
    }
    if (idx < path.length - 1) progress = 1 - Math.min(Math.max(left / step, 0), 1);
  }
  const [x0, y0] = path[idx];
  const [x1, y1] = path[Math.min(idx + 1, path.length - 1)];
  return {
    pos: { x: x0 + (x1 - x0) * progress, y: y0 + (y1 - y0) * progress },
    rest: path.slice(idx + 1),
  };
}

// Упрощённая карта (2026-10-12) - по кнопке, для слабых телефонов. По
// умолчанию карта прежняя. Выбор хранится на устройстве, а не на сервере:
// тормозит конкретный телефон, на ПК тот же игрок хочет полную карту.
//  - сетка на отдалении нарисована один раз в картинку (GRID_RASTER) и едет
//    вместе с картой; векторная - только при приближении, где её мало;
//  - во время жеста сдвигается один слой (transform), без перерисовки
//    раздела; новое положение применяется, когда палец отпущен;
//  - метки пульсируют прозрачностью, без свечения, и без теней у клетки.
const SIMPLE_KEY = 'map-simple';
const GRID_RASTER = 2048;
const GRID_VECTOR_FROM = 1600; // масштаб, с которого сетка снова векторная

function readSimple() {
  try { return localStorage.getItem(SIMPLE_KEY) === '1'; } catch { return false; }
}

// Безопасный путь верхом (2026-10-13): переключатель при отправке маунта.
// Хранится на сервере (настройка персонажа) - отправка из чата тоже идёт
// безопасным путём, если он включён. Путь в обход колец опаснее цели - дольше.

// focus - клетка, которую показать при открытии (цель задания из «Заданий»).
// Легенда значков карты (2026-10-22): открывается кнопкой «?» у карты.
const LEGEND = [
  ['🟡', 'Ты'],
  ['🏛', 'Город'],
  ['⛏', 'Рудник (бледный - жила пуста)'],
  ['🎣', 'Озеро'],
  ['📜', 'Цель сюжетного задания'],
  ['💀', 'Мировой босс'],
  ['🌀', 'Разлом (🩸 - кровавый)'],
  ['🏰', 'База гильдии (🏯 цитадель, 🚩 закладка знамени)'],
  ['🫏', 'Турбоишак'],
  ['🎯', 'Цель заказа на убийство'],
  ['🐂', 'Твоя повозка в пути'],
  ['🏃', 'Курьер'],
  ['⚑', 'Куда едешь'],
];

function MapLegend({ onClose }) {
  return (
    <Sheet title="Значки карты" icon="🗺" onClose={onClose}>
      <ul className="map-legend">
        {LEGEND.map(([icon, text]) => (
          <li key={text}><span className="map-legend__icon" aria-hidden="true">{icon}</span>{text}</li>
        ))}
      </ul>
    </Sheet>
  );
}

export default function MapTab({ focus = null }) {
  const containerRef = useRef(null);
  const [size, setSize] = useState({ width: 360, height: 420 });
  const [view, setView] = useState(null); // {cu, cv, scale}
  const [mapState, setMapState] = useState(null);
  const [status, setStatus] = useState('loading');
  const [imageReady, setImageReady] = useState(false);
  const [hovered, setHovered] = useState(null); // {x, y, sx, sy}
  const [selected, setSelected] = useState(null); // {x, y}
  const [sendFlow, setSendFlow] = useState(null); // {step: 'pick'|'confirm', mount}
  const [safeRouteLocal, setSafeRoute] = useState(null);  // null - как на сервере
  const [routePreview, setRoutePreview] = useState(null); // {key, cells, path, mounts}
  const safeRoute = safeRouteLocal ?? Boolean(mapState?.safe_route);
  const toggleSafeRoute = () => {
    const next = !safeRoute;
    setSafeRoute(next);
    saveUi({ set: { safe_route: next } }).catch(() => { /* не сохранилось - выбор остаётся до перезагрузки */ });
  };
  const [banner, setBanner] = useState(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const [stopping, setStopping] = useState(false);

  const pointers = useRef(new Map());
  const dragRef = useRef(null);
  const pinchRef = useRef(null);
  const isTouchRef = useRef(false);

  const [simple, setSimple] = useState(readSimple);
  const toggleSimple = () => {
    setSimple((on) => {
      try { localStorage.setItem(SIMPLE_KEY, on ? '0' : '1'); } catch { /* приватный режим */ }
      return !on;
    });
  };
  // Класс на корне страницы: упрощённый режим снимает и размытие шапки над
  // картой. Ушёл с вкладки карты - шапка снова как была.
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('map-simple-on', simple);
    return () => root.classList.remove('map-simple-on');
  }, [simple]);
  const stageRef = useRef(null);
  const gridCanvasRef = useRef(null);
  // Положение камеры посреди жеста в упрощённом режиме - ещё не в state.
  const liveRef = useRef(null);

  const load = useCallback(() => {
    getMapState()
      .then((data) => {
        // Момент получения - от него карта сама ведёт значок по пути до
        // следующего опроса (см. ridePos ниже).
        // Каталог в каждом опросе тот же, но новым объектом - и сетка (23
        // тысячи точек) пересчитывалась раз в 5 секунд. Не изменился - тот же.
        setMapState((prev) => ({
          ...data,
          catalog: prev && JSON.stringify(prev.catalog) === JSON.stringify(data.catalog)
            ? prev.catalog : data.catalog,
          fetchedAt: performance.now(),
        }));
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Живой опрос позиции/пути/босса - не каталога.
  useEffect(() => {
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  // Пока едешь верхом, значок ползёт между клетками плавно: раз в 200 мс
  // перерисовка, позиция считается от последнего опроса (ridePos).
  const riding = Boolean(mapState?.mount_travel && !mapState.mount_travel.paused)
    || Boolean(mapState?.turbo?.running)
    || Boolean(mapState?.hunts?.some((h) => h.travel && !h.travel.paused));
  const [, setFrame] = useState(0);
  useEffect(() => {
    if (!riding) return undefined;
    const id = setInterval(() => setFrame((n) => n + 1), 200);
    return () => clearInterval(id);
  }, [riding]);

  // Контейнер появляется только в ветке ready - поэтому эффекты завязаны на
  // status (иначе мерили бы null и навсегда остались бы с размером по умолчанию).
  // Карта занимает всю страницу под шапкой: высоту считаем от верха окна
  // карты до низа экрана. В CSS это не выразить надёжно - высота шапки
  // разная в вебвью ВК на разных платформах.
  const [fillHeight, setFillHeight] = useState(null);
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const fit = () => {
      const top = el.getBoundingClientRect().top + window.scrollY;
      setFillHeight(Math.max(320, Math.round(window.innerHeight - top)));
    };
    fit();
    window.addEventListener('resize', fit);
    return () => window.removeEventListener('resize', fit);
  }, [status]);

  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) setSize({ width: rect.width, height: rect.height });
  }, [status, fillHeight]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [status]);

  // Пергамент тёмной карты нарисован до самых краёв, поэтому картинка
  // накрывает всё окно целиком (cover): на широком экране обрезаются верх и
  // низ пергамента, пустых полос по бокам нет.
  const minScale = Math.max(size.width, size.height);
  const clampScale = useCallback((s) => clamp(s, minScale, MAX_SCALE), [minScale]);
  // Камеру не уводим за край картинки: окно всегда целиком на карте.
  const clampView = useCallback((v) => {
    const halfU = Math.min(0.5, size.width / 2 / v.scale);
    const halfV = Math.min(0.5, size.height / 2 / v.scale);
    return {
      scale: v.scale,
      cu: clamp(v.cu, halfU, 1 - halfU),
      cv: clamp(v.cv, halfV, 1 - halfV),
    };
  }, [size]);

  // Стартовая камера - вся карта целиком: рассматривают её линзой. Пока её
  // не приблизили щипком, она следует за размером окна (сначала размер ещё
  // не измерен, потом меняется при повороте телефона).
  // Только при загрузке и смене размера окна - НЕ на каждом опросе раз в
  // 5 секунд: раньше сдвинутая карта через пару секунд прыгала в центр.
  const fittedRef = useRef(true);
  const focusedRef = useRef(false);
  const hasState = Boolean(mapState);
  useEffect(() => {
    if (!hasState) return;
    if (focus && !focusedRef.current) {
      // Цель задания: приблизить к клетке и открыть её карточку.
      focusedRef.current = true;
      fittedRef.current = false;
      const p = cellToMap(focus.x, focus.y);
      setView(clampView({ cu: p.u, cv: p.v, scale: clampScale(minScale * 3) }));
      setSelected({ x: focus.x, y: focus.y });
      return;
    }
    if (!view || fittedRef.current) {
      setView(clampView({ cu: MAP_CENTER.u, cv: MAP_CENTER.v, scale: minScale }));
    }
  }, [hasState, minScale, clampView]); // eslint-disable-line react-hooks/exhaustive-deps

  // Окно выросло (на телефоне высота дорисовывается не сразу), а карту уже
  // трогали - подгонка выше не сработает. Масштаб всё равно не меньше
  // «закрыть всё окно»: иначе снизу оставалась чёрная полоса.
  useEffect(() => {
    if (view && view.scale < minScale) setView(clampView({ ...view, scale: minScale }));
  }, [minScale, clampView]); // eslint-disable-line react-hooks/exhaustive-deps

  const catalog = mapState?.catalog;
  const ride = mapState ? ridePos(mapState.mount_travel, mapState.fetchedAt) : null;
  // Турбоишак на бегу - значок едет по клеткам, как маунт, но без линии пути.
  const turboRun = mapState?.turbo?.running ? ridePos(mapState.turbo, mapState.fetchedAt) : null;
  const turboPos = mapState?.turbo ? (turboRun ? turboRun.pos : mapState.turbo) : null;
  // Клетка, где персонаж стоит (по ней считаются расстояния и подсказки), и
  // где рисуется значок: верхом он едет между клетками плавно.
  const playerPos = mapState ? { x: mapState.pos_x, y: mapState.pos_y } : null;
  const playerPin = ride ? ride.pos : playerPos;
  const questTarget = mapState?.quest_target ?? null;
  const worldBoss = mapState?.world_boss ?? null;
  // Гильдии: владения и закладки знамён.
  const guildCells = mapState?.guild_cells ?? [];
  // Города (2026-10-13): на рисованной карте их клетки было не найти -
  // подсветка клетки и значок.
  const cityCells = Object.entries(catalog?.city_coords || {}).map(([region, [x, y]]) => ({ region, x, y, title: REGION_TITLES[region] }));

  const toScreen = useCallback((u, v) => ({
    x: (u - view.cu) * view.scale + size.width / 2,
    y: (v - view.cv) * view.scale + size.height / 2,
  }), [view, size]);

  const toMap = useCallback((sx, sy) => ({
    u: view.cu + (sx - size.width / 2) / view.scale,
    v: view.cv + (sy - size.height / 2) / view.scale,
  }), [view, size]);

  const cellScreen = useCallback((x, y) => {
    const p = cellToMap(x, y);
    return toScreen(p.u, p.v);
  }, [toScreen]);

  const cellPx = view ? CELL_K * view.scale : 10;

  // Патч 112: сетка клеток - всегда. Клетки на картинке искривлены
  // калибровкой колец, поэтому границы клеток - не прямые, а кривые: каждая
  // линия x = k + 0.5 (и y = k + 0.5) проходит через ту же калибровку, что и
  // нажатие, и сетка точно совпадает с клетками, куда попадает клик.
  // Считается один раз в долях картинки; на экран - при смене вида.
  const gridLines = useMemo(() => {
    if (!catalog) return [];
    const r = catalog.world_radius + 0.5;
    const lines = [];
    const trace = (fixed, vertical) => {
      let run = [];
      for (let t = -r; t <= r + 1e-9; t += 0.25) {
        const [x, y] = vertical ? [fixed, t] : [t, fixed];
        if (Math.hypot(x, y) <= r) {
          const p = cellToMap(x, y);
          run.push([p.u, p.v]);
        } else if (run.length) {
          lines.push(run);
          run = [];
        }
      }
      if (run.length > 1) lines.push(run);
    };
    for (let k = -catalog.world_radius - 1; k <= catalog.world_radius; k++) {
      trace(k + 0.5, true);
      trace(k + 0.5, false);
    }
    return lines;
  }, [catalog]);

  const rasterGrid = Boolean(simple && view && view.scale < GRID_VECTOR_FROM);
  const gridPath = useMemo(() => {
    if (!view || rasterGrid) return '';
    return gridLines.map((line) => line.map(([u, v], i) => {
      const sx = (u - view.cu) * view.scale + size.width / 2;
      const sy = (v - view.cv) * view.scale + size.height / 2;
      return `${i ? 'L' : 'M'}${sx.toFixed(1)} ${sy.toFixed(1)}`;
    }).join('')).join('');
  }, [gridLines, view, size, rasterGrid]);

  // Сетка-картинка для упрощённой карты: рисуется один раз на каталог.
  const hasView = Boolean(view);
  useEffect(() => {
    const canvas = gridCanvasRef.current;
    if (!simple || !canvas || !gridLines.length) return;
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, GRID_RASTER, GRID_RASTER);
    ctx.strokeStyle = 'rgba(40, 28, 18, 0.3)';
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    for (const line of gridLines) {
      line.forEach(([u, v], i) => {
        if (i) ctx.lineTo(u * GRID_RASTER, v * GRID_RASTER);
        else ctx.moveTo(u * GRID_RASTER, v * GRID_RASTER);
      });
    }
    ctx.stroke();
  }, [simple, gridLines, hasView, status]);

  // Новое положение камеры уже в state - временный сдвиг слоя больше не нужен.
  // До отрисовки, иначе на кадр карта встала бы в двойной сдвиг.
  useLayoutEffect(() => {
    if (stageRef.current) stageRef.current.style.transform = '';
  }, [view]);

  /** Упрощённая карта посреди жеста: сдвинуть и масштабировать слой целиком
   *  от зафиксированной камеры view к next, ничего не перерисовывая. */
  const showLive = (next) => {
    liveRef.current = next;
    const el = stageRef.current;
    if (!el || !view) return;
    const k = next.scale / view.scale;
    const tx = (view.cu - next.cu) * next.scale;
    const ty = (view.cv - next.cv) * next.scale;
    el.style.transformOrigin = `${size.width / 2}px ${size.height / 2}px`;
    el.style.transform = `translate(${tx}px, ${ty}px) scale(${k})`;
  };
  const moveCamera = (next) => (simple ? showLive(next) : setView(next));
  const cameraNow = () => liveRef.current || view;
  const commitLive = () => {
    if (!liveRef.current) return;
    const next = liveRef.current;
    liveRef.current = null;
    setView(next);
  };

  const cellAtScreen = (sx, sy) => {
    const m = toMap(sx, sy);
    return mapToCell(catalog, m.u, m.v);
  };

  const recenterOnPlayer = () => {
    if (!mapState || !view) return;
    const p = cellToMap(mapState.pos_x, mapState.pos_y);
    setView(clampView({ ...view, cu: p.u, cv: p.v }));
  };

  /** Зум с неподвижной точкой (sx, sy) - под курсором или между пальцами. */
  const zoomAt = (factor, sx, sy, base = view) => {
    const scale = clampScale(base.scale * factor);
    const anchor = {
      u: base.cu + (sx - size.width / 2) / base.scale,
      v: base.cv + (sy - size.height / 2) / base.scale,
    };
    moveCamera(clampView({
      scale,
      cu: anchor.u - (sx - size.width / 2) / scale,
      cv: anchor.v - (sy - size.height / 2) / scale,
    }));
  };

  // --- Указатели: драг одним пальцем/мышью, щипок двумя ---

  const localPoint = (e) => {
    const rect = containerRef.current.getBoundingClientRect();
    return { x: e.clientX - rect.left, y: e.clientY - rect.top };
  };

  // Кнопки зума и плашки лежат поверх карты - их нажатия не драг и не
  // выбор клетки.
  const isOverlayTarget = (e) => Boolean(e.target.closest?.('.map-controls, .map-travel-banner'));

  const handlePointerDown = (e) => {
    if (isOverlayTarget(e)) return;
    isTouchRef.current = e.pointerType === 'touch';
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* вебвью ВК иногда бросает */ }
    pointers.current.set(e.pointerId, localPoint(e));
    if (pointers.current.size === 1 && view) {
      const p = localPoint(e);
      dragRef.current = { start: cameraNow(), x: p.x, y: p.y, moved: false };
      pinchRef.current = null;
    } else if (pointers.current.size === 2 && view) {
      dragRef.current = null;
      const [a, b] = [...pointers.current.values()];
      pinchRef.current = {
        dist: Math.hypot(a.x - b.x, a.y - b.y) || 1,
        mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
        start: cameraNow(),
      };
    }
  };

  const handlePointerMove = (e) => {
    if (!view) return;
    const p = localPoint(e);
    if (pointers.current.has(e.pointerId)) pointers.current.set(e.pointerId, p);

    if (pointers.current.size === 2 && pinchRef.current) {
      const [a, b] = [...pointers.current.values()];
      const factor = Math.hypot(a.x - b.x, a.y - b.y) / pinchRef.current.dist;
      fittedRef.current = false;
      zoomAt(factor, pinchRef.current.mid.x, pinchRef.current.mid.y, pinchRef.current.start);
      return;
    }

    if (pointers.current.size === 1 && dragRef.current) {
      const dx = p.x - dragRef.current.x;
      const dy = p.y - dragRef.current.y;
      if (Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
        dragRef.current.moved = true;
      }
      if (dragRef.current.moved) {
        // Карту сдвинули руками - больше не подгоняем её под окно сами.
        fittedRef.current = false;
        const start = dragRef.current.start;
        moveCamera(clampView({ ...start, cu: start.cu - dx / start.scale, cv: start.cv - dy / start.scale }));
        if (!simple) setHovered(null);
      }
      return;
    }

    // Наведение мышью без нажатия - лёгкая подсказка.
    if (!isTouchRef.current && pointers.current.size === 0) {
      const cell = cellAtScreen(p.x, p.y);
      setHovered(cell ? { ...cell, sx: p.x, sy: p.y } : null);
    }
  };

  const handlePointerUp = (e) => {
    const tap = pointers.current.size === 1 && dragRef.current && !dragRef.current.moved;
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinchRef.current = null;
    if (tap && view) {
      const p = localPoint(e);
      const cell = cellAtScreen(p.x, p.y);
      setSelected(cell);
      setSendFlow(null);
    }
    if (pointers.current.size === 0) {
      dragRef.current = null;
      commitLive();
    }
  };

  // Колесо: React вешает onWheel пассивным, preventDefault там не работает -
  // слушатель ставим сами, иначе вместе с картой прокручивалась бы страница.
  const wheelRef = useRef(null);
  wheelRef.current = (e) => {
    if (!view) return;
    e.preventDefault();
    const p = localPoint(e);
    fittedRef.current = false;
    zoomAt(e.deltaY < 0 ? WHEEL_ZOOM : 1 / WHEEL_ZOOM, p.x, p.y, cameraNow());
    commitLive();
  };
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const onWheel = (e) => wheelRef.current(e);
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [status]);

  // --- Отправка маунта ---

  const isTraveling = Boolean(mapState?.foot_travel || mapState?.mount_travel);
  const canSendMount = mapState && !mapState.is_dead && !isTraveling && mapState.mounts.length > 0;

  // Путь для окна отправки - с сервера: безопасный обход считает он.
  const routeKey = sendFlow && selected ? `${selected.x}:${selected.y}:${safeRoute ? 1 : 0}` : null;
  useEffect(() => {
    if (!routeKey || !selected) return undefined;
    let alive = true;
    let timer = null;
    // Не пришло - ещё раз через пару секунд (2026-10-20): иначе окно так и
    // показывало бы время прямого пути при включённом безопасном.
    const load = (attempt) => {
      getMapRoute(selected.x, selected.y, safeRoute)
        .then((data) => { if (alive) setRoutePreview({ key: routeKey, ...data }); })
        .catch(() => {
          if (alive && attempt < 3) timer = setTimeout(() => load(attempt + 1), 1500 * attempt);
        });
    };
    load(1);
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [routeKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const preview = routePreview && routePreview.key === routeKey ? routePreview : null;
  // Безопасный путь пока считается - время и риск не показываем, чтобы не
  // выдать время прямого пути за безопасное.
  const routePending = Boolean(routeKey) && !preview;
  const detourNote = safeRoute && preview
    ? (preview.cells > preview.direct_cells ? `обход +${preview.cells - preview.direct_cells} кл.`
      : preview.detour ? 'обход без потери времени' : 'опасных колец по пути нет')
    : null;

  const confirmSend = async () => {
    if (!selected || !sendFlow?.mount) return;
    try {
      await sendMountFromMap(sendFlow.mount.mount_id, selected.x, selected.y, safeRoute);
      setBanner(`🐎 Путь начат${safeRoute ? ' безопасной дорогой' : ''}: (${selected.x}; ${selected.y}).`);
      setSendFlow(null);
      setSelected(null);
      load();
    } catch (err) {
      setBanner(ERROR_MESSAGES[err.message] || 'Не удалось отправить маунта.');
      setSendFlow(null);
    }
  };

  const stop = async () => {
    setStopping(true);
    try {
      await stopTravel();
      setBanner(`⏹ Остановка на (${mapState.pos_x}; ${mapState.pos_y}).`);
    } catch (err) {
      setBanner(err.message || 'Не удалось остановиться.');
    } finally {
      setStopping(false);
      load();
    }
  };

  useEffect(() => {
    if (!banner) return undefined;
    const id = setTimeout(() => setBanner(null), 4000);
    return () => clearTimeout(id);
  }, [banner]);

  if (status === 'loading') {
    return (
      <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
        <Spinner size="l" />
      </Div>
    );
  }
  if (status === 'error' || !mapState) {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🗺️</div>}>Не удалось загрузить карту.</Placeholder>;
  }

  const info = selected ? cellInfo(catalog, selected.x, selected.y, playerPos, questTarget, worldBoss) : null;
  const levels = mapState.levels || { level: 0, fishing: 0, mining: 0 };
  const cellRift = info ? (mapState.rifts || []).find((r) => r.x === info.x && r.y === info.y) || null : null;
  const center = view ? toScreen(MAP_CENTER.u, MAP_CENTER.v) : null;
  // Метки растут с клеткой: на телефоне карта целиком мелкая, и крупные
  // метки закрывали бы рисунок - рассматривать детали там линзой.
  const markerPx = clamp(cellPx * 1.3, 11, 30);
  const travelTarget = mapState.mount_travel || mapState.foot_travel;
  // Пунктир пути: верхом - от значка по оставшимся клеткам (клетки на
  // картинке искривлены кольцами, прямая линия резала бы их); пешком - прямо.
  const routeCells = ride
    ? [[ride.pos.x, ride.pos.y], ...ride.rest]
    : travelTarget && playerPos ? [[playerPos.x, playerPos.y], [travelTarget.to_x, travelTarget.to_y]]
      : preview ? preview.path : [];

  const pins = [
    ...cityCells.map((c) => [c.x, c.y, 'map-pin--city', '🏛', `${c.title} · город`, 1.15]),
    ...(catalog.lakes || []).map((l) => [l.x, l.y, 'map-pin--lake', '🎣', l.name, 0.8]),
    ...(catalog.mines || []).map((m) => [
      m.x, m.y, `map-pin--mine${(mapState.mine_ore?.[m.id] || 0) > 0 ? '' : ' map-pin--empty'}`,
      '⛏', `${m.name}: руды ${mapState.mine_ore?.[m.id] || 0}`, 0.8,
    ]),
    ...(questTarget ? [[questTarget.x, questTarget.y, 'map-pin--quest', '📜', questTarget.label, 1]] : []),
    ...(worldBoss ? [[worldBoss.x, worldBoss.y, 'map-pin--boss', '💀', worldBoss.name, 1.3]] : []),
    // Турбоишак дня (2026-10-19): бегает по всей карте, поймать - зайти на клетку.
    ...(turboPos ? [[turboPos.x, turboPos.y, 'map-pin--turbo', '🫏',
      mapState.turbo.running ? 'Турбоишак на бегу' : 'Турбоишак стоит - поймай, пока не убежал', 1.25]] : []),
    ...(mapState.trail
      ? [[mapState.trail.x, mapState.trail.y, 'map-pin--trail', mapState.trail.emoji, mapState.trail.title, 1.1]]
      : []),
    ...guildCells.map((g) => [
      g.x, g.y, g.own ? 'map-pin--guild map-pin--guild-own' : 'map-pin--guild',
      g.status === 'claiming' ? '🚩' : (g.base_tier === 'citadel' ? '🏯' : '🏰'),
      `[${g.tag}] ${g.status === 'claiming' ? 'закладка знамени' : 'земля гильдии'}`, 0.8,
    ]),
    // Цели взятых заказов (2026-10-16): видны, пока вне городов.
    // Цель верхом едет плавно, как свой значок (2026-10-30): между опросами
    // её ведёт ridePos по клетке, где она сейчас, и следующей.
    ...(mapState.hunts || []).map((h) => {
      const live = ridePos(h.travel, mapState.fetchedAt)?.pos || h;
      return [live.x, live.y, 'map-pin--hunt', '🎯', `Цель заказа: ${h.name}, ${h.level} ур.`, 1.1];
    }),
    // Повозки торговой фирмы в пути - там, где они сейчас (стоящие ждут в городах).
    ...(mapState.carts || []).filter((c) => c.traveling)
      .map((c) => [c.x, c.y, 'map-pin--cart', '🐂', `Твоя повозка №${c.num} в пути`, 0.9]),
    ...(mapState.rifts || []).map((r) => [
      r.x, r.y,
      r.blood ? 'map-pin--rift map-pin--rift-blood' : `map-pin--rift${r.state !== 'free' ? ' map-pin--rift-busy' : ''}`,
      r.blood ? '🩸' : '🌀',
      `${r.blood ? 'Кровавый разлом: ' : ''}${r.name} · ${r.min_level}-${r.max_level} ур.`, 1.2,
    ]),
    ...(travelTarget ? [[travelTarget.to_x, travelTarget.to_y, 'map-pin--route', '⚑', 'Цель пути', 1]] : []),
    ...(playerPin ? [[playerPin.x, playerPin.y, 'map-pin--player', '', 'Ты здесь', 1.1]] : []),
  ];

  /** Метка в точке (sx, sy); size - её размер в пикселях. */
  // Ключ метки должен быть уникальным: две повозки одной фирмы, отправленные
  // друг за другом, стоят на одной клетке, и с ключом «класс:x:y» React
  // путал их и оставлял на карте старые метки шлейфом (репорт 2026-10-21).
  // Совпавшему ключу - порядковый номер.
  const seenKeys = new Map();
  const pinKey = (className, x, y) => {
    if (className === 'map-pin--player') return className;
    const base = `${className}:${x}:${y}`;
    const n = seenKeys.get(base) || 0;
    seenKeys.set(base, n + 1);
    return n ? `${base}#${n}` : base;
  };

  const pinAt = ([x, y, className, content, title], sx, sy, px) => (
    <div
      key={pinKey(className, x, y)}
      className={`map-pin ${className}`}
      style={{ left: sx - px / 2, top: sy - px / 2, width: px, height: px, fontSize: px * 0.62 }}
      title={title}
    >
      {content}
    </div>
  );

  return (
    <div className="map-tab">
      <div
        ref={containerRef}
        className={`map-viewport${simple ? ' map-viewport--simple' : ''}`}
        style={fillHeight ? { height: fillHeight } : undefined}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={() => setHovered(null)}
      >
        {view && (
          <div className="map-stage" ref={stageRef}>
            <img
              className="map-image"
              src={mapBase}
              alt=""
              draggable={false}
              onLoad={() => setImageReady(true)}
              style={{
                width: view.scale,
                height: view.scale,
                transform: `translate(${size.width / 2 - view.cu * view.scale}px, ${size.height / 2 - view.cv * view.scale}px)`,
              }}
            />
            {simple && (
              <canvas
                ref={gridCanvasRef}
                className="map-image map-grid-raster"
                width={GRID_RASTER}
                height={GRID_RASTER}
                style={{
                  width: view.scale,
                  height: view.scale,
                  visibility: rasterGrid ? 'visible' : 'hidden',
                  transform: `translate(${size.width / 2 - view.cu * view.scale}px, ${size.height / 2 - view.cv * view.scale}px)`,
                }}
              />
            )}

            <svg className="map-overlay" width={size.width} height={size.height}>
              {DRAW_RINGS && ringBorders(catalog).map((r, i) => (
                <circle
                  key={r}
                  cx={center.x} cy={center.y} r={r * view.scale}
                  className={i === 0 ? 'map-ring map-ring--rim' : 'map-ring'}
                />
              ))}
              <path className="map-grid" d={gridPath} />
              {cityCells.map((c) => {
                const s = cellScreen(c.x, c.y);
                const px = Math.max(cellSizeAt(monolithDistance(c.x, c.y)) * view.scale, 10);
                return <rect key={`c:${c.region}`} className="map-city-cell" x={s.x - px / 2} y={s.y - px / 2} width={px} height={px} rx={3} />;
              })}
              {guildCells.map((g) => {
                const s = cellScreen(g.x, g.y);
                const px = Math.max(cellSizeAt(monolithDistance(g.x, g.y)) * view.scale, 8);
                const cls = `map-guild-cell${g.own ? ' map-guild-cell--own' : ''}${g.status === 'claiming' ? ' map-guild-cell--claiming' : ''}`;
                return <rect key={`g:${g.x}:${g.y}`} className={cls} x={s.x - px / 2} y={s.y - px / 2} width={px} height={px} rx={3} />;
              })}
              {routeCells.length > 1 && (
                <polyline
                  className="map-route"
                  points={routeCells.map(([x, y]) => { const p = cellScreen(x, y); return `${p.x},${p.y}`; }).join(' ')}
                />
              )}
              {[[hovered, 'map-cell-hover'], [selected, 'map-cell-selected']].filter(([c]) => c).map(([c, cls]) => {
                const s = cellScreen(c.x, c.y);
                const px = Math.max(cellSizeAt(monolithDistance(c.x, c.y)) * view.scale, 10);
                return <rect key={cls} className={cls} x={s.x - px / 2} y={s.y - px / 2} width={px} height={px} rx={4} />;
              })}
            </svg>

            <div className="map-pins">
              {pins.map((pin) => {
                const sc = cellScreen(pin[0], pin[1]);
                return pinAt(pin, sc.x, sc.y, markerPx * pin[5]);
              })}
            </div>
          </div>
        )}

        {!imageReady && (
          <div className="map-loading"><Spinner size="m" /></div>
        )}

        {hovered && (
          <div
            className="map-tooltip"
            style={{
              left: clamp(hovered.sx + 14, 0, size.width - 190),
              top: clamp(hovered.sy + 14, 0, size.height - 100),
            }}
          >
            <MapTooltipContent
              info={cellInfo(catalog, hovered.x, hovered.y, playerPos, questTarget, worldBoss)}
              mineOre={mapState.mine_ore}
              rift={(mapState.rifts || []).find((r) => r.x === hovered.x && r.y === hovered.y)}
            />
          </div>
        )}

        <div className="map-controls">
          <IconButton className="map-controls__btn" onClick={recenterOnPlayer} aria-label="К себе">◎</IconButton>
          <IconButton className="map-controls__btn" onClick={() => setLegendOpen(true)} aria-label="Значки карты">?</IconButton>
          <button
            type="button"
            className={`map-simple-toggle${simple ? ' map-simple-toggle--on' : ''}`}
            onClick={toggleSimple}
            aria-pressed={simple}
            title="Облегчённая отрисовка для слабых телефонов"
          >
            {simple ? '✓ Упрощённая карта' : 'Упрощённая карта'}
          </button>
        </div>

        {isTraveling && (
          <div className="map-travel-banner">
            {mapState.mount_travel ? (
              <>
                <span>
                  🐎 Сейчас ({mapState.pos_x}; {mapState.pos_y})
                  {' → '}({mapState.mount_travel.to_x}; {mapState.mount_travel.to_y})
                </span>
                {/* Сойти с пути на текущей клетке - как кнопка в чате. */}
                <button className="map-travel-banner__stop" disabled={stopping} onClick={stop}>
                  ⏹ Остановиться
                </button>
              </>
            ) : (
              `🚶 В пути к (${mapState.foot_travel.to_x}; ${mapState.foot_travel.to_y})`
            )}
          </div>
        )}
        {worldBoss && !isTraveling && (
          <div className="map-travel-banner map-travel-banner--boss">
            💀 {worldBoss.name} · ({worldBoss.x}; {worldBoss.y}) · {worldBoss.hp_percent}%
          </div>
        )}
      </div>

      {banner && <div className="map-toast">{banner}</div>}
      {legendOpen && <MapLegend onClose={() => setLegendOpen(false)} />}

      {info && (
        <div className="map-card">
          <button className="map-card__close" onClick={() => { setSelected(null); setSendFlow(null); }} aria-label="Закрыть">✕</button>
          <p className="map-card__coords">({info.x}; {info.y})</p>
          <p className="map-card__line">{info.isMonolith ? '🩸 Багряный Монолит' : info.regionTitle}</p>
          {!info.isMonolith && !info.isCity && <p className="map-card__line">{info.typeName}</p>}
          <p className="map-card__line">Уровень мобов: {info.levelRange[0]}-{info.levelRange[1]} (кольцо {info.ringRange[0]}-{info.ringRange[1]})</p>
          {info.peaceful && <p className="map-card__line">🕊 Мирная зона у города: игроки здесь не нападают</p>}
          <p className="map-card__line">До Монолита: {info.dist} {cellsWord(info.dist)}</p>
          {info.lake && (
            <p className="map-card__line">
              🎣 {info.lake.name} · тир {info.lake.tier} · рыбалка с {info.lake.need} ур.
              {levelNote(levels.fishing, info.lake.need)}{info.lake.safe ? ' · без PvP' : ''}
            </p>
          )}
          {info.mine && (
            <p className="map-card__line">
              ⛏ {info.mine.name} · тир {info.mine.tier} · горное дело с {info.mine.need} ур.
              {levelNote(levels.mining, info.mine.need)} · руды {mapState.mine_ore?.[info.mine.id] || 0}
              {info.mine.safe ? ' · без PvP' : ''}
            </p>
          )}
          {cellRift && (
            <>
              <p className="map-card__line">
                {cellRift.blood ? '🩸 Кровавый разлом' : '🌀 Разлом'}: {cellRift.emoji} {cellRift.name} · {cellRift.min_level}-{cellRift.max_level} ур.
                {levels.level < cellRift.min_level || levels.level > cellRift.max_level ? ' (тебе не по уровню)' : ''}
              </p>
              <p className="map-card__line">
                До {cellRift.max_size} игроков · {RIFT_STATE[cellRift.state] || ''}
                {cellRift.state === 'free' ? ` · закроется через ${cellRift.minutes_left} мин` : ''}
              </p>
              <p className="map-card__line map-card__line--hint">{cellRift.hint}</p>
            </>
          )}
          {info.isMonolith && <p className="map-card__line">Рейды: прикоснись к Монолиту, нужен Ключ Монолита.</p>}
          {info.isCity && <p className="map-card__line">Город · без PvP · торговля, лавки, долгий путь из родного.</p>}
          {info.boss && <p className="map-card__line">💀 {info.boss.name} · ур. {info.boss.level} · {info.boss.hp_percent}%</p>}
          {mapState.turbo && !mapState.turbo.running && mapState.turbo.x === info.x && mapState.turbo.y === info.y && (
            <p className="map-card__line">🫏 Турбоишак здесь. Зайди на клетку и нажми «Подойти» - он долго не стоит.</p>
          )}
          {(() => {
            const g = guildCells.find((c) => c.x === info.x && c.y === info.y);
            if (!g) return null;
            const what = g.status === 'claiming' ? 'закладывают знамя' : (g.mine ? 'рудник гильдии' : 'земля гильдии');
            return <p className="map-card__line">🏰 [{g.tag}] · {what}{g.own ? ' (твоя гильдия)' : ''}</p>;
          })()}
          <div className="map-card__badges">
            {info.isCity && <span className="map-card__badge">Город</span>}
            {info.isPlayer && <span className="map-card__badge">Ты здесь</span>}
            {info.isQuestTarget && <span className="map-card__badge">Цель квеста{info.questLabel ? `: ${info.questLabel}` : ''}</span>}
          </div>

          {!sendFlow && (
            <Button
              size="l" stretched mode="secondary" className="map-card__action"
              disabled={!canSendMount}
              onClick={() => setSendFlow({ step: 'pick', mount: null })}
            >
              🐎 Отправить маунта
            </Button>
          )}
          {!sendFlow && !canSendMount && (
            <p className="map-card__hint">
              {mapState.mounts.length === 0 ? 'У тебя пока нет маунтов.' : isTraveling ? 'Ты уже в пути.' : 'Сейчас недоступно.'}
            </p>
          )}

          {sendFlow && (
            <button
              type="button"
              className={`map-safe-toggle${safeRoute ? ' map-safe-toggle--on' : ''}`}
              onClick={toggleSafeRoute}
              aria-pressed={safeRoute}
            >
              {safeRoute ? '✓ 🛡 Безопасный путь' : '🛡 Безопасный путь'}
              <span className="map-safe-toggle__hint">
                {safeRoute ? `в обход колец опаснее цели${detourNote ? ` - ${detourNote}` : ''}` : 'напрямую, через любые кольца'}
              </span>
            </button>
          )}
          {sendFlow?.step === 'pick' && (
            <div className="map-card__mounts">
              {mapState.mounts.map((m) => {
                const cells = preview ? preview.cells : cellsBetween(playerPos.x, playerPos.y, info.x, info.y);
                const est = preview?.mounts?.[m.mount_id];
                return (
                  <button key={m.mount_id} className="map-card__mount-option" onClick={() => setSendFlow({ step: 'confirm', mount: m })}>
                    <span>{m.emoji} {m.name}</span>
                    <span className="map-card__mount-meta">
                      {routePending ? 'считаю путь…'
                        : `${formatSeconds(est ? est.seconds : m.seconds_per_cell * cells)} · риск ${Math.round((est ? est.ambush : m.ambush_chance) * 100)}%`}
                    </span>
                  </button>
                );
              })}
              <Button size="m" mode="tertiary" onClick={() => setSendFlow(null)}>Отмена</Button>
            </div>
          )}

          {sendFlow?.step === 'confirm' && (() => {
            const cells = preview ? preview.cells : cellsBetween(playerPos.x, playerPos.y, info.x, info.y);
            const est = preview?.mounts?.[sendFlow.mount.mount_id];
            return (
              <div className="map-card__confirm">
                {routePending ? (
                  <p className="map-card__line">Считаю путь…</p>
                ) : (
                  <p className="map-card__line">
                    Путь: {cells} {cellsWord(cells)} · {sendFlow.mount.name} ·{' '}
                    {formatSeconds(est ? est.seconds : sendFlow.mount.seconds_per_cell * cells)} ·{' '}
                    риск нападения {Math.round((est ? est.ambush : sendFlow.mount.ambush_chance) * 100)}%
                    {detourNote ? ` · 🛡 ${detourNote}` : ''}
                  </p>
                )}
                <div className="map-card__confirm-actions">
                  <Button size="m" stretched onClick={confirmSend}>Подтвердить</Button>
                  <Button size="m" stretched mode="tertiary" onClick={() => setSendFlow({ step: 'pick', mount: null })}>Назад</Button>
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

const RIFT_STATE = { free: 'свободен', waiting: 'у входа ждёт группа', running: 'внутри группа' };

/** «(у тебя N)», если уровня профессии не хватает. */
function levelNote(have, need) {
  return have != null && have < need ? ` (у тебя ${have})` : '';
}

function MapTooltipContent({ info, mineOre, rift }) {
  return (
    <>
      <p className="map-tooltip__coords">({info.x}; {info.y})</p>
      <p className="map-tooltip__line">{info.isMonolith ? '🩸 Багряный Монолит' : info.regionTitle}</p>
      {!info.isMonolith && !info.isCity && <p className="map-tooltip__line">{info.typeName}</p>}
      {info.isCity && <p className="map-tooltip__line">Город</p>}
      <p className="map-tooltip__line">Уровень: {info.levelRange[0]}-{info.levelRange[1]} · до Монолита {info.dist}</p>
      {info.lake && (
        <p className="map-tooltip__line map-tooltip__line--lake">
          🎣 {info.lake.name}{info.lake.safe ? ' · без PvP' : ''}
        </p>
      )}
      {info.mine && (
        <p className="map-tooltip__line map-tooltip__line--mine">
          ⛏ {info.mine.name} · руды {mineOre?.[info.mine.id] || 0}
          {info.mine.safe ? ' · без PvP' : ''}
        </p>
      )}
      {info.boss && <p className="map-tooltip__line">💀 {info.boss.name} · {info.boss.hp_percent}%</p>}
      {rift && (
        <p className="map-tooltip__line">
          {rift.blood ? '🩸 Кровавый: ' : '🌀 '}{rift.name} · {rift.min_level}-{rift.max_level} ур. · {RIFT_STATE[rift.state] || ''}
        </p>
      )}
    </>
  );
}
