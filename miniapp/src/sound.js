/**
 * Звук мини-аппа: только переходы между разделами и вступление (решение
 * владельца). Без файлов - синтез Web Audio: нечего грузить, нет вопроса
 * лицензий, и звук не утяжеляет первое открытие.
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

// У каждого раздела свой тон шороха: переход узнаётся на слух, но звук
// остаётся тем же «перелистыванием» - без мелодий.
const TAB_TONE = {
  character: 1.0, dailies: 1.12, inventory: 0.9, craft: 0.8, map: 1.25,
  guild: 0.85, tops: 1.18, trade: 1.05, exchange: 1.3, admin: 0.7,
};

/** Переход в раздел: короткий шорох пергамента и глухой удар. */
export function playTab(tabId) {
  const c = ready();
  if (!c) return;
  const t = c.currentTime;
  const tone = TAB_TONE[tabId] || 1;

  const noise = c.createBufferSource();
  noise.buffer = noiseBuffer(c, 0.3);
  const band = c.createBiquadFilter();
  band.type = 'bandpass';
  band.Q.value = 0.9;
  band.frequency.setValueAtTime(900 * tone, t);
  band.frequency.exponentialRampToValueAtTime(2600 * tone, t + 0.18);
  const ng = c.createGain();
  envelope(ng.gain, t, 0.22, 0.02, 0.22);
  noise.connect(band).connect(ng).connect(master);
  noise.start(t);
  noise.stop(t + 0.3);

  const thump = c.createOscillator();
  thump.type = 'sine';
  thump.frequency.setValueAtTime(110 * tone, t);
  thump.frequency.exponentialRampToValueAtTime(55 * tone, t + 0.18);
  const tg = c.createGain();
  envelope(tg.gain, t, 0.18, 0.005, 0.2);
  thump.connect(tg).connect(master);
  thump.start(t);
  thump.stop(t + 0.25);
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
