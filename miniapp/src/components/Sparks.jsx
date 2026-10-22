import { useEffect, useState } from 'react';

/**
 * Вспышка искр (2026-10-22): новый уровень, вложенные очки, надетая вещь.
 * Ставится внутрь блока с position: relative; burst - счётчик, каждое его
 * изменение (кроме первого показа) - одна вспышка из центра блока.
 * Только CSS: искры живут меньше секунды и сами исчезают. При «уменьшить
 * движение» и на слабых устройствах (body.lite) их нет вовсе - motion.css.
 */
const COUNT = 14;

function makeSparks(seed) {
  return Array.from({ length: COUNT }, (_, i) => {
    const angle = (i / COUNT) * Math.PI * 2 + Math.random() * 0.5;
    const dist = 26 + Math.random() * 34;
    return {
      key: `${seed}-${i}`,
      style: {
        '--dx': `${Math.cos(angle) * dist}px`,
        '--dy': `${Math.sin(angle) * dist - 10}px`,
        '--d': `${0.55 + Math.random() * 0.45}s`,
        '--s': `${2 + Math.random() * 2.5}px`,
      },
    };
  });
}

export default function Sparks({ burst, color = 'ember' }) {
  const [sparks, setSparks] = useState(null);
  const [seen, setSeen] = useState(burst);

  useEffect(() => {
    if (burst === seen) return undefined;
    setSeen(burst);
    setSparks(makeSparks(burst));
    const timer = setTimeout(() => setSparks(null), 1100);
    return () => clearTimeout(timer);
  }, [burst, seen]);

  if (!sparks) return null;
  return (
    <span className={`sparks sparks--${color}`} aria-hidden="true">
      {sparks.map((s) => <i key={s.key} style={s.style} />)}
    </span>
  );
}
