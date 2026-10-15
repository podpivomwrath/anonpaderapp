import { useEffect, useState } from 'react';
import { Div, Group, Header, Placeholder, Spinner, Tabs, TabsItem } from '@vkontakte/vkui';
import { getBoard } from '../api.js';
import ClassIcon from './ClassIcon.jsx';

/**
 * «Доска» (2026-10-15): всё PvP в одном месте - розыск (Пепельное клеймо и
 * награда за голову), рейтинг PTS, последние бои и сезон с рангами.
 * Числа и правила приходят с сервера: клиент их не пересказывает.
 */

const SECTIONS = [
  { id: 'wanted', title: '🩸 Розыск' },
  { id: 'rating', title: '🏅 Рейтинг' },
  { id: 'moments', title: '⚔️ Бои' },
  { id: 'season', title: '📅 Сезон' },
];

function money(value) {
  return Number(value ?? 0).toLocaleString('ru-RU');
}

function minutes(m) {
  if (m == null) return '';
  const h = Math.floor(m / 60);
  return h ? `${h} ч ${m % 60} мин` : `${m} мин`;
}

function ago(iso) {
  if (!iso) return '';
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 60000);
  if (diff < 1) return 'только что';
  if (diff < 60) return `${Math.round(diff)} мин назад`;
  if (diff < 24 * 60) return `${Math.round(diff / 60)} ч назад`;
  return `${Math.round(diff / 1440)} дн назад`;
}

function Wanted({ data }) {
  const { me, rules, wanted } = data;
  return (
    <>
      {(me.marks > 0 || me.revenge) && (
        <Group header={<Header>Ты</Header>}>
          <Div>
            {me.marks > 0 && (
              <>
                <p className="guild-line">🩸 Клеймо: <b>{me.marks}</b>{me.bounty ? ` · 💰 награда за твою голову ${money(me.bounty)}` : ''}</p>
                <p className="craft-hint">Следующая метка сойдёт через {minutes(me.next_decay_min)}. Пока клеймо на тебе: {me.consequences}</p>
              </>
            )}
            {me.revenge && (
              <p className="guild-line">⚔️ Право мести: +{me.revenge.bonus_pct}% урона по {me.revenge.name} до {new Date(me.revenge.until).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</p>
            )}
          </Div>
        </Group>
      )}
      <Group header={<Header>Клеймёные убийцы</Header>}>
        {wanted.length === 0 && (
          <Placeholder icon={<div style={{ fontSize: 48 }}>🕊️</div>}>
            Сейчас никто не носит клеймо.
          </Placeholder>
        )}
        {wanted.map((w) => (
          <div className="stat-row top-row" key={w.id}>
            <span className="stat-row__label">
              <ClassIcon subclass={w.subclass} baseClass={w.base_class} size={40} />
              <span className="top-who">
                <span className="top-name">🩸{w.marks} {w.name}</span>
                <span className="craft-hint">
                  {w.level} ур.{w.city_banned ? ' · в город не пускают' : ''}
                  {w.next_decay_min != null ? ` · метка сойдёт через ${minutes(w.next_decay_min)}` : ''}
                </span>
              </span>
            </span>
            <span className="stat-row__value">{w.bounty ? `💰 ${money(w.bounty)}` : '-'}</span>
          </div>
        ))}
      </Group>
      <Group header={<Header>Как работает клеймо</Header>}>
        <Div className="craft-hint">
          <p>Убил игрока ниже себя на {rules.level_gap}+ уровней - получаешь метку. Каждая сходит сама за {rules.decay_hours} ч.</p>
          <p>{rules.bounty_from}+ метки - с каждой новой {rules.bounty_pct_per_mark}% золота за каждую метку уходит в награду за твою голову. Убьёт тебя кто угодно - заберёт её. Сойдут все метки - золото вернётся.</p>
          <p>{rules.costly_from}+ - смерть отнимает больше опыта, трофеи с тебя заберёт даже младший. {rules.city_penalty_from}+ - лавка дороже на 50%, скупщик за реликвии платит вдвое меньше. {rules.city_ban_from}+ - стража не пускает в город.</p>
          <p>Жертва получает право мести: {rules.revenge_hours} ч её урон по обидчику выше на {rules.revenge_pct}%. За клеймёного PTS дают при любой разнице уровней, а сам охотник клейма не получает.</p>
        </Div>
      </Group>
    </>
  );
}

function Rating({ data }) {
  const { me, rating } = data;
  return (
    <Group header={<Header>Рейтинг PvP · сезон {data.season.name}</Header>}>
      <Div className="craft-hint">Ты: {me.place ? `${me.place} место · ` : ''}{money(me.pts)} PTS · {me.rank}</Div>
      {rating.length === 0 && (
        <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>В этом сезоне ещё никто не дрался в PvP.</Placeholder>
      )}
      {rating.map((e) => (
        <div className="stat-row top-row" key={e.rank}>
          <span className="stat-row__label">
            <ClassIcon subclass={e.subclass} baseClass={e.base_class} size={40} />
            <span className="top-who"><span className="top-name">{e.rank}. {e.premium && '💠 '}{e.name}</span></span>
          </span>
          <span className="stat-row__value">{e.value}</span>
        </div>
      ))}
    </Group>
  );
}

function Moments({ data }) {
  const { moments } = data;
  return (
    <Group header={<Header>Последние бои</Header>}>
      {moments.length === 0 && (
        <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>Боёв пока не было.</Placeholder>
      )}
      {moments.map((m, i) => (
        <div className="stat-row" key={i}>
          <span className="stat-row__label">
            {m.type === 'mass' ? '⚔️' : '🤺'}{' '}
            {m.draw
              ? `Ничья: ${[...m.winners, ...m.losers].join(', ')}`
              : `${m.winners.join(', ')} одолел${m.winners.length > 1 ? 'и' : ''} ${m.losers.join(', ')}`}
          </span>
          <span className="stat-row__value craft-hint">{ago(m.at)}</span>
        </div>
      ))}
    </Group>
  );
}

function Season({ data }) {
  const { season, me } = data;
  return (
    <>
      <Group header={<Header>Сезон: {season.name}</Header>}>
        <Div>
          <p className="guild-line">До конца сезона: {season.days_left} дн.</p>
          <p className="craft-hint">
            Сезон длится календарный месяц. В начале нового сезона рейтинг каждого сжимается к {money(season.start)}: остаётся {season.keep_pct}% того, на сколько ты был выше или ниже.
          </p>
          <p className="guild-line">Твой ранг: {me.rank} · {money(me.pts)} PTS</p>
        </Div>
      </Group>
      <Group header={<Header>Ранги</Header>}>
        {season.ranks.map((r, i) => {
          const next = season.ranks[i + 1];
          return (
            <div className="stat-row" key={r.name}>
              <span className="stat-row__label">{r.name}{me.rank === r.name ? ' ← ты' : ''}</span>
              <span className="stat-row__value">{next ? `${money(r.from)}-${money(next.from - 1)}` : `${money(r.from)}+`} PTS</span>
            </div>
          );
        })}
      </Group>
    </>
  );
}

export default function BoardTab() {
  const [section, setSection] = useState('wanted');
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    let cancelled = false;
    getBoard()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setStatus('ready');
      })
      .catch(() => !cancelled && setStatus('error'));
    return () => { cancelled = true; };
  }, []);

  return (
    <>
      <Tabs>
        {SECTIONS.map((s) => (
          <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>{s.title}</TabsItem>
        ))}
      </Tabs>
      {status === 'loading' && (
        <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}><Spinner size="l" /></Div>
      )}
      {status === 'error' && (
        <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>Не удалось загрузить доску.</Placeholder>
      )}
      {status === 'ready' && section === 'wanted' && <Wanted data={data} />}
      {status === 'ready' && section === 'rating' && <Rating data={data} />}
      {status === 'ready' && section === 'moments' && <Moments data={data} />}
      {status === 'ready' && section === 'season' && <Season data={data} />}
    </>
  );
}
