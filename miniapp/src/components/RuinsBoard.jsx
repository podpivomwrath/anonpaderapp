import { useEffect, useState } from 'react';
import { Group, Header, Placeholder } from '@vkontakte/vkui';
import { getRuinsTop } from '../api.js';
import ClassIcon from './ClassIcon.jsx';
import Skeleton from './Skeleton.jsx';
import { Empty, SectionHead } from './ui.jsx';
import { useBackClose } from '../backStack.js';
import { usePlayerLook } from './PlayerLook.jsx';

// Топ руин (2026-11-13): строка - забег, а не игрок. В группе перечислены
// все участники; бледное имя - у игрока место выше, в другой строке.
// Правила и тексты приходят с сервера (services/ruins_top_service.py).

// Нажатие на участника - окно игрока: надетые вещи и руны (2026-11-14).
function Member({ m, solo, onLook }) {
  return (
    <button type="button" className={`ruins-member${m.best ? '' : ' ruins-member--pale'}`}
      onClick={() => onLook?.(m.id, m.name)} disabled={!m.id}>
      <ClassIcon subclass={m.subclass} baseClass={m.base_class} crown={m.crown_frame || null} size={solo ? 40 : 28} />
      <span className="top-who">
        <span className="top-name">{m.badge ? `${m.badge} ` : ''}{m.name}</span>
        {solo && m.title && (
          <span className={`top-title title-tier title-tier--${m.title_tier || 'common'}`}>«{m.title}»</span>
        )}
      </span>
    </button>
  );
}

function RuinsRow({ r, onLook }) {
  const solo = r.members.length === 1;
  const me = r.members.some((m) => m.me && m.best);
  return (
    <div className={`stat-row top-row ruins-row${me ? ' top-row--me' : ''}`}>
      <span className="stat-row__label">
        <span className="top-rank">{r.rank}</span>
        <span className="ruins-team">
          {r.members.map((m) => <Member key={m.name} m={m} solo={solo} onLook={onLook} />)}
        </span>
      </span>
      <span className="stat-row__value">{r.value}</span>
    </div>
  );
}

// Мои забеги (2026-11-14, владелец): последние свои - и в одиночку, и в группе.
function MyRun({ run }) {
  return (
    <div className="ruins-run">
      <div className="ruins-run__head">
        <b>{run.value}</b>
        <span className="ruins-run__when">{run.when}</span>
      </div>
      <span className="ruins-run__line">
        {run.party.length ? `с ${run.party.join(', ')}` : 'в одиночку'}
        {run.outcome ? ` · ${run.outcome}` : ''}
        {run.length ? ` · ${run.length}` : ''}
      </span>
      {run.bag && <span className="ruins-run__bag">{run.bag}</span>}
    </div>
  );
}

export default function RuinsBoard({ board }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [helpOpen, setHelpOpen] = useState(false);
  const [look, lookSheet] = usePlayerLook();
  useBackClose(() => setHelpOpen(false), helpOpen);

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    getRuinsTop(board)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [board]);

  if (status === 'loading') return <Skeleton />;
  if (status === 'error' || !data) {
    return (
      <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>
        Не удалось загрузить топ.
      </Placeholder>
    );
  }

  const top = data.top || [];
  return (
    <>
      <SectionHead
        kind="tops" icon="🏛"
        value={data.my_rank ? `#${data.my_rank}` : '-'}
        label={data.my_rank ? `ваше место из ${data.total}` : `вас нет в топе · всего ${data.total}`}
        aside={(
          <button type="button" className="top-help" onClick={() => setHelpOpen(true)} aria-label="Правила топа руин">
            ?
          </button>
        )}
      />
      <Group header={<Header>Неделя {data.week}</Header>}>
        {data.record && (
          <p className="ruins-record">
            <span className="craft-hint">Рекорд за всё время:</span> {data.record.value} -{' '}
            {data.record.members.map((m) => m.name).join(', ')}
          </p>
        )}
        {top.length === 0 ? (
          <Empty icon="🏛">На этой неделе ещё никто не прошёл ни одного этажа.</Empty>
        ) : (
          <div className="top-list">
            {top.map((r) => <RuinsRow key={r.rank} r={r} onLook={look} />)}
          </div>
        )}
      </Group>
      {data.me && (
        <div className="top-mine">
          <RuinsRow r={data.me} onLook={look} />
        </div>
      )}
      {data.my_runs && (
        <Group header={<Header>Мои забеги</Header>}>
          {data.my_runs.length === 0 ? (
            <Empty icon="🕳">Вы ещё не спускались в руины.</Empty>
          ) : (
            <div className="ruins-runs">
              {data.my_runs.map((run) => <MyRun key={run.id} run={run} />)}
            </div>
          )}
        </Group>
      )}
      {helpOpen && (
        <>
          <div className="nav-scrim" onClick={() => setHelpOpen(false)} aria-hidden="true" />
          <div className="crown-sheet top-help-sheet" role="dialog" aria-label="Топ руин">
            <b className="top-help-sheet__title">Топ руин</b>
            <p className="top-help-sheet__line"><span className="craft-hint">Место в топе:</span> {data.rule}</p>
            <p className="top-help-sheet__line"><span className="craft-hint">Награды:</span> {data.prizes}</p>
            <div className="trade-dest__actions">
              <button type="button" className="top-help-sheet__close" onClick={() => setHelpOpen(false)}>Понятно</button>
            </div>
          </div>
        </>
      )}
      {lookSheet}
    </>
  );
}
