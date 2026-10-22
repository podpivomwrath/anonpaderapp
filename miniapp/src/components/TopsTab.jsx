import { useEffect, useState } from 'react';
import { Group, Header, Placeholder, TabsItem } from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { getLeaderboard } from '../api.js';
import ClassIcon from './ClassIcon.jsx';
import Skeleton from './Skeleton.jsx';
import { Empty, Podium, SectionHead } from './ui.jsx';

function money(value) {
  return Number(value ?? 0).toLocaleString('ru-RU');
}

// Патч 58: раньше здесь был один топ (PvP). Теперь их четыре, и список вкладок
// приходит С СЕРВЕРА вместе с данными — клиент не хранит собственную копию
// перечня досок, иначе она разъедется с серверной при добавлении пятой.
//
// Строка достижения («14 побед», «12,4 кг · Костяная щука») тоже приходит
// готовой: клиент однажды уже пересказывал серверное правило своими словами и
// соврал (правило пресетов, патч 57).
const DEFAULT_BOARDS = [
  { id: 'pvp', title: '🏅 Рейтинг PvP' },
  { id: 'kills', title: '💀 Убийства' },
  { id: 'fishing', title: '🎣 Рыбалка' },
  { id: 'fish_weight', title: '🐟 Рекорды по рыбе' },
  { id: 'mining', title: '⛏ Горное дело' },
];

const EMPTY_HINTS = {
  pvp: 'В этом сезоне ещё никто не дрался в PvP.',
  kills: 'Пока никто не убил ни одного моба.',
  fishing: 'Пока никто не поднял уровень рыбалки.',
  fish_weight: 'Пока никто ничего не поймал.',
  mining: 'Пока никто не поднял уровень горного дела.',
};

/** На сколько мест сдвинулся со вчера. */
function Moved({ n }) {
  if (!n) return null;
  return n > 0
    ? <span className="top-moved top-moved--up" title="мест вверх со вчера">▲{n}</span>
    : <span className="top-moved top-moved--down" title="мест вниз со вчера">▼{-n}</span>;
}

function TopRow({ e }) {
  return (
    <div className={`stat-row top-row${e.me ? ' top-row--me' : ''}`}>
      <span className="stat-row__label">
        <span className="top-rank">{e.rank}</span>
        {/* Рамка венца - та, что игрок носит (2026-10-15): у каждого,
            у кого есть венец, а не только у первого места доски. */}
        <ClassIcon
          subclass={e.subclass}
          baseClass={e.base_class}
          crown={e.crown_frame || null}
          size={40}
        />
        {/* Имя, титул и Мощь переносятся внутри своей колонки: на
            телефоне в одну строку они наезжали на достижение справа. */}
        <span className="top-who">
          <span className="top-name">{e.premium && '💠 '}{e.name}</span>
          {/* Титул - цветом своего тира, как в шапке профиля. */}
          {e.title && (
            <span className={`top-title title-tier title-tier--${e.title_tier || 'common'}`}>«{e.title}»</span>
          )}
          {/* Патч 111: Мощь - только в боевых топах (сервер шлёт её там). */}
          {e.power != null && <span className="power-chip" title="Мощь">⚔ {money(e.power)}</span>}
        </span>
      </span>
      <span className="stat-row__value">
        {e.value}
        <Moved n={e.moved} />
      </span>
    </div>
  );
}

export default function TopsTab() {
  const [board, setBoard] = useState('pvp');
  const [boards, setBoards] = useState(DEFAULT_BOARDS);
  const [top, setTop] = useState([]);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [crown, setCrown] = useState(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [me, setMe] = useState(null);
  const [total, setTotal] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    getLeaderboard(board)
      .then((res) => {
        if (cancelled) return;
        setTop(res.top || []);
        setCrown(res.crown || null);
        setMe(res.me || null);
        setTotal(res.total ?? (res.top || []).length);
        if (res.boards?.length) setBoards(res.boards);
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [board]);

  const current = boards.find((b) => b.id === board);
  // Своё место: в десятке - из списка, ниже - отдельной строкой с сервера.
  const myRank = (top.find((e) => e.me) || me)?.rank ?? null;

  return (
    <>
      <Tabs>
        {boards.map((b) => (
          <TabsItem key={b.id} selected={board === b.id} onClick={() => setBoard(b.id)}>
            {b.title}
          </TabsItem>
        ))}
      </Tabs>

      {status === 'loading' && (
        <Skeleton />
      )}

      {status === 'error' && (
        <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>
          Не удалось загрузить топ.
        </Placeholder>
      )}

      {status === 'ready' && top.length === 0 && (
        <Group><Empty icon="🕯️">{EMPTY_HINTS[board] || 'Пока пусто.'}</Empty></Group>
      )}

      {status === 'ready' && top.length > 0 && (
        <>
          <SectionHead
            kind="tops" icon="🏆"
            value={myRank ? `#${myRank}` : '-'}
            label={myRank ? `твоё место из ${total}` : `тебя нет в топе · всего ${total}`}
            aside={crown && (
              // Подсказка: за что место в этом топе и что даёт венец первого.
              <button type="button" className="top-help" onClick={() => setHelpOpen(true)} aria-label="Что даёт этот топ">
                ?
              </button>
            )}
          />
          <Group header={<Header>{current?.title || 'Топ'}</Header>}>
            <Podium
              entries={top.slice(0, 3).map((e) => ({
                key: e.rank, name: e.name, value: e.value, raw: e,
                sub: e.title ? `«${e.title}»` : null,
              }))}
              renderBadge={(e, place) => (
                <span className={e.raw.me ? 'podium__me' : undefined}>
                  <ClassIcon
                    subclass={e.raw.subclass} baseClass={e.raw.base_class}
                    crown={e.raw.crown_frame || null} size={place === 1 ? 64 : 52}
                  />
                </span>
              )}
            />
            <div className="top-list">
              {top.slice(3).map((e) => <TopRow key={e.rank} e={e} />)}
            </div>
          </Group>
          {me && (
            <div className="top-mine">
              <TopRow e={me} />
            </div>
          )}
        </>
      )}
      {helpOpen && crown && (
        <>
          <div className="nav-scrim" onClick={() => setHelpOpen(false)} aria-hidden="true" />
          <div className="crown-sheet top-help-sheet" role="dialog" aria-label="Венцы">
            <b className="top-help-sheet__title">{current?.title}</b>
            <p className="top-help-sheet__line"><span className="craft-hint">Место в топе:</span> {crown.rule}</p>
            <p className="top-help-sheet__line">
              👑 Первое место носит венец «{crown.title}»: <b>{crown.effect}</b>, и рамку венца вокруг значка класса.
            </p>
            <div className="trade-dest__section">Правила венцов</div>
            <ul className="top-help-sheet__rules">
              <li>Венец только у первого места. Второе и третье не дают ни бонуса, ни рамки.</li>
              <li>Венцы пересчитываются раз в сутки, в 6 утра по Москве: бонус не меняется посреди боя.</li>
              <li>Можно держать несколько венцов сразу - их бонусы действуют вместе. Рамку носишь одну: выбор - нажатием на значок класса в шапке профиля.</li>
              <li>Если тебя обогнали, венец уходит новому первому при следующем пересчёте, и тебе придёт об этом сообщение.</li>
              <li>Бонус венца никогда не помогает в том, за что его дали: за бои платят добычей, за добычу - временем. Иначе лидер оставался бы первым навсегда.</li>
            </ul>
            <div className="trade-dest__section">Все венцы</div>
            {crown.all.map((c) => (
              <p key={c.title} className="top-help-sheet__line">
                {c.board} - «{c.title}»: {c.effect}
              </p>
            ))}
            <div className="trade-dest__actions">
              <button type="button" className="top-help-sheet__close" onClick={() => setHelpOpen(false)}>Понятно</button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
