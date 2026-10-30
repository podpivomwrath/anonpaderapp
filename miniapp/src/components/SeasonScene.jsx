import { useCallback, useEffect, useRef, useState } from 'react';
import AshLayer from './AshLayer.jsx';

/**
 * Итог сезона PvP (2026-10-30, владелец): катсцена, как вступление, при
 * первом заходе на «Доску» после смены сезона. Кадры собираются из итога,
 * который присылает сервер (recap в /board); досмотрел или пропустил -
 * onDone, и сервер больше её не покажет.
 *
 * Картинки - assets/season/season_N.webp (tools/season_art_prompts.md).
 * Пока их нет, кадр тёмный: сцена работает и без них. Стили - intro.css.
 */

const IMAGES = import.meta.glob('../assets/season/*.webp', { eager: true, import: 'default' });
const image = (n) => IMAGES[`../assets/season/season_${n}.webp`] || null;

const WORD_MS = 140;
const HOLD_MS = 2200;
const READ_MS = 110;

function fightsWord(n) {
  const d = n % 10;
  const h = n % 100;
  if (d === 1 && h !== 11) return 'боя';
  return 'боёв';
}

function money(value) {
  return Number(value ?? 0).toLocaleString('ru-RU');
}

function buildFrames(r) {
  const [first, ...rest] = r.top;
  const frames = [{ img: 1, text: `Сезон «${r.season_name}» окончен. Счёт закрыт, рейтинг подбит.` }];
  if (first) {
    frames.push({ img: 2, text: `«${first.title}» сезона - ${first.name}. ${money(first.pts)} PTS.`, crown: true });
  } else {
    frames.push({ img: 2, text: `До ${r.min_fights} ${fightsWord(r.min_fights)} за сезон не дошёл никто. Клинков в этот раз нет.` });
  }
  if (rest.length) {
    frames.push({ img: 2, text: rest.map((e) => `${e.place} место - ${e.name}.`).join(' ') });
  }
  const me = r.me;
  if (me.place) {
    frames.push({
      img: 2,
      text: `Ты на ${me.place} месте. Титул «${me.title}» твой на весь новый сезон, на счёт пришло 💎 ${money(me.gems)}.`,
      crown: true,
    });
  }
  frames.push({
    img: 3,
    text: `Рейтинг сжат: ${money(me.pts_was)} → ${money(me.pts_now)} PTS. Начинается сезон «${r.next_name}».`,
    final: true,
  });
  return frames;
}

export default function SeasonScene({ recap, onDone }) {
  const frames = useRef(buildFrames(recap)).current;
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const timer = useRef(null);

  const frame = frames[index];
  const words = frame.text.split(' ');

  const next = useCallback(() => {
    clearTimeout(timer.current);
    if (index + 1 >= frames.length) {
      onDone();
      return;
    }
    setIndex(index + 1);
    setRevealed(false);
  }, [index, frames.length, onDone]);

  useEffect(() => {
    frames.forEach((f) => {
      const src = image(f.img);
      if (src) new Image().src = src;
    });
  }, [frames]);

  useEffect(() => {
    const reveal = setTimeout(() => setRevealed(true), words.length * WORD_MS + 600);
    return () => clearTimeout(reveal);
  }, [index]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!revealed) return undefined;
    const hold = HOLD_MS + words.length * READ_MS;
    timer.current = setTimeout(next, frame.final ? hold + 1200 : hold);
    return () => clearTimeout(timer.current);
  }, [revealed, next, frame.final, words.length]);

  const tap = () => {
    if (!revealed) setRevealed(true);
    else next();
  };

  const bg = image(frame.img);
  return (
    <div className="intro" role="dialog" aria-label="Итог сезона" onClick={tap}>
      <div
        key={`bg${frame.img}`}
        className="intro__bg"
        style={bg ? { backgroundImage: `url(${bg})` } : undefined}
      />
      <div className="intro__shade" />
      <AshLayer density={frame.crown ? 9 : 4} ember={frame.crown ? 0.3 : 0.1} />
      {frame.crown && <div key={`flash${index}`} className="intro__flash" />}
      <p key={`t${index}`} className={`intro__text${frame.final ? ' intro__text--final' : ''}${revealed ? ' intro__text--done' : ''}`}>
        {words.map((word, i) => (
          <span key={i} className="intro__word" style={{ animationDelay: `${i * WORD_MS}ms` }}>
            {word}{' '}
          </span>
        ))}
      </p>
      <div className="intro__dots" aria-hidden="true">
        {frames.map((_, i) => <span key={i} className={i === index ? 'intro__dot intro__dot--on' : 'intro__dot'} />)}
      </div>
      <button
        type="button"
        className="intro__skip"
        onClick={(e) => { e.stopPropagation(); onDone(); }}
      >
        Пропустить
      </button>
    </div>
  );
}
