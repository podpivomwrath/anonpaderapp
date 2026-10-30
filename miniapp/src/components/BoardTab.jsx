import { useEffect, useState } from 'react';
import { Div, Group, Header, Placeholder, TabsItem } from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { getBoard, markSeasonSeen } from '../api.js';
import ClassIcon from './ClassIcon.jsx';
import SeasonScene from './SeasonScene.jsx';
import ContractsSection from './ContractsSection.jsx';
import Skeleton from './Skeleton.jsx';
import { Bar, Empty, Podium, SectionHead } from './ui.jsx';

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
      <SectionHead
        kind="board" icon="🩸" value={wanted.length} label="клеймёных убийц сейчас"
        aside={me.marks > 0 ? <>🩸 {me.marks}<br /><small>твоё клеймо</small></> : null}
      />
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
        {wanted.length === 0 && <Empty icon="🕊️">Сейчас никто не носит клеймо.</Empty>}
        {wanted.length > 0 && (
          <div className="wanted-grid">
            {wanted.map((w) => (
              <div className="wanted-card" key={w.id}>
                <span className="wanted-card__head">Разыскивается</span>
                <ClassIcon subclass={w.subclass} baseClass={w.base_class} crown={w.crown_frame || null} size={56} />
                <b className="wanted-card__name">{w.name}</b>
                <span className="wanted-card__marks" aria-label={`меток: ${w.marks}`}>
                  {'🩸'.repeat(Math.min(w.marks, 5))}{w.marks > 5 ? ` ×${w.marks}` : ''}
                </span>
                <small className="wanted-card__meta">
                  {w.level} ур.{w.city_banned ? ' · вне закона' : ''}
                </small>
                {w.next_decay_min != null && (
                  <small className="wanted-card__meta">метка сойдёт через {minutes(w.next_decay_min)}</small>
                )}
              </div>
            ))}
          </div>
        )}
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
    <>
      {/* Своё место видно всегда, даже за пределами двадцатки (2026-10-15). */}
      <SectionHead
        kind="board" icon="🏅" value={me.place ? `#${me.place}` : '-'}
        label={me.place ? `место из ${me.rated_total} · ${me.rank}` : `ты в рейтинге после первого PvP-боя · ${me.rank}`}
        aside={<>{money(me.pts)}<br /><small>PTS</small></>}
      />
      <Group header={<Header>Рейтинг PvP · сезон {data.season.name}</Header>}>
        {rating.length === 0 && <Empty icon="🕯️">В этом сезоне ещё никто не дрался в PvP.</Empty>}
        {rating.length > 0 && (
          <Podium
            entries={rating.slice(0, 3).map((e) => ({ key: e.rank, name: (e.season_medal ? `${e.season_medal} ` : '') + e.name, value: e.value.split(' · ')[0], raw: e, sub: e.value.split(' · ')[1] }))}
            renderBadge={(e, place) => (
              <ClassIcon subclass={e.raw.subclass} baseClass={e.raw.base_class} crown={e.raw.crown_frame || null} size={place === 1 ? 64 : 52} />
            )}
          />
        )}
        <div className="top-list">
          {rating.slice(3).map((e) => (
            <div className="stat-row top-row" key={e.rank}>
              <span className="stat-row__label">
                <span className="top-rank">{e.rank}</span>
                {/* Рамка венца, которую носит игрок (своя у каждого). */}
                <ClassIcon subclass={e.subclass} baseClass={e.base_class} crown={e.crown_frame || null} size={40} />
                <span className="top-who">
                  {/* Значок - место в прошлом сезоне PvP (2026-10-30). */}
                  <span className="top-name">{e.premium && '💠 '}{e.season_medal && `${e.season_medal} `}{e.name}</span>
                  {e.title && <span className={`top-title title-tier title-tier--${e.title_tier || 'common'}`}>«{e.title}»</span>}
                </span>
              </span>
              <span className="stat-row__value">{e.value}</span>
            </div>
          ))}
        </div>
      </Group>
    </>
  );
}

function Season({ data }) {
  const { season, me } = data;
  const idx = Math.max(0, season.ranks.findIndex((r) => r.name === me.rank));
  const next = season.ranks[idx + 1];
  const cur = season.ranks[idx];
  return (
    <>
      <SectionHead
        kind="board" icon="📅" value={`${season.days_left} дн.`} label={`до конца сезона «${season.name}»`}
        aside={<>{me.rank}<br /><small>{money(me.pts)} PTS</small></>}
      />
      {season.prizes && (
        <Group header={<Header>Награды сезона</Header>}>
          <Div className="craft-hint">
            Пятёрка лучших по PTS среди тех, кто провёл за сезон не меньше {season.min_fights} PvP-боёв
            (арена не в счёт). Титул держится весь следующий сезон.
          </Div>
          {season.prizes.map((p) => (
            <div className="stat-row" key={p.place}>
              <span className="stat-row__label">{p.place} место · «{p.title}»</span>
              <span className="stat-row__value">💎 {money(p.gems)}</span>
            </div>
          ))}
        </Group>
      )}
      <Group header={<Header>Ранги</Header>}>
        {next && (
          <div className="milestone">
            <span className="milestone__head">
              <span>До ранга «{next.name}»</span>
              <span>{money(Math.max(0, next.from - me.pts))} PTS</span>
            </span>
            <Bar value={me.pts - cur.from} max={next.from - cur.from} tone="red" />
          </div>
        )}
        <ol className="rank-ladder">
          {[...season.ranks].reverse().map((r) => {
            const i = season.ranks.indexOf(r);
            const after = season.ranks[i + 1];
            const state = i < idx ? 'done' : i === idx ? 'now' : 'todo';
            return (
              <li key={r.name} className={`rank-ladder__step rank-ladder__step--${state}`}>
                <span className="rank-ladder__dot" />
                <span className="rank-ladder__name">{r.name}</span>
                <span className="rank-ladder__pts">{after ? `${money(r.from)}-${money(after.from - 1)}` : `${money(r.from)}+`}</span>
              </li>
            );
          })}
        </ol>
        <p className="craft-hint season-note">
          Сезон длится календарный месяц. В начале нового сезона рейтинг каждого сжимается к {money(season.start)}: остаётся {season.keep_pct}% того, на сколько ты был выше или ниже.
        </p>
      </Group>
    </>
  );
}

export default function BoardTab() {
  const [section, setSection] = useState('wanted');
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  // Итог прошлого сезона - катсцена один раз (2026-10-30).
  const [recap, setRecap] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getBoard()
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setRecap(res.recap || null);
        setStatus('ready');
      })
      .catch(() => !cancelled && setStatus('error'));
    return () => { cancelled = true; };
  }, []);

  const recapDone = () => {
    setRecap(null);
    setSection('rating');
    markSeasonSeen().catch(() => {});
  };

  return (
    <>
      {recap && <SeasonScene recap={recap} onDone={recapDone} />}
      <Tabs>
        {SECTIONS.map((s) => (
          <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>{s.title}</TabsItem>
        ))}
      </Tabs>
      {status === 'loading' && (
        <Skeleton />
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
