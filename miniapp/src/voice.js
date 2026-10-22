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
 *
 * Браузер не даёт играть звук, пока игрок ни разу не коснулся страницы, - а
 * подсказка часто появляется сразу при открытии мини-аппа. Тогда фраза ждёт
 * и звучит от первого касания в любом месте экрана (2026-10-22, владелец:
 * «чтобы звук сам воспроизводился при открытии»).
 */
const FILES = import.meta.glob('./assets/voice/*.mp3', { eager: true, query: '?url', import: 'default' });

const BY_KEY = Object.fromEntries(
  Object.entries(FILES).map(([path, url]) => [path.split('/').pop().replace('.mp3', ''), url]),
);

let current = null;
let pending = null;

function onFirstTouch() {
  document.removeEventListener('pointerdown', onFirstTouch, true);
  document.removeEventListener('keydown', onFirstTouch, true);
  const key = pending;
  pending = null;
  if (key) start(key);
}

function waitForTouch(key) {
  pending = key;
  document.addEventListener('pointerdown', onFirstTouch, true);
  document.addEventListener('keydown', onFirstTouch, true);
}

function start(key) {
  const audio = new Audio(BY_KEY[key]);
  audio.volume = 0.95;
  current = audio;
  audio.play().catch((err) => {
    if (current === audio) current = null;
    if (err?.name === 'NotAllowedError') waitForTouch(key);
  });
}

export function hasVoice(key) {
  return Boolean(key && BY_KEY[key]);
}

export function stopVoice() {
  pending = null;
  if (!current) return;
  current.pause();
  current = null;
}

export function playVoice(key, { force = false } = {}) {
  stopVoice();
  if (!hasVoice(key) || (!force && !soundEnabled())) return;
  start(key);
}
