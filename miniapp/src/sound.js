/**
 * Звук мини-аппа: только переходы между разделами и вступление (решение
 * владельца). Вступление и треск Монолита - синтез Web Audio, смена раздела -
 * короткий файл (см. playTab).
 *
 * Браузеры (iOS особенно) не дают играть звук до первого касания: контекст
 * создаётся и «будится» в unlock(), который зовут из обработчика нажатия.
 */

let ctx = null;
let enabled = true;
let master = null;

function audio() {
  if (ctx) return ctx;
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return null;
  ctx = new Ctx();
  master = ctx.createGain();
  master.gain.value = 0.6;
  master.connect(ctx.destination);
  return ctx;
}

/** Из обработчика нажатия: создать и разбудить контекст. */
export function unlock() {
  const c = audio();
  if (c && c.state === 'suspended') c.resume().catch(() => {});
}

export function setSoundEnabled(on) {
  enabled = Boolean(on);
  if (!enabled && ctx) ctx.suspend().catch(() => {});
  if (enabled && ctx) ctx.resume().catch(() => {});
}

export function soundEnabled() {
  return enabled;
}

function ready() {
  if (!enabled) return null;
  const c = audio();
  if (!c || c.state !== 'running') return null;
  return c;
}

function noiseBuffer(c, seconds) {
  const buffer = c.createBuffer(1, Math.floor(c.sampleRate * seconds), c.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;
  return buffer;
}

/** Огибающая: быстрый подъём, плавный спад. */
function envelope(param, t, peak, attack, release) {
  param.cancelScheduledValues(t);
  param.setValueAtTime(0.0001, t);
  param.exponentialRampToValueAtTime(peak, t + attack);
  param.exponentialRampToValueAtTime(0.0001, t + attack + release);
}

// Звук смены раздела - файлом из public/sfx (2026-10-11). Синтезированный
// шорох владельцу не понравился; файл выбирают из готовых библиотек.
// Нет файла - переход молча: ни ошибки, ни запасного звука.
const TAB_SAMPLE = `${import.meta.env.BASE_URL}sfx/tab.mp3`;
const TAB_VOLUME = 0.5;

const samples = new Map();

/** Загрузить и раскодировать один раз; неудача - null навсегда. */
function sample(c, url) {
  if (!samples.has(url)) {
    samples.set(url, fetch(url)
      .then((res) => (res.ok ? res.arrayBuffer() : Promise.reject(new Error(res.status))))
      .then((data) => new Promise((resolve, reject) => c.decodeAudioData(data, resolve, reject)))
      .catch(() => null));
  }
  return samples.get(url);
}

/** Переход в раздел. */
export function playTab() {
  const c = ready();
  if (!c) return;
  sample(c, TAB_SAMPLE).then((buffer) => {
    if (!buffer || !ready()) return;
    const src = c.createBufferSource();
    src.buffer = buffer;
    const g = c.createGain();
    g.gain.value = TAB_VOLUME;
    src.connect(g).connect(master);
    src.start();
  });
}

/** Заранее подтянуть звук раздела, чтобы первый переход не запаздывал. */
export function preloadTab() {
  const c = ready();
  if (c) sample(c, TAB_SAMPLE);
}

/** Гул вступления: низкий тон и ветер. Возвращает «остановить». */
export function startDrone() {
  const c = ready();
  if (!c) return () => {};
  const t = c.currentTime;
  const out = c.createGain();
  out.gain.setValueAtTime(0.0001, t);
  out.gain.exponentialRampToValueAtTime(0.5, t + 3);
  out.connect(master);

  const nodes = [];
  for (const [freq, level] of [[48, 0.35], [72.3, 0.18], [96.6, 0.08]]) {
    const osc = c.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = freq;
    const g = c.createGain();
    g.gain.value = level;
    osc.connect(g).connect(out);
    osc.start(t);
    nodes.push(osc);
  }
  const wind = c.createBufferSource();
  wind.buffer = noiseBuffer(c, 4);
  wind.loop = true;
  const low = c.createBiquadFilter();
  low.type = 'lowpass';
  low.frequency.value = 420;
  const wg = c.createGain();
  wg.gain.value = 0.12;
  // Ветер «дышит»: медленная модуляция громкости.
  const lfo = c.createOscillator();
  lfo.frequency.value = 0.12;
  const lfoGain = c.createGain();
  lfoGain.gain.value = 0.06;
  lfo.connect(lfoGain).connect(wg.gain);
  wind.connect(low).connect(wg).connect(out);
  wind.start(t);
  lfo.start(t);
  nodes.push(wind, lfo);

  return () => {
    const now = c.currentTime;
    out.gain.cancelScheduledValues(now);
    out.gain.setValueAtTime(out.gain.value, now);
    out.gain.exponentialRampToValueAtTime(0.0001, now + 1.5);
    nodes.forEach((n) => { try { n.stop(now + 1.6); } catch { /* уже остановлен */ } });
  };
}

/** Треск Монолита: удар и рассыпающийся шум. */
export function playCrack() {
  const c = ready();
  if (!c) return;
  const t = c.currentTime;
  const boom = c.createOscillator();
  boom.type = 'sine';
  boom.frequency.setValueAtTime(90, t);
  boom.frequency.exponentialRampToValueAtTime(30, t + 1.2);
  const bg = c.createGain();
  envelope(bg.gain, t, 0.7, 0.01, 1.4);
  boom.connect(bg).connect(master);
  boom.start(t);
  boom.stop(t + 1.5);

  const crack = c.createBufferSource();
  crack.buffer = noiseBuffer(c, 1.6);
  const hp = c.createBiquadFilter();
  hp.type = 'highpass';
  hp.frequency.value = 700;
  const cg = c.createGain();
  envelope(cg.gain, t, 0.35, 0.005, 1.3);
  crack.connect(hp).connect(cg).connect(master);
  crack.start(t);
}
