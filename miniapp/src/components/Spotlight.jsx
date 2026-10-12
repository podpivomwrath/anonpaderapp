import { useEffect, useState } from 'react';

/**
 * Подсветка по шагам: экран затемнён, нужный элемент - в светлой рамке,
 * рядом карточка с текстом. Общая для тура по шапке и подсказок разделов.
 *
 * Цель шага (target):
 *   'menu'          - элемент с data-tour="menu";
 *   'h:Надето'      - блок раздела, чей заголовок начинается с «Надето»;
 *   '.map-controls' - любой CSS-селектор;
 *   null            - карточка по центру, без подсветки.
 *
 * Раздел грузит данные после открытия, поэтому цель ждём до WAIT_MS. Не
 * дождались - шаг показывается по центру: текст всё равно полезен.
 */

const WAIT_MS = 2500;
const PAD = 6;
// Сверху - шапка ВК и хаба, подсветка под неё не заезжает.
const TOP_GAP = 56;

function visible(el) {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
}

function findTarget(target) {
  if (!target) return null;
  if (target.startsWith('h:')) {
    const title = target.slice(2);
    const groups = document.querySelectorAll('.hub-content .vkuiGroup__host');
    return [...groups].find((g) => {
      const header = g.querySelector('.vkuiHeader__host');
      return header && header.textContent.trim().startsWith(title) && visible(g);
    }) || null;
  }
  const selector = /^[a-z]+$/.test(target) ? `[data-tour="${target}"]` : target;
  return [...document.querySelectorAll(selector)].find(visible) || null;
}

/** Рамка вокруг элемента, обрезанная по экрану: длинный список целиком
 *  не подсвечиваем - хватает его начала, и карточке остаётся место. */
function frameOf(el) {
  const r = el.getBoundingClientRect();
  // Шапку не трогаем: её кнопки и так наверху. Блок раздела - не выше шапки.
  const top = el.closest('.hub-content') ? Math.max(r.top - PAD, TOP_GAP) : r.top - PAD;
  const maxBottom = window.innerHeight * 0.55;
  const bottom = Math.min(r.bottom + PAD, Math.max(maxBottom, top + 60));
  return { top, left: r.left - PAD, width: r.width + PAD * 2, height: Math.max(bottom - top, 40) };
}

export default function Spotlight({ steps, onDone, label, onNavigate }) {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState(null);
  const [searching, setSearching] = useState(true);
  const current = steps[step];

  useEffect(() => {
    let el = null;
    let stopped = false;
    const measure = () => setRect(el ? frameOf(el) : null);
    setSearching(Boolean(current.target));
    setRect(null);

    // Шаг полного гайда сам открывает раздел (tab) и вкладку в нём (sub).
    if (current.tab && onNavigate) onNavigate(current.tab);
    // sub - подпись вкладки или путь по вложенным вкладкам: ['Казна', 'Сдать'].
    const subPath = current.sub ? [].concat(current.sub) : [];
    let subIndex = 0;
    let subDone = subPath.length === 0;

    const began = Date.now();
    // Необязательный блок в уже открытом разделе: данные загружены, и раз его
    // нет сразу - его нет вовсе. Ждать полные 2.5 с под тёмным экраном незачем.
    const sameTab = step > 0 && steps[step - 1].tab === current.tab
      && String(steps[step - 1].sub || '') === String(current.sub || '');
    const waitMs = current.optional && sameTab ? 600 : WAIT_MS;
    let poll = 0;
    let settle = 0;
    let again = 0;
    const look = () => {
      if (stopped) return;
      while (!subDone) {
        const tab = [...document.querySelectorAll('.tab-enter [role="tab"]')]
          .find((t) => t.textContent.trim() === subPath[subIndex]);
        if (!tab) break;
        if (tab.getAttribute('aria-selected') !== 'true') {
          tab.click();
          // Вложенные вкладки появятся после отрисовки - следующий заход.
          subIndex += 1;
          subDone = subIndex >= subPath.length;
          break;
        }
        subIndex += 1;
        subDone = subIndex >= subPath.length;
      }
      el = subDone ? findTarget(current.target) : null;
      if (el) {
        // Блоки раздела въезжают каскадом - через полсекунды они на месте.
        again = setTimeout(measure, 700);
        const r = el.getBoundingClientRect();
        // Не на экране или под шапкой - сначала докрутить к нему.
        if (el.closest('.hub-content') && (r.top < TOP_GAP || r.top > window.innerHeight * 0.45)) {
          window.scrollTo({ top: window.scrollY + r.top - TOP_GAP - 12, behavior: 'smooth' });
          settle = setTimeout(() => { measure(); setSearching(false); }, 420);
        } else {
          measure();
          setSearching(false);
        }
        return;
      }
      if (!current.target || Date.now() - began > waitMs) {
        // Блока у игрока нет (не в гильдии, нет венца) - шаг молча пропускаем.
        if (current.optional && current.target) {
          if (step + 1 >= steps.length) onDone();
          else setStep(step + 1);
          return;
        }
        setSearching(false);
        return;
      }
      poll = setTimeout(look, 150);
    };
    // Раздел или вкладку только что переключили - дать им отрисоваться.
    poll = setTimeout(look, current.tab || current.sub ? 90 : 0);

    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      stopped = true;
      clearTimeout(poll);
      clearTimeout(settle);
      clearTimeout(again);
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [current.target, step]); // eslint-disable-line react-hooks/exhaustive-deps

  const next = () => (step + 1 >= steps.length ? onDone() : setStep(step + 1));
  // Гайд раздела: «Вкладка ›» - сразу к следующей вкладке раздела.
  const subKey = (s) => String([].concat(s.sub || '')[0]);
  const nextChapter = current.chapter
    ? steps.findIndex((s, i) => i > step
      && (s.chapterIndex !== current.chapterIndex || subKey(s) !== subKey(current)))
    : -1;

  // Карточка - под подсветкой, если та в верхней части экрана, иначе над ней.
  const below = rect && rect.top + rect.height < window.innerHeight * 0.6;
  const cardStyle = rect
    ? (below ? { top: rect.top + rect.height + 14 } : { bottom: window.innerHeight - rect.top + 14 })
    : { top: '50%', translate: '-50% -50%' };

  return (
    <div className="tour" role="dialog" aria-label={label}>
      {rect
        ? <div className="tour__spot" style={rect} />
        : <div className="tour__dim" />}
      {!searching && (
        <div key={step} className="tour__card" style={cardStyle}>
          <p className="tour__title">{current.title}</p>
          <p className="tour__text">{current.text}</p>
          <div className="tour__row">
            <span className="tour__count">
              {current.chapter
                ? `${current.chapter} · ${current.chapterStep + 1}/${current.chapterSize}`
                : `${step + 1} / ${steps.length}`}
            </span>
            {nextChapter > 0 && (
              <button type="button" className="tour__skip" onClick={() => setStep(nextChapter)}>Вкладка ›</button>
            )}
            {steps.length > 1 && (
              <button type="button" className="tour__skip" onClick={onDone}>{current.chapter ? 'Закрыть' : 'Пропустить'}</button>
            )}
            <button type="button" className="tour__next" onClick={next}>
              {step + 1 >= steps.length ? 'Понятно' : 'Дальше'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
