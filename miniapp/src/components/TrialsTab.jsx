import { useEffect, useState } from 'react';
import { Group, Header, Placeholder } from '@vkontakte/vkui';
import { getTrials } from '../api.js';
import Skeleton from './Skeleton.jsx';
import { Bar, Empty, SectionHead } from './ui.jsx';

// Испытания подкласса (2026-10-22): карточки с полоской прогресса, нажатие
// раскрывает эффект бафа. Открытые - отдельной сеткой ниже.

function TrialCard({ t, open, onToggle }) {
  return (
    <div className={`trial-card${t.unlocked ? ' trial-card--open' : ''}`}>
      <button type="button" className="trial-card__row" onClick={onToggle} aria-expanded={open}>
        <span className="trial-card__seal" aria-hidden="true">{t.unlocked ? '✦' : '🔒'}</span>
        <span className="trial-card__text">
          <b className="trial-card__name">{t.buff_name}{!t.implemented && ' ⚙️'}</b>
          {!t.unlocked && <small className="trial-card__task">{t.text}</small>}
          {t.unlocked && <small className="trial-card__task">{t.category}</small>}
          {!t.unlocked && (
            <span className="daily-card__progress">
              <Bar value={t.progress} max={t.target} tone="blue" thin />
              <span className="daily-card__count">{Math.min(t.progress, t.target)}/{t.target}</span>
            </span>
          )}
        </span>
        <span className={open ? 'chronicle-row__arrow chronicle-row__arrow--open' : 'chronicle-row__arrow'}>›</span>
      </button>
      <div className={open ? 'fold fold--open' : 'fold'} aria-hidden={!open}>
        <div className="fold__inner">
          <div className="trial-card__detail">
            {t.implemented
              ? (t.description && <p>{t.description}</p>)
              : <p className="trial-card__wip">⚙️ В разработке - эффект пока не действует в бою.</p>}
            {!t.unlocked && <small>Категория: {t.category}</small>}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function TrialsTab() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    setStatus('loading');
    getTrials()
      .then((res) => {
        setData(res);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }, []);

  if (status === 'loading') return <Skeleton />;

  if (status === 'error') {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>Не удалось загрузить испытания.</Placeholder>;
  }

  if (!data.subclass) {
    return (
      <Group>
        <Empty icon="📖">Твоя Метка ещё не обрела форму. Возвращайся, когда кровь потребует имени.</Empty>
      </Group>
    );
  }

  const toggle = (id) => setExpandedId((cur) => (cur === id ? null : id));

  const unlocked = data.trials.filter((t) => t.unlocked);
  const locked = data.trials.filter((t) => !t.unlocked);

  return (
    <>
      <SectionHead
        kind="trials" icon="✦" value={`${unlocked.length}/${data.trials.length}`} label="испытаний пройдено"
      />
      {locked.length > 0 && (
        <Group header={<Header>Испытания ({locked.length})</Header>}>
          <div className="card-list">
            {locked.map((t) => (
              <TrialCard key={t.id} t={t} open={expandedId === t.id} onToggle={() => toggle(t.id)} />
            ))}
          </div>
        </Group>
      )}
      {unlocked.length > 0 && (
        <Group header={<Header>Открыто ({unlocked.length})</Header>}>
          <div className="card-list">
            {unlocked.map((t) => (
              <TrialCard key={t.id} t={t} open={expandedId === t.id} onToggle={() => toggle(t.id)} />
            ))}
          </div>
        </Group>
      )}
    </>
  );
}
