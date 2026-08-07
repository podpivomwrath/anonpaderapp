import { useEffect, useState } from 'react';
import {
  Tabs, TabsItem, Group, Header, Div, Spinner, Placeholder, Button, Input, FormItem, Select, Textarea,
} from '@vkontakte/vkui';
import {
  getAdminOverview, searchAdminPlayers, getAdminPlayer, postAdminAction, getAdminJournal,
} from '../api.js';

// Патч 27, ч.2: вкладка «Админ» — видна только если character.is_admin
// (сервер сам это подтвердил в /character); но КАЖДЫЙ вызов ниже сервер
// перепроверяет заново (403 при несовпадении vk_id) — эта вкладка не
// является источником прав, только удобство отображения.
//
// Патч 31, п.4: раздел «Баги» убран из интерфейса — репорты приходят в ЛС
// администратору от бота, этого достаточно. Таблица bug_reports и её API
// (bot/miniapp_admin_api.py, api.js::getAdminBugReports/setAdminBugReportStatus)
// не тронуты — данные продолжают сохраняться для истории.
const SECTIONS = [
  { id: 'overview', label: 'Обзор' },
  { id: 'player', label: 'Игрок' },
  { id: 'journal', label: 'Журнал' },
];

function StatRow({ label, value }) {
  return (
    <div className="stat-row">
      <span className="stat-row__label">{label}</span>
      <span className="stat-row__value">{value}</span>
    </div>
  );
}

function OverviewSection() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    setStatus('loading');
    getAdminOverview()
      .then((res) => { setData(res); setStatus('ready'); })
      .catch(() => setStatus('error'));
  }, []);

  if (status === 'loading') return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 24 }}><Spinner size="l" /></Div>;
  if (status === 'error' || !data) return <Placeholder>Не удалось загрузить обзор.</Placeholder>;

  const { players, progression, retention, economy, combat } = data;
  return (
    <>
      <Group header={<Header>👥 Игроки</Header>}>
        <StatRow label="Всего персонажей" value={players.total_characters} />
        <StatRow label="Застряло на создании" value={players.stuck_onboarding} />
        <StatRow label="Активны за 24ч / 7д / 30д" value={`${players.active_24h} / ${players.active_7d} / ${players.active_30d}`} />
        <StatRow label="Новых сегодня / за неделю" value={`${players.new_today} / ${players.new_week}`} />
      </Group>
      <Group header={<Header>📈 Прогрессия</Header>}>
        <StatRow label="Дошли до 30 ур. (подкласс)" value={progression.reached_subclass_level} />
        <StatRow label="Средний уровень активных (7д)" value={progression.avg_level_active_7d} />
        {Object.entries(progression.level_buckets).map(([bucket, count]) => (
          <StatRow key={bucket} label={`Ур. ${bucket}`} value={count} />
        ))}
        {Object.entries(progression.by_class).map(([cls, count]) => (
          <StatRow key={cls} label={`Класс: ${cls}`} value={count} />
        ))}
        {Object.entries(progression.by_region).map(([region, count]) => (
          <StatRow key={region} label={`Регион: ${region}`} value={count} />
        ))}
      </Group>
      <Group header={<Header>📉 Удержание</Header>}>
        <StatRow label="Одна сессия и не вернулись" value={retention.one_session_gone} />
        {Object.entries(retention.dropoff_level_buckets).map(([bucket, count]) => (
          <StatRow key={bucket} label={`Отвалились на ур. ${bucket}`} value={count} />
        ))}
        {Object.keys(retention.dropoff_level_buckets).length === 0 && (
          <Div style={{ opacity: 0.7 }}>Нет отвалившихся за последние 7 дней.</Div>
        )}
      </Group>
      <Group header={<Header>💰 Экономика</Header>}>
        <StatRow label="Золота всего" value={economy.total_gold} />
        <StatRow label="Самоцветов всего" value={economy.total_gems} />
        {Object.entries(economy.trophies_in_circulation).map(([id, count]) => (
          <StatRow key={id} label={`Трофей: ${id}`} value={count} />
        ))}
      </Group>
      <Group header={<Header>⚔️ Бой</Header>}>
        <StatRow label="Смертей за 24ч" value={combat.deaths_24h} />
        <StatRow label="PvP-боёв за 24ч" value={combat.pvp_battles_24h} />
        {Object.entries(combat.deaths_by_zone_24h).map(([zone, count]) => (
          <StatRow key={zone} label={`Зона ${zone} ур.`} value={count} />
        ))}
      </Group>
    </>
  );
}

function ActionForm({ playerId, onDone }) {
  const [action, setAction] = useState('grant_currency');
  const [fields, setFields] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const set = (key) => (e) => setFields((f) => ({ ...f, [key]: e.target.value }));

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const params = {};
      if (action === 'grant_currency') {
        params.currency = fields.currency || 'farm';
        params.amount = parseInt(fields.amount, 10) || 0;
      } else if (action === 'grant_xp') {
        params.amount = parseInt(fields.amount, 10) || 0;
      } else if (action === 'grant_trophy') {
        params.trophy_id = fields.trophy_id || '';
        params.amount = parseInt(fields.amount, 10) || 0;
      } else if (action === 'grant_item') {
        params.ilvl = parseInt(fields.ilvl, 10) || 1;
      } else if (action === 'set_level') {
        params.level = parseInt(fields.level, 10) || 1;
        params.confirm = true;
      } else if (action === 'teleport') {
        params.x = parseInt(fields.x, 10) || 0;
        params.y = parseInt(fields.y, 10) || 0;
      } else if (action === 'reset_stats') {
        params.confirm = true;
      } else if (action === 'ban') {
        params.reason = fields.reason || '';
        params.confirm = true;
      }
      const updated = await postAdminAction(playerId, action, params);
      onDone(updated);
    } catch (e) {
      setError(e.message || 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Group header={<Header>Действие</Header>}>
      <FormItem top="Действие">
        <Select
          value={action}
          onChange={(e) => setAction(e.target.value)}
          options={[
            { value: 'grant_currency', label: 'Выдать/забрать валюту' },
            { value: 'grant_xp', label: 'Выдать опыт' },
            { value: 'grant_trophy', label: 'Выдать трофей' },
            { value: 'grant_item', label: 'Выдать случайный предмет' },
            { value: 'set_level', label: 'Изменить уровень' },
            { value: 'teleport', label: 'Телепорт' },
            { value: 'restore_hp', label: 'Восстановить HP + снять респавн' },
            { value: 'reset_activity', label: 'Сбросить активности (аналог /застрял)' },
            { value: 'reset_stats', label: 'Сбросить статы' },
            { value: 'ban', label: 'Забанить' },
            { value: 'unban', label: 'Разбанить' },
          ]}
        />
      </FormItem>

      {action === 'grant_currency' && (
        <>
          <FormItem top="Валюта">
            <Select
              value={fields.currency || 'farm'}
              onChange={(e) => setFields((f) => ({ ...f, currency: e.target.value }))}
              options={[{ value: 'farm', label: '💰 Золото' }, { value: 'donate', label: '💎 Самоцветы' }]}
            />
          </FormItem>
          <FormItem top="Количество (можно отрицательное — забрать)">
            <Input type="number" value={fields.amount || ''} onChange={set('amount')} />
          </FormItem>
        </>
      )}
      {action === 'grant_xp' && (
        <FormItem top="Опыт">
          <Input type="number" value={fields.amount || ''} onChange={set('amount')} />
        </FormItem>
      )}
      {action === 'grant_trophy' && (
        <>
          <FormItem top="ID трофея">
            <Input value={fields.trophy_id || ''} onChange={set('trophy_id')} placeholder="ash_dust" />
          </FormItem>
          <FormItem top="Количество">
            <Input type="number" value={fields.amount || ''} onChange={set('amount')} />
          </FormItem>
        </>
      )}
      {action === 'grant_item' && (
        <FormItem top="Уровень предмета (ilvl)">
          <Input type="number" value={fields.ilvl || ''} onChange={set('ilvl')} />
        </FormItem>
      )}
      {action === 'set_level' && (
        <FormItem top="Новый уровень">
          <Input type="number" value={fields.level || ''} onChange={set('level')} />
        </FormItem>
      )}
      {action === 'teleport' && (
        <>
          <FormItem top="X (-50..50)">
            <Input type="number" value={fields.x || ''} onChange={set('x')} />
          </FormItem>
          <FormItem top="Y (-50..50)">
            <Input type="number" value={fields.y || ''} onChange={set('y')} />
          </FormItem>
        </>
      )}
      {action === 'ban' && (
        <FormItem top="Причина">
          <Textarea value={fields.reason || ''} onChange={set('reason')} />
        </FormItem>
      )}

      {error && <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{error}</Div>}
      <Div>
        <Button size="l" stretched loading={busy} onClick={run}>Выполнить</Button>
      </Div>
    </Group>
  );
}

// Патч 31, п.5: человеко-читаемый статус игрока — приоритет так же, как в
// игре (мёртв/бой перебивают перемещение, перемещение перебивает "в городе").
function statusLabel(card) {
  if (card.is_dead) return '☠ Мёртв';
  if (card.in_combat) return '⚔️ В бою (PvE)';
  if (card.in_pvp) return '⚔️ В PvP-бою';
  if (card.mount_travel) return `🐎 В пути на маунте → (${card.mount_travel.to_x}; ${card.mount_travel.to_y})`;
  if (card.foot_travel) return `🚶 В пути пешком → (${card.foot_travel.to_x}; ${card.foot_travel.to_y})`;
  if (card.busy) return '⏳ Занят (исследование/отдых)';
  if (card.in_city) return '🏙 В городе';
  return '🗺 На карте';
}

function PlayerCard({ card, onRefresh }) {
  return (
    <>
      <Group header={<Header>{card.name}{card.title ? ` «${card.title}»` : ''} (vk_id {card.vk_id})</Header>}>
        <StatRow label="Ник" value={card.name} />
        <StatRow label="vk_id" value={card.vk_id ?? '—'} />
        <StatRow label="Создан" value={card.created_at ? new Date(card.created_at).toLocaleString('ru') : '—'} />
        <StatRow label="Последняя активность" value={card.last_active_at ? new Date(card.last_active_at).toLocaleString('ru') : '—'} />
        <StatRow label="Титул" value={card.title || '—'} />
      </Group>

      <Group header={<Header>Прогресс</Header>}>
        <StatRow label="Уровень" value={`${card.level} (опыт ${card.experience} / ${card.xp_to_next})`} />
        <StatRow label="Класс" value={`${card.class_title}${card.subclass ? ` (${card.subclass})` : ''}`} />
        <StatRow label="Регион" value={card.region || '—'} />
        <StatRow label="Позиция" value={`(${card.pos_x}; ${card.pos_y})`} />
        <StatRow label="Состояние" value={statusLabel(card)} />
      </Group>

      {card.stats && (
        <Group header={<Header>Характеристики</Header>}>
          <StatRow label="СИЛ / ЛОВ / ИНТ / ВЫН / ВОЛ" value={`${card.stats.str} / ${card.stats.agi} / ${card.stats.int} / ${card.stats.vit} / ${card.stats.wil}`} />
          <StatRow label="Свободных очков" value={card.stats.unspent_points} />
          {card.derived && (
            <>
              <StatRow label="HP (текущее / макс.)" value={`${card.derived.current_hp} / ${card.derived.max_hp}`} />
              <StatRow label="Урон" value={card.derived.damage} />
              <StatRow label="Шанс крита" value={`${Math.round(card.derived.crit_chance * 100)}%`} />
              <StatRow label="Снижение урона" value={`${Math.round(card.derived.mitigation * 100)}%`} />
              <StatRow label="Сопротивление контролю" value={`${Math.round(card.derived.control_resist * 100)}%`} />
              <StatRow label="Сила поддержки" value={card.derived.support_power} />
            </>
          )}
        </Group>
      )}

      <Group header={<Header>Ресурсы</Header>}>
        <StatRow label="Золото / Самоцветы" value={`${card.gold} / ${card.gems}`} />
        {Object.entries(card.trophies).map(([id, count]) => (
          <StatRow key={id} label={`Трофей: ${id}`} value={count} />
        ))}
      </Group>

      <Group header={<Header>Снаряжение</Header>}>
        {card.inventory.length === 0 && <Div style={{ opacity: 0.7 }}>Инвентарь пуст.</Div>}
        {card.inventory.map((item) => (
          <StatRow
            key={item.id}
            label={`${item.equipped ? '✅ ' : ''}${item.name} (${item.slot}, ${item.rarity || '—'})`}
            value={`ур. ${item.ilvl}`}
          />
        ))}
        {card.elixirs.length === 0 && <Div style={{ opacity: 0.7 }}>Зелий и эликсиров нет.</Div>}
        {card.elixirs.map((e) => (
          <StatRow key={e.id} label={`${e.emoji} ${e.name}`} value={`×${e.count}`} />
        ))}
      </Group>

      <Group header={<Header>Маунты</Header>}>
        {card.mounts.length === 0 && <Div style={{ opacity: 0.7 }}>Маунтов нет.</Div>}
        {card.mounts.map((m) => (
          <StatRow key={m.mount_id} label={`${m.emoji} ${m.name}`} value={m.rarity} />
        ))}
        {card.mount_travel && (
          <StatRow
            label="Активный путь"
            value={`(${card.mount_travel.to_x}; ${card.mount_travel.to_y}) · осталось ${Math.round(card.mount_travel.remaining_seconds)} сек.`}
          />
        )}
      </Group>

      <Group header={<Header>Прогрессия контента</Header>}>
        <StatRow label="Текущий квест" value={card.current_quest || '—'} />
        {card.story_progress.map((s) => (
          <StatRow key={s.region} label={`Сюжет: ${s.region}`} value={`акт ${s.act}, шаг ${s.quest_step ?? '—'} (${s.status})`} />
        ))}
        <StatRow label="Микробаффы" value={`${card.trial_progress.unlocked} / ${card.trial_progress.total}`} />
        <StatRow
          label="Активный пресет"
          value={card.active_preset ? `${card.active_preset.name} (${card.active_preset.buff_ids.length} баффов)` : '—'}
        />
        <StatRow label="Пепельная Песнь" value={`${card.song_progress.seen} / ${card.song_progress.total}${card.song_progress.complete ? ' ✅' : ''}`} />
      </Group>

      <Group header={<Header>Активность</Header>}>
        <StatRow label="Стрики (вход/ежедневки)" value={`${card.login_streak} / ${card.daily_streak}`} />
        <StatRow label="PvP" value={`${card.pvp_wins} побед / ${card.pvp_losses} поражений`} />
        {card.dailies_today.length === 0 && <Div style={{ opacity: 0.7 }}>Ежедневки на сегодня не назначены.</Div>}
        {card.dailies_today.map((q) => (
          <StatRow key={q.title} label={`${q.completed ? '✅ ' : ''}${q.title}`} value={`${q.progress} / ${q.target}`} />
        ))}
      </Group>

      <Group header={<Header>Служебное</Header>}>
        <StatRow label="Бан" value={card.is_banned ? `🚫 ${card.ban_reason || 'без причины'}${card.banned_until ? ` до ${new Date(card.banned_until).toLocaleString('ru')}` : ' (навсегда)'}` : 'нет'} />
        {card.recent_admin_actions.length === 0 && <Div style={{ opacity: 0.7 }}>Действий администратора не было.</Div>}
        {card.recent_admin_actions.map((a, i) => (
          <StatRow
            key={i}
            label={`${a.action_type} · ${new Date(a.created_at).toLocaleString('ru')}`}
            value={a.note || '—'}
          />
        ))}
      </Group>

      <ActionForm playerId={card.id} onDone={onRefresh} />
    </>
  );
}

function PlayerSection() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [card, setCard] = useState(null);
  const [status, setStatus] = useState('idle');

  const search = async () => {
    setStatus('loading');
    try {
      const res = await searchAdminPlayers(query);
      setResults(res.results);
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  const openCard = async (id) => {
    setStatus('loading');
    try {
      setCard(await getAdminPlayer(id));
      setStatus('ready');
    } catch {
      setStatus('error');
    }
  };

  return (
    <>
      <Group header={<Header>Поиск (ник или vk_id)</Header>}>
        <FormItem>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Валгар или 123456789" />
        </FormItem>
        <Div>
          <Button size="l" stretched onClick={search} loading={status === 'loading'}>Найти</Button>
        </Div>
        {results.map((r) => (
          <div className="stat-row" key={r.id} onClick={() => openCard(r.id)} style={{ cursor: 'pointer' }}>
            <span className="stat-row__label">
              {r.is_banned ? '🚫 ' : ''}{r.name} (vk_id {r.vk_id})
            </span>
            <span className="stat-row__value">ур. {r.level}</span>
          </div>
        ))}
      </Group>
      {card && <PlayerCard card={card} onRefresh={setCard} />}
    </>
  );
}

function JournalSection() {
  const [actions, setActions] = useState(null);
  const [status, setStatus] = useState('loading');

  useEffect(() => {
    getAdminJournal()
      .then((res) => { setActions(res.actions); setStatus('ready'); })
      .catch(() => setStatus('error'));
  }, []);

  if (status === 'loading') return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 24 }}><Spinner size="l" /></Div>;
  if (status === 'error' || !actions) return <Placeholder>Не удалось загрузить журнал.</Placeholder>;

  return (
    <Group header={<Header>Журнал действий</Header>}>
      {actions.length === 0 && <Div style={{ opacity: 0.7 }}>Пока пусто.</Div>}
      {actions.map((a) => (
        <Div key={a.id} style={{ borderBottom: '1px solid var(--vkui--color_separator_primary)', paddingBottom: 8 }}>
          <p style={{ marginBottom: 4 }}>
            <b>{a.action_type}</b> · персонаж #{a.target_character_id ?? '—'} · {new Date(a.created_at).toLocaleString('ru')}
          </p>
          {a.note && <p style={{ opacity: 0.8, marginBottom: 0 }}>{a.note}</p>}
        </Div>
      ))}
    </Group>
  );
}

export default function AdminTab() {
  const [section, setSection] = useState('overview');

  return (
    <>
      <Tabs>
        {SECTIONS.map((s) => (
          <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>
            {s.label}
          </TabsItem>
        ))}
      </Tabs>
      {section === 'overview' && <OverviewSection />}
      {section === 'player' && <PlayerSection />}
      {section === 'journal' && <JournalSection />}
    </>
  );
}
