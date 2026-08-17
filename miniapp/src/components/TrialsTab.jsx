import { useEffect, useState } from 'react';
import { Group, Header, Div, Text, Spinner, Placeholder } from '@vkontakte/vkui';
import { getTrials } from '../api.js';

function BuffDetail({ trial }) {
  return (
    <Div className="buff-detail">
      <Text style={{ opacity: 0.7, fontSize: 13 }}>Категория: {trial.category}</Text>
      {trial.implemented ? (
        trial.description && (
          <Text style={{ fontSize: 14, marginTop: 4 }}>{trial.description}</Text>
        )
      ) : (
        <Text style={{ fontSize: 14, marginTop: 4, opacity: 0.7 }}>⚙️ В разработке — эффект пока не действует в бою.</Text>
      )}
      <Text style={{ opacity: 0.7, fontSize: 13, marginTop: 6 }}>
        Статус: {trial.unlocked ? 'открыт' : 'не открыт'}
      </Text>
      {!trial.unlocked && (
        <Text style={{ opacity: 0.7, fontSize: 13 }}>
          Испытание: {trial.text} ({trial.progress}/{trial.target})
        </Text>
      )}
    </Div>
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
        Твоя Метка ещё не обрела форму. Возвращайся, когда кровь потребует имени.
      </Placeholder>
    );
  }

  const toggle = (id) => setExpandedId((cur) => (cur === id ? null : id));

  const unlocked = data.trials.filter((t) => t.unlocked);
  const locked = data.trials.filter((t) => !t.unlocked);

  return (
    <>
      {locked.length > 0 && (
        <Group header={<Header>Испытания ({locked.length})</Header>}>
          {locked.map((t) => (
            <div key={t.id}>
              <div className="stat-row" style={{ cursor: 'pointer' }} onClick={() => toggle(t.id)}>
                <div>
                  <div className="stat-row__label">
                    🔒 {t.buff_name}
                    {!t.implemented && ' ⚙️'}
                  </div>
                  <Text style={{ opacity: 0.7, fontSize: 13 }}>{t.text}</Text>
                </div>
                <span className="stat-row__value">
                  {t.progress}/{t.target}
                </span>
              </div>
              {expandedId === t.id && <BuffDetail trial={t} />}
            </div>
          ))}
        </Group>
      )}
      {unlocked.length > 0 && (
        <Group header={<Header>Открыто ({unlocked.length})</Header>}>
          {unlocked.map((t) => (
            <div key={t.id}>
              <div className="stat-row" style={{ cursor: 'pointer' }} onClick={() => toggle(t.id)}>
                <span className="stat-row__label">
                  🔓 {t.buff_name}
                  {!t.implemented && ' ⚙️'}
                </span>
              </div>
              {expandedId === t.id && <BuffDetail trial={t} />}
            </div>
          ))}
        </Group>
      )}
    </>
  );
}
