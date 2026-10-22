import { useEffect, useRef, useState } from 'react';
import { onVoice } from '../voice.js';

/**
 * Рассказчик подсказок (2026-10-22): старый проводник по Пепельным Землям,
 * стоит в карточке подсказки и «рассказывает» её. Кадры - assets/narrator/
 * <поза>_<кадр>.webp (tools/narrator_assets.py): 1 - рот закрыт,
 * 2 - приоткрыт, 3 - открыт, 4 - моргает. Позы: 1 - спокойно рассказывает,
 * 2 - показывает рукой, 3 - усмехается.
 *
 * Пока звучит фраза этого шага, рот открывается в такт громкости записи;
 * раз в несколько секунд он моргает. Все четыре кадра лежат стопкой, виден
 * один - смена без мигания и без догрузки.
 */
const FILES = import.meta.glob('../assets/narrator/*.webp', { eager: true, query: '?url', import: 'default' });
const FRAME = Object.fromEntries(
  Object.entries(FILES).map(([path, url]) => [path.split('/').pop().replace('.webp', ''), url]),
);
const REDUCED = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Кадр рта по громкости: тишина - закрыт, тихо - приоткрыт, громко - открыт. */
function mouthFrom(analyser, buffer) {
  analyser.getByteTimeDomainData(buffer);
  let sum = 0;
  for (let i = 0; i < buffer.length; i += 1) {
    const v = (buffer[i] - 128) / 128;
    sum += v * v;
  }
  const rms = Math.sqrt(sum / buffer.length);
  if (rms < 0.03) return 1;
  return rms < 0.09 ? 2 : 3;
}

export default function Narrator({ voice, pose = 1 }) {
  const [frame, setFrame] = useState(1);
  const [speaking, setSpeaking] = useState(null);
  const blinkAt = useRef(0);

  useEffect(() => onVoice((s) => setSpeaking(s.key && s.key === voice ? s : null)), [voice]);

  useEffect(() => {
    if (REDUCED) return undefined;
    let raf = 0;
    let last = 0;
    let blinkUntil = 0;
    const buffer = speaking?.analyser ? new Uint8Array(speaking.analyser.fftSize) : null;
    blinkAt.current = performance.now() + 1500 + Math.random() * 2500;
    const tick = (now) => {
      raf = requestAnimationFrame(tick);
      if (now - last < 85) return;  // ~12 кадров в секунду: чаще губы мельтешат
      last = now;
      if (now > blinkAt.current) {
        blinkUntil = now + 140;
        blinkAt.current = now + 2800 + Math.random() * 3200;
      }
      let mouth = 1;
      if (speaking) {
        mouth = buffer ? mouthFrom(speaking.analyser, buffer) : 1 + Math.floor(Math.random() * 3);
      }
      // Моргает, только когда рот закрыт: открытый рот с закрытыми глазами
      // в кадрах не нарисован.
      setFrame(mouth === 1 && now < blinkUntil ? 4 : mouth);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [speaking]);

  if (!FRAME[`${pose}_1`]) return null;
  return (
    <div className={speaking ? 'narrator narrator--speaking' : 'narrator'} aria-hidden="true">
      {[1, 2, 3, 4].map((k) => (
        <img
          key={k} src={FRAME[`${pose}_${k}`]} alt="" draggable="false"
          className={k === frame ? 'narrator__frame narrator__frame--on' : 'narrator__frame'}
        />
      ))}
    </div>
  );
}
