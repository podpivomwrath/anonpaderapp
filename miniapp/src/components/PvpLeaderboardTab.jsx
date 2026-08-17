import { useEffect, useState } from 'react';
import { Group, Header, Div, Spinner, Placeholder } from '@vkontakte/vkui';
import { getPvpLeaderboard } from '../api.js';

export default function PvpLeaderboardTab() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error

  useEffect(() => {
    setStatus('loading');
    getPvpLeaderboard()
      .then((res) => {
        setData(res);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }, []);

  if (status === 'loading') {
    return (
      <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
        <Spinner size="l" />
      </Div>
    );
  }

  if (status === 'error') {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>Не удалось загрузить топ.</Placeholder>;
  }

  const inTop = data.top.some((e) => e.rank === data.you.rank);

  return (
    <Group header={<Header>🏆 Лучшие из Меченых</Header>}>
      {data.top.map((e) => (
        <div className="stat-row" key={e.rank}>
          <span className="stat-row__label">
            {e.rank}. {e.premium && '💠 '}{e.name}
          </span>
          <span className="stat-row__value">
            {e.wins} / {e.losses}
          </span>
        </div>
      ))}
      {!inTop && (
        <div className="stat-row" style={{ opacity: 0.8, borderTop: '1px solid var(--vkui--color_separator_primary)' }}>
          <span className="stat-row__label">Ты: {data.you.premium && '💠 '}{data.you.rank} место</span>
          <span className="stat-row__value">
            {data.you.wins} / {data.you.losses}
          </span>
        </div>
      )}
    </Group>
  );
}
