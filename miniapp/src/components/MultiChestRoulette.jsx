import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@vkontakte/vkui';
import ItemIcon from './ItemIcon.jsx';
import { itemIcon } from '../itemIcons.js';

/**
 * Открытие пачки ларцов (2026-11-02, владелец: «для тех, кто копит»).
 *
 * Исходы уже решены сервером - он прислал градацию каждого ларца и сводку
 * наград. Здесь до трёх лент: ларцы раскладываются по ним по очереди, и
 * ленты крутятся одна за другой со сдвигом. Чем больше ларцов, тем быстрее
 * прокрутка: вся пачка укладывается примерно в TOTAL_MS. Если ларцов два -
 * две ленты, один - одна.
 *
 * Ленты-обманки собираются здесь же из шансов градаций: так ответ сервера
 * на сотни ларцов остаётся маленьким. Порядок фаз - таймерами, как в
 * одиночной рулетке: в свёрнутом клиенте ВК transitionend не приходит.
 */

const MAX_LANES = 3;
const TOTAL_MS = 12000; // на сколько растягивается вся пачка
const SPIN_MIN = 140;
const SPIN_MAX = 2600;
const STRIP = 18;
const WIN = 14;

function pickGrade(grades) {
  const total = grades.reduce((s, g) => s + (g.chance || 0), 0) || 1;
  let roll = Math.random() * total;
  for (const g of grades) {
    roll -= g.chance || 0;
    if (roll <= 0) return g.grade;
  }
  return grades[grades.length - 1]?.grade || 'dusty';
}

function buildStrip(grades, win) {
  const strip = Array.from({ length: STRIP }, () => pickGrade(grades));
  strip[WIN] = win;
  return strip;
}

function Lane({ queue, grades, chestIcon, spinMs, startDelay, skip, onLand, onDone }) {
  const viewportRef = useRef(null);
  const trackRef = useRef(null);
  const [step, setStep] = useState(-1); // -1: ждёт своей очереди
  const [offset, setOffset] = useState(0);
  const [moving, setMoving] = useState(false);
  const [landed, setLanded] = useState(false);
  const pause = Math.min(450, Math.round(spinMs * 0.35));

  const strip = useMemo(
    () => (step >= 0 && step < queue.length ? buildStrip(grades, queue[step].grade) : []),
    [step, queue, grades],
  );

  useEffect(() => {
    if (skip) return undefined;
    const t = setTimeout(() => setStep(0), startDelay);
    return () => clearTimeout(t);
  }, [startDelay, skip]);

  // Новый ларец: лента в начало без анимации, через миг - прокрутка к выигрышу.
  useLayoutEffect(() => {
    if (step < 0 || step >= queue.length || skip) return undefined;
    setMoving(false);
    setLanded(false);
    setOffset(0);
    const t = setTimeout(() => {
      const viewport = viewportRef.current;
      const win = trackRef.current?.children[WIN];
      if (!viewport || !win) return;
      const w = win.getBoundingClientRect();
      const v = viewport.getBoundingClientRect();
      const jitter = (Math.random() - 0.5) * w.width * 0.4;
      setMoving(true);
      setOffset(-((w.left + w.width / 2) - (v.left + v.width / 2) + jitter));
    }, 30);
    return () => clearTimeout(t);
  }, [step, queue.length, skip]);

  useEffect(() => {
    if (!moving || skip) return undefined;
    const land = setTimeout(() => { setLanded(true); onLand(); }, spinMs + 40);
    const next = setTimeout(() => {
      if (step + 1 < queue.length) setStep(step + 1);
      else onDone();
    }, spinMs + 40 + pause);
    return () => { clearTimeout(land); clearTimeout(next); };
    // onLand/onDone - стабильные колбэки родителя по смыслу; шаг ведёт moving.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [moving, skip]);

  const icon = (grade) => (chestIcon && itemIcon(chestIcon) ? chestIcon : `chest:${grade}`);

  return (
    <div className="roulette__viewport roulette__viewport--mini" ref={viewportRef}>
      <div className="roulette__marker" aria-hidden="true" />
      <div
        className="roulette__track"
        ref={trackRef}
        style={{
          transform: `translateX(${offset}px)`,
          transition: moving ? `transform ${spinMs}ms cubic-bezier(0.15, 0.7, 0.15, 1)` : 'none',
        }}
      >
        {strip.map((grade, index) => (
          <div
            key={`${step}-${index}`}
            className={`roulette__card roulette__card--mini roulette__card--${grade}${landed && index === WIN ? ' roulette__card--win' : ''}`}
          >
            <ItemIcon icon={icon(grade)} alt="" size={40} />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MultiChestRoulette({ results, grades, title, chestIcon, summary, onClose }) {
  const total = results.length;
  const lanes = Math.min(MAX_LANES, total);
  const queues = useMemo(
    () => Array.from({ length: lanes }, (_, lane) => results.filter((_, i) => i % lanes === lane)),
    [results, lanes],
  );
  const perLane = Math.ceil(total / lanes);
  const spinMs = Math.max(SPIN_MIN, Math.min(SPIN_MAX, Math.round(TOTAL_MS / perLane)));
  const [landed, setLanded] = useState(0);
  const [doneLanes, setDoneLanes] = useState(0);
  const [skip, setSkip] = useState(false);
  const finished = skip || doneLanes >= lanes;

  // Сколько каких градаций выпало - в порядке шансов, от частых к редким.
  const tally = useMemo(() => {
    const counts = {};
    results.forEach((r) => { counts[r.grade] = counts[r.grade] || { name: r.grade_name, n: 0 }; counts[r.grade].n += 1; });
    const order = grades.map((g) => g.grade);
    return Object.entries(counts).sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  }, [results, grades]);

  // Сводка - цветом самой редкой выпавшей градации.
  const best = tally.length ? tally[tally.length - 1][0] : 'dusty';

  return (
    <>
      <div className="nav-scrim roulette-scrim" aria-hidden="true" />
      <div className={`roulette roulette--multi roulette--${best}`} role="dialog" aria-label={title}>
        <div className="roulette__title">{title} ×{total}</div>

        {!finished && (
          <>
            <div className="roulette__lanes">
              {queues.map((queue, lane) => (
                <Lane
                  key={lane}
                  queue={queue}
                  grades={grades}
                  chestIcon={chestIcon}
                  spinMs={spinMs}
                  startDelay={Math.round((lane * spinMs) / lanes)}
                  skip={skip}
                  onLand={() => setLanded((n) => n + 1)}
                  onDone={() => setDoneLanes((n) => n + 1)}
                />
              ))}
            </div>
            <div className="roulette__result">
              <span className="roulette__hint">Открыто {Math.min(landed, total)} из {total}</span>
              <Button mode="tertiary" size="m" onClick={() => setSkip(true)}>Пропустить</Button>
            </div>
          </>
        )}

        {finished && (
          <div className="roulette__result roulette__result--shown">
            <div className="multi-tally">
              {tally.map(([grade, { name, n }]) => (
                <span key={grade} className={`roulette__result-grade--${grade}`}>{name} ×{n}</span>
              ))}
            </div>
            <div className="loot-drops loot-drops--summary">
              {summary.map((line, i) => (
                <span key={line} className={`loot-drop loot-drop--${best}`} style={{ animationDelay: `${0.1 + Math.min(i, 12) * 0.08}s` }}>
                  {line}
                </span>
              ))}
            </div>
            <div className="roulette__take">
              <Button mode="primary" size="l" stretched onClick={onClose}>Забрать</Button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
