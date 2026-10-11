import { useEffect, useState } from 'react';

/**
 * Короткий тур после вступления: 4 шага по шапке хаба. Подсвечиваемый
 * элемент ищется по data-tour; затемнение вокруг - тень огромного радиуса
 * у прозрачной рамки поверх элемента. Нет элемента на экране - шаг
 * показывается по центру, без подсветки.
 *
 * Остальное объясняют подсказки разделов (TabHint) - при первом заходе.
 */

const STEPS = [
  {
    target: 'banner',
    title: 'Это ты',
    text: 'Класс, уровень, золото и самоцветы. Справа - Мощь: одно число силы персонажа. Нажми на титул, чтобы сменить его.',
  },
  {
    target: 'menu',
    title: 'Разделы',
    text: 'Здесь всё остальное: сумка, мастерская, карта, торговля, биржа, топы и гильдия.',
  },
  {
    target: 'tools',
    title: 'Шапка',
    text: '🔄 - обновить, если что-то изменилось в чате. 🔊 - звук. 📖 - путеводитель по игре.',
  },
  {
    target: null,
    title: 'Дальше - сам',
    text: 'Играешь ты в чате бота, а здесь управляешь персонажем. В каждом разделе при первом заходе будет короткая подсказка.',
  },
];

function rectOf(target) {
  if (!target) return null;
  const el = document.querySelector(`[data-tour="${target}"]`);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return null;
  return { top: r.top - 6, left: r.left - 6, width: r.width + 12, height: r.height + 12 };
}

export default function Tour({ onDone }) {
  const [step, setStep] = useState(0);
  const [rect, setRect] = useState(null);
  const current = STEPS[step];

  useEffect(() => {
    const update = () => setRect(rectOf(current.target));
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, [current.target]);

  const next = () => (step + 1 >= STEPS.length ? onDone() : setStep(step + 1));

  // Карточка - под подсвеченным элементом, если он в верхней половине экрана.
  const below = rect && rect.top + rect.height < window.innerHeight * 0.6;
  const cardStyle = rect
    ? (below ? { top: rect.top + rect.height + 14 } : { bottom: window.innerHeight - rect.top + 14 })
    : { top: '50%', translate: '-50% -50%' };

  return (
    <div className="tour" role="dialog" aria-label="Знакомство с мини-аппом">
      {rect
        ? <div className="tour__spot" style={rect} />
        : <div className="tour__dim" />}
      <div key={step} className="tour__card" style={cardStyle}>
        <p className="tour__title">{current.title}</p>
        <p className="tour__text">{current.text}</p>
        <div className="tour__row">
          <span className="tour__count">{step + 1} / {STEPS.length}</span>
          <button type="button" className="tour__skip" onClick={onDone}>Пропустить</button>
          <button type="button" className="tour__next" onClick={next}>
            {step + 1 >= STEPS.length ? 'Понятно' : 'Дальше'}
          </button>
        </div>
      </div>
    </div>
  );
}
