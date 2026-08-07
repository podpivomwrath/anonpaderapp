import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Div, Spinner, Placeholder, Button, IconButton } from '@vkontakte/vkui';
import { getMapState, sendMountFromMap } from '../api.js';
import {
  cellColor, cellInfo, chebyshevDistance, clamp, screenToWorld, worldToScreen,
} from '../mapCatalog.js';

const MIN_CELL_PX = 8;
const MAX_CELL_PX = 40;
const DEFAULT_CELL_PX = 20;
const DRAG_THRESHOLD_PX = 4;

const ERROR_MESSAGES = {
  dead: 'Сначала очнись.',
  in_pvp: 'Сначала разберись с открытым боем.',
  in_combat: 'В бою не до маунта.',
  busy: 'Сначала закончи то, что начал.',
  traveling_on_foot: 'Ты уже в пути пешком.',
  already_on_mount: 'Ты уже в пути на маунте.',
  out_of_bounds: 'Эти координаты за пределами обжитых земель.',
  already_there: 'Ты уже здесь.',
  mount_not_owned: 'Этого маунта у тебя нет.',
  bad_request: 'Что-то пошло не так.',
};

function formatSeconds(seconds) {
  if (seconds >= 60) return `~${(seconds / 60).toFixed(1)} мин.`;
  return `~${Math.round(seconds)} сек.`;
}

export default function MapTab() {
  const containerRef = useRef(null);
  const [size, setSize] = useState({ width: 360, height: 420 });
  const [camera, setCamera] = useState(null);
  const [cellPx, setCellPx] = useState(DEFAULT_CELL_PX);
  const [mapState, setMapState] = useState(null);
  const [status, setStatus] = useState('loading');
  const [hovered, setHovered] = useState(null); // {x,y, screenX, screenY} — десктоп-хавер
  const [selected, setSelected] = useState(null); // {x,y} — открытая карточка (клик/тап)
  const [sendFlow, setSendFlow] = useState(null); // {step:'pick'|'confirm', mount}
  const [banner, setBanner] = useState(null);

  const pointers = useRef(new Map());
  const dragRef = useRef(null);
  const pinchRef = useRef(null);
  const isTouchRef = useRef(false);

  const load = useCallback(() => {
    getMapState()
      .then((data) => {
        setMapState(data);
        setStatus('ready');
        setCamera((prev) => prev ?? { cx: data.pos_x, cy: data.pos_y });
      })
      .catch(() => setStatus('error'));
  }, []);

  useEffect(() => { load(); }, [load]);

  // Живой опрос ПОЗИЦИИ/путешествия — не клеток (см. mapCatalog.js).
  useEffect(() => {
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  // Оба эффекта завязаны на status: контейнер .map-viewport рендерится ТОЛЬКО
  // в ветке status==='ready' (при 'loading' — ранний возврат со спиннером),
  // поэтому эффект с пустыми deps срабатывает СЛИШКОМ РАНО (containerRef.current
  // ещё null) и больше никогда не перезапускается — size навсегда остаётся
  // дефолтным. Замечено при тестировании: клик резолвился в клетку с уходом
  // на десятки клеток от ожидаемой.
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) setSize({ width: rect.width, height: rect.height });
  }, [status]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      if (width > 0 && height > 0) setSize({ width, height });
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [status]);

  const catalog = mapState?.catalog;
  const boundsMin = catalog?.bounds_min ?? -50;
  const boundsMax = catalog?.bounds_max ?? 50;

  const visibleCells = useMemo(() => {
    if (!camera || !catalog) return [];
    const halfW = size.width / 2 / cellPx;
    const halfH = size.height / 2 / cellPx;
    const x0 = clamp(Math.floor(camera.cx - halfW) - 1, boundsMin, boundsMax);
    const x1 = clamp(Math.ceil(camera.cx + halfW) + 1, boundsMin, boundsMax);
    const y0 = clamp(Math.floor(camera.cy - halfH) - 1, boundsMin, boundsMax);
    const y1 = clamp(Math.ceil(camera.cy + halfH) + 1, boundsMin, boundsMax);
    const cells = [];
    for (let gy = y0; gy <= y1; gy++) {
      for (let gx = x0; gx <= x1; gx++) cells.push([gx, gy]);
    }
    return cells;
  }, [camera, cellPx, size, catalog, boundsMin, boundsMax]);

  const playerPos = mapState ? { x: mapState.pos_x, y: mapState.pos_y } : null;
  const questTarget = mapState?.quest_target ?? null;

  const recenterOnPlayer = () => {
    if (mapState) setCamera({ cx: mapState.pos_x, cy: mapState.pos_y });
  };

  // --- Указатели: драг одним пальцем/мышью, щипок двумя пальцами ---

  const handlePointerDown = (e) => {
    isTouchRef.current = e.pointerType === 'touch';
    // Некоторые вебвью (встречается в ВК-мобильном на отдельных версиях
    // Android/iOS) кидают исключение на setPointerCapture в редких гонках —
    // не даём этому сорвать сам драг, capture — не более чем оптимизация.
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* noop */ }
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 1 && camera) {
      dragRef.current = {
        startCx: camera.cx, startCy: camera.cy, startX: e.clientX, startY: e.clientY, moved: false,
      };
      pinchRef.current = null;
    } else if (pointers.current.size === 2) {
      dragRef.current = null;
      const pts = [...pointers.current.values()];
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      pinchRef.current = { startDist: dist || 1, startCellPx: cellPx };
    }
  };

  const handlePointerMove = (e) => {
    if (!pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (pointers.current.size === 2 && pinchRef.current) {
      const pts = [...pointers.current.values()];
      const dist = Math.hypot(pts[0].x - pts[1].x, pts[0].y - pts[1].y);
      const scale = dist / pinchRef.current.startDist;
      setCellPx(clamp(pinchRef.current.startCellPx * scale, MIN_CELL_PX, MAX_CELL_PX));
      return;
    }

    if (pointers.current.size === 1 && dragRef.current && camera) {
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      if (Math.hypot(dx, dy) > DRAG_THRESHOLD_PX) dragRef.current.moved = true;
      setCamera({
        cx: clamp(dragRef.current.startCx - dx / cellPx, boundsMin, boundsMax),
        cy: clamp(dragRef.current.startCy + dy / cellPx, boundsMin, boundsMax),
      });
      return;
    }

    // Наведение (десктоп-мышь, без активного драга) — лёгкая подсказка.
    if (!isTouchRef.current && pointers.current.size === 1 && !dragRef.current?.moved && camera) {
      const rect = containerRef.current.getBoundingClientRect();
      const world = screenToWorld(camera, cellPx, size, e.clientX - rect.left, e.clientY - rect.top);
      const gx = Math.round(world.x);
      const gy = Math.round(world.y);
      if (gx >= boundsMin && gx <= boundsMax && gy >= boundsMin && gy <= boundsMax) {
        setHovered({ x: gx, y: gy, screenX: e.clientX - rect.left, screenY: e.clientY - rect.top });
      }
    }
  };

  const handlePointerUp = (e) => {
    const wasSinglePointerTap = pointers.current.size === 1 && dragRef.current && !dragRef.current.moved;
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinchRef.current = null;

    if (wasSinglePointerTap && camera) {
      const rect = containerRef.current.getBoundingClientRect();
      const world = screenToWorld(camera, cellPx, size, e.clientX - rect.left, e.clientY - rect.top);
      const gx = clamp(Math.round(world.x), boundsMin, boundsMax);
      const gy = clamp(Math.round(world.y), boundsMin, boundsMax);
      setSelected({ x: gx, y: gy });
      setSendFlow(null);
    }
    if (pointers.current.size === 0) dragRef.current = null;
  };

  const handlePointerLeave = () => setHovered(null);

  const handleWheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setCellPx((prev) => clamp(prev * factor, MIN_CELL_PX, MAX_CELL_PX));
  };

  const zoomBy = (factor) => setCellPx((prev) => clamp(prev * factor, MIN_CELL_PX, MAX_CELL_PX));

  // --- Отправка маунта ---

  const isTraveling = Boolean(mapState?.foot_travel || mapState?.mount_travel);
  const canSendMount = mapState && !mapState.is_dead && !isTraveling && mapState.mounts.length > 0;

  const startSendFlow = () => setSendFlow({ step: 'pick', mount: null });
  const pickMount = (mount) => setSendFlow({ step: 'confirm', mount });

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
    if (!banner) return;
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
  if (status === 'error' || !mapState || !camera) {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🗺️</div>}>Не удалось загрузить карту.</Placeholder>;
  }

  const info = selected ? cellInfo(catalog, selected.x, selected.y, playerPos, questTarget) : null;
  const showSymbols = cellPx >= 14;

  return (
    <div className="map-tab">
      <div
        ref={containerRef}
        className="map-viewport"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        onPointerLeave={handlePointerLeave}
        onWheel={handleWheel}
      >
        {visibleCells.map(([gx, gy]) => {
          const dist = chebyshevDistance(gx, gy);
          const screen = worldToScreen(camera, cellPx, size, gx, gy);
          const isCity = catalog.city_coords && Object.values(catalog.city_coords).some(([cx, cy]) => cx === gx && cy === gy);
          const isMonolith = gx === 0 && gy === 0;
          return (
            <div
              key={`${gx}:${gy}`}
              className="map-cell"
              style={{
                left: screen.x - cellPx / 2, top: screen.y - cellPx / 2,
                width: cellPx - 1, height: cellPx - 1,
                background: cellColor(gx, gy, dist),
              }}
            >
              {showSymbols && isMonolith && (
                <span className="map-cell__symbol" style={{ fontSize: Math.max(10, cellPx * 0.5) }}>◆</span>
              )}
              {showSymbols && isCity && !isMonolith && (
                <span className="map-cell__symbol" style={{ fontSize: Math.max(10, cellPx * 0.5) }}>⛩</span>
              )}
            </div>
          );
        })}

        {questTarget && (
          <div
            className="map-marker map-marker--quest"
            style={{
              left: worldToScreen(camera, cellPx, size, questTarget.x, questTarget.y).x - cellPx / 2,
              top: worldToScreen(camera, cellPx, size, questTarget.x, questTarget.y).y - cellPx / 2,
              width: cellPx, height: cellPx,
            }}
          />
        )}

        {playerPos && (
          <div
            className="map-marker map-marker--player"
            style={{
              left: worldToScreen(camera, cellPx, size, playerPos.x, playerPos.y).x - cellPx / 2,
              top: worldToScreen(camera, cellPx, size, playerPos.x, playerPos.y).y - cellPx / 2,
              width: cellPx, height: cellPx,
            }}
          />
        )}

        {hovered && (
          <div
            className="map-tooltip"
            style={{ left: clamp(hovered.screenX + 12, 0, size.width - 180), top: clamp(hovered.screenY + 12, 0, size.height - 90) }}
          >
            <MapTooltipContent info={cellInfo(catalog, hovered.x, hovered.y, playerPos, questTarget)} />
          </div>
        )}

        <div className="map-controls">
          <IconButton className="map-controls__btn" onClick={() => zoomBy(1.3)} aria-label="Приблизить">＋</IconButton>
          <IconButton className="map-controls__btn" onClick={() => zoomBy(1 / 1.3)} aria-label="Отдалить">－</IconButton>
          <IconButton className="map-controls__btn" onClick={recenterOnPlayer} aria-label="К себе">◎</IconButton>
        </div>

        {isTraveling && (
          <div className="map-travel-banner">
            {mapState.mount_travel
              ? `🐎 В пути к (${mapState.mount_travel.to_x}; ${mapState.mount_travel.to_y})`
              : `🚶 В пути к (${mapState.foot_travel.to_x}; ${mapState.foot_travel.to_y})`}
          </div>
        )}
      </div>

      {banner && <div className="map-toast">{banner}</div>}

      {info && (
        <div className="map-card">
          <button className="map-card__close" onClick={() => { setSelected(null); setSendFlow(null); }} aria-label="Закрыть">✕</button>
          <p className="map-card__coords">({info.x}; {info.y})</p>
          <p className="map-card__line">{info.isMonolith ? '🩸 Багряный Монолит' : info.regionTitle}</p>
          {!info.isMonolith && <p className="map-card__line">{info.typeName}</p>}
          <p className="map-card__line">Уровень мобов: {info.levelRange[0]}-{info.levelRange[1]}</p>
          <p className="map-card__line">Расстояние: {info.dist} клеток</p>
          <div className="map-card__badges">
            {info.isCity && <span className="map-card__badge">Город</span>}
            {info.isPlayer && <span className="map-card__badge">Ты здесь</span>}
            {info.isQuestTarget && <span className="map-card__badge">Цель квеста{info.questLabel ? `: ${info.questLabel}` : ''}</span>}
          </div>

          {!sendFlow && (
            <Button
              size="l" stretched mode="secondary" className="map-card__action"
              disabled={!canSendMount}
              onClick={startSendFlow}
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
                const cells = chebyshevDistance(info.x - playerPos.x, info.y - playerPos.y);
                const seconds = m.seconds_per_cell * cells;
                return (
                  <button key={m.mount_id} className="map-card__mount-option" onClick={() => pickMount(m)}>
                    <span>{m.emoji} {m.name}</span>
                    <span className="map-card__mount-meta">{formatSeconds(seconds)} · риск {Math.round(m.ambush_chance * 100)}%</span>
                  </button>
                );
              })}
              <Button size="m" mode="tertiary" onClick={() => setSendFlow(null)}>Отмена</Button>
            </div>
          )}

          {sendFlow?.step === 'confirm' && (
            <div className="map-card__confirm">
              <p className="map-card__line">
                Путь: {chebyshevDistance(info.x - playerPos.x, info.y - playerPos.y)} клеток · {sendFlow.mount.name} ·{' '}
                {formatSeconds(sendFlow.mount.seconds_per_cell * chebyshevDistance(info.x - playerPos.x, info.y - playerPos.y))} ·{' '}
                риск нападения {Math.round(sendFlow.mount.ambush_chance * 100)}%
              </p>
              <div className="map-card__confirm-actions">
                <Button size="m" stretched onClick={confirmSend}>Подтвердить</Button>
                <Button size="m" stretched mode="tertiary" onClick={() => setSendFlow({ step: 'pick', mount: null })}>Назад</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function MapTooltipContent({ info }) {
  return (
    <>
      <p className="map-tooltip__coords">({info.x}; {info.y})</p>
      <p className="map-tooltip__line">{info.isMonolith ? '🩸 Багряный Монолит' : info.regionTitle}</p>
      {!info.isMonolith && <p className="map-tooltip__line">{info.typeName}</p>}
      <p className="map-tooltip__line">Уровень: {info.levelRange[0]}-{info.levelRange[1]} · {info.dist} кл.</p>
    </>
  );
}
