import { useEffect, useRef, useState } from 'react';
import Sparks from './Sparks.jsx';

/**
 * Радар характеристик (2026-10-22): пятиугольник из пяти статов, видно, во
 * что собран персонаж. Залитый - сейчас (со снаряжением), зелёный контур -
 * что будет после вложенных, но ещё не подтверждённых очков.
 */
const AXES = [
  { key: 'str', icon: '💪' },
  { key: 'agi', icon: '🏃' },
  { key: 'int', icon: '🧠' },
  { key: 'vit', icon: '❤️' },
  { key: 'wil', icon: '✨' },
];
const SIZE = 220;
const C = SIZE / 2;
const R = 78;
const REDUCED = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

function point(i, share) {
  const angle = -Math.PI / 2 + (i * 2 * Math.PI) / AXES.length;
  return [C + Math.cos(angle) * R * share, C + Math.sin(angle) * R * share];
}

function shape(values, scale) {
  return AXES.map((a, i) => point(i, Math.min(1, (values[a.key] || 0) / scale)).join(',')).join(' ');
}

// Плавный переход между наборами чисел: многоугольник перетекает, а не прыгает.
function useTween(target, ms = 320) {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  const key = JSON.stringify(target);
  useEffect(() => {
    const start = from.current;
    const end = JSON.parse(key);
    from.current = end;
    if (REDUCED) {
      setShown(end);
      return undefined;
    }
    let raf = 0;
    const began = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - began) / ms);
      const e = 1 - (1 - t) ** 3;
      setShown(Object.fromEntries(Object.keys(end).map((k) => [k, start[k] + (end[k] - start[k]) * e])));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [key, ms]);
  return shown;
}

export default function StatRadar({ current, preview, burst = 0 }) {
  const changed = AXES.some((a) => preview[a.key] !== current[a.key]);
  const scale = Math.max(10, ...AXES.map((a) => Math.max(current[a.key], preview[a.key]))) * 1.08;
  const now = useTween(current);
  const next = useTween(preview);
  return (
    <div className="stat-radar">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="stat-radar__svg" aria-hidden="true">
        {[0.25, 0.5, 0.75, 1].map((s) => (
          <polygon key={s} points={shape(Object.fromEntries(AXES.map((a) => [a.key, scale * s])), scale)}
            className="stat-radar__grid" />
        ))}
        {AXES.map((a, i) => {
          const [x, y] = point(i, 1);
          return <line key={a.key} x1={C} y1={C} x2={x} y2={y} className="stat-radar__axis" />;
        })}
        <polygon points={shape(now, scale)} className="stat-radar__now" />
        {changed && <polygon points={shape(next, scale)} className="stat-radar__next" />}
        {AXES.map((a, i) => {
          const [x, y] = point(i, Math.min(1, (changed ? next : now)[a.key] / scale));
          return <circle key={a.key} cx={x} cy={y} r="3" className="stat-radar__dot" />;
        })}
        {AXES.map((a, i) => {
          const [x, y] = point(i, 1.24);
          return (
            <text key={a.key} x={x} y={y} className="stat-radar__icon" textAnchor="middle" dominantBaseline="central">
              {a.icon}
            </text>
          );
        })}
      </svg>
      <Sparks burst={burst} />
    </div>
  );
}
