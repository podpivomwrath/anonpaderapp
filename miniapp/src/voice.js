import { soundEnabled } from './sound.js';

/**
 * Озвучка подсказок (2026-10-22): тур по шапке и подсказки разделов читает
 * рассудительный пожилой мужчина. Файлы - assets/voice/<ключ>.mp3, ключ
 * стоит у шага (voice: 'tour_1'). Сюда попадают только адреса: браузер
 * качает файл, когда шаг показан.
 *
 * Играет одна фраза за раз: новая обрывает прежнюю. Сама фраза звучит при
 * показе шага, только если звук включён (рог в шапке); кнопка «повторить»
 * играет всегда - её нажали нарочно.
 */
const FILES = import.meta.glob('./assets/voice/*.mp3', { eager: true, query: '?url', import: 'default' });

const BY_KEY = Object.fromEntries(
  Object.entries(FILES).map(([path, url]) => [path.split('/').pop().replace('.mp3', ''), url]),
);

let current = null;

export function hasVoice(key) {
  return Boolean(key && BY_KEY[key]);
}

export function stopVoice() {
  if (!current) return;
  current.pause();
  current = null;
}

export function playVoice(key, { force = false } = {}) {
  stopVoice();
  if (!hasVoice(key) || (!force && !soundEnabled())) return;
  const audio = new Audio(BY_KEY[key]);
  audio.volume = 0.95;
  current = audio;
  // Браузер может не дать играть без касания - тогда подсказка просто
  // остаётся текстом, а «повторить» сработает по нажатию.
  audio.play().catch(() => {
    if (current === audio) current = null;
  });
}
