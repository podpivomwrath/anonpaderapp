import { useEffect, useState } from 'react';
import { TabsItem, Group, Header, Placeholder } from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { getDailies } from '../api.js';
import Skeleton from './Skeleton.jsx';
import { Bar, Empty, SectionHead, hm, useCountdown } from './ui.jsx';

// Патч 23: вкладка «Задания» - три раздела (Сюжет/Ежедневные/Вход).
// 2026-10-22: путь актов, карточки заданий с полоской, календарь входа.
const SECTIONS = [
  { id: 'story', label: 'Сюжет' },
  { id: 'dailies', label: 'Ежедневные' },
  { id: 'login', label: 'Вход' },
];

// Патч 78: локальный сборщик строки награды убран - он печатал сырой id
// («heal_small ×3»). Текст и значок награды приходят с сервера готовыми
// (патч 73: формат принадлежит серверу).

function ActsPath({ acts }) {
  if (!acts?.length) return null;
  return (
    <ol className="acts-path">
      {acts.map((a) => (
        <li key={a.act} className={`acts-path__step acts-path__step--${a.state}`}>
          <span className="acts-path__dot">{a.state === 'done' ? '✓' : a.act}</span>
          <span className="acts-path__title">{a.title || `Акт ${a.act}`}</span>
        </li>
      ))}
    </ol>
  );
}

function StoryTab({ story, onShowOnMap }) {
  const quest = story.active_quest;
  return (
    <Group header={<Header>📜 Сюжет</Header>}>
      <ActsPath acts={story.acts} />
      {quest ? (
        <div className={`quest-card${quest.ready ? ' quest-card--ready' : ''}`}>
          <b className="quest-card__title">{quest.title}</b>
          <p className="quest-card__text">{quest.text}</p>
          {quest.ready && <p className="quest-card__ready">Цель достигнута - вернись к наставнику.</p>}
          {quest.target && !quest.ready && (
            <button type="button" className="pill-btn" onClick={() => onShowOnMap(quest.target)}>
              📍 {quest.target.label} ({quest.target.x}; {quest.target.y})
            </button>
          )}
        </div>
      ) : (
        <Empty icon="📜">Активного сюжетного задания нет.</Empty>
      )}
    </Group>
  );
}

/** Строка летописи: нажатие раскрывает содержимое. */
function ChronicleRow({ icon, title, note, open, onToggle, children }) {
  return (
    <div className="chronicle-item">
      <button type="button" className="chronicle-row" onClick={onToggle} aria-expanded={open}>
        <span className="chronicle-row__title">{icon} {title}</span>
        <span className="chronicle-row__note">{note}</span>
        <span className={open ? 'chronicle-row__arrow chronicle-row__arrow--open' : 'chronicle-row__arrow'}>›</span>
      </button>
      {/* Тело всегда в разметке и раскрывается по высоте - плавно в обе стороны. */}
      <div className={open ? 'fold fold--open' : 'fold'} aria-hidden={!open}>
        <div className="fold__inner">
          <div className="chronicle-body">{children}</div>
        </div>
      </div>
    </div>
  );
}

// Летопись: Пепельная Песнь и титулы свёрнуты и открываются по нажатию.
// Сюда же ложатся будущие достижения - отдельной строкой каждое.
export function ChronicleSection({ song, titles }) {
  const [open, setOpen] = useState(null);
  const toggle = (id) => setOpen((cur) => (cur === id ? null : id));
  const seen = song.fragments.filter((f) => f.seen).length;
  const songNote = song.read ? 'прочитана' : song.complete ? 'собрана' : `${seen} / ${song.fragments.length}`;
  const openedTitles = (titles || []).filter((t) => t.unlocked).length;
  return (
    <Group header={<Header>📖 Летопись</Header>}>
      <ChronicleRow icon="🩶" title="Пепельная Песнь" note={songNote} open={open === 'song'} onToggle={() => toggle('song')}>
        {song.fragments.map((f) => (
          <p key={f.index} className={f.seen ? 'chronicle-line' : 'chronicle-line chronicle-line--hidden'}>
            {f.seen ? f.text : '???'}
          </p>
        ))}
      </ChronicleRow>
      <ChronicleRow
        icon="🏷" title="Титулы" note={`${openedTitles} / ${(titles || []).length}`}
        open={open === 'titles'} onToggle={() => toggle('titles')}
      >
        {(titles || []).map((t) => (
          <div key={t.id} className={t.unlocked ? 'chronicle-title' : 'chronicle-title chronicle-title--locked'}>
            <span className={t.unlocked ? `title-tier title-tier--${t.tier}` : ''}>«{t.name}»</span>
            <span className="chronicle-title__how">
              {t.unlocked ? 'открыт' : t.secret ? 'тайный - условие не раскрывается' : t.how}
            </span>
          </div>
        ))}
      </ChronicleRow>
    </Group>
  );
}

function LootboxSection({ dailies }) {
  const grades = dailies.lootbox_grades.filter((g) => dailies.lootbox_counts[g.id]);
  return (
    <Group header={<Header>🗃️ Пепельные ларцы</Header>}>
      {grades.length === 0 && <Empty icon="🗃️">Ларцов пока не было. Они падают за ежедневные задания.</Empty>}
      {grades.length > 0 && (
        <div className="tile-grid">
          {grades.map((g) => (
            <div className="tile" key={g.id}>
              <span className="tile__icon" aria-hidden="true">{g.emoji}</span>
              <b className="tile__value">{dailies.lootbox_counts[g.id]}</b>
              <small className="tile__label">{g.name}</small>
            </div>
          ))}
        </div>
      )}
      {dailies.lootbox_history.length > 0 && (
        <>
          <div className="list-caption">Последние ларцы</div>
          <ul className="plain-list">
            {dailies.lootbox_history.slice(0, 5).map((h, idx) => (
              <li key={idx}><span aria-hidden="true">{h.emoji}</span> {h.name}: {h.reward_summary}</li>
            ))}
          </ul>
        </>
      )}
    </Group>
  );
}

function QuestCard({ q }) {
  return (
    <div className={`daily-card${q.completed ? ' daily-card--done' : ''}`}>
      <span className="daily-card__mark" aria-hidden="true">{q.completed ? '✓' : ''}</span>
      <div className="daily-card__body">
        <b className="daily-card__title">{q.title}</b>
        <small className="daily-card__how">{q.progress_label}</small>
        <span className="daily-card__progress">
          <Bar value={q.progress} max={q.target} tone={q.completed ? 'green' : 'gold'} />
          <span className="daily-card__count">{Math.min(q.progress, q.target)}/{q.target}</span>
        </span>
      </div>
      <span className="daily-card__reward">
        {q.xp_reward > 0 && <span>✨ {q.xp_reward}</span>}
        {q.gold_reward > 0 && <span>🪙 {q.gold_reward}</span>}
      </span>
    </div>
  );
}

function DailyQuestsTab({ dailies }) {
  const left = useCountdown(dailies.seconds_until_reset);
  const done = dailies.quests.filter((q) => q.completed).length;
  return (
    <>
      <SectionHead
        kind="dailies" icon="🔥" value={dailies.daily_streak}
        label="дней подряд" aside={<>⏳ {hm(left)}<br /><small>до нового дня</small></>}
      />
      <Group header={<Header>🗓️ Ежедневные задания · {done}/{dailies.quests.length}</Header>}>
        <div className="card-list">
          {dailies.quests.map((q) => <QuestCard key={q.id} q={q} />)}
        </div>
        {dailies.next_milestone_day && (
          <div className="milestone">
            <span className="milestone__head">
              <span>Рубеж: день {dailies.next_milestone_day}</span>
              <span>{dailies.daily_streak}/{dailies.next_milestone_day}</span>
            </span>
            <Bar value={dailies.daily_streak} max={dailies.next_milestone_day} tone="red" thin />
            <small className="milestone__reward">🎁 {dailies.next_milestone_reward_text}</small>
          </div>
        )}
      </Group>
      <LootboxSection dailies={dailies} />
    </>
  );
}

function LoginCycleTab({ login }) {
  const [picked, setPicked] = useState(login.cycle_day);
  const days = Array.from({ length: login.cycle_length }, (_, i) => i + 1);
  const state = (day) => {
    if (day < login.cycle_day || (day === login.cycle_day && login.claimed_today)) return 'taken';
    if (day === login.cycle_day) return 'today';
    return 'later';
  };
  return (
    <>
      <SectionHead kind="login" icon="📅" value={login.login_streak} label="дней входа подряд" />
      <Group header={<Header>Награда за вход · день {login.cycle_day}/{login.cycle_length}</Header>}>
        <div className="login-cal">
          {days.map((day) => (
            <button
              type="button" key={day}
              className={`login-cal__day login-cal__day--${state(day)}${picked === day ? ' login-cal__day--picked' : ''}`}
              onClick={() => setPicked(day)}
              aria-label={`День ${day}: ${login.rewards_text?.[day] || 'без награды'}`}
            >
              <span className="login-cal__num">{day}</span>
              <span className="login-cal__icon" aria-hidden="true">
                {state(day) === 'taken' ? '✓' : (login.rewards_icon?.[day] || '·')}
              </span>
            </button>
          ))}
        </div>
        <p className="login-cal__caption">
          <b>День {picked}{picked === login.cycle_day ? ' (сегодня)' : ''}:</b>{' '}
          {login.rewards_text?.[picked] || 'без награды'}
          {picked === login.cycle_day && login.today_reward && (
            <span className="login-cal__status">{login.claimed_today ? ' · получена' : ' · придёт сама'}</span>
          )}
        </p>
      </Group>
    </>
  );
}

export default function DailiesTab({ onShowOnMap }) {
  const [section, setSection] = useState('story');
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error

  useEffect(() => {
    setStatus('loading');
    getDailies()
      .then((res) => {
        setData(res);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }, []);

  if (status === 'loading') {
    return (
      <Skeleton />
    );
  }

  if (status === 'error') {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🕯️</div>}>Не удалось загрузить задания.</Placeholder>;
  }

  return (
    <>
      <Tabs>
        {SECTIONS.map((s) => (
          <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>
            {s.label}
          </TabsItem>
        ))}
      </Tabs>
      {section === 'story' && (
        <>
          <StoryTab story={data.story} onShowOnMap={onShowOnMap} />
          <ChronicleSection song={data.song} titles={data.titles} />
        </>
      )}
      {section === 'dailies' && <DailyQuestsTab dailies={data.dailies} />}
      {section === 'login' && <LoginCycleTab login={data.login} />}
    </>
  );
}
