import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';
import { Button } from '@vkontakte/vkui';
import ItemIcon from './ItemIcon.jsx';
import { itemIcon } from '../itemIcons.js';

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
 *
 * После ленты (2026-10-11) - вскрытие: выпавший ларец трясётся всё сильнее,
 * светясь цветом своей градации, потом вспышка, лучи, искры - и награды
 * вылетают из него по одной. Нажатие во время тряски вскрывает сразу.
 */

const SPIN_MS = 6200;
const PAUSE_MS = 650; // выигрышная карточка подсвечена - и ларец выезжает
const SHAKE_MS = 1500;
const SPARKS = 22;

const REDUCED = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

// Чем реже градация, тем сильнее отдача в руку.
const BURST_HAPTIC = { dusty: 'light', dim: 'medium', crimson: 'heavy', searing: 'heavy', tear: 'heavy' };

function haptic(style) {
  bridge.send('VKWebAppTapticImpactOccurred', { style }).catch(() => {});
}

export default function ChestRoulette({ strip, winIndex, result, onClose }) {
  const viewportRef = useRef(null);
  const trackRef = useRef(null);
  const [offset, setOffset] = useState(0);
  const [spinning, setSpinning] = useState(false);
  // spin -> win (карточка подсвечена) -> shake -> burst
  const [phase, setPhase] = useState('spin');

  // Искры разлетаются по кругу с разбросом - считаем один раз.
  const sparks = useMemo(() => Array.from({ length: SPARKS }, (_, i) => ({
    angle: (360 / SPARKS) * i + (Math.random() - 0.5) * 14,
    dist: 70 + Math.random() * 70,
    size: 3 + Math.random() * 4,
    delay: Math.random() * 0.12,
  })), []);

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

  // Фазы идут таймерами, а не по animationend: в свёрнутом клиенте ВК
  // анимации не доигрываются, а награду показать всё равно нужно.
  useEffect(() => {
    if (!spinning) return undefined;
    const timer = setTimeout(() => setPhase('win'), SPIN_MS + 150);
    return () => clearTimeout(timer);
  }, [spinning]);

  useEffect(() => {
    if (phase === 'win') {
      const timer = setTimeout(() => setPhase(REDUCED ? 'burst' : 'shake'), PAUSE_MS);
      return () => clearTimeout(timer);
    }
    if (phase === 'shake') {
      haptic('light');
      const pulse = setTimeout(() => haptic('medium'), SHAKE_MS * 0.6);
      const timer = setTimeout(() => setPhase('burst'), SHAKE_MS);
      return () => { clearTimeout(pulse); clearTimeout(timer); };
    }
    if (phase === 'burst') haptic(BURST_HAPTIC[result.grade] || 'medium');
    return undefined;
  }, [phase, result.grade]);

  const opening = phase === 'shake' || phase === 'burst';
  const done = phase === 'burst';
  const grade = result.grade;
  // Ларцы кровавого разлома (2026-10-13): своё имя и одна картинка ларца на
  // вид; у Пепельного - картинка своей градации.
  const title = result.title || 'Пепельный ларец';
  const lootChest = Boolean(result.kind && result.kind !== 'ashen');
  // Своей картинки ларца ещё нет - Пепельный того же цвета градации.
  const chestIcon = result.chest_icon && itemIcon(result.chest_icon) ? result.chest_icon : `chest:${grade}`;

  return (
    <>
      <div className="nav-scrim roulette-scrim" aria-hidden="true" />
      <div className={`roulette roulette--${grade}${done ? ' roulette--burst' : ''}`} role="dialog" aria-label={title}>
        <div className="roulette__title">{title}</div>

        {!opening && (
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
                  className={`roulette__card roulette__card--${card.grade}${phase === 'win' && index === winIndex ? ' roulette__card--win' : ''}`}
                >
                  <ItemIcon icon={card.icon} alt={card.grade_name} size={56} />
                  {/* Содержимое на ленте не показываем: награда - сюрприз вскрытия. */}
                  {/* Ларцы разлома: только ларец и свечение карточки, без
                      подписи - у Ларца руды она называла бы руду. */}
                  {!lootChest && <span className="roulette__grade">{card.grade_name}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {opening && (
          <div
            className={`chest-stage chest-stage--${grade} chest-stage--${phase}`}
            onClick={() => phase === 'shake' && setPhase('burst')}
            aria-hidden="true"
          >
            <div className="chest-stage__glow" />
            {done && <div className="chest-stage__rays" />}
            {done && <div className="chest-stage__flash" />}
            {done && sparks.map((s, i) => (
              <span
                key={i}
                className="chest-stage__spark"
                style={{
                  '--a': `${s.angle}deg`, '--d': `${s.dist}px`,
                  width: s.size, height: s.size, animationDelay: `${s.delay}s`,
                }}
              />
            ))}
            <div className="chest-stage__chest">
              <ItemIcon icon={chestIcon} alt={title} size={104} />
            </div>
          </div>
        )}

        <div className={`roulette__result${done ? ' roulette__result--shown' : ''}`}>
          {done ? (
            <>
              <b className={`roulette__result-grade roulette__result-grade--${grade}`}>
                {result.title ? result.grade_name : `${result.grade_name} ларец`}
              </b>
              <div className="loot-drops">
                {result.lines.map((line, i) => (
                  <span
                    key={line}
                    className={`loot-drop loot-drop--${grade}`}
                    style={{ animationDelay: `${0.25 + i * 0.18}s`, '--from-x': `${(i - (result.lines.length - 1) / 2) * -40}px` }}
                  >
                    {line}
                  </span>
                ))}
              </div>
              <div className="roulette__take" style={{ animationDelay: `${0.45 + result.lines.length * 0.18}s` }}>
                <Button mode="primary" size="l" stretched onClick={onClose}>Забрать</Button>
              </div>
            </>
          ) : (
            <span className="roulette__hint">
              {phase === 'shake' ? 'Ларец рвётся из рук... (нажми, чтобы вскрыть)' : 'Крышка поддаётся...'}
            </span>
          )}
        </div>
      </div>
    </>
  );
}
