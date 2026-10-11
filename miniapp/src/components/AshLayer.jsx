import { useEffect, useRef } from 'react';

/**
 * Падающий пепел - один canvas поверх сцены. Лёгкий: частиц немного, кадр
 * не чаще 30 раз в секунду, на скрытой вкладке не рисует вовсе, при
 * «уменьшить движение» в системе - не запускается.
 *
 * density - частиц на 100 000 пикселей площади; ember - доля тлеющих
 * (багровых) частиц.
 */
export default function AshLayer({ density = 6, ember = 0.15, className = '' }) {
  const ref = useRef(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return undefined;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return undefined;
    const g = canvas.getContext('2d');
    let width = 0;
    let height = 0;
    let parts = [];
    let frame = 0;
    let last = 0;

    const spawn = (anywhere) => ({
      x: Math.random() * width,
      y: anywhere ? Math.random() * height : -10,
      r: 0.6 + Math.random() * 1.8,
      vy: 8 + Math.random() * 18,
      vx: -6 + Math.random() * 12,
      sway: Math.random() * Math.PI * 2,
      ember: Math.random() < ember,
      alpha: 0.25 + Math.random() * 0.5,
    });

    const fit = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.round((width * height) / 100000 * density);
      parts = Array.from({ length: Math.min(count, 140) }, () => spawn(true));
    };

    const draw = (now) => {
      frame = requestAnimationFrame(draw);
      if (document.hidden || now - last < 33) return;
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      g.clearRect(0, 0, width, height);
      for (const p of parts) {
        p.sway += dt;
        p.x += (p.vx + Math.sin(p.sway) * 6) * dt;
        p.y += p.vy * dt;
        if (p.y > height + 10 || p.x < -20 || p.x > width + 20) Object.assign(p, spawn(false));
        g.beginPath();
        g.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        g.fillStyle = p.ember
          ? `rgba(220, 70, 40, ${p.alpha})`
          : `rgba(200, 196, 190, ${p.alpha * 0.7})`;
        g.fill();
      }
    };

    fit();
    window.addEventListener('resize', fit);
    frame = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener('resize', fit);
    };
  }, [density, ember]);

  return <canvas ref={ref} className={`ash-layer ${className}`} aria-hidden="true" />;
}
