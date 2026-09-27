import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button } from '@vkontakte/vkui';
import ItemIcon from './ItemIcon.jsx';

/**
 * Рулетка Пепельного ларца (патч 106).
 *
 * Исход уже решён сервером: ответ несёт ленту карточек и место выигрыша в
 * ней. Здесь только показ - лента уезжает влево и останавливается так, что
 * выигрышная карточка встаёт ровно под меткой в центре.
 *
 * Точку остановки меряем по вёрстке (положение выигрышной карточки), а не
 * считаем из констант: CSS меняет размер карточек на узком экране, и
 * рассчитанная вслепую точка промахивалась бы на полкарточки.
 */

const SPIN_MS = 6200;

export default function ChestRoulette({ strip, winIndex, result, onClose }) {
  const viewportRef = useRef(null);
  const trackRef = useRef(null);
  const [offset, setOffset] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [done, setDone] = useState(false);

  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    const track = trackRef.current;
    const win = track?.children[winIndex];
    if (!viewport || !win) return undefined;
    // Меряем по вёрстке в стартовой позиции: насколько центр выигрышной
    // карточки правее центра окна - на столько ленту и увезти влево.
    const winRect = win.getBoundingClientRect();
    const viewRect = viewport.getBoundingClientRect();
    // Небольшой случайный сдвиг внутри карточки: иначе метка всегда встаёт
    // в её точный центр, и рулетка выглядит заводной.
    const jitter = (Math.random() - 0.5) * winRect.width * 0.4;
    const target = (winRect.left + winRect.width / 2) - (viewRect.left + viewRect.width / 2) + jitter;
    // Сначала стартовая позиция, через миг - анимация к цели. Таймер, а не
    // requestAnimationFrame: кадры браузер не выдаёт, пока вкладка не
    // рисуется (свёрнутый клиент ВК), и лента так и стояла бы на месте.
    const id = setTimeout(() => {
      setSpinning(true);
      setOffset(-target);
    }, 60);
    return () => clearTimeout(id);
  }, [winIndex]);

  useEffect(() => {
    if (!spinning) return undefined;
    const timer = setTimeout(() => setDone(true), SPIN_MS + 150);
    return () => clearTimeout(timer);
  }, [spinning]);

  return (
    <>
      <div className="nav-scrim roulette-scrim" aria-hidden="true" />
      <div className="roulette" role="dialog" aria-label="Пепельный ларец">
        <div className="roulette__title">Пепельный ларец</div>
        <div className="roulette__viewport" ref={viewportRef}>
          <div className="roulette__marker" aria-hidden="true" />
          <div
            className="roulette__track"
            ref={trackRef}
            style={{
              transform: `translateX(${offset}px)`,
              transition: spinning ? `transform ${SPIN_MS}ms cubic-bezier(0.12, 0.72, 0.12, 1)` : 'none',
            }}
          >
            {strip.map((card, index) => (
              <div
                key={index}
                className={`roulette__card roulette__card--${card.grade}${done && index === winIndex ? ' roulette__card--win' : ''}`}
              >
                <ItemIcon icon={card.icon} alt={card.grade_name} size={56} />
                <span className="roulette__grade">{card.grade_name}</span>
                <span className="roulette__label">{card.label}</span>
              </div>
            ))}
          </div>
        </div>

        <div className={`roulette__result${done ? ' roulette__result--shown' : ''}`}>
          {done ? (
            <>
              <b className={`roulette__result-grade roulette__result-grade--${result.grade}`}>
                {result.grade_name} ларец
              </b>
              <span>Получено: {result.lines.join(', ')}</span>
              <Button mode="primary" size="l" stretched onClick={onClose}>Забрать</Button>
            </>
          ) : (
            <span className="roulette__hint">Крышка поддаётся...</span>
          )}
        </div>
      </div>
    </>
  );
}
