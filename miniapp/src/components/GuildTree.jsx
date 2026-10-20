import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Div, Placeholder, Spinner } from '@vkontakte/vkui';
import { getGuildTree, guildAction } from '../api.js';
import { ARM_IMAGES, ARM_POINTS, ROOT_POINT, STAGE_H, STAGE_W, armOf } from './guildTreeLayout.js';

// Древо гильдии - созвездия (2026-10-20, решение владельца). Раньше всё
// древо было одной картой с перетаскиванием и щипком, и в VK жесты
// путались: тап считался сдвигом, щипок перехватывало приложение. Теперь
// на экране одна рука ветви - картинка-силуэт и 21 звезда по её контуру,
// всё видно целиком: ни прокрутки, ни масштаба, только нажатия.
//
// Координаты и связи узлов - с сервера (game/guild/tree.py), положение
// звёзд на картинке - guildTreeLayout.js.

const BRANCH_COLOR = { war: '#d9483b', craft: '#e8a33d', kin: '#5fa8d9' };
const RADIUS = { root: 30, small: 15, notable: 23, keystone: 34 };
//: Невидимая зона нажатия вокруг звезды - палец больше звезды.
const HIT = 40;
const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');
const KIND_TITLES = { root: 'начало ветви', small: 'малый узел', notable: 'средний узел', keystone: 'ключевой узел' };
const ARM_TITLES_FALLBACK = ['Рука 1', 'Рука 2', 'Рука 3'];

export default function GuildTree({ onChanged }) {
  const [tree, setTree] = useState(null);
  const [status, setStatus] = useState('loading');
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [info, setInfo] = useState(false);
  const [branch, setBranch] = useState('war');
  const [arm, setArm] = useState(0);
  // Ширина экрана руки: картинка 2:3 целиком влезает до низа окна, сколько
  // бы места ни заняли шапка и вкладки над ней (на телефоне их много).
  const stage = useRef(null);
  const [stageWidth, setStageWidth] = useState(null);

  const load = useCallback(() => {
    getGuildTree()
      .then((data) => { setTree(data); setStatus('ready'); })
      .catch(() => setStatus('error'));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const measure = () => {
      const el = stage.current;
      if (!el) return;
      const top = el.getBoundingClientRect().top + window.scrollY;
      const room = window.innerHeight - top - 12;
      setStageWidth(Math.max(220, Math.floor(room * 2 / 3)));
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
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
  const color = BRANCH_COLOR[branch];
  const rootId = `${branch}:root`;
  const armIds = ARM_POINTS[branch][arm].map((_, i) => `${branch}:${arm}:${i}`);
  const point = Object.fromEntries(armIds.map((id, i) => [id, ARM_POINTS[branch][arm][i]]));
  point[rootId] = ROOT_POINT;
  const armTitle = (b, a) => byId[`${b}:${a}:20`]?.name || ARM_TITLES_FALLBACK[a];

  // Перемычка ветви (узел между руками 1 и 2) - обычная звезда сбоку от
  // своего соседа на обеих руках: без неё узел не взять. Связи в соседние
  // руки не рисуем (2026-10-20, владелец: кнопки перехода мешали) - каждая
  // рука и так растёт от корня.
  const outside = [];
  armIds.forEach((id) => {
    (byId[id]?.links || []).forEach((linked) => {
      if (armOf(linked) !== null || linked === rootId || outside.some((o) => o.id === linked)) return;
      const [x, y] = point[id];
      outside.push({ id: linked, from: id, x: arm === 0 ? Math.min(x + 170, 930) : Math.max(x - 170, 70), y: y - 40 });
    });
  });
  outside.forEach((o) => { point[o.id] = [o.x, o.y]; });

  const edges = [[rootId, armIds[0]]];
  for (let i = 1; i < armIds.length; i += 1) edges.push([armIds[i - 1], armIds[i]]);
  outside.forEach((o) => edges.push([o.from, o.id]));

  const pick = (id) => {
    setInfo(false);
    setSelected(id);
  };

  /** Почему узел сейчас не взять - или null, если можно. */
  const lack = (n) => {
    if (!tree.can_edit) return 'Брать узлы могут глава и казначеи.';
    if (!n.available) return 'Сначала возьми соседний узел - древо растёт от уже взятых.';
    if (tree.points_available < n.points) return `Не хватает очков древа: нужно ${n.points}. Очки дают уровни гильдии.`;
    if (tree.treasury_gold < n.gold) return `В казне не хватает золота: нужно ${money(n.gold)}.`;
    return null;
  };

  const taken = (b) => tree.nodes.filter((n) => n.branch === b && n.taken && n.kind !== 'root').length;

  return (
    <div className="guild-tree">
      <div className="guild-tree__tabs">
        {Object.entries(tree.branches).map(([id, title]) => (
          <button type="button" key={id}
            className={`guild-tree__tab${id === branch ? ' guild-tree__tab--on' : ''}`}
            style={{ '--branch': BRANCH_COLOR[id] }}
            onClick={() => { setBranch(id); setArm(0); setSelected(null); }}>
            {title} <span>{taken(id)}</span>
          </button>
        ))}
      </div>
      <div className="guild-tree__arms">
        {[0, 1, 2].map((a) => (
          <button type="button" key={a}
            className={`guild-tree__arm${a === arm ? ' guild-tree__arm--on' : ''}`}
            style={{ '--branch': color }}
            onClick={() => { setArm(a); setSelected(null); }}>
            {armTitle(branch, a)}
          </button>
        ))}
      </div>

      <div className="guild-tree__bar">
        <span>Очков: <b>{tree.points_available}</b> · узлов {tree.taken}/{tree.total_nodes}</span>
        <button type="button" onClick={() => { setInfo(!info); setSelected(null); }}>
          {info ? '✕' : 'Итоги'}
        </button>
      </div>

      <div className="guild-tree__stage" ref={stage}
        style={stageWidth ? { width: `min(100%, ${stageWidth}px)` } : undefined}>
        <img className="guild-tree__art" src={ARM_IMAGES[branch][arm]} alt="" draggable="false" />
        <svg viewBox={`0 0 ${STAGE_W} ${STAGE_H}`} className="guild-tree__svg">
          {edges.map(([a, b]) => {
            const lit = (id) => byId[id]?.kind === 'root' || byId[id]?.taken;
            const on = lit(a) && lit(b);
            const [x1, y1] = point[a];
            const [x2, y2] = point[b];
            return (
              <line key={`${a}|${b}`} x1={x1} y1={y1} x2={x2} y2={y2}
                className={on ? 'guild-tree__edge guild-tree__edge--on' : 'guild-tree__edge'}
                style={on ? { stroke: color } : undefined} />
            );
          })}
          {Object.entries(point).map(([id, [x, y]]) => {
            const n = byId[id];
            if (!n) return null;
            return (
              <g key={id} className="guild-tree__star" onClick={() => pick(id)}>
                <circle cx={x} cy={y} r={HIT} fill="transparent" />
                <circle cx={x} cy={y} r={RADIUS[n.kind]}
                  className={[
                    'guild-tree__node',
                    n.taken || n.kind === 'root' ? 'guild-tree__node--taken' : '',
                    n.available ? 'guild-tree__node--available' : '',
                    selected === id ? 'guild-tree__node--selected' : '',
                  ].join(' ')}
                  style={{ '--branch': color }} />
              </g>
            );
          })}
        </svg>

        {info && (
          <div className="guild-tree__card guild-tree__card--top">
            <p className="guild-tree__card-title">Древо гильдии</p>
            <p className="craft-hint">
              Три ветви по три руки. Узел берут рядом с уже взятым: малый - 1 очко, средний - 2, ключевой - 3,
              плюс золото из казны{tree.can_edit ? ` (в казне ${money(tree.treasury_gold)})` : ''}. Каждая рука растёт
              от начала ветви, перемычка - звезда между первыми двумя руками. Очки дают уровни гильдии. Брать могут глава и казначеи.
            </p>
            {tree.effects.length === 0
              ? <p className="guild-line">Узлов пока нет.</p>
              : tree.effects.map((e) => <p key={e} className="guild-line">• {e}</p>)}
          </div>
        )}

        {node && !info && (
          <div className="guild-tree__card">
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
            onClick={() => setNotice(null)}>
            {notice.text}
          </div>
        )}
      </div>
    </div>
  );
}
