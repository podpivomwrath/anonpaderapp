import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Div, Group, Header, Placeholder, Spinner } from '@vkontakte/vkui';
import { getGuildTree, guildAction } from '../api.js';

// Древо гильдии: три ветви, почти двести узлов. Рисуется SVG целиком, а
// смотрится как карта - перетаскиванием и масштабом. Координаты и связи
// приходят с сервера (game/guild/tree.py): клиент ничего не пересчитывает.

const BRANCH_COLOR = { war: '#d9483b', craft: '#e8a33d', kin: '#5fa8d9' };
const RADIUS = { root: 22, small: 9, notable: 15, keystone: 22 };
const WORLD = 1800;
const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');

export default function GuildTree({ onChanged }) {
  const [tree, setTree] = useState(null);
  const [status, setStatus] = useState('loading');
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [view, setView] = useState({ x: 0, y: 0, scale: 0.35 });
  const drag = useRef(null);

  const load = useCallback(() => {
    getGuildTree()
      .then((data) => { setTree(data); setStatus('ready'); })
      .catch(() => setStatus('error'));
  }, []);
  useEffect(() => { load(); }, [load]);

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

  const onPointerDown = (e) => {
    drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true;
    // Пиксели экрана -> единицы viewBox: видимая ширина мира / ширина окна.
    const width = e.currentTarget.getBoundingClientRect().width || 1;
    setView((v) => {
      const k = WORLD / v.scale / 2 / width;
      return { ...v, x: d.vx + dx * k, y: d.vy + dy * k };
    });
  };
  const onPointerUp = () => { setTimeout(() => { drag.current = null; }, 0); };
  const zoom = (k) => setView((v) => ({ ...v, scale: Math.min(2.5, Math.max(0.2, v.scale * k)) }));
  const onWheel = (e) => zoom(e.deltaY < 0 ? 1.15 : 1 / 1.15);
  const pick = (id) => { if (!drag.current?.moved) setSelected(id); };

  const vbSize = WORLD / view.scale / 2;
  const viewBox = `${-view.x - vbSize / 2} ${-view.y - vbSize / 2} ${vbSize} ${vbSize}`;

  return (
    <>
      <Group header={<Header>🌳 Древо гильдии</Header>}>
        <Div>
          <p className="guild-line">
            Взято узлов: {tree.taken}/{tree.total_nodes} · свободных очков: {tree.points_available}
            {tree.can_edit ? ` · в казне ${money(tree.treasury_gold)} 💰` : ''}
          </p>
          <p className="craft-hint">
            Очки дают уровни гильдии. Узел берут рядом с уже взятым. Малый - 1 очко, средний - 2, ключевой - 3,
            плюс золото из казны. Брать могут глава и казначеи.
          </p>
          <div className="guild-tree__legend">
            {Object.entries(tree.branches).map(([id, title]) => (
              <span key={id}><i style={{ background: BRANCH_COLOR[id] }} /> {title}</span>
            ))}
          </div>
        </Div>
        <div
          className="guild-tree"
          onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp} onWheel={onWheel}
        >
          <svg viewBox={viewBox} className="guild-tree__svg">
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
                onClick={() => pick(n.id)}
              />
            ))}
          </svg>
          <div className="guild-tree__zoom">
            <button type="button" onClick={() => zoom(1.3)}>+</button>
            <button type="button" onClick={() => zoom(1 / 1.3)}>−</button>
            <button type="button" onClick={() => setView({ x: 0, y: 0, scale: 0.35 })}>◎</button>
          </div>
        </div>
      </Group>

      {notice && (
        <Div className={`craft-notice ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`} onClick={() => setNotice(null)}>
          {notice.text}
        </Div>
      )}

      {node && (
        <Group header={<Header>{node.name}</Header>}>
          <Div>
            <p className="craft-hint">
              {tree.branches[node.branch]} · {{ root: 'начало ветви', small: 'малый узел', notable: 'средний узел', keystone: 'ключевой узел' }[node.kind]}
            </p>
            <p className="guild-line">{node.description}</p>
            {node.kind !== 'root' && !node.taken && (
              <p className="craft-hint">Цена: {node.points} очк. и {money(node.gold)} золота.</p>
            )}
            {node.taken && node.kind !== 'root' && <p className="guild-line">✅ Взят</p>}
            {tree.can_edit && node.available && (
              <Button size="m" disabled={busy} onClick={() => act('tree_allocate', { node_id: node.id }, `Узел «${node.name}» взят.`)}>
                Взять узел
              </Button>
            )}
          </Div>
        </Group>
      )}

      {tree.effects.length > 0 && (
        <Group header={<Header>Итого с древа</Header>}>
          <Div>{tree.effects.map((e) => <p key={e} className="guild-line">• {e}</p>)}</Div>
        </Group>
      )}
    </>
  );
}
