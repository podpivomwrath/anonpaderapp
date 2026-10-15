/**
 * Все запросы к бэкенду мини-аппа. Подписанные launch-параметры VK приходят
 * в query-строке при открытии мини-аппа (window.location.search) - сервер
 * проверяет подпись на КАЖДОМ запросе, поэтому просто перекладываем эту
 * строку в каждый вызов как есть, ничего не добавляя и не подделывая.
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';
const SEARCH = new URLSearchParams(window.location.search);
// Внутри VK в адресе подписанные launch-параметры. Без них это сайт
// (monolithgame.ru, 2026-10-15): вход через VK ID и ключ сессии в
// Authorization - те же запросы, те же данные.
export const IN_VK = SEARCH.has('vk_user_id') && SEARCH.has('sign');
const LAUNCH_PARAMS = IN_VK ? window.location.search : ''; // включает ведущий "?" либо пуст
const WEB_TOKEN_KEY = 'monolith_web_token';

export function webToken() {
  try { return localStorage.getItem(WEB_TOKEN_KEY); } catch { return null; }
}

export function setWebToken(token) {
  try {
    if (token) localStorage.setItem(WEB_TOKEN_KEY, token);
    else localStorage.removeItem(WEB_TOKEN_KEY);
  } catch { /* приватный режим - вход живёт до закрытия вкладки */ }
}

export async function getWebConfig() {
  const res = await fetch(`${API_BASE}/api/web/config`);
  return res.json();
}

export async function webLogin(body) {
  const res = await fetch(`${API_BASE}/api/web/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({ error: 'bad_response' }));
  if (!res.ok) throw new Error(data.error || `http_${res.status}`);
  return data;
}

function buildUrl(path) {
  // Патч 34, ч.2, доп. фикс: слепая конкатенация path + LAUNCH_PARAMS ломалась,
  // если path уже нёс свой "?" (searchAdminPlayers/getAdminJournal) - получалось
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
  // Безвредно для любого другого хостинга - заголовок просто игнорируется.
  const token = IN_VK ? null : webToken();
  const res = await fetch(url, {
    ...options,
    headers: {
      'ngrok-skip-browser-warning': 'true',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options?.headers || {}),
    },
  });
  const data = await res.json().catch(() => ({ error: 'bad_response' }));
  if (!res.ok) {
    const error = new Error(data.error || `http_${res.status}`);
    error.details = data;
    if (!IN_VK && ['web_session_expired', 'invalid_signature'].includes(data.error)) {
      setWebToken(null);
      window.dispatchEvent(new CustomEvent('web-login-required'));
    }
    if (data.error === 'account_banned') {
      window.dispatchEvent(new CustomEvent('account-banned', { detail: data }));
    }
    throw error;
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

export function setTitle(titleId) {
  return request('/title', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title_id: titleId }),
  });
}

// Что игрок уже видел (вступление, тур, подсказка вкладки) и звук.
// {set: {intro: 1, sound: false}} или {hint: 'map'}.
export function saveUi(body) {
  return request('/ui', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function glance() {
  return request('/glance', { method: 'POST' });
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

// Патч 111: снять надетую вещь в сумку.
export function unequipItem(itemId) {
  return request('/unequip', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId }),
  });
}

// Открыть самый старый ларец из сумки. Исход решает сервер, рулетка его
// только показывает: ответ несёт ленту карточек и место выигрыша.
export function openChest(kind = 'ashen') {
  return request('/chest/open', { method: 'POST', body: JSON.stringify({ kind }) });
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

// Патч 58: общие топы. board - id доски, перечень которых приходит в
// ответе (клиент свой список не хранит, чтобы он не разъехался с сервером).
// Вкладка «Доска» (2026-10-15): розыск, рейтинг, сезон, последние бои.
export async function getBoard() {
  return request('/board');
}

export async function getLeaderboard(board) {
  return request(`/leaderboard?board=${encodeURIComponent(board)}`);
}

// Патч 92: какую рамку венца носить. board === null - снять рамку.
// Бонусы при этом не трогаются: действуют все венцы сразу, выбирается
// только вид.
export function setCrownFrame(board) {
  return request('/crown-frame', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ board }),
  });
}

export function getDailies() {
  return request('/dailies');
}

// --- Админка (патч 27) - доступна, только если character.is_admin; сервер
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

// Патч 107: всё, что можно выдать игроку, по группам.
export function getAdminCatalog() {
  return request('/admin/catalog');
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

// Патч 58: массовый сброс зависших состояний + служебная рассылка игрокам.
export function resetAdminActivities() {
  return request('/admin/reset_activities', { method: 'POST' });
}

// Патч 61: телеметрия горного дела и тестовое пополнение жил.
export function getAdminMiningStats(hours = 24) {
  return request(`/admin/mining_stats?hours=${hours}`);
}

export function refillAdminMining() {
  return request('/admin/mining_refill', { method: 'POST' });
}

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

export function sendMountFromMap(mountId, x, y, safe = false) {
  return request('/map/send_mount', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mount_id: mountId, x, y, safe }),
  });
}

// Предпросмотр пути верхом: клетки, время и риск по каждому маунту.
// safe - безопасный путь в обход колец опаснее цели.
export function getMapRoute(x, y, safe) {
  return request(`/map/route?x=${x}&y=${y}&safe=${safe ? 1 : 0}`);
}

export function stopTravel() {
  return request('/map/stop_travel', { method: 'POST' });
}

// --- Мастерская (патч 72) ---

export const getCraft = () => request('/craft');

export const craftItem = (itemId, spec, oreId, grade) =>
  request('/craft', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId, spec, ore_id: oreId, grade }),
  });

export const craftTool = (oreId, grade) =>
  request('/craft/tool', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ore_id: oreId, grade }),
  });

export const upgradeCraft = (itemId, ceiling) =>
  request('/craft/upgrade', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item_id: itemId, ceiling }),
  });

// --- Гильдии ---

export const getGuild = () => request('/guild');

export const getGuildTree = () => request('/guild/tree');

/** Любое действие гильдии. В ответ - новое состояние целиком. */
export const guildAction = (action, params = {}) =>
  request('/guild/action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...params }),
  });

// --- Биржа ---

export const getExchange = () => request('/exchange');

export const exchangeTrade = (direction, lots) =>
  request('/exchange', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ direction, lots }),
  });

export const getTrade = () => request('/trade');

export const tradeAction = (action, params = {}) =>
  request('/trade', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, ...params }),
  });

// --- Магазин (2026-10-13) ---

export const getShop = () => request('/shop');

export const buyShop = (item, days) =>
  request('/shop', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ item, days }),
  });
