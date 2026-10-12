import AshLayer from './AshLayer.jsx';
import background from '../assets/intro/intro_6.webp';

/**
 * Страница новичка (2026-10-12): персонажа ещё нет или его создание брошено
 * на полпути. Раньше здесь была голая ошибка «не удалось открыть хаб» - и
 * новичок не понимал, что делать. Персонаж создаётся только в диалоге с
 * игрой, мини-апп - пульт к уже созданному.
 */

const GROUP_ID = 240167847;
const CHAT_URL = `https://vk.me/club${GROUP_ID}`;
const GUIDE_URL = `https://vk.com/@-${GROUP_ID}-putevoditel-mechenogo`;

const STEPS = [
  ['Открой диалог с игрой', 'кнопка ниже - это сообщения сообщества Monolith.'],
  ['Напиши «Начать»', 'Хранитель Списков встретит тебя у порога.'],
  ['Назови себя', 'имя увидят другие игроки - в топах, группах и гильдиях.'],
  ['Выбери путь и родную землю', 'воин, разбойник или маг; земля - твой город и сюжет.'],
  ['Вернись сюда', 'и нажми «Я создал персонажа».'],
];

export default function NewPlayer({ inCreation, onRetry, checking, stillMissing }) {
  return (
    <div className="newbie">
      <div className="newbie__bg" style={{ backgroundImage: `url(${background})` }} aria-hidden="true" />
      <AshLayer density={4} />
      <div className="newbie__card">
        <p className="newbie__eyebrow">Монолит</p>
        {inCreation ? (
          <>
            <h1 className="newbie__title">Список ещё не дописан</h1>
            <p className="newbie__lead">
              Ты начал создавать персонажа, но не закончил. Вернись в диалог с игрой - Хранитель помнит, на чём
              вы остановились. Если кнопок не видно, напиши «Начать».
            </p>
          </>
        ) : (
          <>
            <h1 className="newbie__title">Тебя ещё нет в Списке</h1>
            <p className="newbie__lead">
              Эта страница - пульт твоего персонажа: характеристики, сумка, карта, торговля. Но сам персонаж
              рождается в диалоге с игрой. Пять шагов, пара минут:
            </p>
            <ol className="newbie__steps">
              {STEPS.map(([title, text], i) => (
                <li key={title} style={{ '--i': i }}>
                  <b>{title}</b> - {text}
                </li>
              ))}
            </ol>
          </>
        )}
        {stillMissing && !checking && (
          <p className="newbie__notice" role="status">
            Персонажа пока нет. Закончи создание в диалоге - последним шагом выбирается родная земля.
          </p>
        )}
        <a className="newbie__primary" href={CHAT_URL} target="_blank" rel="noopener noreferrer">
          💬 Открыть диалог с игрой
        </a>
        <button type="button" className="newbie__secondary" onClick={onRetry} disabled={checking}>
          {checking ? 'Проверяю...' : 'Я создал персонажа'}
        </button>
        <a className="newbie__link" href={GUIDE_URL} target="_blank" rel="noopener noreferrer">
          📖 Путеводитель Меченого - что ждёт за воротами
        </a>
      </div>
    </div>
  );
}
