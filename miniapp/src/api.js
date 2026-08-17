/**
 * Все запросы к бэкенду мини-аппа. Подписанные launch-параметры VK приходят
 * в query-строке при открытии мини-аппа (window.location.search) — сервер
 * проверяет подпись на КАЖДОМ запросе, поэтому просто перекладываем эту
 * строку в каждый вызов как есть, ничего не добавляя и не подделывая.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
const LAUNCH_PARAMS = window.location.search; // включает ведущий "?" либо пуст

function buildUrl(path) {
  // Патч 34, ч.2, доп. фикс: слепая конкатенация path + LAUNCH_PARAMS ломалась,
  // если path уже нёс свой "?" (searchAdminPlayers/getAdminJournal) — получалось
  // "...?q=X?vk_user_id=...", браузер считает query-строкой только часть ДО
  // второго "?", vk_user_id пропадал из распарсенных параметров целиком, и
  // подпись launch-параметров на сервере переставала сходиться (invalid_signature).
  if (!LAUNCH_PARAMS) return `${API_BASE}/api/miniapp${path}`;
  const launchQuery = LAUNCH_PARAMS.slice(1); // без ведущего "?"
  const separator = path.includes('?') ? '&' : '?';
  return `${API_BASE}/api/miniapp${path}${separator}${launchQuery}`;
}

async function request(path, options) {
  const url = buildUrl(path);
  // ngrok-skip-browser-warning: без него бесплатный ngrok-туннель (альфа-тест,
  // см. README) отдаёт HTML-заглушку вместо JSON на первый запрос из вебвью.
  // Безвредно для любого другого хостинга — заголовок просто игнорируется.
  const res = await fetch(url, {
    ...options,
    headers: { 'ngrok-skip-browser-warning': 'true', ...(options?.headers || {}) },
  });
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

export function getDailies() {
  return request('/dailies');
}

// --- Админка (патч 27) — доступна, только если character.is_admin; сервер
// перепроверяет права на каждом из этих вызовов независимо (403 иначе). ---

export function getAdminOverview() {
  return request('/admin/overview');
}

export function searchAdminPlayers(query) {
  return request(`/admin/search?q=${encodeURIComponent(query)}`);
}

export function getAdminPlayer(characterId) {
  return request(`/admin/player/${characterId}`);
}

export function postAdminAction(characterId, action, params = {}) {
  return request(`/admin/player/${characterId}/action`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...params }),
  });
}

export function getAdminJournal(limit = 50, offset = 0) {
  return request(`/admin/journal?limit=${limit}&offset=${offset}`);
}

export function getAdminBugReports(status) {
  return request(`/admin/bug_reports${status ? `?status=${status}` : ''}`);
}

export function setAdminBugReportStatus(reportId, status) {
  return request(`/admin/bug_reports/${reportId}/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status }),
  });
}

// --- Промокоды (патч 50) ---

export function getAdminPromoCodes() {
  return request('/admin/promo_codes');
}

export function createAdminPromoCode(params) {
  return request('/admin/promo_codes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
}

export function deleteAdminPromoCode(promoId) {
  return request(`/admin/promo_codes/${promoId}`, { method: 'DELETE' });
}

export function getAdminPromoCodeActivations(promoId) {
  return request(`/admin/promo_codes/${promoId}/activations`);
}

// --- Карта (патч 29) ---

export function getMapState() {
  return request('/map/state');
}

export function sendMountFromMap(mountId, x, y) {
  return request('/map/send_mount', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mount_id: mountId, x, y }),
  });
}
