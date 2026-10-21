import { useEffect, useState } from 'react';
import { TabsItem, Group, Header, Div, Spinner, Placeholder } from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { getDailies } from '../api.js';

// Патч 23: вкладка «Задания» - три раздела (Сюжет/Ежедневные/Вход).
const SECTIONS = [
  { id: 'story', label: 'Сюжет' },
  { id: 'dailies', label: 'Ежедневные' },
  { id: 'login', label: 'Вход' },
];

// Патч 78: локальный сборщик строки награды убран - он печатал сырой id
// («heal_small ×3»). Текст приходит с сервера готовым, как и всё остальное
// форматирование (патч 73: формат принадлежит серверу).

function StoryTab({ story }) {
  return (
    <Group header={<Header>📜 Сюжет</Header>}>
      {story.active_quest ? (
        <Div>
          <p style={{ fontWeight: 600, marginBottom: 4 }}>{story.active_quest.title}</p>
          <p style={{ marginBottom: 8 }}>{story.active_quest.text}</p>
          {story.active_quest.target && (
            <p style={{ opacity: 0.8 }}>
              📍 Цель: ({story.active_quest.target.x}; {story.active_quest.target.y}) -{' '}
              {story.active_quest.target.label}
            </p>
          )}
          {story.active_quest.ready && <p style={{ opacity: 0.8 }}>Цель достигнута - вернись к наставнику.</p>}
        </Div>
      ) : (
        <Div style={{ opacity: 0.8 }}>Активного сюжетного квеста нет.</Div>
      )}
      {story.passed_acts.length > 0 && (
        <Div>
          <p style={{ fontWeight: 600, marginBottom: 4 }}>Пройденные акты:</p>
          {story.passed_acts.map((a) => (
            <p key={a.act} style={{ opacity: 0.8 }}>
              Акт {a.act}: {a.title}
            </p>
          ))}
        </Div>
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
  return (
    <Group header={<Header>🗃️ Пепельные ларцы</Header>}>
      {dailies.lootbox_grades.map((g) => {
        const count = dailies.lootbox_counts[g.id] || 0;
        if (!count) return null;
        return (
          <div className="stat-row" key={g.id}>
            <span className="stat-row__label">
              {g.emoji} {g.name}
            </span>
            <span className="stat-row__value">{count} раз</span>
          </div>
        );
      })}
      {dailies.lootbox_history.length === 0 && <Div style={{ opacity: 0.8 }}>Ларцов пока не было.</Div>}
      {dailies.lootbox_history.length > 0 && (
        <div className="trade-dest__section" style={{ padding: '0 16px' }}>История выпадения · последние 5</div>
      )}
      {dailies.lootbox_history.slice(0, 5).map((h, idx) => (
        <Div key={idx} style={{ opacity: 0.85 }}>
          <p style={{ marginBottom: 0 }}>
            {h.emoji} {h.name}: {h.reward_summary}
          </p>
        </Div>
      ))}
    </Group>
  );
}

function DailyQuestsTab({ dailies }) {
  const hours = Math.floor(dailies.seconds_until_reset / 3600);
  const minutes = Math.floor((dailies.seconds_until_reset % 3600) / 60);
  return (
    <>
      <Group header={<Header>🗓️ Ежедневные задания</Header>}>
        {dailies.quests.map((q) => (
          <div className="stat-row" key={q.id}>
            <span className="stat-row__label">
              {q.completed ? '✅' : '▫️'} {q.title}: {q.progress_label}
            </span>
            <span className="stat-row__value">
              {q.progress}/{q.target}
            </span>
          </div>
        ))}
        <Div>
          <p>🔥 Стрик ежедневок: {dailies.daily_streak} дней</p>
          {dailies.next_milestone_day && (
            <p style={{ opacity: 0.8 }}>
              Следующий рубеж: день {dailies.next_milestone_day} - {dailies.next_milestone_reward_text}
            </p>
          )}
          <p style={{ opacity: 0.8 }}>
            ⏳ До сброса дня: {hours}ч {minutes}м
          </p>
        </Div>
      </Group>
      <LootboxSection dailies={dailies} />
    </>
  );
}

function LoginCycleTab({ login }) {
  return (
    <Group header={<Header>📅 Награда за вход</Header>}>
      <Div>
        <p>Стрик входа: {login.login_streak} дней</p>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', margin: '8px 0' }}>
          {Array.from({ length: login.cycle_length }, (_, i) => i + 1).map((day) => (
            <div
              key={day}
              title={login.rewards_text?.[day] || ''}
              style={{
                width: 28,
                height: 28,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 6,
                fontSize: 12,
                background: day === login.cycle_day ? 'var(--vkui--color_accent_blue)' : 'var(--vkui--color_background_secondary)',
                color: day === login.cycle_day ? '#fff' : 'inherit',
              }}
            >
              {day}
            </div>
          ))}
        </div>
        {login.today_reward && (
          <p style={{ opacity: 0.8 }}>
            Награда дня: {login.today_reward_text} ({login.claimed_today ? 'уже получена сегодня' : 'будет выдана автоматически'})
          </p>
        )}
      </Div>
    </Group>
  );
}

export default function DailiesTab() {
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
      <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
        <Spinner size="l" />
      </Div>
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
          <StoryTab story={data.story} />
          <ChronicleSection song={data.song} titles={data.titles} />
        </>
      )}
      {section === 'dailies' && <DailyQuestsTab dailies={data.dailies} />}
      {section === 'login' && <LoginCycleTab login={data.login} />}
    </>
  );
}
