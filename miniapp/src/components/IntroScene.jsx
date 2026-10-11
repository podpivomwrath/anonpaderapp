import { useCallback, useEffect, useRef, useState } from 'react';
import AshLayer from './AshLayer.jsx';
import { playCrack, startDrone, unlock } from '../sound.js';

/**
 * Вступление: краткий ввод в лор при первом запуске (и всем один раз после
 * обновления - версия INTRO_VERSION в Hub.jsx).
 *
 * Сначала «коснись» - без касания браузер не даст звук. Дальше шесть кадров:
 * текст проявляется по словам поверх тёмной картины, кадр меняется сам или
 * по нажатию (первое нажатие дописывает текст, второе листает). «Пропустить»
 * - всегда. В конце - выбор: оставить звук или нет.
 *
 * Картинки кадров - assets/intro/intro_N.webp (tools/intro_art_prompts.md).
 * Пока их нет, кадр просто тёмный: вступление работает и без них.
 */

const IMAGES = import.meta.glob('../assets/intro/*.webp', { eager: true, import: 'default' });
const image = (n) => IMAGES[`../assets/intro/intro_${n}.webp`] || null;

const FRAMES = [
  { text: 'Когда-то здесь было небо.' },
  { text: 'Посреди мира стоял Монолит. Он держал небо, как стержень держит свод, - и никто не помнил, кто его поставил.' },
  { text: 'Однажды он треснул. С неба посыпался пепел - и сыплется до сих пор.', crack: true },
  { text: 'Выжившие ушли к краям мира: в горы Кряжа, к соляным Пристаням, в огонь Предела, под кроны Пущ. А в пепле зашевелилось то, чему не следовало просыпаться.' },
  { text: 'Но пепел оставил и метку. На тех, кого коснулся, - и кто не сгорел.' },
  { text: 'Ты - Меченый. Монолит зовёт.', final: true },
];

const WORD_MS = 140;     // шаг появления слов
const HOLD_MS = 2200;    // пауза после того, как текст дописан...
const READ_MS = 110;     // ...плюс время на чтение каждого слова

export default function IntroScene({ onDone }) {
  const [stage, setStage] = useState('start'); // start | frames | sound
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const stopDrone = useRef(() => {});
  const timer = useRef(null);

  const frame = FRAMES[index];
  const words = frame.text.split(' ');

  const finishFrames = useCallback(() => {
    clearTimeout(timer.current);
    stopDrone.current();
    setStage('sound');
  }, []);

  const next = useCallback(() => {
    clearTimeout(timer.current);
    if (index + 1 >= FRAMES.length) {
      finishFrames();
      return;
    }
    setIndex(index + 1);
    setRevealed(false);
  }, [index, finishFrames]);

  // Текст дописался - через паузу следующий кадр.
  useEffect(() => {
    if (stage !== 'frames') return undefined;
    if (frame.crack) playCrack();
    const writeMs = words.length * WORD_MS + 600;
    const reveal = setTimeout(() => setRevealed(true), writeMs);
    return () => clearTimeout(reveal);
  }, [stage, index]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (stage !== 'frames' || !revealed) return undefined;
    const hold = HOLD_MS + words.length * READ_MS;
    timer.current = setTimeout(next, frame.final ? hold + 1200 : hold);
    return () => clearTimeout(timer.current);
  }, [stage, revealed, next, frame.final, words.length]);

  useEffect(() => () => stopDrone.current(), []);

  const begin = () => {
    // Все кадры заранее: иначе на медленной сети следующий мигал бы пустотой.
    FRAMES.forEach((_, i) => {
      const src = image(i + 1);
      if (src) new Image().src = src;
    });
    unlock();
    // Контексту нужен миг, чтобы проснуться после касания.
    setTimeout(() => { stopDrone.current = startDrone(); }, 60);
    setStage('frames');
  };

  const tap = () => {
    if (stage !== 'frames') return;
    if (!revealed) setRevealed(true);
    else next();
  };

  if (stage === 'start') {
    return (
      <div className="intro" role="dialog" aria-label="Вступление">
        <AshLayer density={4} />
        <button type="button" className="intro__start" onClick={begin}>
          <span className="intro__sigil" aria-hidden="true" />
          <span className="intro__start-text">Коснись, чтобы начать</span>
        </button>
        <button type="button" className="intro__skip" onClick={() => setStage('sound')}>Пропустить</button>
      </div>
    );
  }

  if (stage === 'sound') {
    return (
      <div className="intro intro--choice" role="dialog" aria-label="Звук">
        <AshLayer density={4} />
        <div className="intro__choice">
          <p className="intro__choice-title">Звук</p>
          <p className="intro__choice-text">
            Переходы между разделами сопровождает тихий звук. Его можно включить и выключить в любой
            момент - кнопкой в шапке.
          </p>
          <div className="intro__choice-buttons">
            <button type="button" className="intro__btn intro__btn--main" onClick={() => onDone(true)}>
              🔊 Продолжить со звуком
            </button>
            <button type="button" className="intro__btn" onClick={() => onDone(false)}>
              🔇 Без звука
            </button>
          </div>
        </div>
      </div>
    );
  }

  const bg = image(index + 1);
  return (
    <div className="intro" role="dialog" aria-label="Вступление" onClick={tap}>
      <div
        key={`bg${index}`}
        className={`intro__bg${frame.crack ? ' intro__bg--crack' : ''}`}
        style={bg ? { backgroundImage: `url(${bg})` } : undefined}
      />
      <div className="intro__shade" />
      <AshLayer density={frame.crack || index > 2 ? 9 : 3} ember={index >= 2 ? 0.25 : 0.05} />
      {frame.crack && <div key={`flash${index}`} className="intro__flash" />}
      <p key={`t${index}`} className={`intro__text${frame.final ? ' intro__text--final' : ''}${revealed ? ' intro__text--done' : ''}`}>
        {words.map((word, i) => (
          <span key={i} className="intro__word" style={{ animationDelay: `${i * WORD_MS}ms` }}>
            {word}{' '}
          </span>
        ))}
      </p>
      <div className="intro__dots" aria-hidden="true">
        {FRAMES.map((_, i) => <span key={i} className={i === index ? 'intro__dot intro__dot--on' : 'intro__dot'} />)}
      </div>
      <button
        type="button"
        className="intro__skip"
        onClick={(e) => { e.stopPropagation(); finishFrames(); }}
      >
        Пропустить
      </button>
    </div>
  );
}
