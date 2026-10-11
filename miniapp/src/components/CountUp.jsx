import { useEffect, useRef, useState } from 'react';

const DURATION_MS = 700;
const REDUCED = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

const easeOut = (t) => 1 - (1 - t) ** 3;

/**
 * Число, которое «докручивается» до нового значения, а не меняется скачком,
 * и коротко вспыхивает: зелёным, если выросло, красным - если упало.
 * Первое значение показывается сразу: при открытии считать не от чего.
 */
export default function CountUp({ value, format = (n) => n }) {
  const target = Number(value ?? 0);
  const [shown, setShown] = useState(target);
  const [flash, setFlash] = useState(null);
  const from = useRef(target);

  useEffect(() => {
    const start = from.current;
    from.current = target;
    if (start === target) return undefined;
    setFlash(target > start ? 'up' : 'down');
    const clear = setTimeout(() => setFlash(null), 900);
    // Скрытая вкладка кадров не получает - тогда сразу конечное число.
    if (REDUCED || document.hidden) {
      setShown(target);
      return () => clearTimeout(clear);
    }
    let raf = 0;
    const began = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - began) / DURATION_MS);
      setShown(Math.round(start + (target - start) * easeOut(t)));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(clear);
      setShown(target);
    };
  }, [target]);

  return (
    <span className={flash ? `count-up count-up--${flash}` : 'count-up'}>
      {format(shown)}
    </span>
  );
}
