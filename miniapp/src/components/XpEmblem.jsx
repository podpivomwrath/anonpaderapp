import ClassIcon from './ClassIcon.jsx';
import Sparks from './Sparks.jsx';

/**
 * Эмблема пути в кольце опыта (2026-10-22). Кольцо - сколько набрано до
 * следующего уровня, на потолке уровня оно полное и золотое. Номер уровня -
 * в плашке на кольце, отдельная строка «Ур. N» в шапке больше не нужна.
 * Свечение кольца - цвет тира активного титула.
 */
const SIZE = 62;
const STROKE = 3;
const R = (SIZE - STROKE) / 2 - 1;
const LEN = 2 * Math.PI * R;

export default function XpEmblem({ character, burst = 0 }) {
  const max = character.xp_to_next == null;
  const share = max ? 1 : Math.max(0, Math.min(1, (character.xp || 0) / character.xp_to_next));
  const tier = character.title ? character.title_tier : null;
  const hint = max ? 'Предельный уровень' : `${character.xp} / ${character.xp_to_next} опыта`;
  return (
    <span
      className={`xp-emblem${tier ? ` xp-emblem--${tier}` : ''}${max ? ' xp-emblem--max' : ''}`}
      title={hint}
    >
      <svg className="xp-emblem__ring" width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true">
        <defs>
          <linearGradient id="xp-grad" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--xp-a)" />
            <stop offset="1" stopColor="var(--xp-b)" />
          </linearGradient>
        </defs>
        <circle cx={SIZE / 2} cy={SIZE / 2} r={R} className="xp-emblem__track" strokeWidth={STROKE} fill="none" />
        <circle
          cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke="url(#xp-grad)" strokeWidth={STROKE}
          strokeLinecap="round" strokeDasharray={LEN} strokeDashoffset={LEN * (1 - share)}
          transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`} className="xp-emblem__bar"
        />
      </svg>
      <span className="xp-emblem__icon">
        <ClassIcon
          subclass={character.subclass} baseClass={character.base_class}
          crown={character.crown_frame || null} size={44}
        />
      </span>
      <span className="xp-emblem__level">{character.level}</span>
      <Sparks burst={burst} />
    </span>
  );
}
