import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Div, Spinner, Placeholder, Button, IconButton } from '@vkontakte/vkui';
import { getMapState, sendMountFromMap } from '../api.js';
import mapBase from '../assets/world-map-drawn-2048.webp';
import mapDetail from '../assets/world-map-drawn-4096.webp';
import lensFrame from '../assets/lens-frame.webp';
import {
  DRAW_RINGS, MAP_CENTER, cellInfo, cellSizeAt, cellToMap, cellsBetween, clamp, mapToCell,
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
 * Патч 112: рисованная карта и линза. Карта стоит целиком, рассматривать её
 * - линзой: на компьютере она ездит за курсором (кнопка 🔍 или колесо), на
 * телефоне появляется по долгому нажатию и висит над пальцем. В линзе -
 * детальная картинка 4096, она грузится только при первом открытии.
 */

const DRAG_THRESHOLD_PX = 5;
const MAX_SCALE = 4400;          // щипком на телефоне - клетка до ~60 px
const GRID_FROM_CELL_PX = 20;    // сетка видна с этого размера клетки
const CELL_K = 0.0143;           // средний размер клетки на картинке (доля ширины)

// Линза: увеличение от ×2 до ×4 шагом 0.1 (колесо мыши).
const LENS_MIN = 2;
const LENS_MAX = 4;
const LENS_STEP = 0.1;
const LENS_DEFAULT = 2.5;
const LENS_D_DESKTOP = 240;      // диаметр окна линзы, px
const LENS_D_TOUCH = 176;
// Окно линзы относительно картинки оправы: внутренний край кольца - 0.765
// от половины её размера (замерено по прозрачности, tools/map_art_prompt.md).
const LENS_FRAME_RATIO = 0.765;
const LONG_PRESS_MS = 300;

const ERROR_MESSAGES = {
  dead: 'Сначала очнись.',
  in_pvp: 'Сначала разберись с открытым боем.',
  in_combat: 'В бою не до маунта.',
  busy: 'Сначала закончи то, что начал.',
  mining: 'Ты в забое - сначала закончи или брось добычу.',
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

export default function MapTab() {
  const containerRef = useRef(null);
  const [size, setSize] = useState({ width: 360, height: 420 });
  const [view, setView] = useState(null); // {cu, cv, scale}
  const [mapState, setMapState] = useState(null);
  const [status, setStatus] = useState('loading');
  const [imageReady, setImageReady] = useState(false);
  const [hovered, setHovered] = useState(null); // {x, y, sx, sy}
  const [selected, setSelected] = useState(null); // {x, y}
  const [sendFlow, setSendFlow] = useState(null); // {step: 'pick'|'confirm', mount}
  const [banner, setBanner] = useState(null);

  const pointers = useRef(new Map());
  const dragRef = useRef(null);
  const pinchRef = useRef(null);
  const isTouchRef = useRef(false);

  // Линза: включена ли (кнопка 🔍 / колесо), увеличение, точка под ней и
  // режим «удерживаю палец» на телефоне.
  const [lens, setLens] = useState({ on: false, mag: LENS_DEFAULT });
  const [lensPoint, setLensPoint] = useState(null); // {x, y} в пикселях окна карты
  const [touchLens, setTouchLens] = useState(false);
  const [detailUsed, setDetailUsed] = useState(false);
  const longPressRef = useRef(null);

  const load = useCallback(() => {
    getMapState()
      .then((data) => {
        setMapState(data);
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

  // Весь мир (~0.92 ширины картинки) целиком влезает в окно - дальше
  // отдалять незачем.
  const minScale = Math.min(size.width, size.height) / 0.96;
  const clampScale = useCallback((s) => clamp(s, minScale, MAX_SCALE), [minScale]);
  // Камеру не уводим за край мира: центр окна может отойти от Монолита
  // ровно настолько, чтобы край мира доходил до края окна. На полном
  // отдалении это ноль - карта стоит по центру.
  const clampView = useCallback((v) => {
    const reachU = Math.max(0, 0.47 - size.width / 2 / v.scale);
    const reachV = Math.max(0, 0.47 - size.height / 2 / v.scale);
    return {
      scale: v.scale,
      cu: clamp(v.cu, MAP_CENTER.u - reachU, MAP_CENTER.u + reachU),
      cv: clamp(v.cv, MAP_CENTER.v - reachV, MAP_CENTER.v + reachV),
    };
  }, [size]);

  // Стартовая камера - вся карта целиком: рассматривают её линзой. Пока её
  // не приблизили щипком, она следует за размером окна (сначала размер ещё
  // не измерен, потом меняется при повороте телефона).
  const fittedRef = useRef(true);
  useEffect(() => {
    if (!mapState) return;
    if (!view || fittedRef.current) {
      setView({ cu: MAP_CENTER.u, cv: MAP_CENTER.v, scale: minScale });
    }
  }, [mapState, minScale]); // eslint-disable-line react-hooks/exhaustive-deps

  const catalog = mapState?.catalog;
  const playerPos = mapState ? { x: mapState.pos_x, y: mapState.pos_y } : null;
  const questTarget = mapState?.quest_target ?? null;
  const worldBoss = mapState?.world_boss ?? null;

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

  // Все клетки мира - один раз: их ~2800, дальше только фильтр по окну.
  const allCells = useMemo(() => {
    if (!catalog) return [];
    const r = catalog.world_radius;
    const cells = [];
    for (let x = -r; x <= r; x++) {
      for (let y = -r; y <= r; y++) {
        if (monolithDistance(x, y) <= r) cells.push([x, y]);
      }
    }
    return cells;
  }, [catalog]);

  const gridCells = useMemo(() => {
    if (!view || cellPx < GRID_FROM_CELL_PX) return [];
    const pad = cellPx;
    return allCells
      .map(([x, y]) => {
        const s = cellScreen(x, y);
        return { x, y, sx: s.x, sy: s.y, size: cellSizeAt(monolithDistance(x, y)) * view.scale };
      })
      .filter((c) => c.sx > -pad && c.sy > -pad && c.sx < size.width + pad && c.sy < size.height + pad);
  }, [allCells, cellScreen, cellPx, view, size]);

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
    setView(clampView({
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

  const clearLongPress = () => {
    if (longPressRef.current) clearTimeout(longPressRef.current);
    longPressRef.current = null;
  };

  const showLens = () => {
    setDetailUsed(true);
    setLens((cur) => ({ ...cur, on: true }));
  };

  const handlePointerDown = (e) => {
    if (isOverlayTarget(e)) return;
    isTouchRef.current = e.pointerType === 'touch';
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* вебвью ВК иногда бросает */ }
    pointers.current.set(e.pointerId, localPoint(e));
    if (pointers.current.size === 1 && view) {
      const p = localPoint(e);
      dragRef.current = { start: view, x: p.x, y: p.y, moved: false };
      pinchRef.current = null;
      if (isTouchRef.current) {
        // Телефон: линза по долгому нажатию, а если она включена кнопкой -
        // сразу. Пока держишь палец, он водит линзой, а не двигает карту.
        clearLongPress();
        const start = () => { setDetailUsed(true); setTouchLens(true); setLensPoint(p); };
        if (lens.on) start();
        else longPressRef.current = setTimeout(start, LONG_PRESS_MS);
      }
    } else if (pointers.current.size === 2 && view) {
      clearLongPress();
      setTouchLens(false);
      dragRef.current = null;
      const [a, b] = [...pointers.current.values()];
      pinchRef.current = {
        dist: Math.hypot(a.x - b.x, a.y - b.y) || 1,
        mid: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
        start: view,
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

    if (touchLens && pointers.current.size === 1) {
      setLensPoint(p);
      return;
    }

    if (pointers.current.size === 1 && dragRef.current) {
      const dx = p.x - dragRef.current.x;
      const dy = p.y - dragRef.current.y;
      if (Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) {
        dragRef.current.moved = true;
        clearLongPress();
      }
      if (dragRef.current.moved) {
        const start = dragRef.current.start;
        setView(clampView({ ...start, cu: start.cu - dx / start.scale, cv: start.cv - dy / start.scale }));
        setHovered(null);
      }
      return;
    }

    // Наведение мышью без нажатия - лёгкая подсказка; линза едет за курсором.
    if (!isTouchRef.current && pointers.current.size === 0) {
      const cell = cellAtScreen(p.x, p.y);
      setHovered(cell ? { ...cell, sx: p.x, sy: p.y } : null);
      if (lens.on) setLensPoint(p);
    }
  };

  const handlePointerUp = (e) => {
    clearLongPress();
    if (touchLens) {
      // Отпустил палец под линзой - выбрана клетка под её центром.
      pointers.current.delete(e.pointerId);
      setTouchLens(false);
      const p = localPoint(e);
      setSelected(cellAtScreen(p.x, p.y));
      setSendFlow(null);
      setLensPoint(null);
      if (pointers.current.size === 0) dragRef.current = null;
      return;
    }
    const tap = pointers.current.size === 1 && dragRef.current && !dragRef.current.moved;
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinchRef.current = null;
    if (tap && view) {
      const p = localPoint(e);
      const cell = cellAtScreen(p.x, p.y);
      setSelected(cell);
      setSendFlow(null);
    }
    if (pointers.current.size === 0) dragRef.current = null;
  };

  // Колесо: React вешает onWheel пассивным, preventDefault там не работает -
  // слушатель ставим сами, иначе вместе с картой прокручивалась бы страница.
  const wheelRef = useRef(null);
  wheelRef.current = (e) => {
    if (!view) return;
    e.preventDefault();
    const p = localPoint(e);
    setLensPoint(p);
    if (!lens.on) {
      // Первое движение колеса только показывает линзу.
      showLens();
      return;
    }
    const step = e.deltaY < 0 ? LENS_STEP : -LENS_STEP;
    if (step < 0 && lens.mag <= LENS_MIN) {
      // Отдаление дальше ×2 - линза убирается; следующее колесо вернёт её.
      setLens((cur) => ({ ...cur, on: false }));
      setLensPoint(null);
      return;
    }
    setLens((cur) => ({
      ...cur,
      mag: Math.round(clamp(cur.mag + step, LENS_MIN, LENS_MAX) * 10) / 10,
    }));
  };

  const toggleLens = () => {
    if (lens.on) {
      setLens((cur) => ({ ...cur, on: false }));
      setLensPoint(null);
      return;
    }
    showLens();
    // До первого движения мыши линза стоит в центре карты.
    if (!isTouchRef.current) setLensPoint({ x: size.width / 2, y: size.height / 2 });
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

  const confirmSend = async () => {
    if (!selected || !sendFlow?.mount) return;
    try {
      await sendMountFromMap(sendFlow.mount.mount_id, selected.x, selected.y);
      setBanner(`🐎 Путь начат: (${selected.x}; ${selected.y}).`);
      setSendFlow(null);
      setSelected(null);
      load();
    } catch (err) {
      setBanner(ERROR_MESSAGES[err.message] || 'Не удалось отправить маунта.');
      setSendFlow(null);
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
  const center = view ? toScreen(MAP_CENTER.u, MAP_CENTER.v) : null;
  // Метки растут с клеткой: на телефоне карта целиком мелкая, и крупные
  // метки закрывали бы рисунок - рассматривать детали там линзой.
  const markerPx = clamp(cellPx * 1.3, 11, 30);
  const travelTarget = mapState.mount_travel || mapState.foot_travel;

  const pins = [
    ...(catalog.lakes || []).map((l) => [l.x, l.y, 'map-pin--lake', '🎣', l.name, 0.8]),
    ...(catalog.mines || []).map((m) => [
      m.x, m.y, `map-pin--mine${(mapState.mine_ore?.[m.id] || 0) > 0 ? '' : ' map-pin--empty'}`,
      '⛏', `${m.name}: руды ${mapState.mine_ore?.[m.id] || 0}`, 0.8,
    ]),
    ...(questTarget ? [[questTarget.x, questTarget.y, 'map-pin--quest', '📜', questTarget.label, 1]] : []),
    ...(worldBoss ? [[worldBoss.x, worldBoss.y, 'map-pin--boss', '💀', worldBoss.name, 1.3]] : []),
    ...(mapState.trail
      ? [[mapState.trail.x, mapState.trail.y, 'map-pin--trail', mapState.trail.emoji, mapState.trail.title, 1.1]]
      : []),
    ...(travelTarget ? [[travelTarget.to_x, travelTarget.to_y, 'map-pin--route', '⚑', 'Цель пути', 1]] : []),
    ...(playerPos ? [[playerPos.x, playerPos.y, 'map-pin--player', '', 'Ты здесь', 1.1]] : []),
  ];

  /** Метка в точке (sx, sy); size - её размер в пикселях. */
  const pinAt = ([x, y, className, content, title], sx, sy, px) => (
    <div
      key={`${className}:${x}:${y}`}
      className={`map-pin ${className}`}
      style={{ left: sx - px / 2, top: sy - px / 2, width: px, height: px, fontSize: px * 0.62 }}
      title={title}
    >
      {content}
    </div>
  );

  // --- Линза ---
  const lensVisible = Boolean(view && lensPoint && (touchLens || (lens.on && !isTouchRef.current)));
  const lensD = touchLens ? LENS_D_TOUCH : LENS_D_DESKTOP;
  let lensBox = null;
  if (lensVisible) {
    // На телефоне окно висит над пальцем - иначе палец его и закроет.
    const cx = clamp(lensPoint.x, lensD / 2, size.width - lensD / 2);
    const rawY = touchLens ? lensPoint.y - lensD * 0.8 : lensPoint.y;
    const cy = clamp(rawY, lensD / 2, size.height - lensD / 2);
    const m = toMap(lensPoint.x, lensPoint.y);
    const S = view.scale * lens.mag;
    lensBox = { cx, cy, S, m };
  }

  return (
    <div className="map-tab">
      <div
        ref={containerRef}
        className={`map-viewport${lensVisible && !touchLens ? ' map-viewport--lens' : ''}`}
        style={fillHeight ? { height: fillHeight } : undefined}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={() => { setHovered(null); if (!touchLens) setLensPoint(null); }}
      >
        {view && (
          <div className="map-stage">
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

            <svg className="map-overlay" width={size.width} height={size.height}>
              {DRAW_RINGS && ringBorders(catalog).map((r, i) => (
                <circle
                  key={r}
                  cx={center.x} cy={center.y} r={r * view.scale}
                  className={i === 0 ? 'map-ring map-ring--rim' : 'map-ring'}
                />
              ))}
              {gridCells.map((c) => (
                <rect
                  key={`${c.x}:${c.y}`}
                  className="map-grid-cell"
                  x={c.sx - c.size / 2 + 1} y={c.sy - c.size / 2 + 1}
                  width={Math.max(c.size - 2, 1)} height={Math.max(c.size - 2, 1)} rx={3}
                />
              ))}
              {travelTarget && playerPos && (() => {
                const a = cellScreen(playerPos.x, playerPos.y);
                const b = cellScreen(travelTarget.to_x, travelTarget.to_y);
                return <line className="map-route" x1={a.x} y1={a.y} x2={b.x} y2={b.y} />;
              })()}
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

        {lensBox && (
          <div
            className="map-lens"
            style={{ left: lensBox.cx - lensD / 2, top: lensBox.cy - lensD / 2, width: lensD, height: lensD }}
          >
            <div className="map-lens__glass">
              <img
                className="map-image"
                src={detailUsed ? mapDetail : mapBase}
                alt=""
                draggable={false}
                style={{
                  width: lensBox.S,
                  height: lensBox.S,
                  transform: `translate(${lensD / 2 - lensBox.m.u * lensBox.S}px, ${lensD / 2 - lensBox.m.v * lensBox.S}px)`,
                }}
              />
              {(() => {
                const cell = cellAtScreen(lensPoint.x, lensPoint.y);
                if (!cell) return null;
                const sc = cellScreen(cell.x, cell.y);
                const px = cellSizeAt(monolithDistance(cell.x, cell.y)) * lensBox.S;
                const lx = lensD / 2 + (sc.x - lensPoint.x) * lens.mag;
                const ly = lensD / 2 + (sc.y - lensPoint.y) * lens.mag;
                return <div className="map-lens__cell" style={{ left: lx - px / 2, top: ly - px / 2, width: px, height: px }} />;
              })()}
              {pins.map((pin) => {
                const sc = cellScreen(pin[0], pin[1]);
                const lx = lensD / 2 + (sc.x - lensPoint.x) * lens.mag;
                const ly = lensD / 2 + (sc.y - lensPoint.y) * lens.mag;
                if (Math.hypot(lx - lensD / 2, ly - lensD / 2) > lensD / 2 + 20) return null;
                return pinAt(pin, lx, ly, clamp(markerPx * pin[5] * 1.4, 18, 34));
              })}
            </div>
            <img
              className="map-lens__frame"
              src={lensFrame}
              alt=""
              draggable={false}
              style={{ width: lensD / LENS_FRAME_RATIO, height: lensD / LENS_FRAME_RATIO }}
            />
            {!touchLens && <span className="map-lens__mag">×{lens.mag.toFixed(1)}</span>}
          </div>
        )}

        {!imageReady && (
          <div className="map-loading"><Spinner size="m" /></div>
        )}

        {hovered && (
          <div
            className="map-tooltip"
            style={{
              left: clamp(hovered.sx + (lensBox && !touchLens ? lensD / 2 + 14 : 14), 0, size.width - 190),
              top: clamp(hovered.sy + 14, 0, size.height - 100),
            }}
          >
            <MapTooltipContent
              info={cellInfo(catalog, hovered.x, hovered.y, playerPos, questTarget, worldBoss)}
              mineOre={mapState.mine_ore}
            />
          </div>
        )}

        <div className="map-controls">
          <IconButton
            className={`map-controls__btn${lens.on ? ' map-controls__btn--on' : ''}`}
            onClick={toggleLens} aria-label="Линза" title="Линза: колесо мыши - увеличение ×2…×4"
          >
            🔍
          </IconButton>
          <IconButton className="map-controls__btn" onClick={recenterOnPlayer} aria-label="К себе">◎</IconButton>
        </div>

        {isTraveling && (
          <div className="map-travel-banner">
            {mapState.mount_travel
              ? `🐎 В пути к (${mapState.mount_travel.to_x}; ${mapState.mount_travel.to_y})`
              : `🚶 В пути к (${mapState.foot_travel.to_x}; ${mapState.foot_travel.to_y})`}
          </div>
        )}
        {worldBoss && !isTraveling && (
          <div className="map-travel-banner map-travel-banner--boss">
            💀 {worldBoss.name} · ({worldBoss.x}; {worldBoss.y}) · {worldBoss.hp_percent}%
          </div>
        )}
      </div>

      {banner && <div className="map-toast">{banner}</div>}

      {info && (
        <div className="map-card">
          <button className="map-card__close" onClick={() => { setSelected(null); setSendFlow(null); }} aria-label="Закрыть">✕</button>
          <p className="map-card__coords">({info.x}; {info.y})</p>
          <p className="map-card__line">{info.isMonolith ? '🩸 Багряный Монолит' : info.regionTitle}</p>
          {!info.isMonolith && !info.isCity && <p className="map-card__line">{info.typeName}</p>}
          <p className="map-card__line">Уровень мобов: {info.levelRange[0]}-{info.levelRange[1]}</p>
          <p className="map-card__line">До Монолита: {info.dist} {cellsWord(info.dist)}</p>
          {info.lake && <p className="map-card__line">🎣 {info.lake.name}{info.lake.safe ? ' · без PvP' : ''}</p>}
          {info.mine && (
            <p className="map-card__line">
              ⛏ {info.mine.name} · руды {mapState.mine_ore?.[info.mine.id] || 0}{info.mine.safe ? ' · без PvP' : ''}
            </p>
          )}
          {info.boss && <p className="map-card__line">💀 {info.boss.name} · ур. {info.boss.level} · {info.boss.hp_percent}%</p>}
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

          {sendFlow?.step === 'pick' && (
            <div className="map-card__mounts">
              {mapState.mounts.map((m) => {
                const cells = cellsBetween(playerPos.x, playerPos.y, info.x, info.y);
                return (
                  <button key={m.mount_id} className="map-card__mount-option" onClick={() => setSendFlow({ step: 'confirm', mount: m })}>
                    <span>{m.emoji} {m.name}</span>
                    <span className="map-card__mount-meta">{formatSeconds(m.seconds_per_cell * cells)} · риск {Math.round(m.ambush_chance * 100)}%</span>
                  </button>
                );
              })}
              <Button size="m" mode="tertiary" onClick={() => setSendFlow(null)}>Отмена</Button>
            </div>
          )}

          {sendFlow?.step === 'confirm' && (() => {
            const cells = cellsBetween(playerPos.x, playerPos.y, info.x, info.y);
            return (
              <div className="map-card__confirm">
                <p className="map-card__line">
                  Путь: {cells} {cellsWord(cells)} · {sendFlow.mount.name} · {formatSeconds(sendFlow.mount.seconds_per_cell * cells)} ·{' '}
                  риск нападения {Math.round(sendFlow.mount.ambush_chance * 100)}%
                </p>
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

function MapTooltipContent({ info, mineOre }) {
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
    </>
  );
}
