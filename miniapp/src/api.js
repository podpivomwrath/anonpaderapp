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

export function getTrials() {
  return request('/trials');
}

export function getInventory() {
  return request('/inventory');
}

export function equipItem(itemId) {
  return request('/equip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId }),
  });
}

export function getPresets() {
  return request('/presets');
}

export function savePreset(name, buffIds, presetId) {
  return request('/presets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, buff_ids: buffIds, preset_id: presetId ?? null }),
  });
}

export function switchPreset(presetId) {
  return request('/presets/switch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preset_id: presetId }),
  });
}

export function buyPresetSlot() {
  return request('/presets/buy_slot', { method: 'POST' });
}

export function getPvpLeaderboard() {
  return request('/pvp_leaderboard');
}
