import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Div, Placeholder, Spinner } from '@vkontakte/vkui';
import { getGuildTree, guildAction } from '../api.js';

// Древо гильдии: три ветви, почти двести узлов. Рисуется SVG целиком, а
// смотрится как карта - перетаскиванием и масштабом. Координаты и связи
// приходят с сервера (game/guild/tree.py): клиент ничего не пересчитывает.
//
// Ветви растут снизу вверх. Экран древа занимает всю высоту окна, а сама
// страница на нём не листается: иначе жест по древу то тянул его, то
// прокручивал страницу. Сводка, итоги и карточка узла - плашками поверх.

const BRANCH_COLOR = { war: '#d9483b', craft: '#e8a33d', kin: '#5fa8d9' };
const RADIUS = { root: 22, small: 9, notable: 15, keystone: 22 };
//: Ширина древа в его единицах при масштабе 1 - видно всё целиком.
const BASE_WIDTH = 2500;
//: Начальный вид: центр чуть выше корней, древо целиком.
const HOME = { x: 0, y: -380, scale: 1 };
const MIN_SCALE = 0.6;
const MAX_SCALE = 10;
const clampScale = (s) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));
const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');
const KIND_TITLES = { root: 'начало ветви', small: 'малый узел', notable: 'средний узел', keystone: 'ключевой узел' };

export default function GuildTree({ onChanged }) {
  const [tree, setTree] = useState(null);
  const [status, setStatus] = useState('loading');
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [view, setView] = useState(HOME);
  const [size, setSize] = useState({ w: 1, h: 0 });
  const [info, setInfo] = useState(false);
  const drag = useRef(null);
  // Пальцы на экране: один - тянем древо, два - масштаб щипком.
  const pointers = useRef(new Map());
  const pinch = useRef(null);
  const box = useRef(null);

  const load = useCallback(() => {
    getGuildTree()
      .then((data) => { setTree(data); setStatus('ready'); })
      .catch(() => setStatus('error'));
  }, []);
  useEffect(() => { load(); }, [load]);

  // Страница на экране древа не листается: древо само заполняет окно.
  useEffect(() => {
    const body = document.body.style.overflow;
    const html = document.documentElement.style.overflow;
    document.body.style.overflow = 'hidden';
    document.documentElement.style.overflow = 'hidden';
    window.scrollTo(0, 0);
    return () => {
      document.body.style.overflow = body;
      document.documentElement.style.overflow = html;
    };
  }, []);

  // Высота - до низа окна от верха древа.
  useEffect(() => {
    const measure = () => {
      const el = box.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      setSize({ w: rect.width, h: Math.max(320, Math.round(window.innerHeight - rect.top - 8)) });
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [status]);

  // Колесо - нативным обработчиком: в React он пассивный, preventDefault в
  // нём не работает, и вместо приближения листалась вся страница.
  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      setView((v) => ({ ...v, scale: clampScale(v.scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15)) }));
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [status]);

  const act = async (action, params, okText) => {
    setBusy(true);
    try {
      const state = await guildAction(action, params);
      onChanged?.(state);
      setNotice({ ok: true, text: okText });
      load();
    } catch (err) {
      setNotice({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  if (status === 'loading') {
    return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}><Spinner size="l" /></Div>;
  }
  if (status === 'error' || !tree) {
    return <Placeholder action={<Button onClick={load}>Ещё раз</Button>}>Не удалось загрузить древо.</Placeholder>;
  }

  const byId = Object.fromEntries(tree.nodes.map((n) => [n.id, n]));
  const node = selected ? byId[selected] : null;
  const edges = [];
  const seen = new Set();
  tree.nodes.forEach((n) => n.links.forEach((l) => {
    const key = n.id < l ? `${n.id}|${l}` : `${l}|${n.id}`;
    if (seen.has(key)) return;
    seen.add(key);
    edges.push([n, byId[l]]);
  }));

  const distance = () => {
    const [a, b] = [...pointers.current.values()];
    return Math.hypot(a.x - b.x, a.y - b.y) || 1;
  };
  const onPointerDown = (e) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    e.currentTarget.setPointerCapture?.(e.pointerId);
    if (pointers.current.size === 2) {
      pinch.current = { dist: distance(), scale: view.scale };
      if (drag.current) drag.current.moved = true;
      return;
    }
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
  };
  const onPointerMove = (e) => {
    if (!pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size >= 2 && pinch.current) {
      const ratio = distance() / pinch.current.dist;
      setView((v) => ({ ...v, scale: clampScale(pinch.current.scale * ratio) }));
      return;
    }
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true;
    // Пиксели экрана -> единицы древа: видимая ширина / ширина окна.
    const width = e.currentTarget.getBoundingClientRect().width || 1;
    setView((v) => {
      const k = BASE_WIDTH / v.scale / width;
      return { ...v, x: d.vx - dx * k, y: d.vy - dy * k };
    });
  };
  const onPointerUp = (e) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
    if (pointers.current.size === 1) {
      // Один палец остался - продолжаем тянуть от него, без скачка.
      const [rest] = [...pointers.current.values()];
      drag.current = { x: rest.x, y: rest.y, vx: view.x, vy: view.y, moved: true };
      return;
    }
    // Нажатие без сдвига - выбор узла под пальцем. По точке, а не по onClick:
    // захват указателя уводит click на контейнер, и узел его не получает.
    if (drag.current && !drag.current.moved) {
      const hit = document.elementFromPoint(e.clientX, e.clientY);
      const id = hit?.getAttribute?.('data-node');
      if (id) setSelected(id);
    }
    drag.current = null;
  };
  const zoom = (k) => setView((v) => ({ ...v, scale: clampScale(v.scale * k) }));

  /** Почему узел сейчас не взять - или null, если можно. */
  const lack = (n) => {
    if (!tree.can_edit) return 'Брать узлы могут глава и казначеи.';
    if (!n.available) return 'Сначала возьми соседний узел - древо растёт от уже взятых.';
    if (tree.points_available < n.points) return `Не хватает очков древа: нужно ${n.points}. Очки дают уровни гильдии.`;
    if (tree.treasury_gold < n.gold) return `В казне не хватает золота: нужно ${money(n.gold)}.`;
    return null;
  };

  // Видимая область в единицах древа: ширина от масштаба, высота - по
  // пропорциям экрана, чтобы древо не сплющивалось.
  const vbW = BASE_WIDTH / view.scale;
  const vbH = vbW * (size.h / Math.max(size.w, 1));
  const viewBox = `${view.x - vbW / 2} ${view.y - vbH / 2} ${vbW} ${vbH}`;
  const stop = { onPointerDown: (e) => e.stopPropagation(), onPointerUp: (e) => e.stopPropagation() };

  return (
    <div
      ref={box}
      className="guild-tree"
      style={{ height: size.h || undefined }}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <svg viewBox={viewBox} className="guild-tree__svg" preserveAspectRatio="xMidYMid meet">
        {edges.map(([a, b]) => (
          <line key={`${a.id}|${b.id}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            className={a.taken && b.taken ? 'guild-tree__edge guild-tree__edge--on' : 'guild-tree__edge'}
            style={a.taken && b.taken ? { stroke: BRANCH_COLOR[a.branch] } : undefined} />
        ))}
        {tree.nodes.map((n) => (
          <circle key={n.id} cx={n.x} cy={n.y} r={RADIUS[n.kind]}
            className={[
              'guild-tree__node',
              n.taken ? 'guild-tree__node--taken' : '',
              n.available ? 'guild-tree__node--available' : '',
              selected === n.id ? 'guild-tree__node--selected' : '',
            ].join(' ')}
            style={{ '--branch': BRANCH_COLOR[n.branch] }}
            data-node={n.id}
          />
        ))}
        {tree.nodes.filter((n) => n.kind === 'root').map((n) => (
          <text key={`t:${n.id}`} x={n.x} y={n.y + 48} className="guild-tree__root-label"
            style={{ fill: BRANCH_COLOR[n.branch] }}>{n.name}</text>
        ))}
      </svg>

      {/* Сводка - плашкой поверх древа: страница не листается, всё здесь. */}
      <div className="guild-tree__bar" {...stop}>
        <span>Очков: <b>{tree.points_available}</b> · узлов {tree.taken}/{tree.total_nodes}</span>
        <button type="button" onClick={() => { setInfo(!info); setSelected(null); }}>
          {info ? '✕' : 'Итоги'}
        </button>
      </div>

      {info && (
        <div className="guild-tree__card guild-tree__card--top" {...stop}>
          <p className="guild-tree__card-title">Древо гильдии</p>
          <div className="guild-tree__legend">
            {Object.entries(tree.branches).map(([id, title]) => (
              <span key={id}><i style={{ background: BRANCH_COLOR[id] }} /> {title}</span>
            ))}
          </div>
          <p className="craft-hint">
            Ветви растут снизу вверх. Узел берут рядом с уже взятым: малый - 1 очко, средний - 2, ключевой - 3,
            плюс золото из казны{tree.can_edit ? ` (в казне ${money(tree.treasury_gold)})` : ''}. Очки дают уровни
            гильдии. Брать могут глава и казначеи.
          </p>
          {tree.effects.length === 0
            ? <p className="guild-line">Узлов пока нет.</p>
            : tree.effects.map((e) => <p key={e} className="guild-line">• {e}</p>)}
        </div>
      )}

      {node && !info && (
        // Карточка узла - как карточка клетки на карте.
        <div className="guild-tree__card guild-tree__card--top" {...stop}>
          <button type="button" className="guild-tree__card-close" onClick={() => setSelected(null)}
            aria-label="Закрыть">✕</button>
          <p className="guild-tree__card-title" style={{ color: BRANCH_COLOR[node.branch] }}>{node.name}</p>
          <p className="craft-hint">{tree.branches[node.branch]} · {KIND_TITLES[node.kind]}</p>
          <p className="guild-line guild-tree__desc">{node.description}</p>
          {node.kind === 'root' || node.taken ? (
            node.kind !== 'root' && <p className="guild-line">✅ Взят</p>
          ) : (
            <>
              <p className="craft-hint">
                Цена: {node.points} очк. (есть {tree.points_available}) и {money(node.gold)} 💰
              </p>
              {lack(node) ? (
                <p className="guild-tree__card-lack">{lack(node)}</p>
              ) : (
                <Button size="m" stretched disabled={busy}
                  onClick={() => act('tree_allocate', { node_id: node.id }, `Узел «${node.name}» взят.`)}>
                  Взять узел
                </Button>
              )}
            </>
          )}
        </div>
      )}

      {notice && (
        <div className={`guild-tree__toast ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`}
          {...stop} onClick={() => setNotice(null)}>
          {notice.text}
        </div>
      )}

      <div className="guild-tree__zoom" {...stop}>
        <button type="button" onClick={() => zoom(1.3)}>+</button>
        <button type="button" onClick={() => zoom(1 / 1.3)}>−</button>
        <button type="button" onClick={() => setView(HOME)}>◎</button>
      </div>
    </div>
  );
}
