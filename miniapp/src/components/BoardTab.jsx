import { useEffect, useState } from 'react';
import { Div, Group, Header, Placeholder, Spinner, TabsItem } from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { getBoard } from '../api.js';
import ClassIcon from './ClassIcon.jsx';
import ContractsSection from './ContractsSection.jsx';

/**
 * «Доска» (2026-10-15): всё PvP в одном месте - розыск (Кровавое клеймо и
 * их метки), рейтинг PTS и сезон с рангами. Последние бои не
 * показываем: кто с кем дрался - личное дело игроков (решение владельца).
 * Числа и правила приходят с сервера: клиент их не пересказывает.
 */

const SECTIONS = [
  { id: 'wanted', title: '🩸 Розыск' },
  { id: 'contracts', title: '📜 Заказы' },
  { id: 'rating', title: '🏅 Рейтинг' },
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

function Wanted({ data }) {
  const { me, rules, wanted } = data;
  return (
    <>
      {(me.marks > 0 || me.revenge) && (
        <Group header={<Header>Ты</Header>}>
          <Div>
            {me.marks > 0 && (
              <>
                <p className="guild-line">🩸 Клеймо: <b>{me.marks}</b></p>
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
              <ClassIcon subclass={w.subclass} baseClass={w.base_class} crown={w.crown_frame || null} size={40} />
              <span className="top-who">
                <span className="top-name">🩸{w.marks} {w.name}</span>
                <span className="craft-hint">
                  {w.level} ур.{w.city_banned ? ' · в город не пускают' : ''}
                  {w.next_decay_min != null ? ` · метка сойдёт через ${minutes(w.next_decay_min)}` : ''}
                </span>
              </span>
            </span>
            <span className="stat-row__value">🩸 {w.marks}</span>
          </div>
        ))}
      </Group>
      {/* Правила свёрнуты - развёрнутые занимали полэкрана (2026-10-15). */}
      <Group>
        <details className="board-rules">
          <summary>Как работает Кровавое клеймо</summary>
          <div className="craft-hint">
          <p><b>Когда даётся метка.</b> Ты убил в PvP игрока, у которого уровень меньше твоего на {rules.level_gap} или больше. Пример: тебе 30 уровень, убил игрока 25 уровня или ниже - метка. Убил 26 уровня - метки нет.</p>
          <p><b>Сколько держится.</b> Каждая метка исчезает сама через {rules.decay_hours} ч, играешь ты или нет. 3 метки исчезнут через {rules.decay_hours * 3} ч.</p>
          <p><b>Что грозит</b> (всё складывается):</p>
          <p>• 1+ метка - 🩸 рядом с именем, видят все.</p>
          <p>• {rules.costly_from}+ - при смерти теряешь в 1,5 раза больше опыта, даже в PvP. Твои трофеи заберёт любой победитель, даже тот, кто старше тебя на 11+ уровней (обычно таким трофеи не достаются).</p>
          <p>• {rules.city_penalty_from}+ - зелья в лавке в 1,5 раза дороже, скупщик платит за реликвии в 2 раза меньше.</p>
          <p>• {rules.city_ban_from}+ - в город не пускают, после смерти появляешься у ворот.</p>
          <p><b>Тому, кого убили:</b> {rules.revenge_hours} ч его урон по убийце на {rules.revenge_pct}% больше.</p>
          <p><b>Охота на клеймёных:</b> за убийство игрока с клеймом метку не дают, даже если он намного слабее. PTS за него начисляются при любой разнице уровней.</p>
          </div>
        </details>
      </Group>
    </>
  );
}

function Rating({ data }) {
  const { me, rating } = data;
  return (
    <Group header={<Header>Рейтинг PvP · сезон {data.season.name}</Header>}>
      {/* Своё место видно всегда, даже за пределами двадцатки (2026-10-15). */}
      <Div className="craft-hint">
        {me.place
          ? <>Ты: <b>{me.place} место</b> из {me.rated_total} · {money(me.pts)} PTS · {me.rank}</>
          : <>Тебя пока нет в рейтинге: ты попадёшь в него после первого PvP-боя. Сейчас у тебя {money(me.pts)} PTS · {me.rank}.</>}
      </Div>
      {rating.length === 0 && (
        <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>В этом сезоне ещё никто не дрался в PvP.</Placeholder>
      )}
      {rating.map((e) => (
        <div className="stat-row top-row" key={e.rank}>
          <span className="stat-row__label">
            {/* Рамка венца, которую носит игрок (своя у каждого). */}
            <ClassIcon subclass={e.subclass} baseClass={e.base_class} crown={e.crown_frame || null} size={40} />
            <span className="top-who">
              <span className="top-name">{e.rank}. {e.premium && '💠 '}{e.name}</span>
              {e.title && <span className={`top-title title-tier title-tier--${e.title_tier || 'common'}`}>«{e.title}»</span>}
            </span>
          </span>
          <span className="stat-row__value">{e.value}</span>
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
      {section === 'contracts' && <ContractsSection />}
      {status === 'ready' && section === 'rating' && <Rating data={data} />}
      {status === 'ready' && section === 'season' && <Season data={data} />}
    </>
  );
}
