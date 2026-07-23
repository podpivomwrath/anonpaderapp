/**
 * Все запросы к бэкенду мини-аппа. Подписанные launch-параметры VK приходят
 * в query-строке при открытии мини-аппа (window.location.search) — сервер
 * проверяет подпись на КАЖДОМ запросе, поэтому просто перекладываем эту
 * строку в каждый вызов как есть, ничего не добавляя и не подделывая.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
const LAUNCH_PARAMS = window.location.search; // включает ведущий "?" либо пуст

async function request(path, options) {
  const url = `${API_BASE}/api/miniapp${path}${LAUNCH_PARAMS}`;
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({ error: 'bad_response' }));
  if (!res.ok) {
    throw new Error(data.error || `http_${res.status}`);
  }
  return data;
}

export function getCharacter() {
  return request('/character');
}

export function submitStats(increments) {
  return request('/stats', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(increments),
  });
}
