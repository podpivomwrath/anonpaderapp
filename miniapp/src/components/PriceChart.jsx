import { useEffect, useRef, useState } from 'react';

// График курса биржи: время слева направо, цена лота снизу вверх от нуля.
// Две линии - покупка (сплошная, с заливкой) и продажа (пунктир). Точки -
// сделки и закрытия дней. Наведение или касание показывает ближайшую точку:
// направляющая, увеличенные точки и карточка с ценами.
//
// Рисуется в реальных пикселях (ширина меряется), а не растягиванием
// viewBox: иначе подписи осей и точки плющились бы вместе с графиком.

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');
const HEIGHT = 220;
const PAD = { left: 52, right: 14, top: 14, bottom: 30 };
const DAY = 86_400_000;

/** Шкала цены по диапазону курса с запасом и «круглым» шагом: от нуля
 *  колебания в несколько процентов выглядели бы ровной линией. */
function scale(lo, hi) {
  const pad = Math.max((hi - lo) * 0.15, hi * 0.03);
  const raw = (hi + pad - Math.max(lo - pad, 0)) / 4 || 1;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * pow >= raw) * pow;
  const min = Math.max(Math.floor((lo - pad) / step) * step, 0);
  const max = Math.ceil((hi + pad) / step) * step;
  return { min, max, step };
}

const KIND = {
  buy: (p) => `куплено лотов: ${p.lots}`,
  sell: (p) => `продано лотов: ${p.lots}`,
  close: (p) => `закрытие дня · куплено ${p.bought}, продано ${p.sold}`,
};

/** Дата и время по Москве - как всё в игре: закрытие дня 30.09 23:59 МСК
 *  в другом часовом поясе иначе показалось бы как 01.10. */
function stamp(ms, withTime) {
  const d = new Date(ms);
  const zone = { timeZone: 'Europe/Moscow' };
  const date = d.toLocaleDateString('ru-RU', { ...zone, day: '2-digit', month: '2-digit' });
  return withTime ? `${date} ${d.toLocaleTimeString('ru-RU', { ...zone, hour: '2-digit', minute: '2-digit' })}` : date;
}

export default function PriceChart({ points }) {
  const box = useRef(null);
  const [width, setWidth] = useState(320);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const measure = () => setWidth(Math.max(240, el.clientWidth));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (!points.length) {
    return (
      <p className="craft-hint">
        Пока пусто: точки появляются раз в сутки, после полуночи по Москве, за прошедший день.
      </p>
    );
  }

  const data = points.map((p) => ({ ...p, ms: new Date(p.t).getTime() }));
  let tMin = data[0].ms;
  let tMax = data[data.length - 1].ms;
  if (tMax - tMin < DAY) {
    // Одна точка или один день - раздвигаем окно, чтобы точка не липла к краю.
    const mid = (tMin + tMax) / 2;
    tMin = mid - DAY / 2;
    tMax = mid + DAY / 2;
  }
  const { min: yMin, max: yMax, step: yStep } = scale(
    Math.min(...data.map((p) => p.sell)), Math.max(...data.map((p) => p.buy)),
  );
  const plotW = width - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const x = (ms) => PAD.left + ((ms - tMin) / (tMax - tMin)) * plotW;
  const y = (v) => PAD.top + (1 - (v - yMin) / (yMax - yMin)) * plotH;
  const path = (key) => data.map((p, i) => `${i ? 'L' : 'M'}${x(p.ms).toFixed(1)} ${y(p[key]).toFixed(1)}`).join(' ');
  const area = `${path('buy')} L${x(data[data.length - 1].ms).toFixed(1)} ${y(yMin)} L${x(data[0].ms).toFixed(1)} ${y(yMin)} Z`;
  const yTicks = [];
  for (let v = yMin; v <= yMax + 1e-9; v += yStep) yTicks.push(v);
  const xTickCount = Math.max(2, Math.min(6, Math.floor(plotW / 90)));
  const single = data[data.length - 1].ms - data[0].ms < DAY;
  const withTime = !single && tMax - tMin < 3 * DAY;
  const xTicks = single
    ? [data[0].ms]
    : Array.from({ length: xTickCount }, (_, i) => tMin + (i / (xTickCount - 1)) * (tMax - tMin));

  const pick = (clientX) => {
    const rect = box.current.getBoundingClientRect();
    const px = clientX - rect.left;
    let best = 0;
    data.forEach((p, i) => {
      if (Math.abs(x(p.ms) - px) < Math.abs(x(data[best].ms) - px)) best = i;
    });
    setHover(best);
  };

  const cur = hover !== null ? data[hover] : null;
  // Карточка - с противоположной от точки стороны, чтобы не закрывать её.
  const tipLeft = cur && x(cur.ms) > width / 2 ? PAD.left + 6 : width - PAD.right - 186;

  return (
    <div
      ref={box}
      className="price-chart"
      onMouseMove={(e) => pick(e.clientX)}
      onMouseLeave={() => setHover(null)}
      onTouchStart={(e) => pick(e.touches[0].clientX)}
      onTouchMove={(e) => pick(e.touches[0].clientX)}
    >
      <svg width={width} height={HEIGHT}>
        <defs>
          <linearGradient id="price-chart-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e8a33d" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#e8a33d" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {yTicks.map((v) => (
          <g key={v}>
            <line className="price-chart__grid" x1={PAD.left} x2={width - PAD.right} y1={y(v)} y2={y(v)} />
            <text className="price-chart__label" x={PAD.left - 6} y={y(v) + 4} textAnchor="end">{money(v)}</text>
          </g>
        ))}
        {xTicks.map((ms) => (
          <text key={ms} className="price-chart__label" x={x(ms)} y={HEIGHT - 8} textAnchor="middle">
            {stamp(ms, withTime)}
          </text>
        ))}
        <path d={area} fill="url(#price-chart-fill)" />
        <path className="price-chart__line price-chart__line--buy" d={path('buy')} />
        <path className="price-chart__line price-chart__line--sell" d={path('sell')} />
        {cur && <line className="price-chart__cursor" x1={x(cur.ms)} x2={x(cur.ms)} y1={PAD.top} y2={y(yMin)} />}
        {data.map((p, i) => (
          <g key={`${p.t}:${i}`}>
            <circle className="price-chart__dot price-chart__dot--buy" cx={x(p.ms)} cy={y(p.buy)} r={hover === i ? 5.5 : 3.2} />
            <circle className="price-chart__dot price-chart__dot--sell" cx={x(p.ms)} cy={y(p.sell)} r={hover === i ? 5 : 2.6} />
          </g>
        ))}
      </svg>
      {cur && (
        <div className="price-chart__tip" style={{ left: tipLeft, top: PAD.top }}>
          <div className="price-chart__tip-time">{cur.kind === 'close' ? stamp(cur.ms, false) : `${stamp(cur.ms, true)} МСК`}</div>
          <div><i className="price-chart__key price-chart__key--buy" />Покупка лота: <b>{money(cur.buy)}</b></div>
          <div><i className="price-chart__key price-chart__key--sell" />Продажа лота: <b>{money(cur.sell)}</b></div>
          <div className="price-chart__tip-note">{KIND[cur.kind](cur)}</div>
        </div>
      )}
      <div className="price-chart__legend">
        <span><i className="price-chart__key price-chart__key--buy" />покупка</span>
        <span><i className="price-chart__key price-chart__key--sell" />продажа</span>
        <span className="craft-hint">обновляется раз в сутки</span>
      </div>
    </div>
  );
}
