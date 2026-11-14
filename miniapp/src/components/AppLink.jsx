import { useEffect, useState } from 'react';
import { Button, Div, Group, Header, SimpleCell } from '@vkontakte/vkui';
import { createAppCode, getAppDevices, revokeAppDevice } from '../api.js';

// Приложение «Монолит» для ПК и Android (2026-11-15, владелец): вход без
// VK ID - код отсюда вводят в приложении (services/app_link_service.py).
// До выхода приложения раздел видит только владелец (SettingsTab).

const PLATFORM = { windows: '💻', android: '📱' };

function left(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function seen(ts) {
  if (!ts) return 'ещё не заходило';
  const d = new Date(ts * 1000);
  return `заходило ${d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })} в ${d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}`;
}

export default function AppLink() {
  const [code, setCode] = useState(null);       // {code, expires_at}
  const [devices, setDevices] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [, setTick] = useState(0);

  const loadDevices = () => getAppDevices().then((r) => setDevices(r.devices)).catch(() => setDevices([]));
  useEffect(() => { loadDevices(); }, []);

  const secondsLeft = code ? code.expires_at - Date.now() / 1000 : 0;
  useEffect(() => {
    if (!code) return undefined;
    const id = setInterval(() => {
      setTick((t) => t + 1);
      // Пока код на экране, проверяем, не вошли ли им: новое устройство появится в списке.
      if (Math.floor(Date.now() / 1000) % 5 === 0) loadDevices();
    }, 1000);
    return () => clearInterval(id);
  }, [code]);

  const makeCode = () => {
    setBusy(true);
    setError(null);
    createAppCode()
      .then((r) => setCode(r))
      .catch(() => setError('Не удалось получить код. Попробуйте ещё раз.'))
      .finally(() => setBusy(false));
  };

  const revoke = (id) => {
    revokeAppDevice(id).then(loadDevices).catch(() => setError('Не удалось отключить устройство.'));
  };

  return (
    <Group header={<Header>Приложение для ПК и Android</Header>}>
      <Div className="app-link">
        <p className="app-link__text">
          Тот же персонаж, что здесь, в отдельном приложении. Нажмите кнопку и введите код
          в приложении. Код одноразовый и действует 10 минут.
        </p>
        {code && secondsLeft > 0 ? (
          <div className="app-link__code">
            <b className="app-link__digits">{code.code}</b>
            <small>осталось {left(secondsLeft)}</small>
          </div>
        ) : (
          <Button size="l" stretched mode="primary" loading={busy} onClick={makeCode}>
            Авторизовать приложение
          </Button>
        )}
        {code && secondsLeft <= 0 && <small className="app-link__note">Код истёк, получите новый.</small>}
        {error && <small className="app-link__note">{error}</small>}
      </Div>
      {devices && devices.length > 0 && devices.map((d) => (
        <SimpleCell
          key={d.id} multiline before={<span aria-hidden="true">{PLATFORM[d.platform] || '🖥'}</span>}
          subtitle={seen(d.last_seen_at)}
          after={<Button size="s" mode="secondary" onClick={() => revoke(d.id)}>Отключить</Button>}
        >
          {d.name}
        </SimpleCell>
      ))}
    </Group>
  );
}
