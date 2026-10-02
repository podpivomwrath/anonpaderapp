import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import bgWide from '../assets/bg-wide.webp';
import { glance } from '../api.js';

/**
 * Живой фон (патч 106): мерцание у основания Монолита, дрейф тумана и
 * параллакс от курсора.
 *
 * Только на широком экране - картинка фона есть только там (background.css).
 * Слой выносится порталом прямо в body, рядом с #root, как раньше
 * body::before: #root поднят z-index 1, и сцена гарантированно под ним.
 *
 * Свечение привязано к точке на КАРТИНКЕ, а не на экране: трещина у
 * основания Монолита (83.5% ширины, 57.5% высоты кадра 1600x900 - найдено
 * по самым красным пикселям картинки: трещина узкая и вертикальная). Картинка
 * растянута как cover и прижата к верху, поэтому точку пересчитываем под
 * размер окна. Свечение лежит внутри слоя картинки и сдвигается вместе с ней.
 *
 * Параллакс пишется в CSS-переменные напрямую, без перерисовки React: иначе
 * каждое движение мыши гоняло бы рендер всей сцены.
 */

const IMAGE_W = 1600;
const IMAGE_H = 900;
const GLOW = { x: 0.835, y: 0.575 };
const WIDE_QUERY = '(min-width: 720px)';

// Слой картинки больше экрана на PAD с каждой стороны (запас под параллакс,
// см. .scene__image) - точку считаем от его размера, в его координатах.
const PAD = 16;

function coverGeometry() {
  const w = window.innerWidth + PAD * 2;
  const h = window.innerHeight + PAD * 2;
  const scale = Math.max(w / IMAGE_W, h / IMAGE_H);
  const imgW = IMAGE_W * scale;
  const imgH = IMAGE_H * scale;
  const left = (w - imgW) / 2; // background-position: center top
  return { x: left + GLOW.x * imgW, y: GLOW.y * imgH, width: imgW * 0.03, height: imgW * 0.075 };
}

// Секрет: 100 нажатий подряд по тлеющей трещине на экране персонажа - титул
// «Внимательный». Ничем не подсказывается: ни курсора-руки, ни отклика на
// нажатие до самой сотни. Пауза дольше EMBER_GAP или нажатие мимо трещины
// сбрасывает счёт. Сцена лежит под интерфейсом (pointer-events: none),
// поэтому нажатие ловится на window и сверяется с рамкой свечения - она
// сама пересчитана под размер окна и сдвинута параллаксом.
const EMBER_TAPS = 100;
const EMBER_GAP = 3000;
const NOT_EMPTY = 'button, a, input, textarea, select, label, [role="button"], [role="tab"], .vkuiGroup';

function useEmber(wide, sceneRef) {
  const [woke, setWoke] = useState(false);
  useEffect(() => {
    if (!wide) return undefined;
    let taps = 0;
    let last = 0;
    let sent = false;
    const onDown = (e) => {
      if (sent || document.body.dataset.view !== 'character') return;
      if (e.target instanceof Element && e.target.closest(NOT_EMPTY)) return;
      const ember = sceneRef.current?.querySelector('.scene__glow');
      if (!ember) return;
      const r = ember.getBoundingClientRect();
      const inside = e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom;
      const now = e.timeStamp;
      taps = inside && now - last < EMBER_GAP ? taps + 1 : inside ? 1 : 0;
      last = now;
      if (taps < EMBER_TAPS) return;
      sent = true;
      glance()
        .then((res) => {
          setWoke(true);
          if (res.fresh) window.dispatchEvent(new CustomEvent('character-refresh'));
          setTimeout(() => setWoke(false), 6000);
        })
        .catch(() => { sent = false; taps = 0; });
    };
    window.addEventListener('pointerdown', onDown, { passive: true });
    return () => window.removeEventListener('pointerdown', onDown);
  }, [wide, sceneRef]);
  return woke;
}

function useMedia(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

export default function BackgroundScene() {
  const wide = useMedia(WIDE_QUERY);
  const calm = useMedia('(prefers-reduced-motion: reduce)');
  const sceneRef = useRef(null);
  const [glow, setGlow] = useState(coverGeometry);

  useEffect(() => {
    if (!wide) return undefined;
    const onResize = () => setGlow(coverGeometry());
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [wide]);

  useEffect(() => {
    if (!wide || calm) return undefined;
    let frame = 0;
    let px = 0;
    let py = 0;
    const onMove = (e) => {
      px = (e.clientX / window.innerWidth) * 2 - 1;
      py = (e.clientY / window.innerHeight) * 2 - 1;
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        sceneRef.current?.style.setProperty('--px', px.toFixed(3));
        sceneRef.current?.style.setProperty('--py', py.toFixed(3));
      });
    };
    window.addEventListener('mousemove', onMove, { passive: true });
    return () => {
      window.removeEventListener('mousemove', onMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [wide, calm]);

  // Нажатия по трещине (см. useEmber ниже).
  const woke = useEmber(wide, sceneRef);

  if (!wide) return null;

  return createPortal(
    <div className={`scene${calm ? ' scene--calm' : ''}`} ref={sceneRef} aria-hidden="true">
      <div className="scene__image" style={{ backgroundImage: `url(${bgWide})` }}>
        <div
          className={`scene__glow${woke ? ' scene__glow--woke' : ''}`}
          style={{ left: glow.x, top: glow.y, width: glow.width, height: glow.height }}
        />
        {woke && (
          <div className="scene__whisper" style={{ left: glow.x - glow.width, top: glow.y }}>
            Трещина затихает<br />под твоим взглядом.<br />Титул «Внимательный».
          </div>
        )}
      </div>
      <div className="scene__mist scene__mist--far" />
      <div className="scene__mist scene__mist--near" />
    </div>,
    document.body,
  );
}
