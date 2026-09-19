import { useEffect, useState } from 'react';
import { Group, Header, Div, Spinner, Placeholder, Tabs, TabsItem } from '@vkontakte/vkui';
import { getLeaderboard } from '../api.js';

// Патч 58: раньше здесь был один топ (PvP). Теперь их четыре, и список вкладок
// приходит С СЕРВЕРА вместе с данными — клиент не хранит собственную копию
// перечня досок, иначе она разъедется с серверной при добавлении пятой.
//
// Строка достижения («14 побед», «12,4 кг · Костяная щука») тоже приходит
// готовой: клиент однажды уже пересказывал серверное правило своими словами и
// соврал (правило пресетов, патч 57).
const DEFAULT_BOARDS = [
  { id: 'pvp', title: '⚔️ PvP' },
  { id: 'kills', title: '💀 Убийства' },
  { id: 'fishing', title: '🎣 Рыбалка' },
  { id: 'fish_weight', title: '🐟 Рекорды по рыбе' },
  { id: 'mining', title: '⛏ Горное дело' },
];

const EMPTY_HINTS = {
  pvp: 'Пока никто не побеждал в PvP.',
  kills: 'Пока никто не убил ни одного моба.',
  fishing: 'Пока никто не поднял уровень рыбалки.',
  fish_weight: 'Пока никто ничего не поймал.',
  mining: 'Пока никто не поднял уровень горного дела.',
};

export default function TopsTab() {
  const [board, setBoard] = useState('pvp');
  const [boards, setBoards] = useState(DEFAULT_BOARDS);
  const [top, setTop] = useState([]);
  const [status, setStatus] = useState('loading'); // loading | ready | error

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    getLeaderboard(board)
      .then((res) => {
        if (cancelled) return;
        setTop(res.top || []);
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
        <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
          <Spinner size="l" />
        </Div>
      )}

      {status === 'error' && (
        <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>
          Не удалось загрузить топ.
        </Placeholder>
      )}

      {status === 'ready' && top.length === 0 && (
        <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>
          {EMPTY_HINTS[board] || 'Пока пусто.'}
        </Placeholder>
      )}

      {status === 'ready' && top.length > 0 && (
        <Group header={<Header>{current?.title || 'Топ'}</Header>}>
          {top.map((e) => (
            <div className="stat-row" key={e.rank}>
              <span className="stat-row__label">
                {e.rank}. {e.premium && '💠 '}
                {e.name}
              </span>
              <span className="stat-row__value">{e.value}</span>
            </div>
          ))}
        </Group>
      )}
    </>
  );
}
