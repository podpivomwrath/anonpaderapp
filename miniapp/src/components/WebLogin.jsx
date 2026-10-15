import { useEffect, useState } from 'react';
import { Button, Div, Placeholder, Spinner } from '@vkontakte/vkui';
import { getWebConfig, setWebToken, webLogin } from '../api.js';

/**
 * Вход на сайте (monolithgame.ru) через VK ID - OAuth 2.1 с PKCE
 * (2026-10-15). Внутри VK этот экран не появляется: там вход по
 * launch-параметрам, как и раньше.
 *
 * code_verifier и state живут в sessionStorage до возврата с id.vk.com;
 * обмен кода - на сервере (/api/web/login), он и выдаёт ключ сессии.
 */

const VERIFIER_KEY = 'vkid_verifier';
const STATE_KEY = 'vkid_state';

function redirectUri() {
  return `${window.location.origin}/`;
}

function randomString(bytes = 48) {
  const data = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...data)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function challengeOf(verifier) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

async function startLogin(clientId) {
  const verifier = randomString();
  const state = randomString(16);
  sessionStorage.setItem(VERIFIER_KEY, verifier);
  sessionStorage.setItem(STATE_KEY, state);
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: clientId,
    redirect_uri: redirectUri(),
    state,
    code_challenge: await challengeOf(verifier),
    code_challenge_method: 'S256',
    scope: 'vkid.personalize',
  });
  window.location.href = `https://id.vk.com/authorize?${params}`;
}

/** Возврат с id.vk.com: true - вход выполнен, false - это не возврат. */
export async function completeWebLogin() {
  const search = new URLSearchParams(window.location.search);
  const code = search.get('code');
  if (!code) return false;
  const state = search.get('state');
  const verifier = sessionStorage.getItem(VERIFIER_KEY);
  const expected = sessionStorage.getItem(STATE_KEY);
  sessionStorage.removeItem(VERIFIER_KEY);
  sessionStorage.removeItem(STATE_KEY);
  // Код одноразовый: убираем его из адреса сразу, чтобы обновление
  // страницы не пыталось войти повторно.
  window.history.replaceState(null, '', '/');
  if (!verifier || state !== expected) throw new Error('state_mismatch');
  const res = await webLogin({
    code, state, code_verifier: verifier, device_id: search.get('device_id') || '', redirect_uri: redirectUri(),
  });
  setWebToken(res.token);
  return true;
}

const ERRORS = {
  state_mismatch: 'Вход прервался. Попробуй ещё раз.',
  login_failed: 'VK не подтвердил вход. Попробуй ещё раз.',
  web_login_disabled: 'Вход на сайте ещё не включён.',
};

export default function WebLogin({ error }) {
  const [clientId, setClientId] = useState(undefined);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getWebConfig().then((c) => setClientId(c.vk_id_client_id || null)).catch(() => setClientId(null));
  }, []);

  return (
    <Placeholder
      icon={<div style={{ fontSize: 56 }}>🜂</div>}
      header="Monolith"
      action={clientId === undefined ? <Spinner size="m" /> : clientId ? (
        <Button size="l" loading={busy} onClick={() => { setBusy(true); startLogin(clientId); }}>
          Войти через VK ID
        </Button>
      ) : null}
    >
      Тот же персонаж, что и в игре ВКонтакте: войди через свой аккаунт VK.
      {error && <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{ERRORS[error] || 'Не удалось войти.'}</Div>}
      {clientId === null && <Div style={{ opacity: 0.7 }}>{ERRORS.web_login_disabled}</Div>}
    </Placeholder>
  );
}
