import { useEffect, useState } from 'react';
import {
  Tabs, TabsItem, Group, Header, Div, Spinner, Placeholder, Button, Input, FormItem, Select, Textarea, Checkbox,
} from '@vkontakte/vkui';
import {
  getAdminOverview, searchAdminPlayers, getAdminPlayer, postAdminAction, getAdminJournal,
  getAdminPromoCodes, createAdminPromoCode, deleteAdminPromoCode, getAdminPromoCodeActivations,
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
  { id: 'promo', label: '🎟 Промокоды' },
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
      // Патч 34, ч.3: тестовые предметы — только себе (services/admin_service.py::NotSelfTarget).
      const message = e.message === 'self_only'
        ? 'Тестовые предметы можно выдать только себе.'
        : e.message || 'Ошибка';
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
      <Group header={<Header>{card.is_premium ? '💠 ' : ''}{card.name}{card.title ? ` «${card.title}»` : ''} (vk_id {card.vk_id})</Header>}>
        <StatRow label="Ник" value={card.name} />
        <StatRow label="vk_id" value={card.vk_id ?? '—'} />
        <StatRow label="Создан" value={card.created_at ? new Date(card.created_at).toLocaleString('ru') : '—'} />
        <StatRow label="Последняя активность" value={card.last_active_at ? new Date(card.last_active_at).toLocaleString('ru') : '—'} />
        <StatRow label="Титул" value={card.title || '—'} />
        <StatRow
          label="💠 Метка Хранителя"
          value={card.premium_until ? `до ${new Date(card.premium_until).toLocaleString('ru')}${card.is_premium ? '' : ' (истекла)'}` : 'нет'}
        />
      </Group>

      <Group header={<Header>Прогресс</Header>}>
        <StatRow label="Уровень" value={`${card.level} (опыт ${card.xp_to_next == null ? 'МАКС' : `${card.experience} / ${card.xp_to_next}`})`} />
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
              <StatRow
                label="Уклонение"
                value={`${Math.round(card.derived.dodge_chance * 100)}% (от способностей: ${Math.round(card.derived.ability_dodge_chance * 100)}%)`}
              />
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
  const [results, setResults] = useState(null); // null — поиска ещё не было
  const [card, setCard] = useState(null);
  const [status, setStatus] = useState('idle');
  const [errorMsg, setErrorMsg] = useState(null);

  const search = async () => {
    setStatus('loading');
    setErrorMsg(null);
    setCard(null);
    try {
      const res = await searchAdminPlayers(query);
      setResults(res.results);
      setStatus('ready');
    } catch (e) {
      // Патч 34, ч.2: ошибка запроса (403/сеть/что угодно) раньше молча
      // проглатывалась — экран выглядел так же, как "ничего не нашли".
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

  return (
    <>
      <Group header={<Header>Поиск (ник или vk_id)</Header>}>
        <FormItem>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') search(); }}
            placeholder="Валгар или 123456789"
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
        {status === 'ready' && results && results.length === 0 && (
          <Div style={{ opacity: 0.7 }}>Игрок не найден.</Div>
        )}
        {results && results.map((r) => (
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

// Патч 50: типы наград промокода — поля зависят от типа (см.
// services/promo_service.py::_apply_reward — те же ключи один в один).
const REWARD_TYPE_OPTIONS = [
  { value: 'gold', label: '💰 Золото' },
  { value: 'gems', label: '💎 Самоцветы' },
  { value: 'xp', label: '✨ Опыт' },
  { value: 'trophy', label: 'Трофей' },
  { value: 'elixir', label: 'Зелье/эликсир' },
  { value: 'raid_keys', label: '🗝 Ключи Монолита' },
  { value: 'premium', label: '💠 Метка Хранителя' },
  { value: 'mount', label: '🐎 Маунт' },
];

function emptyReward() {
  return { type: 'gold', amount: '', trophy_id: '', elixir_id: '', days: 30, mount_id: '' };
}

function rewardToPayload(r) {
  if (r.type === 'gold' || r.type === 'gems' || r.type === 'xp' || r.type === 'raid_keys') {
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
      {(reward.type === 'gold' || reward.type === 'gems' || reward.type === 'xp' || reward.type === 'raid_keys') && (
        <FormItem top="Количество">
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
      <FormItem top="Лимит активаций (пусто — без лимита)">
        <Input type="number" value={maxActivations} onChange={(e) => setMaxActivations(e.target.value)} />
      </FormItem>
      <FormItem>
        <Checkbox checked={onePerPlayer} onChange={(e) => setOnePerPlayer(e.target.checked)}>
          Одна активация на игрока
        </Checkbox>
      </FormItem>
      <FormItem top="Действует до (пусто — бессрочно)">
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
              {a.character_name} · {new Date(a.activated_at).toLocaleString('ru')}
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
      {section === 'promo' && <PromoSection />}
    </>
  );
}
