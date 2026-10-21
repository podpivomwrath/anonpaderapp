import { createContext, useContext, useEffect, useState } from 'react';
import {
  Tabs, TabsItem, Group, Header, Div, Spinner, Placeholder, Button, Input, FormItem, Select, Textarea, Checkbox,
  Caption, SimpleCell,
} from '@vkontakte/vkui';
import {
  getAdminOverview, searchAdminPlayers, getAdminPlayer, postAdminAction, getAdminJournal,
  getAdminPromoCodes, createAdminPromoCode, deleteAdminPromoCode, getAdminPromoCodeActivations,
  resetAdminActivities, getAdminMiningStats, refillAdminMining, getAdminCatalog,
  getAdminBugReports, setAdminBugReportStatus, getAdminDonations, postAdminDonations,
} from '../api.js';

// Патч 27, ч.2: вкладка «Админ» - видна только если character.is_admin
// (сервер сам это подтвердил в /character); но КАЖДЫЙ вызов ниже сервер
// перепроверяет заново (403 при несовпадении vk_id) - эта вкладка не
// является источником прав, только удобство отображения.
//
// Раздел «Баги» убирали в патче 31 (репорты и так приходят в ЛС), вернули
// 2026-10-13: без него репорт нельзя было отметить разобранным.
// Имя игрока в панели - ссылка на его карточку в разделе «Игрок»
// (2026-10-15). Только здесь: в самой игре имена ссылками не бывают.
const OpenPlayerContext = createContext(null);

function PlayerLink({ id, name }) {
  const openPlayer = useContext(OpenPlayerContext);
  if (!id || !openPlayer) return <>{name}</>;
  return (
    <span
      role="link" tabIndex={0}
      onClick={() => openPlayer(id)}
      onKeyDown={(e) => { if (e.key === 'Enter') openPlayer(id); }}
      style={{ color: 'var(--vkui--color_text_accent)', cursor: 'pointer', textDecoration: 'underline' }}
    >
      {name}
    </span>
  );
}

// Текст журнала с именем цели внутри: имя - ссылкой.
function TextWithPlayer({ text, name, id }) {
  if (!name || !id || !text || !text.includes(name)) return <>{text}</>;
  const at = text.indexOf(name);
  return <>{text.slice(0, at)}<PlayerLink id={id} name={name} />{text.slice(at + name.length)}</>;
}

const SECTIONS = [
  { id: 'overview', label: 'Обзор' },
  { id: 'player', label: 'Игрок' },
  { id: 'journal', label: 'Журнал' },
  { id: 'mining', label: '⛏ Руда' },
  { id: 'promo', label: '🎟 Промокоды' },
  { id: 'bugs', label: '🐞 Баги' },
  { id: 'donations', label: '💰 Донаты' },
];

function StatRow({ label, value }) {
  return (
    <div className="stat-row">
      <span className="stat-row__label">{label}</span>
      <span className="stat-row__value">{value}</span>
    </div>
  );
}

// Патч 58: кнопка «вытащить всех из зависания» после рестарта сервера.
// Подтверждение обязательно: действие рассылает сообщение ВСЕМ игрокам, а
// такое нельзя запускать одним случайным касанием.
function MaintenanceSection() {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  async function run() {
    setBusy(true);
    setResult(null);
    try {
      const res = await resetAdminActivities();
      setResult({
        ok: true,
        text: `Сброшено: пеших переходов ${res.travel_reset}, поездок ${res.mount_reset}, `
          + `снастей ${res.fishing_reset}, добыч ${res.mining_reset}. `
          + `Уведомлено игроков: ${res.notified}.`,
      });
    } catch {
      setResult({ ok: false, text: 'Не удалось сбросить состояния.' });
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <Group header={<Header>🛠 Обслуживание</Header>}>
      <Div>
        <Caption level="1" style={{ opacity: 0.7, display: 'block', marginBottom: 8 }}>
          Отменяет пешие переходы, поездки на маунте и заброшенные снасти у всех
          игроков, затем рассылает всем служебное сообщение с актуальной
          клавиатурой. Позиции, инвентарь, статы и садок не трогает.
        </Caption>
        {confirming ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <Button mode="primary" loading={busy} onClick={run} stretched>
              Да, сбросить всем
            </Button>
            <Button mode="secondary" disabled={busy} onClick={() => setConfirming(false)} stretched>
              Отмена
            </Button>
          </div>
        ) : (
          <Button mode="secondary" onClick={() => setConfirming(true)} stretched>
            Сбросить состояния всех игроков
          </Button>
        )}
        {result && (
          <Caption
            level="1"
            style={{ display: 'block', marginTop: 8, color: result.ok ? undefined : '#c81e3a' }}
          >
            {result.text}
          </Caption>
        )}
      </Div>
    </Group>
  );
}

// Патч 61: телеметрия горного дела. Смотрим не остаток в жилах (он не
// показывает ни оборота, ни скорости), а журнал событий: сколько собрали,
// какой руды, и успевает ли спавн за добычей.
function MiningSection() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = () => {
    setStatus('loading');
    getAdminMiningStats(24)
      .then((res) => { setData(res); setStatus('ready'); })
      .catch(() => setStatus('error'));
  };

  useEffect(load, []);

  async function refill() {
    setBusy(true);
    setNotice(null);
    try {
      const res = await refillAdminMining();
      setNotice(`Добавлено ${res.added} руды, в жилах ${res.in_veins}.`);
      load();
    } catch {
      setNotice('Не удалось пополнить жилы.');
    } finally {
      setBusy(false);
    }
  }

  if (status === 'loading') return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 24 }}><Spinner size="l" /></Div>;
  if (status === 'error' || !data) return <Placeholder>Не удалось загрузить статистику руды.</Placeholder>;

  const balance = data.spawned_window - data.dug_window;
  return (
    <>
      <Group header={<Header>⛏ Руда в мире</Header>}>
        <StatRow label="Сейчас в жилах" value={`${data.in_veins} / ${data.veins_total * data.vein_cap}`} />
        <StatRow label="Непустых жил" value={`${data.veins_with_ore} из ${data.veins_total}`} />
        <StatRow label="Добыто всего" value={data.dug_total} />
        <StatRow label="Заспавнено всего" value={data.spawned_total} />
        <StatRow label="Из рудников / из жил" value={`${data.dug_from_veins} / ${data.dug_from_event_veins}`} />
      </Group>

      <Group header={<Header>📈 За {data.hours} ч</Header>}>
        <StatRow label="Заспавнено" value={`${data.spawned_window} (${data.spawn_per_hour}/ч)`} />
        <StatRow label="Добыто" value={`${data.dug_window} (${data.dig_per_hour}/ч)`} />
        <StatRow label="Баланс" value={balance >= 0 ? `+${balance} (спавн успевает)` : `${balance} (выкапывают быстрее)`} />
        <StatRow
          label="Добыча длится"
          value={data.avg_dig_seconds
            ? `в среднем ${Math.round(data.avg_dig_seconds / 60)} мин, максимум ${Math.round(data.max_dig_seconds / 60)} мин`
            : 'нет данных'}
        />
      </Group>

      {data.ores.length > 0 && (
        <Group header={<Header>🪨 Что добывают</Header>}>
          {data.ores.map((ore) => (
            <StatRow
              key={ore.name}
              label={`${ore.emoji} ${ore.name}`}
              value={`${ore.total} шт. · ${Object.entries(ore.by_grade).map(([g, n]) => `${g} ${n}`).join(', ')}`}
            />
          ))}
        </Group>
      )}

      <Group header={<Header>🛠 Тестовое</Header>}>
        <Div>
          <Caption level="1" style={{ opacity: 0.7, display: 'block', marginBottom: 8 }}>
            Наполняет все жилы до кромки. В статистику эти события не попадают —
            иначе они исказили бы картину настоящего спавна.
          </Caption>
          <Button mode="secondary" loading={busy} onClick={refill} stretched>
            Пополнить руду по всей карте
          </Button>
          {notice && (
            <Caption level="1" style={{ display: 'block', marginTop: 8 }}>{notice}</Caption>
          )}
        </Div>
      </Group>
    </>
  );
}

// Баг-репорты (вернулись 2026-10-13): репорты по-прежнему приходят в ЛС, а
// здесь их разбирают - без статусов счётчик «не разобрано» в обзоре только рос.
const BUG_FILTERS = [
  { id: 'new', label: 'Новые' },
  { id: 'in_progress', label: 'В работе' },
  { id: 'closed', label: 'Разобраны' },
];
const BUG_ACTIONS = {
  new: [['in_progress', 'В работу'], ['closed', '✅ Разобран']],
  in_progress: [['closed', '✅ Разобран'], ['new', 'Вернуть в новые']],
  closed: [['new', 'Открыть снова']],
};

function BugsSection() {
  const [filter, setFilter] = useState('new');
  const [reports, setReports] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setReports(null);
    setError(null);
    getAdminBugReports(filter)
      .then((res) => setReports(res.reports))
      .catch(() => setError('Не удалось загрузить репорты.'));
  }, [filter]);

  const move = async (id, status) => {
    setBusyId(id);
    try {
      await setAdminBugReportStatus(id, status);
      // Репорт ушёл в другой фильтр - из этого списка убираем.
      setReports((list) => list.filter((r) => r.id !== id));
    } catch {
      setError('Не удалось сменить статус.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <>
      <Group>
        <Tabs>
          {BUG_FILTERS.map((f) => (
            <TabsItem key={f.id} selected={filter === f.id} onClick={() => setFilter(f.id)}>{f.label}</TabsItem>
          ))}
        </Tabs>
      </Group>
      {error && <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{error}</Div>}
      {reports === null && !error && <Div style={{ display: 'flex', justifyContent: 'center' }}><Spinner size="m" /></Div>}
      {reports && reports.length === 0 && <Placeholder>Здесь пусто.</Placeholder>}
      {reports && reports.map((r) => {
        const snap = r.snapshot || {};
        const attachments = snap.attachments || [];
        return (
          <Group key={r.id} header={<Header>#{r.id} · {snap.name ? <PlayerLink id={r.character_id} name={snap.name} /> : 'без персонажа'} · {new Date(r.created_at).toLocaleString('ru')}</Header>}>
            <Div>
              <Caption level="1" style={{ opacity: 0.7 }}>
                {snap.level ? `${snap.level} ур. · ${snap.class_title || ''} · ` : ''}
                {snap.pos_x != null ? `(${snap.pos_x}; ${snap.pos_y}) · ` : ''}
                {snap.state || ''}{snap.vk_id ? ` · vk ${snap.vk_id}` : ''}
              </Caption>
              <p style={{ whiteSpace: 'pre-wrap', margin: '8px 0' }}>{r.text}</p>
              {attachments.map((a, i) => (
                (a.url || a.id)
                  ? <p key={i} style={{ margin: '2px 0' }}><a href={a.url || `https://vk.com/${a.id}`} target="_blank" rel="noopener noreferrer">📎 {a.title || ({ photo: 'Скриншот', video: 'Видео' }[a.type] || 'Файл')}</a></p>
                  : <p key={i} style={{ margin: '2px 0' }}>📎 {a.type === 'video' ? 'Видео' : a.type} {a.id || ''}</p>
              ))}
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
                {(BUG_ACTIONS[r.status] || []).map(([status, label]) => (
                  <Button key={status} size="s" mode={status === 'closed' ? 'primary' : 'secondary'}
                    disabled={busyId === r.id} onClick={() => move(r.id, status)}>
                    {label}
                  </Button>
                ))}
              </div>
            </Div>
          </Group>
        );
      })}
    </>
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

  const { players, progression, retention, economy, combat, systems = [] } = data;
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
        {Object.entries(progression.by_subclass || {}).map(([sub, count]) => (
          <StatRow key={sub} label={`Подкласс: ${sub}`} value={count} />
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
        <StatRow label="Золота у игроков" value={economy.total_gold} />
        <StatRow label="Самоцветов у игроков" value={economy.total_gems} />
        {Object.entries(economy.trophies_in_circulation).map(([id, count]) => (
          <StatRow key={id} label={id} value={count} />
        ))}
      </Group>
      <Group header={<Header>⚔️ Бой</Header>}>
        <StatRow label="Смертей за 24ч" value={combat.deaths_24h} />
        <StatRow label="PvP-боёв за 24ч" value={combat.pvp_battles_24h} />
        {Object.entries(combat.deaths_by_zone_24h).map(([zone, count]) => (
          <StatRow key={zone} label={`Смертей в зоне ${zone} ур.`} value={count} />
        ))}
      </Group>
      {/* Системы игры (2026-10-13): блоки и подписи готовит сервер. */}
      {systems.map((block) => (
        <Group key={block.title} header={<Header>{block.title}</Header>}>
          {block.rows.map((row) => <StatRow key={row.label} label={row.label} value={row.value} />)}
        </Group>
      ))}
    </>
  );
}

// Тексты отказов обнуления персонажа (bot/miniapp_admin_api.py, reset_character).
const RESET_ERRORS = {
  name_mismatch: 'Ник не совпал - персонаж не тронут.',
  in_battle: 'Игрок сейчас в бою (PvE/PvP/рейд/группа). Дождитесь конца боя.',
  guild_leader: 'Игрок - глава гильдии. Сначала передайте главу другому или распустите гильдию.',
};

function ActionForm({ playerId, playerName, onDone }) {
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
      } else if (action === 'reset_character') {
        params.confirm = true;
        params.confirm_name = fields.confirm_name || '';
      } else if (action === 'set_craft_level') {
        params.craft = fields.craft || 'herbalism';
        params.level = parseInt(fields.level, 10) || 1;
      } else if (action === 'ban') {
        params.reason = fields.reason || '';
        params.confirm = true;
      }
      const updated = await postAdminAction(playerId, action, params);
      onDone(updated);
    } catch (e) {
      // Патч 34, ч.3: тестовые предметы - только себе (services/admin_service.py::NotSelfTarget).
      const message = e.message === 'self_only'
        ? 'Тестовые предметы можно выдать только себе.'
        : RESET_ERRORS[e.message] || e.message || 'Ошибка';
      setError(message);
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
            { value: 'grant_admin_mount', label: '🛠 Выдать тестовый маунт (себе)' },
            { value: 'grant_admin_weapon', label: '🛠 Выдать тестовое оружие (себе)' },
            { value: 'set_level', label: 'Изменить уровень' },
            { value: 'set_craft_level', label: 'Уровень ремесла' },
            { value: 'clear_house_work', label: 'Снять работу в доме (варка/готовка)' },
            { value: 'teleport', label: 'Телепорт' },
            { value: 'restore_hp', label: 'Восстановить HP + снять респавн' },
            { value: 'reset_activity', label: 'Сбросить активности (аналог /застрял)' },
            { value: 'reset_stats', label: 'Сбросить статы' },
            { value: 'reset_character', label: '🗑 Обнулить персонажа (начать заново)' },
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
          <FormItem top="Количество (можно отрицательное - забрать)">
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
      {action === 'set_craft_level' && (
        <>
          <FormItem top="Ремесло">
            <Select
              value={fields.craft || 'herbalism'}
              onChange={(e) => setFields((f) => ({ ...f, craft: e.target.value }))}
              options={[
                { value: 'herbalism', label: '🌿 Травничество (до 50)' },
                { value: 'alchemy', label: '⚗️ Алхимия (до 50)' },
                { value: 'cooking', label: '🔥 Кулинария (до 50)' },
                { value: 'fishing', label: '🎣 Рыбалка' },
                { value: 'mining', label: '⛏ Горное дело' },
              ]}
            />
          </FormItem>
          <FormItem top="Уровень">
            <Input type="number" value={fields.level || ''} onChange={set('level')} />
          </FormItem>
        </>
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
      {action === 'reset_character' && (
        <>
          <Div style={{ color: 'var(--vkui--color_text_negative)' }}>
            Персонаж, инвентарь, золото, самоцветы, рыба, трофеи и прогресс будут удалены
            безвозвратно. Аккаунт останется: игрок начнёт заново с создания персонажа.
          </Div>
          <FormItem top={`Для подтверждения введите ник: ${playerName}`}>
            <Input value={fields.confirm_name || ''} onChange={set('confirm_name')} placeholder={playerName} />
          </FormItem>
        </>
      )}

      {error && <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{error}</Div>}
      <Div>
        <Button
          size="l" stretched loading={busy} onClick={run}
          appearance={action === 'reset_character' ? 'negative' : 'accent'}
          disabled={action === 'reset_character'
            && (fields.confirm_name || '').trim().toLowerCase() !== (playerName || '').trim().toLowerCase()}
        >
          {action === 'reset_character' ? 'Обнулить персонажа' : 'Выполнить'}
        </Button>
      </Div>
    </Group>
  );
}

// Патч 31, п.5: человеко-читаемый статус игрока - приоритет так же, как в
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

// Сворачиваемая группа карточки игрока - как слоты в сумке: строка с
// названием, по нажатию раскрывается. Изначально свёрнута: карточка длинная,
// а смотрят обычно одну-две группы.
function Fold({ title, children }) {
  const [open, setOpen] = useState(false);
  return (
    <Group>
      <SimpleCell onClick={() => setOpen((v) => !v)} after={open ? '▴' : '▾'}>
        <b>{title}</b>
      </SimpleCell>
      {open && children}
    </Group>
  );
}

// Патч 107: выдача любого предмета игры. Кнопка раскрывает типы, тип -
// предметы, предмет - форму выдачи. Каталог приходит с сервера целиком
// (admin_grant_service.catalog), так что новая руда или реликвия появится
// здесь без правки мини-аппа.
function GrantEntry({ entry, playerId, onDone }) {
  const [open, setOpen] = useState(false);
  const [variant, setVariant] = useState(entry.variants ? entry.variants[0].key : entry.key);
  const [amount, setAmount] = useState('1');
  const [ilvl, setIlvl] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    setBusy(true);
    setResult(null);
    try {
      const params = { key: variant, amount: parseInt(amount, 10) || 0 };
      if (entry.ilvl && ilvl) params.ilvl = parseInt(ilvl, 10) || 1;
      const updated = await postAdminAction(playerId, 'grant_any', params);
      setResult({ ok: true, text: `Выдано: ${updated.granted}` });
      onDone(updated);
    } catch (e) {
      const text = e.message === 'self_only' ? 'Это можно выдать только себе.' : e.message || 'Ошибка';
      setResult({ ok: false, text });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <SimpleCell onClick={() => setOpen((v) => !v)} after={open ? '▴' : '▾'} style={{ paddingLeft: 32 }}>
        {entry.label}
      </SimpleCell>
      {open && (
        <div style={{ paddingLeft: 32 }}>
          {entry.variants && (
            <FormItem top="Градация">
              <Select
                value={variant}
                onChange={(e) => setVariant(e.target.value)}
                options={entry.variants.map((v) => ({ value: v.key, label: v.label }))}
              />
            </FormItem>
          )}
          {entry.ilvl && (
            <FormItem top="Уровень предмета (пусто - уровень игрока)">
              <Input type="number" value={ilvl} onChange={(e) => setIlvl(e.target.value)} />
            </FormItem>
          )}
          {entry.amount !== 'one' && (
            <FormItem top={entry.amount === 'pieces' ? 'Сколько штук (до 50)' : 'Количество'}>
              <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} />
            </FormItem>
          )}
          <Div>
            <Button size="m" stretched loading={busy} onClick={run}>Выдать</Button>
            {result && (
              <Caption
                level="1"
                style={{ display: 'block', marginTop: 8, color: result.ok ? undefined : 'var(--vkui--color_text_negative)' }}
              >
                {result.text}
              </Caption>
            )}
          </Div>
        </div>
      )}
    </>
  );
}

function GrantGroup({ group, playerId, onDone }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <SimpleCell onClick={() => setOpen((v) => !v)} after={open ? '▴' : '▾'} style={{ paddingLeft: 16 }}>
        {group.title} <span style={{ opacity: 0.5 }}>· {group.entries.length}</span>
      </SimpleCell>
      {open && group.entries.map((entry) => (
        <GrantEntry key={entry.key} entry={entry} playerId={playerId} onDone={onDone} />
      ))}
    </>
  );
}

function GrantSection({ playerId, onDone }) {
  const [open, setOpen] = useState(false);
  const [groups, setGroups] = useState(null);
  const [error, setError] = useState(null);

  const toggle = () => {
    setOpen((v) => !v);
    if (groups === null) {
      getAdminCatalog()
        .then((res) => setGroups(res.groups))
        .catch(() => setError('Не удалось загрузить каталог.'));
    }
  };

  return (
    <Group>
      <SimpleCell onClick={toggle} after={open ? '▴' : '▾'}>
        <b>🎁 Выдать предмет</b>
      </SimpleCell>
      {open && error && <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{error}</Div>}
      {open && !error && groups === null && (
        <Div style={{ display: 'flex', justifyContent: 'center' }}><Spinner size="m" /></Div>
      )}
      {open && groups && groups.filter((g) => g.entries.length > 0).map((group) => (
        <GrantGroup key={group.id} group={group} playerId={playerId} onDone={onDone} />
      ))}
    </Group>
  );
}

function PlayerCard({ card, onRefresh }) {
  return (
    <>
      <Fold title={<>{card.is_premium ? '💠 ' : ''}{card.name}{card.title ? ` «${card.title}»` : ''} (vk_id {card.vk_id})</>}>
        <StatRow label="Ник" value={card.name} />
        <StatRow label="vk_id" value={card.vk_id ?? '-'} />
        <StatRow
          label="Страница VK"
          value={card.vk_id
            ? <a href={`https://vk.com/id${card.vk_id}`} target="_blank" rel="noopener noreferrer">{card.vk_name || `id${card.vk_id}`}</a>
            : '-'}
        />
        <StatRow label="Создан" value={card.created_at ? new Date(card.created_at).toLocaleString('ru') : '-'} />
        <StatRow label="Последняя активность" value={card.last_active_at ? new Date(card.last_active_at).toLocaleString('ru') : '-'} />
        <StatRow label="Титул" value={card.title || '-'} />
        <StatRow
          label="💠 Метка Хранителя"
          value={card.premium_until ? `до ${new Date(card.premium_until).toLocaleString('ru')}${card.is_premium ? '' : ' (истекла)'}` : 'нет'}
        />
      </Fold>

      <Fold title={<>Прогресс</>}>
        <StatRow label="Уровень" value={`${card.level} (опыт ${card.xp_to_next == null ? 'МАКС' : `${card.experience} / ${card.xp_to_next}`})`} />
        <StatRow label="Класс" value={card.class_title} />
        <StatRow label="Регион" value={card.region_title || '-'} />
        <StatRow label="Позиция" value={`(${card.pos_x}; ${card.pos_y})`} />
        <StatRow label="Состояние" value={statusLabel(card)} />
      </Fold>

      {card.stats && (
        <Fold title={<>Характеристики</>}>
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
              <StatRow
                label="Уклонение"
                value={`${Math.round(card.derived.dodge_chance * 100)}% (от способностей: ${Math.round(card.derived.ability_dodge_chance * 100)}%)`}
              />
            </>
          )}
        </Fold>
      )}

      <Fold title={<>Ресурсы</>}>
        <StatRow label="Золото / Самоцветы" value={`${card.gold} / ${card.gems}`} />
        {Object.entries(card.trophies).map(([id, count]) => (
          <StatRow key={id} label={`Трофей: ${id}`} value={count} />
        ))}
      </Fold>

      <Fold title={<>Снаряжение</>}>
        {card.inventory.length === 0 && <Div style={{ opacity: 0.7 }}>Инвентарь пуст.</Div>}
        {card.inventory.map((item) => (
          <StatRow
            key={item.id}
            label={`${item.equipped ? '✅ ' : ''}${item.name} (${item.slot_title}, ${item.rarity_title || '-'})`}
            value={`ур. ${item.ilvl}`}
          />
        ))}
        {card.elixirs.length === 0 && <Div style={{ opacity: 0.7 }}>Зелий и эликсиров нет.</Div>}
        {card.elixirs.map((e) => (
          <StatRow key={e.id} label={`${e.emoji} ${e.name}`} value={`×${e.count}`} />
        ))}
      </Fold>

      {card.crafts && (
        <Fold title={<>Ремесла, дом и еда</>}>
          {card.crafts.map((c) => (
            <StatRow key={c.title} label={c.title}
              value={`${c.level} ур.${c.xp_to_next ? ` (${c.xp} / ${c.xp_to_next})` : ''}`} />
          ))}
          <StatRow label="Дом" value={card.house.has ? (card.house.work || 'есть, сейчас пусто') : 'нет'} />
          <StatRow label="Сытость" value={card.food_buff || 'нет'} />
          <StatRow label="Садок / руда" value={`${card.fish_kg} кг / ${card.ore_pieces} шт.`} />
          {card.herbs.map((h) => <StatRow key={h.name} label={h.name} value={`×${h.count}`} />)}
          {card.food.map((f) => <StatRow key={f.name + f.grade} label={`${f.name} (рыба ${f.grade})`} value={`×${f.count}`} />)}
        </Fold>
      )}

      {card.flags && (
        <Fold title={<>Гильдия и покупки</>}>
          <StatRow label="Гильдия" value={card.guild ? `[${card.guild.tag}] ${card.guild.name}, ${card.guild.rank}` : 'нет'} />
          <StatRow label="Курьер" value={card.flags.courier ? 'есть' : 'нет'} />
          <StatRow label="Тайный карман" value={card.flags.pocket ? 'есть' : 'нет'} />
          <StatRow label="Подкласс" value={card.flags.subclass_declined ? 'отказался, путь базового класса' : (card.subclass_title || 'не выбран')} />
        </Fold>
      )}

      <Fold title={<>Маунты</>}>
        {card.mounts.length === 0 && <Div style={{ opacity: 0.7 }}>Маунтов нет.</Div>}
        {card.mounts.map((m) => (
          <StatRow key={m.mount_id} label={`${m.emoji} ${m.name}`} value={m.rarity_title || m.rarity} />
        ))}
        {card.mount_travel && (
          <StatRow
            label="Активный путь"
            value={`(${card.mount_travel.to_x}; ${card.mount_travel.to_y}) · осталось ${Math.round(card.mount_travel.remaining_seconds)} сек.`}
          />
        )}
      </Fold>

      <Fold title={<>Прогрессия контента</>}>
        <StatRow label="Текущий квест" value={card.current_quest || '-'} />
        {card.story_progress.map((s) => (
          <StatRow key={s.region} label={`Сюжет: ${s.region_title || s.region}`} value={`акт ${s.act}, шаг ${s.quest_step ?? '-'} (${s.status})`} />
        ))}
        <StatRow label="Микробаффы" value={`${card.trial_progress.unlocked} / ${card.trial_progress.total}`} />
        <StatRow
          label="Активный пресет"
          value={card.active_preset ? `${card.active_preset.name} (${card.active_preset.buff_ids.length} баффов)` : '-'}
        />
        <StatRow label="Пепельная Песнь" value={`${card.song_progress.seen} / ${card.song_progress.total}${card.song_progress.complete ? ' ✅' : ''}`} />
      </Fold>

      <Fold title={<>Активность</>}>
        <StatRow label="Стрики (вход/ежедневки)" value={`${card.login_streak} / ${card.daily_streak}`} />
        <StatRow label="PvP" value={`${card.pvp_wins} побед / ${card.pvp_losses} поражений`} />
        {card.dailies_today.length === 0 && <Div style={{ opacity: 0.7 }}>Ежедневки на сегодня не назначены.</Div>}
        {card.dailies_today.map((q) => (
          <StatRow key={q.title} label={`${q.completed ? '✅ ' : ''}${q.title}`} value={`${q.progress} / ${q.target}`} />
        ))}
      </Fold>

      <Fold title={<>Служебное</>}>
        <StatRow label="Бан" value={card.is_banned ? `🚫 ${card.ban_reason || 'без причины'}${card.banned_until ? ` до ${new Date(card.banned_until).toLocaleString('ru')}` : ' (навсегда)'}` : 'нет'} />
        {card.recent_admin_actions.length === 0 && <Div style={{ opacity: 0.7 }}>Действий администратора не было.</Div>}
        {card.recent_admin_actions.map((a, i) => (
          <StatRow
            key={i}
            label={a.text || a.action_type}
            value={new Date(a.created_at).toLocaleString('ru')}
          />
        ))}
      </Fold>

      <GrantSection playerId={card.id} onDone={onRefresh} />
      <ActionForm playerId={card.id} playerName={card.name} onDone={onRefresh} />
    </>
  );
}

function PlayerSection({ requestedId }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState(null); // null - поиска ещё не было
  const [card, setCard] = useState(null);
  const [status, setStatus] = useState('idle');
  const [errorMsg, setErrorMsg] = useState(null);
  const [notice, setNotice] = useState(null);

  // Ответ действия - обновлённая карточка; после обнуления персонажа карточки
  // нет (reset: true) - убираем её и показываем итог.
  const handleCardUpdate = (updated) => {
    if (updated && updated.reset) {
      setCard(null);
      setResults(null);
      setNotice(`Персонаж «${updated.name}» (vk_id ${updated.vk_id}) обнулён. Игрок начнёт заново.`);
      return;
    }
    setCard(updated);
  };

  const search = async () => {
    setStatus('loading');
    setErrorMsg(null);
    setNotice(null);
    setCard(null);
    try {
      const res = await searchAdminPlayers(query);
      setResults(res.results);
      setStatus('ready');
    } catch (e) {
      // Патч 34, ч.2: ошибка запроса (403/сеть/что угодно) раньше молча
      // проглатывалась - экран выглядел так же, как "ничего не нашли".
      setResults(null);
      setErrorMsg(e.message || 'Не удалось выполнить поиск');
      setStatus('error');
    }
  };

  const openCard = async (id) => {
    setStatus('loading');
    setErrorMsg(null);
    try {
      setCard(await getAdminPlayer(id));
      setStatus('ready');
    } catch (e) {
      setErrorMsg(e.message || 'Не удалось загрузить карточку игрока');
      setStatus('error');
    }
  };

  useEffect(() => {
    if (requestedId) openCard(requestedId.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedId]);

  return (
    <>
      <Group header={<Header>Поиск (ник, имя и фамилия в VK или vk_id)</Header>}>
        <FormItem>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') search(); }}
            placeholder="Валгар, Иван Петров или 123456789"
          />
        </FormItem>
        <Div>
          <Button size="l" stretched onClick={search} loading={status === 'loading'} disabled={!query.trim()}>
            Найти
          </Button>
        </Div>
        {errorMsg && (
          <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{errorMsg}</Div>
        )}
        {notice && <Div>✅ {notice}</Div>}
        {status === 'ready' && results && results.length === 0 && (
          <Div style={{ opacity: 0.7 }}>Игрок не найден.</Div>
        )}
        {results && results.map((r) => (
          <div className="stat-row" key={r.id} onClick={() => openCard(r.id)} style={{ cursor: 'pointer' }}>
            <span className="stat-row__label">
              {r.is_banned ? '🚫 ' : ''}{r.name}{r.vk_name ? ` · ${r.vk_name}` : ''} (vk_id {r.vk_id})
            </span>
            <span className="stat-row__value">ур. {r.level}</span>
          </div>
        ))}
      </Group>
      {card && <PlayerCard card={card} onRefresh={handleCardUpdate} />}
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
            <b>{a.who_character_id
              ? <TextWithPlayer text={a.who || 'Админ'} name={(a.who || '').replace(/^(Бывший модератор|Модератор) /, '')} id={a.who_character_id} />
              : (a.who || 'Админ')}</b>{' '}
            <TextWithPlayer text={a.text || a.action_type} name={a.target_name} id={a.target_character_id} />
          </p>
          <Caption level="1" style={{ opacity: 0.6 }}>{new Date(a.created_at).toLocaleString('ru')}</Caption>
        </Div>
      ))}
    </Group>
  );
}

// Патч 50: типы наград промокода - поля зависят от типа (см.
// services/promo_service.py::_apply_reward - те же ключи один в один).
const REWARD_TYPE_OPTIONS = [
  { value: 'gold', label: '💰 Золото' },
  { value: 'gems', label: '💎 Самоцветы' },
  { value: 'xp', label: '✨ Опыт' },
  { value: 'trophy', label: 'Трофей' },
  { value: 'elixir', label: 'Зелье/эликсир' },
  { value: 'raid_keys', label: '🗝 Ключи Монолита' },
  { value: 'lootbox', label: '🗃️ Пепельные ларцы' },
  { value: 'premium', label: '💠 Метка Хранителя' },
  { value: 'mount', label: '🐎 Маунт' },
];

function emptyReward() {
  return { type: 'gold', amount: '', trophy_id: '', elixir_id: '', days: 30, mount_id: '' };
}

function rewardToPayload(r) {
  if (r.type === 'gold' || r.type === 'gems' || r.type === 'xp' || r.type === 'raid_keys' || r.type === 'lootbox') {
    return { type: r.type, amount: parseInt(r.amount, 10) || 0 };
  }
  if (r.type === 'trophy') {
    return { type: 'trophy', trophy_id: r.trophy_id, amount: parseInt(r.amount, 10) || 0 };
  }
  if (r.type === 'elixir') {
    return { type: 'elixir', elixir_id: r.elixir_id, amount: parseInt(r.amount, 10) || 0 };
  }
  if (r.type === 'premium') {
    return { type: 'premium', days: parseInt(r.days, 10) || 0 };
  }
  if (r.type === 'mount') {
    return { type: 'mount', mount_id: r.mount_id };
  }
  return { type: r.type };
}

function rewardSummary(r) {
  if (r.type === 'gold') return `💰 ${r.amount ?? 0} золота`;
  if (r.type === 'gems') return `💎 ${r.amount ?? 0} самоцветов`;
  if (r.type === 'xp') return `✨ ${r.amount ?? 0} опыта`;
  if (r.type === 'raid_keys') return `🗝 ${r.amount ?? 0} ключей`;
  if (r.type === 'lootbox') return `🗃️ ${r.amount ?? 0} ларцов`;
  if (r.type === 'trophy') return `Трофей ${r.trophy_id || '?'} ×${r.amount ?? 0}`;
  if (r.type === 'elixir') return `Зелье ${r.elixir_id || '?'} ×${r.amount ?? 0}`;
  if (r.type === 'premium') return `💠 Премиум на ${r.days} дн.`;
  if (r.type === 'mount') return `🐎 ${r.mount_id || '?'}`;
  return r.type;
}

function RewardRow({ reward, onChange, onRemove }) {
  const set = (key) => (e) => onChange({ ...reward, [key]: e.target.value });
  return (
    <Div style={{ borderBottom: '1px solid var(--vkui--color_separator_primary)', paddingBottom: 8 }}>
      <FormItem top="Тип награды">
        <Select value={reward.type} onChange={set('type')} options={REWARD_TYPE_OPTIONS} />
      </FormItem>
      {(reward.type === 'gold' || reward.type === 'gems' || reward.type === 'xp' || reward.type === 'raid_keys' || reward.type === 'lootbox') && (
        <FormItem top={reward.type === 'lootbox' ? 'Сколько ларцов (до 50)' : 'Количество'}>
          <Input type="number" value={reward.amount} onChange={set('amount')} />
        </FormItem>
      )}
      {reward.type === 'trophy' && (
        <>
          <FormItem top="ID трофея"><Input value={reward.trophy_id} onChange={set('trophy_id')} placeholder="ash_dust" /></FormItem>
          <FormItem top="Количество"><Input type="number" value={reward.amount} onChange={set('amount')} /></FormItem>
        </>
      )}
      {reward.type === 'elixir' && (
        <>
          <FormItem top="ID эликсира"><Input value={reward.elixir_id} onChange={set('elixir_id')} placeholder="heal_small" /></FormItem>
          <FormItem top="Количество"><Input type="number" value={reward.amount} onChange={set('amount')} /></FormItem>
        </>
      )}
      {reward.type === 'premium' && (
        <FormItem top="Срок">
          <Select value={String(reward.days)} onChange={set('days')} options={[
            { value: '3', label: '3 дня' }, { value: '7', label: '7 дней' }, { value: '30', label: '30 дней' },
          ]} />
        </FormItem>
      )}
      {reward.type === 'mount' && (
        <FormItem top="ID маунта"><Input value={reward.mount_id} onChange={set('mount_id')} /></FormItem>
      )}
      <Button mode="tertiary" size="s" onClick={onRemove}>Убрать эту награду</Button>
    </Div>
  );
}

function PromoCreateForm({ onCreated }) {
  const [code, setCode] = useState('');
  const [rewards, setRewards] = useState([emptyReward()]);
  const [maxActivations, setMaxActivations] = useState('');
  const [onePerPlayer, setOnePerPlayer] = useState(true);
  const [expiresAt, setExpiresAt] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const updateReward = (i, next) => setRewards((rs) => rs.map((r, idx) => (idx === i ? next : r)));
  const removeReward = (i) => setRewards((rs) => rs.filter((_, idx) => idx !== i));
  const addReward = () => setRewards((rs) => [...rs, emptyReward()]);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await createAdminPromoCode({
        code,
        rewards: rewards.map(rewardToPayload),
        max_activations: maxActivations ? parseInt(maxActivations, 10) : null,
        one_per_player: onePerPlayer,
        expires_at: expiresAt || null,
      });
      setCode('');
      setRewards([emptyReward()]);
      setMaxActivations('');
      setExpiresAt('');
      onCreated();
    } catch (e) {
      setError(e.message || 'Не удалось создать код');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Group header={<Header>Новый промокод</Header>}>
      <FormItem top="Код">
        <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="MONOLITH2026" />
      </FormItem>
      <FormItem top="Лимит активаций (пусто - без лимита)">
        <Input type="number" value={maxActivations} onChange={(e) => setMaxActivations(e.target.value)} />
      </FormItem>
      <FormItem>
        <Checkbox checked={onePerPlayer} onChange={(e) => setOnePerPlayer(e.target.checked)}>
          Одна активация на игрока
        </Checkbox>
      </FormItem>
      <FormItem top="Действует до (пусто - бессрочно)">
        <Input type="datetime-local" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
      </FormItem>

      <Div style={{ opacity: 0.7, paddingBottom: 0 }}>Награды:</Div>
      {rewards.map((r, i) => (
        <RewardRow key={i} reward={r} onChange={(next) => updateReward(i, next)} onRemove={() => removeReward(i)} />
      ))}
      <Div>
        <Button mode="secondary" size="s" onClick={addReward}>+ Добавить награду</Button>
      </Div>

      {error && <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{error}</Div>}
      <Div>
        <Button size="l" stretched loading={busy} onClick={submit} disabled={!code.trim() || rewards.length === 0}>
          Создать код
        </Button>
      </Div>
    </Group>
  );
}

function PromoCodeRow({ promo, onDeleted }) {
  const [expanded, setExpanded] = useState(false);
  const [activations, setActivations] = useState(null);
  const [busy, setBusy] = useState(false);

  const toggle = async () => {
    if (!expanded && activations === null) {
      const res = await getAdminPromoCodeActivations(promo.id);
      setActivations(res.activations);
    }
    setExpanded((v) => !v);
  };

  const remove = async () => {
    setBusy(true);
    try {
      await deleteAdminPromoCode(promo.id);
      onDeleted();
    } finally {
      setBusy(false);
    }
  };

  const limitLabel = promo.max_activations == null
    ? `${promo.activation_count} активаций`
    : `${promo.activation_count} / ${promo.max_activations}`;

  return (
    <Div style={{ borderBottom: '1px solid var(--vkui--color_separator_primary)', paddingBottom: 8 }}>
      <div className="stat-row" style={{ cursor: 'pointer', padding: 0 }} onClick={toggle}>
        <span className="stat-row__label">{promo.code}</span>
        <span className="stat-row__value">{limitLabel}</span>
      </div>
      <p style={{ opacity: 0.7, fontSize: 13, margin: '4px 0' }}>
        {promo.rewards.map(rewardSummary).join(', ')}
      </p>
      <p style={{ opacity: 0.7, fontSize: 13, margin: '4px 0' }}>
        {promo.one_per_player ? 'Одна активация на игрока' : 'Можно активировать многократно'}
        {promo.expires_at ? ` · до ${new Date(promo.expires_at).toLocaleString('ru')}` : ' · бессрочно'}
      </p>
      {expanded && (
        <div style={{ paddingLeft: 8 }}>
          {activations && activations.length === 0 && <Div style={{ opacity: 0.7 }}>Пока никто не активировал.</Div>}
          {activations && activations.map((a, i) => (
            <p key={i} style={{ fontSize: 13, margin: '2px 0' }}>
              <PlayerLink id={a.character_id} name={a.character_name} /> · {new Date(a.activated_at).toLocaleString('ru')}
            </p>
          ))}
        </div>
      )}
      <Button mode="tertiary" size="s" loading={busy} onClick={remove}>Удалить код</Button>
    </Div>
  );
}

function PromoSection() {
  const [codes, setCodes] = useState(null);
  const [status, setStatus] = useState('loading');

  const load = () => {
    setStatus('loading');
    getAdminPromoCodes()
      .then((res) => { setCodes(res.codes); setStatus('ready'); })
      .catch(() => setStatus('error'));
  };

  useEffect(load, []);

  return (
    <>
      <PromoCreateForm onCreated={load} />
      <Group header={<Header>Существующие коды</Header>}>
        {status === 'loading' && <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 24 }}><Spinner size="l" /></Div>}
        {status === 'error' && <Placeholder>Не удалось загрузить коды.</Placeholder>}
        {status === 'ready' && codes.length === 0 && <Div style={{ opacity: 0.7 }}>Пока нет ни одного кода.</Div>}
        {status === 'ready' && codes.map((c) => (
          <PromoCodeRow key={c.id} promo={c} onDeleted={load} />
        ))}
      </Group>
    </>
  );
}

// --- Донаты (2026-10-16): кто и сколько задонатил - для выдачи после вайпа.
// Оплаты ЮKassa пишутся сами, остальное вносится здесь. Только владелец.

const rub = (v) => `${Number(v ?? 0).toLocaleString('ru-RU')} ₽`;

function DonationsSection() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [form, setForm] = useState({ donor: '', amount: '', vk_id: '', note: '' });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [confirmId, setConfirmId] = useState(null);

  useEffect(() => {
    getAdminDonations()
      .then((d) => { setData(d); setStatus('ready'); })
      .catch((e) => setStatus(e?.message === 'forbidden' ? 'forbidden' : 'error'));
  }, []);

  const send = async (params, ok) => {
    setBusy(true);
    setNotice(null);
    try {
      setData(await postAdminDonations(params));
      setNotice({ ok: true, text: ok });
      return true;
    } catch (e) {
      setNotice({ ok: false, text: e?.message || 'Не удалось.' });
      return false;
    } finally {
      setBusy(false);
      setConfirmId(null);
    }
  };

  const add = async () => {
    const amount = parseInt(form.amount, 10);
    const vk = form.vk_id.trim() ? parseInt(form.vk_id.replace(/\D/g, ''), 10) : null;
    const done = await send(
      { action: 'add', donor: form.donor.trim(), amount, vk_id: vk, note: form.note },
      `Записано: ${form.donor.trim()} - ${rub(amount)}.`,
    );
    if (done) setForm({ donor: '', amount: '', vk_id: '', note: '' });
  };

  if (status === 'loading') return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 24 }}><Spinner size="l" /></Div>;
  if (status === 'forbidden') return <Placeholder>Учёт донатов видит только владелец.</Placeholder>;
  if (status === 'error' || !data) return <Placeholder>Не удалось загрузить донаты.</Placeholder>;

  return (
    <>
      {notice && (
        <Div className={`craft-notice ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`} onClick={() => setNotice(null)}>
          {notice.text}
        </Div>
      )}
      <Group header={<Header>💰 По донатерам · всего {rub(data.total_rub)}</Header>}>
        {data.donors.length === 0 && <Div style={{ opacity: 0.7 }}>Донатов пока нет.</Div>}
        {data.donors.map((d) => (
          <div className="stat-row" key={`${d.vk_id}-${d.donor}`}>
            <span className="stat-row__label">
              {d.vk_id ? <a href={`https://vk.com/id${d.vk_id}`} target="_blank" rel="noreferrer">{d.donor}</a> : d.donor}
              {d.character_name ? ` · ${d.character_name}` : ''}
              {d.count > 1 ? ` · ${d.count} раз` : ''}
            </span>
            <span className="stat-row__value"><b>{rub(d.total_rub)}</b></span>
          </div>
        ))}
        <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
          Учёт хранится отдельно от персонажей и переживает вайп. Оплаты через ЮКассу записываются сами.
        </Caption>
      </Group>

      <Group header={<Header>Внести донат вручную</Header>}>
        <FormItem top="Кто (имя VK)">
          <Input value={form.donor} onChange={(e) => setForm({ ...form, donor: e.target.value })} />
        </FormItem>
        <FormItem top="Сумма, ₽">
          <Input type="number" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
        </FormItem>
        <FormItem top="VK id или ссылка (необязательно)">
          <Input value={form.vk_id} onChange={(e) => setForm({ ...form, vk_id: e.target.value })} />
        </FormItem>
        <FormItem top="Заметка (необязательно)">
          <Input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
        </FormItem>
        <Div>
          <Button size="m" disabled={busy || !form.donor.trim() || !(parseInt(form.amount, 10) > 0)} onClick={add}>
            Записать
          </Button>
        </Div>
      </Group>

      <Group header={<Header>Все записи</Header>}>
        {data.entries.map((r) => (
          <div className="stat-row" key={r.id}>
            <span className="stat-row__label">
              {r.donor}{r.character_name ? ` · ${r.character_name}` : ''}
              <Caption level="1" style={{ opacity: 0.7 }}>
                {r.created_at ? new Date(r.created_at).toLocaleString('ru-RU') : ''}
                {' · '}{r.source === 'yookassa' ? `ЮКасса${r.gems ? `, ${r.gems} 💎` : ''}` : 'вручную'}
                {r.note ? ` · ${r.note}` : ''}
              </Caption>
            </span>
            <span className="stat-row__value">
              <b>{rub(r.amount_rub)}</b>
              {r.source === 'manual' && (confirmId === r.id ? (
                <>
                  {' '}<Button size="s" mode="secondary" disabled={busy}
                    onClick={() => send({ action: 'delete', id: r.id }, 'Запись удалена.')}>Удалить</Button>
                  {' '}<Button size="s" mode="tertiary" onClick={() => setConfirmId(null)}>Нет</Button>
                </>
              ) : (
                <>{' '}<Button size="s" mode="tertiary" onClick={() => setConfirmId(r.id)}>✕</Button></>
              ))}
            </span>
          </div>
        ))}
      </Group>
    </>
  );
}

export default function AdminTab() {
  const [section, setSection] = useState('overview');
  const [requested, setRequested] = useState(null);
  // Новый объект на каждое нажатие - повторный клик по тому же имени тоже
  // откроет карточку.
  const openPlayer = (id) => { setRequested({ id }); setSection('player'); };

  return (
    <OpenPlayerContext.Provider value={openPlayer}>
      <Tabs>
        {SECTIONS.map((s) => (
          <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>
            {s.label}
          </TabsItem>
        ))}
      </Tabs>
      {section === 'overview' && <><OverviewSection /><MaintenanceSection /></>}
      {section === 'player' && <PlayerSection requestedId={requested} />}
      {section === 'journal' && <JournalSection />}
      {section === 'mining' && <MiningSection />}
      {section === 'promo' && <PromoSection />}
      {section === 'bugs' && <BugsSection />}
      {section === 'donations' && <DonationsSection />}
    </OpenPlayerContext.Provider>
  );
}
