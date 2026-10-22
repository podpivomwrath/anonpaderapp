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
 * раз в несколько секунд он моргает. Кадры лежат стопкой: основной снизу
 * всегда, рот или моргание поверх - смена без мигания и без догрузки.
 */
const FILES = import.meta.glob('../assets/narrator/*.webp', { eager: true, query: '?url', import: 'default' });
const FRAME = Object.fromEntries(
  Object.entries(FILES).map(([path, url]) => [path.split('/').pop().replace('.webp', ''), url]),
);
const REDUCED = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Громкость фразы сейчас, 0..~0.3. */
function loudness(analyser, buffer) {
  analyser.getByteTimeDomainData(buffer);
  let sum = 0;
  for (let i = 0; i < buffer.length; i += 1) {
    const v = (buffer[i] - 128) / 128;
    sum += v * v;
  }
  return Math.sqrt(sum / buffer.length);
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
    let level = 0;
    let mouth = 1;
    let fallback = 0;
    const buffer = speaking?.analyser ? new Uint8Array(speaking.analyser.fftSize) : null;
    blinkAt.current = performance.now() + 2000 + Math.random() * 3000;
    const tick = (now) => {
      raf = requestAnimationFrame(tick);
      // ~8 смен в секунду: чаще губы мельтешат.
      if (now - last < 120) return;
      last = now;
      if (now > blinkAt.current) {
        blinkUntil = now + 150;
        blinkAt.current = now + 4000 + Math.random() * 3000;
      }
      if (speaking && buffer) {
        // Громкость сглажена, а рот переходит на соседний кадр, только когда
        // она уверенно ушла за порог: иначе он дёргался на каждом шорохе.
        level = level * 0.55 + loudness(speaking.analyser, buffer) * 0.45;
        const want = level < 0.025 ? 1 : level < 0.075 ? 2 : 3;
        if (Math.abs(want - mouth) >= 1) mouth += Math.sign(want - mouth);
      } else if (speaking) {
        // Без анализатора: спокойное «открыл - прикрыл», не наугад.
        fallback = (fallback + 1) % 4;
        mouth = [2, 3, 2, 1][fallback];
      } else {
        mouth = 1;
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
    <div className="narrator" aria-hidden="true">
      {[1, 2, 3, 4].map((k) => (
        <img
          key={k} src={FRAME[`${pose}_${k}`]} alt="" draggable="false"
          className={k === 1 ? 'narrator__frame narrator__frame--base'
            : k === frame ? 'narrator__frame narrator__frame--on' : 'narrator__frame'}
        />
      ))}
    </div>
  );
}
