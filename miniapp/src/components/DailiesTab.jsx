import { useEffect, useState } from 'react';
import { Tabs, TabsItem, Group, Header, Div, Spinner, Placeholder } from '@vkontakte/vkui';
import { getDailies } from '../api.js';

// Патч 23: вкладка «Задания» — три раздела (Сюжет/Ежедневные/Вход).
const SECTIONS = [
  { id: 'story', label: 'Сюжет' },
  { id: 'dailies', label: 'Ежедневные' },
  { id: 'login', label: 'Вход' },
];

function rewardText(reward) {
  if (!reward) return '';
  const parts = [];
  if (reward.gold) parts.push(`${reward.gold} золота`);
  if (reward.gems) parts.push(`💎 ${reward.gems} самоцветов`);
  if (reward.elixir) {
    const [elixirId, count] = reward.elixir;
    parts.push(`${elixirId} ×${count}`);
  }
  if (reward.elixirs_random_combat) {
    parts.push(`${reward.elixirs_random_combat} случайных боевых эликсира (по 2 шт.)`);
  }
  if (reward.title) parts.push(`титул «${reward.title}»`);
  return parts.join(', ');
}

function StoryTab({ story }) {
  return (
    <Group header={<Header>📜 Сюжет</Header>}>
      {story.active_quest ? (
        <Div>
          <p style={{ fontWeight: 600, marginBottom: 4 }}>{story.active_quest.title}</p>
          <p style={{ marginBottom: 8 }}>{story.active_quest.text}</p>
          {story.active_quest.target && (
            <p style={{ opacity: 0.8 }}>
              📍 Цель: ({story.active_quest.target.x}; {story.active_quest.target.y}) —{' '}
              {story.active_quest.target.label}
            </p>
          )}
          {story.active_quest.ready && <p style={{ opacity: 0.8 }}>Цель достигнута — вернись к наставнику.</p>}
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

function SongSection({ song }) {
  return (
    <Group header={<Header>🩶 Пепельная Песнь {song.read ? '(прочитана)' : song.complete ? '(собрана)' : ''}</Header>}>
      {song.fragments.map((f) => (
        <Div key={f.index} style={{ opacity: f.seen ? 1 : 0.5 }}>
          <p style={{ marginBottom: 0 }}>{f.seen ? f.text : '???'}</p>
        </Div>
      ))}
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
      {dailies.lootbox_history.map((h, idx) => (
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
              Следующий рубеж: день {dailies.next_milestone_day} — {rewardText(dailies.next_milestone_reward)}
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
            Награда дня: {rewardText(login.today_reward)} ({login.claimed_today ? 'уже получена сегодня' : 'будет выдана автоматически'})
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
          <SongSection song={data.song} />
        </>
      )}
      {section === 'dailies' && <DailyQuestsTab dailies={data.dailies} />}
      {section === 'login' && <LoginCycleTab login={data.login} />}
    </>
  );
}
