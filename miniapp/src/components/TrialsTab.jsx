import { useEffect, useState } from 'react';
import { Group, Header, Div, Text, Spinner, Placeholder } from '@vkontakte/vkui';
import { getTrials } from '../api.js';

export default function TrialsTab() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error

  useEffect(() => {
    setStatus('loading');
    getTrials()
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
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>Не удалось загрузить испытания.</Placeholder>;
  }

  if (!data.subclass) {
    return (
      <Placeholder icon={<div style={{ fontSize: 48 }}>📖</div>}>
        Путь ещё не выбран. Хранитель Списков предложит «Раскол пути» с 30 уровня — за золото, в городе.
      </Placeholder>
    );
  }

  const unlocked = data.trials.filter((t) => t.unlocked);
  const locked = data.trials.filter((t) => !t.unlocked);

  return (
    <>
      {locked.length > 0 && (
        <Group header={<Header>Испытания ({locked.length})</Header>}>
          {locked.map((t) => (
            <div className="stat-row" key={t.id}>
              <div>
                <div className="stat-row__label">🔒 {t.buff_name}</div>
                <Text style={{ opacity: 0.7, fontSize: 13 }}>{t.text}</Text>
              </div>
              <span className="stat-row__value">
                {t.progress}/{t.target}
              </span>
            </div>
          ))}
        </Group>
      )}
      {unlocked.length > 0 && (
        <Group header={<Header>Открыто ({unlocked.length})</Header>}>
          {unlocked.map((t) => (
            <div className="stat-row" key={t.id}>
              <span className="stat-row__label">🔓 {t.buff_name}</span>
            </div>
          ))}
        </Group>
      )}
    </>
  );
}
