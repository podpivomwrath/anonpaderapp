import { useCallback, useEffect, useState } from 'react';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, Spinner, Tabs, TabsItem,
} from '@vkontakte/vkui';
import { getGuild, guildAction } from '../api.js';
import GuildTree from './GuildTree.jsx';

// Гильдии. Всё управление - здесь: состав, казна и склад, земли и стройка,
// древо, осады. В чате остаётся то, что происходит в поле.
//
// Каждое действие возвращает новое состояние целиком (сервер считает всё
// сам), поэтому вкладка не держит своих копий чисел и не пересчитывает их.

const SECTIONS = [
  { id: 'overview', label: 'Обзор' },
  { id: 'members', label: 'Состав' },
  { id: 'quests', label: 'Задания' },
  { id: 'treasury', label: 'Казна' },
  { id: 'lands', label: 'Земли' },
  { id: 'tree', label: 'Древо' },
  { id: 'war', label: 'Осады' },
];

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');

function timeLeft(iso) {
  if (!iso) return '';
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return 'сейчас';
  const min = Math.round(ms / 60000);
  if (min < 60) return `${min} мин`;
  const h = Math.floor(min / 60);
  if (h < 48) return `${h} ч ${min % 60} мин`;
  return `${Math.floor(h / 24)} д ${h % 24} ч`;
}

function when(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
}

function Bar({ value, max }) {
  const pct = max > 0 ? Math.min(100, Math.round((100 * value) / max)) : 0;
  return (
    <div className="guild-bar"><div className="guild-bar__fill" style={{ width: `${pct}%` }} /></div>
  );
}

/** Кнопка с подтверждением в два нажатия - без системных диалогов. */
function Confirm({ children, onConfirm, disabled, mode = 'secondary', size = 's' }) {
  const [armed, setArmed] = useState(false);
  if (!armed) {
    return <Button size={size} mode={mode} disabled={disabled} onClick={() => setArmed(true)}>{children}</Button>;
  }
  return (
    <span className="guild-confirm">
      <Button size={size} mode="primary" disabled={disabled} onClick={() => { setArmed(false); onConfirm(); }}>Да</Button>
      <Button size={size} mode="tertiary" onClick={() => setArmed(false)}>Нет</Button>
    </span>
  );
}

function NumberInput({ value, onChange, placeholder }) {
  return (
    <input
      className="guild-input" inputMode="numeric" placeholder={placeholder} value={value}
      onChange={(e) => onChange(e.target.value.replace(/[^0-9]/g, ''))}
    />
  );
}

// --- Без гильдии -----------------------------------------------------------------

// Топ гильдий: сортирует клиент - гильдий десятки, ответ один.
const DIRECTORY_SORTS = [
  { id: 'members', label: 'Участники', key: (g) => g.members },
  { id: 'pve', label: 'PvE', key: (g) => g.pve },
  { id: 'pvp', label: 'PvP', key: (g) => g.pvp },
  { id: 'level', label: 'Уровень', key: (g) => g.level },
];

function NoGuild({ state, run, busy }) {
  const [name, setName] = useState('');
  const [tag, setTag] = useState('');
  const [sort, setSort] = useState('members');
  const canFound = state.level >= state.found_min_level && state.gems >= state.found_cost;
  const key = DIRECTORY_SORTS.find((s) => s.id === sort).key;
  const sorted = [...state.directory].sort((a, b) => key(b) - key(a) || b.fame_total - a.fame_total);
  return (
    <>
      {state.rejoin_wait_hours > 0 && (
        <Div className="craft-hint">После ухода вступить в гильдию можно через {state.rejoin_wait_hours} ч.</Div>
      )}
      {state.invites.length > 0 && (
        <Group header={<Header>📨 Приглашения</Header>}>
          {state.invites.map((inv) => (
            <SimpleCell
              key={`${inv.guild_id}:${inv.kind}`}
              subtitle={inv.kind === 'invite' ? `${inv.level} ур. · зовут тебя` : 'Твоя заявка ждёт ответа'}
              after={inv.kind === 'invite' && (
                <span className="guild-confirm">
                  <Button size="s" disabled={busy} onClick={() => run('accept_invite', { guild_id: inv.guild_id }, 'Ты в гильдии!')}>Вступить</Button>
                  <Button size="s" mode="tertiary" disabled={busy} onClick={() => run('decline_invite', { guild_id: inv.guild_id })}>✕</Button>
                </span>
              )}
            >
              [{inv.tag}] {inv.name}
            </SimpleCell>
          ))}
        </Group>
      )}
      <Group header={<Header>🏆 Топ гильдий</Header>}>
        <Tabs className="guild-tabs">
          {DIRECTORY_SORTS.map((s) => (
            <TabsItem key={s.id} selected={sort === s.id} onClick={() => setSort(s.id)}>{s.label}</TabsItem>
          ))}
        </Tabs>
        {state.directory.length === 0 && <Div style={{ opacity: 0.8 }}>Гильдий пока нет - стань первым.</Div>}
        {sorted.map((g, i) => (
          <SimpleCell
            key={g.id}
            multiline
            subtitle={
              `${g.level} ур. · 👥 ${g.members}/${g.cap} · ⚔️ PvE ${money(g.pve)} · 🩸 PvP ${money(g.pvp)}`
            }
            after={(
              <Button size="s" mode="secondary" disabled={busy || g.members >= g.cap}
                onClick={() => run('apply', { guild_id: g.id }, 'Заявка отправлена.')}>
                Проситься
              </Button>
            )}
          >
            {i + 1}. {g.crown ? '👑 ' : ''}[{g.tag}] {g.name}
          </SimpleCell>
        ))}
        <Div className="craft-hint">
          PvE - сколько мобов убили все участники вместе, PvP - сколько побед у всех вместе.
        </Div>
      </Group>
      <Group header={<Header>Основать гильдию</Header>}>
        <Div className="guild-form">
          <p className="craft-hint">
            Стоит 💎 {state.found_cost} самоцветов, с {state.found_min_level} уровня. У тебя 💎 {money(state.gems)}.
          </p>
          <input className="guild-input" placeholder="Название" maxLength={24} value={name} onChange={(e) => setName(e.target.value)} />
          <input className="guild-input" placeholder="Тег (2-4 знака)" maxLength={4} value={tag} onChange={(e) => setTag(e.target.value.toUpperCase())} />
          <Button size="l" stretched disabled={busy || !canFound || !name || !tag}
            onClick={() => run('create', { name, tag }, 'Гильдия основана!')}>
            Основать за 💎 {state.found_cost}
          </Button>
        </Div>
      </Group>
    </>
  );
}

// --- Обзор -------------------------------------------------------------------------

function Overview({ state, run, busy }) {
  const { guild, me, boss } = state;
  const [stat, setStat] = useState('str');
  const perms = me.perms;
  return (
    <>
      <Group>
        <Div>
          <p className="guild-title">{guild.crown ? '👑 ' : ''}[{guild.tag}] {guild.name}</p>
          <p className="craft-hint">
            {guild.level} уровень · участников {guild.members}/{guild.cap}
            {guild.season_wins ? ` · побед в сезонах: ${guild.season_wins}` : ''}
          </p>
          <p className="guild-line">Слава: {money(guild.fame)} / {money(guild.fame_next)}</p>
          <Bar value={guild.fame} max={guild.fame_next} />
          <p className="guild-line">Ты - {me.rank_title.toLowerCase()} · вклад за неделю {money(me.contribution_week)}, всего {money(me.contribution_total)}</p>
          <p className="guild-line">Казна: 💰 {money(guild.treasury_gold)} · 💎 {money(guild.treasury_gems)}</p>
          {state.season.place && (
            <p className="guild-line">Сезон {state.season.season}: {state.season.place} место</p>
          )}
        </Div>
      </Group>

      <Group header={<Header>Бонусы гильдии</Header>}>
        {guild.effects.length === 0
          ? <Div style={{ opacity: 0.8 }}>Пока нет: их дают узлы древа.</Div>
          : <Div>{guild.effects.map((e) => <p key={e} className="guild-line">• {e}</p>)}</Div>}
      </Group>

      <Group header={<Header>⛪ Часовня</Header>}>
        {!me.prayer.available ? (
          <Div style={{ opacity: 0.8 }}>У гильдии нет часовни - её строят на базе.</Div>
        ) : (
          <Div className="guild-form">
            {me.prayer.active && (
              <p className="guild-line">
                🙏 Молитва: {me.prayer.stats[me.prayer.stat]} +10% ещё {timeLeft(me.prayer.until)}
              </p>
            )}
            <select className="guild-input" value={stat} onChange={(e) => setStat(e.target.value)}>
              {Object.entries(me.prayer.stats).map(([id, title]) => <option key={id} value={id}>{title}</option>)}
            </select>
            <Button size="m" disabled={busy} onClick={() => run('pray', { stat }, 'Молитва услышана: +10% на час.')}>
              Вознести молитву ({money(me.prayer.cost)} золота)
            </Button>
            <label className="guild-check">
              <input type="checkbox" checked={me.respawn_at_chapel} disabled={busy}
                onChange={(e) => run('respawn_pref', { on: e.target.checked })} />
              Возрождаться у часовни, а не в городе
            </label>
          </Div>
        )}
      </Group>

      <Group header={<Header>🗿 Страж цитадели</Header>}>
        <Div>
          {boss.active ? (
            <>
              <p className="guild-line">Призван на ({boss.x}; {boss.y}): {money(boss.hp)} / {money(boss.max_hp)}, уйдёт через {timeLeft(boss.expires_at)}.</p>
              <Bar value={boss.hp} max={boss.max_hp} />
              <p className="craft-hint">Бить - в чате: встань на клетку и напиши «Страж».</p>
            </>
          ) : !boss.has_citadel ? (
            <p style={{ opacity: 0.8 }}>Стража призывают в цитадели.</p>
          ) : (
            <>
              <p className="craft-hint">
                Призыв: {money(boss.summon_gold)} золота и {boss.summon_ore} ×{boss.summon_ore_count} со склада. Раз в неделю.
              </p>
              {boss.cooldown_hours > 0 && <p className="guild-line">Наберётся сил через {boss.cooldown_hours} ч.</p>}
              {perms.treasury && (
                <Button size="m" disabled={busy || boss.cooldown_hours > 0} onClick={() => run('summon_boss', {}, 'Страж призван!')}>
                  Призвать
                </Button>
              )}
            </>
          )}
        </Div>
      </Group>

      <Group header={<Header>Журнал</Header>}>
        <Div className="guild-log">
          {state.log.map((row, i) => (
            <p key={i} className="guild-log__row"><span className="guild-log__at">{when(row.at)}</span> {row.text}</p>
          ))}
        </Div>
      </Group>

      <Div className="guild-danger">
        {perms.leader
          ? <Confirm onConfirm={() => run('disband', {}, 'Гильдия распущена.')} disabled={busy}>Распустить гильдию</Confirm>
          : <Confirm onConfirm={() => run('leave', {}, 'Ты покинул гильдию.')} disabled={busy}>Покинуть гильдию</Confirm>}
      </Div>
    </>
  );
}

// --- Состав ------------------------------------------------------------------------

function Members({ state, run, busy }) {
  const { me, members, applications, tops } = state;
  const [invite, setInvite] = useState('');
  const [open, setOpen] = useState(null);
  const [topMode, setTopMode] = useState('week');
  return (
    <>
      {me.perms.invite && (
        <Group header={<Header>Позвать в гильдию</Header>}>
          <Div className="guild-row">
            <input className="guild-input" placeholder="Ник персонажа" value={invite} onChange={(e) => setInvite(e.target.value)} />
            <Button size="m" disabled={busy || !invite.trim()} onClick={() => { run('invite', { name: invite }, 'Приглашение отправлено.'); setInvite(''); }}>
              Позвать
            </Button>
          </Div>
        </Group>
      )}
      {applications.length > 0 && (
        <Group header={<Header>📨 Заявки</Header>}>
          {applications.map((a) => (
            <SimpleCell key={a.id} subtitle={`${a.level} ур.`} after={(
              <span className="guild-confirm">
                <Button size="s" disabled={busy} onClick={() => run('accept_application', { character_id: a.id }, 'Принят.')}>Принять</Button>
                <Button size="s" mode="tertiary" disabled={busy} onClick={() => run('decline_application', { character_id: a.id })}>✕</Button>
              </span>
            )}>{a.name}</SimpleCell>
          ))}
        </Group>
      )}
      <Group header={<Header>Участники ({members.length})</Header>}>
        {members.map((m) => (
          <div key={m.id}>
            <SimpleCell
              onClick={() => setOpen(open === m.id ? null : m.id)}
              subtitle={`${m.rank_title} · ${m.level} ур. ${m.class || ''} · неделя ${money(m.week)}`}
              after={m.id === me.id ? 'ты' : (open === m.id ? '▴' : '▾')}
            >
              {m.name}
            </SimpleCell>
            {open === m.id && m.id !== me.id && (
              <Div className="guild-member-actions">
                <select className="guild-input" value={m.rank} disabled={busy}
                  onChange={(e) => run('rank', { character_id: m.id, rank: e.target.value }, 'Звание изменено.')}>
                  {Object.entries(state.config.ranks).filter(([id]) => id !== 'leader').map(([id, title]) => (
                    <option key={id} value={id}>{title}</option>
                  ))}
                  {m.rank === 'leader' && <option value="leader">Глава</option>}
                </select>
                <Confirm disabled={busy} onConfirm={() => run('kick', { character_id: m.id }, 'Исключён.')}>Исключить</Confirm>
                {me.perms.leader && (
                  <Confirm disabled={busy} onConfirm={() => run('transfer', { character_id: m.id }, 'Главенство передано.')}>Сделать главой</Confirm>
                )}
              </Div>
            )}
          </div>
        ))}
      </Group>
      <Group header={<Header>Топ вклада</Header>}>
        <Tabs>
          <TabsItem selected={topMode === 'week'} onClick={() => setTopMode('week')}>Неделя</TabsItem>
          <TabsItem selected={topMode === 'total'} onClick={() => setTopMode('total')}>Всё время</TabsItem>
        </Tabs>
        {(tops[topMode] || []).length === 0 && <Div style={{ opacity: 0.8 }}>Вклада пока нет.</Div>}
        {(tops[topMode] || []).map((row, i) => (
          <div className="stat-row" key={row.id}>
            <span className="stat-row__label">{i + 1}. {row.name}</span>
            <span className="stat-row__value">{money(row.value)}</span>
          </div>
        ))}
      </Group>
    </>
  );
}

// --- Задания -----------------------------------------------------------------------

function QuestRow({ q, extra }) {
  return (
    <Div className="guild-quest">
      <p className="guild-line"><b>{q.completed ? '✅ ' : ''}{q.title}</b> - {q.label}</p>
      <Bar value={q.progress} max={q.target} />
      <p className="craft-hint">{money(q.progress)} / {money(q.target)} · {q.reward}{extra ? ` · ${extra}` : ''}</p>
    </Div>
  );
}

function Quests({ state }) {
  const { quests } = state;
  return (
    <>
      <Group header={<Header>Личные - на сегодня</Header>}>
        {quests.dailies.map((q) => <QuestRow key={q.metric} q={q} />)}
      </Group>
      <Group header={<Header>Общие - на неделю</Header>}>
        {quests.weekly.map((q) => <QuestRow key={q.metric} q={q} extra={`твой вклад ${money(q.mine)}`} />)}
      </Group>
    </>
  );
}

// --- Казна и склад -----------------------------------------------------------------

/** Подсписок: заголовок со счётчиком, раскрывается нажатием. */
function Folder({ title, count, children }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <SimpleCell onClick={() => setOpen(!open)} after={`${count} ${open ? '▴' : '▾'}`}>{title}</SimpleCell>
      {open && <div className="craft-expand">{children}</div>}
    </>
  );
}

/** Руда - по видам, внутри вида - градации. */
function groupOre(rows) {
  const groups = new Map();
  rows.forEach((o) => {
    const g = groups.get(o.ore_id) || { id: o.ore_id, title: `${o.emoji} ${o.name}`, tier: o.tier, rows: [], total: 0 };
    g.rows.push(o);
    g.total += o.count;
    groups.set(o.ore_id, g);
  });
  return [...groups.values()].sort((a, b) => a.tier - b.tier);
}

/** Снаряжение - по слотам. */
function groupItems(items) {
  const groups = new Map();
  items.forEach((i) => {
    const g = groups.get(i.slot) || { id: i.slot, title: i.slot, rows: [] };
    g.rows.push(i);
    groups.set(i.slot, g);
  });
  return [...groups.values()];
}

const TREASURY_MODES = [
  { id: 'stock', label: 'Склад и выдача' },
  { id: 'give', label: 'Сдать' },
];

function Treasury({ state, run, busy }) {
  const { guild, me, warehouse, members } = state;
  const [mode, setMode] = useState('stock');
  const [gold, setGold] = useState('');
  const [gems, setGems] = useState('');
  const [wGold, setWGold] = useState('');
  const [wGems, setWGems] = useState('');
  const [to, setTo] = useState('');
  const [counts, setCounts] = useState({});
  const target = to ? Number(to) : undefined;
  const amount = (key, fallback) => counts[key] ?? String(fallback);
  const setAmount = (key, v) => setCounts({ ...counts, [key]: v });

  const header = (
    <Group>
      <Div>
        <p className="guild-line">💰 Казна: {money(guild.treasury_gold)} · 💎 {money(guild.treasury_gems)}</p>
        <p className="craft-hint">
          📦 Склад: руда {warehouse.ore_total}/{warehouse.capacity.ore}, вещи {warehouse.items.length}/{warehouse.capacity.items}
        </p>
      </Div>
      <Tabs>
        {TREASURY_MODES.map((m) => (
          <TabsItem key={m.id} selected={mode === m.id} onClick={() => setMode(m.id)}>{m.label}</TabsItem>
        ))}
      </Tabs>
    </Group>
  );

  if (mode === 'give') {
    return (
      <>
        {header}
        <Group header={<Header>Внести в казну</Header>}>
          <Div>
            <p className="craft-hint">У тебя: 💰 {money(me.gold)} · 💎 {money(me.gems)}. Взнос виден в журнале.</p>
            <div className="guild-row">
              <NumberInput value={gold} onChange={setGold} placeholder="Золото" />
              <Button size="m" disabled={busy || !gold} onClick={() => { run('deposit', { currency: 'gold', amount: Number(gold) }, 'Внесено.'); setGold(''); }}>Внести</Button>
            </div>
            <div className="guild-row">
              <NumberInput value={gems} onChange={setGems} placeholder="Самоцветы" />
              <Button size="m" disabled={busy || !gems} onClick={() => { run('deposit', { currency: 'gems', amount: Number(gems) }, 'Внесено.'); setGems(''); }}>Внести 💎</Button>
            </div>
          </Div>
        </Group>
        <Group header={<Header>Сдать руду</Header>}>
          {warehouse.my_ore.length === 0 && <Div style={{ opacity: 0.8 }}>У тебя нет руды.</Div>}
          {groupOre(warehouse.my_ore).map((g) => (
            <Folder key={g.id} title={g.title} count={g.total}>
              {g.rows.map((o) => {
                const key = `my:${o.ore_id}:${o.grade}`;
                const count = amount(key, o.count);
                return (
                  <SimpleCell key={key} subtitle={`у тебя ${o.count}`} after={(
                    <span className="guild-row guild-row--tight">
                      <NumberInput value={count} onChange={(v) => setAmount(key, v)} placeholder="шт" />
                      <Button size="s" disabled={busy || !Number(count)}
                        onClick={() => run('deposit_ore', { ore_id: o.ore_id, grade: o.grade, count: Number(count) }, 'Сдано на склад.')}>
                        Сдать
                      </Button>
                    </span>
                  )}>
                    {o.grade_name}
                  </SimpleCell>
                );
              })}
            </Folder>
          ))}
        </Group>
        <Group header={<Header>Сдать снаряжение</Header>}>
          {warehouse.my_items.length === 0 && <Div style={{ opacity: 0.8 }}>В сумке нечего сдать.</Div>}
          {groupItems(warehouse.my_items).map((g) => (
            <Folder key={g.id} title={g.title} count={g.rows.length}>
              {g.rows.map((i) => (
                <SimpleCell key={i.id} after={(
                  <Button size="s" disabled={busy} onClick={() => run('deposit_item', { item_id: i.id }, 'Сдано на склад.')}>Сдать</Button>
                )}>{i.name}</SimpleCell>
              ))}
            </Folder>
          ))}
          <Div className="craft-hint">Надетые и привязанные вещи и реликвии на склад не кладут.</Div>
        </Group>
      </>
    );
  }

  const canGive = me.perms.treasury;
  return (
    <>
      {header}
      {canGive && (
        <Group header={<Header>Кому выдавать</Header>}>
          <Div className="guild-form">
            <select className="guild-input" value={to} onChange={(e) => setTo(e.target.value)}>
              <option value="">Себе</option>
              {members.filter((m) => m.id !== me.id).map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <div className="guild-row">
              <NumberInput value={wGold} onChange={setWGold} placeholder="Золото" />
              <Button size="m" disabled={busy || !wGold} onClick={() => { run('withdraw', { currency: 'gold', amount: Number(wGold), to: target }, 'Выдано.'); setWGold(''); }}>Выдать</Button>
            </div>
            <div className="guild-row">
              <NumberInput value={wGems} onChange={setWGems} placeholder="Самоцветы" />
              <Button size="m" disabled={busy || !wGems} onClick={() => { run('withdraw', { currency: 'gems', amount: Number(wGems), to: target }, 'Выдано.'); setWGems(''); }}>Выдать 💎</Button>
            </div>
          </Div>
        </Group>
      )}
      <Group header={<Header>Руда на складе</Header>}>
        {warehouse.ore.length === 0 && <Div style={{ opacity: 0.8 }}>Руды нет.</Div>}
        {groupOre(warehouse.ore).map((g) => (
          <Folder key={g.id} title={g.title} count={g.total}>
            {g.rows.map((o) => {
              const key = `wh:${o.ore_id}:${o.grade}`;
              const count = amount(key, o.count);
              return (
                <SimpleCell key={key} subtitle={`на складе ${o.count}`} after={canGive && (
                  <span className="guild-row guild-row--tight">
                    <NumberInput value={count} onChange={(v) => setAmount(key, v)} placeholder="шт" />
                    <Button size="s" mode="secondary" disabled={busy || !Number(count)}
                      onClick={() => run('withdraw_ore', { ore_id: o.ore_id, grade: o.grade, count: Number(count), to: target }, 'Выдано.')}>
                      Выдать
                    </Button>
                  </span>
                )}>
                  {o.grade_name}
                </SimpleCell>
              );
            })}
          </Folder>
        ))}
      </Group>
      <Group header={<Header>Снаряжение на складе</Header>}>
        {warehouse.items.length === 0 && <Div style={{ opacity: 0.8 }}>Пусто.</Div>}
        {groupItems(warehouse.items).map((g) => (
          <Folder key={g.id} title={g.title} count={g.rows.length}>
            {g.rows.map((i) => (
              <SimpleCell key={i.id} after={canGive && (
                <Button size="s" mode="secondary" disabled={busy} onClick={() => run('withdraw_item', { item_id: i.id, to: target }, 'Выдано.')}>Выдать</Button>
              )}>{i.name}</SimpleCell>
            ))}
          </Folder>
        ))}
        {!canGive && <Div className="craft-hint">Выдают со склада глава и казначеи.</Div>}
      </Group>
    </>
  );
}

// --- Земли -------------------------------------------------------------------------

function Here({ state, run, busy }) {
  const { here, me } = state;
  if (!here || here.x == null) return null;
  return (
    <Group header={<Header>📍 Ты на ({here.x}; {here.y})</Header>}>
      <Div className="guild-form">
        {here.banner && (here.banner.reason ? (
          <p className="craft-hint">{here.banner.reason}</p>
        ) : (
          <>
            <p className="guild-line">
              {here.banner.mine ? `⛏ Рудник «${here.banner.mine}» - свободен.` : 'Клетка свободна.'}
            </p>
            <p className="craft-hint">
              Знамя: {money(here.banner.cost)} золота из казны и {here.banner.ore} ×{here.banner.ore_count} со склада.
              Потом участники гильдии исследуют клетку {here.banner.explorations} раз за {here.banner.hours} ч.
            </p>
            {me.perms.treasury && (
              <Button size="m" disabled={busy} onClick={() => run('banner', {}, 'Знамя заложено!')}>🚩 Заложить знамя</Button>
            )}
          </>
        ))}
        {here.owner && (
          <p className="guild-line">🏰 Земля [{here.owner.tag}] {here.owner.name}{here.owner.own ? ' - твоя гильдия' : ''}</p>
        )}
        {here.siege && (
          <>
            <p className="craft-hint">
              {here.siege.base_title}. Осада: {money(here.siege.cost)} золота из казны, начало - в окно защитников,
              ближайшее {when(here.siege.starts_at)}. За {state.config.gather_minutes} мин до начала драки на клетке запрещены.
            </p>
            {here.siege.shield_until && new Date(here.siege.shield_until) > new Date() && (
              <p className="guild-line">🛡 Под щитом ещё {timeLeft(here.siege.shield_until)}.</p>
            )}
            {me.perms.treasury && (
              <Confirm mode="primary" size="m" disabled={busy}
                onConfirm={() => run('declare_siege', { cell_id: here.siege.cell_id }, 'Осада объявлена!')}>
                ⚔️ Объявить осаду
              </Confirm>
            )}
          </>
        )}
      </Div>
      {state.gates.length > 0 && (
        <Div className="guild-form">
          <p className="guild-line">🌀 Врата ведут:</p>
          {state.gates.map((g) => (
            <Button key={g.cell_id} size="s" mode="secondary" disabled={busy}
              onClick={() => run('gates', { cell_id: g.cell_id }, 'Ты прошёл через врата.')}>
              ({g.x}; {g.y})
            </Button>
          ))}
        </Div>
      )}
    </Group>
  );
}

function Cell({ cell, state, run, busy }) {
  const [open, setOpen] = useState(false);
  const perms = state.me.perms;
  const building = cell.buildings.some((b) => b.upgrading_to);
  if (cell.status === 'claiming') {
    return (
      <Div className="guild-cell">
        <p className="guild-line"><b>🚩 Закладка ({cell.x}; {cell.y}){cell.mine ? ` · ⛏ ${cell.mine}` : ''}</b></p>
        <Bar value={cell.claim_progress} max={cell.claim_needed} />
        <p className="craft-hint">
          Исследований {cell.claim_progress}/{cell.claim_needed}, осталось {timeLeft(cell.claim_expires_at)}.
        </p>
      </Div>
    );
  }
  return (
    <div className="guild-cell">
      <SimpleCell onClick={() => setOpen(!open)} after={open ? '▴' : '▾'}
        subtitle={[
          `${cell.base_title} · кольцо ${cell.ring}`,
          `построек ${cell.used_slots}/${cell.slots}`,
          cell.shield_until && new Date(cell.shield_until) > new Date() ? `🛡 ${timeLeft(cell.shield_until)}` : null,
          cell.here ? 'ты здесь' : null,
        ].filter(Boolean).join(' · ')}>
        {cell.base_tier === 'citadel' ? '🏯' : '🏰'} ({cell.x}; {cell.y}){cell.mine ? ` · ⛏ ${cell.mine}` : ''}
      </SimpleCell>
      {open && (
        <Div className="guild-form">
          {cell.upgrade_to && <p className="guild-line">🏗 Перестройка: ещё {timeLeft(cell.upgrade_done_at)}</p>}
          {cell.buildings.map((b) => (
            <div key={b.building} className="guild-building">
              <p className="guild-line">
                {b.emoji} <b>{b.title}</b> {b.built ? `${b.level}/${b.max}` : '- не построена'}
                {b.upgrading_to ? ` · строится ${b.upgrading_to} ур., ещё ${timeLeft(b.done_at)}` : ''}
              </p>
              {b.next && perms.treasury && !b.upgrading_to && (
                <div className="guild-row">
                  <span className="craft-hint">
                    {money(b.next.gold)} 💰 · {b.next.ore} ×{b.next.ore_count} · {b.next.hours} ч
                  </span>
                  <Button size="s" disabled={busy || building || (!b.built && cell.used_slots >= cell.slots)}
                    onClick={() => run('build', { cell_id: cell.id, building: b.building }, 'Стройка началась.')}>
                    {b.built ? 'Улучшить' : 'Построить'}
                  </Button>
                </div>
              )}
            </div>
          ))}
          {cell.upgrade && perms.treasury && !cell.upgrade_to && (
            <div className="guild-row">
              <span className="craft-hint">
                → {cell.upgrade.title}: {money(cell.upgrade.gold)} 💰 · {cell.upgrade.ore} ×{cell.upgrade.ore_count} · {cell.upgrade.hours} ч
                (с {cell.upgrade.level_needed} ур. гильдии)
              </span>
              <Button size="s" disabled={busy || state.guild.level < cell.upgrade.level_needed}
                onClick={() => run('upgrade_base', { cell_id: cell.id }, 'Перестройка началась.')}>
                Поднять
              </Button>
            </div>
          )}
          {perms.treasury && (
            <Confirm disabled={busy} onConfirm={() => run('abandon', { cell_id: cell.id }, 'Клетка оставлена.')}>Оставить клетку</Confirm>
          )}
        </Div>
      )}
    </div>
  );
}

function Lands({ state, run, busy }) {
  const { slots, cells } = state;
  return (
    <>
      <Here state={state} run={run} busy={busy} />
      <Group header={<Header>Владения</Header>}>
        <Div>
          <p className="guild-line">
            Клетки: {slots.cells}/{slots.cells_max}{slots.next_cell_level ? ` (следующий слот - ${slots.next_cell_level} ур.)` : ''}
            {' · '}Рудник: {slots.mines}/{slots.mines_max}{slots.mines_max === 0 ? ` (с ${slots.mine_level} ур.)` : ''}
          </p>
          <p className="craft-hint">
            Знамя ставят на свободной клетке второго-четвёртого колец: внешнее кольцо - земля новичков,
            у Монолита и на озёрах - ничьё. Каждое исследование на своей клетке приносит казне десятину.
          </p>
        </Div>
        {cells.length === 0 && <Div style={{ opacity: 0.8 }}>Земли пока нет.</Div>}
        {cells.map((c) => <Cell key={c.id} cell={c} state={state} run={run} busy={busy} />)}
      </Group>
    </>
  );
}

// --- Осады и сезон -----------------------------------------------------------------

const SIEGE_STATUS = {
  scheduled: 'назначена', running: 'идёт', captured: 'клетка взята', repelled: 'отбита',
  failed: 'не состоялась', cancelled: 'сорвалась',
};

function War({ state, run, busy }) {
  const { guild, me, sieges, season } = state;
  return (
    <>
      <Group header={<Header>⚔️ Осады</Header>}>
        {sieges.length === 0 && <Div style={{ opacity: 0.8 }}>Осад не было.</Div>}
        {sieges.map((s) => (
          <SimpleCell key={s.id} multiline
            subtitle={s.result || `${SIEGE_STATUS[s.status]} · ${when(s.starts_at)} МСК`}>
            {s.role === 'attack' ? '⚔️ Штурм' : '🛡 Оборона'} ({s.x}; {s.y}) · {s.enemy}
          </SimpleCell>
        ))}
        <Div className="craft-hint">
          Осаду объявляют, стоя на чужой базе (раздел «Земли»). Начало - в окно защитников, не раньше чем через 12 ч.
          В назначенный час в бой встают все свободные участники обеих гильдий на клетке; опоздавшие вступают через «Осмотреться».
        </Div>
      </Group>
      <Group header={<Header>Окно наших осад</Header>}>
        <Div className="guild-row">
          <span className="guild-line">Осады на наши земли начинаются в {guild.siege_hour}:00 МСК.</span>
          {me.perms.treasury && (
            <select className="guild-input guild-input--short" value={guild.siege_hour} disabled={busy}
              onChange={(e) => run('siege_hour', { hour: Number(e.target.value) }, 'Окно изменено.')}>
              {state.config.siege_hours.map((h) => <option key={h} value={h}>{h}:00</option>)}
            </select>
          )}
        </Div>
      </Group>
      <Group header={<Header>👑 Сезон {season.season}</Header>}>
        {season.top.length === 0 && <Div style={{ opacity: 0.8 }}>Очков пока ни у кого.</Div>}
        {season.top.map((row, i) => (
          <div className="stat-row" key={row.tag}>
            <span className="stat-row__label">{i + 1}. [{row.tag}] {row.name}</span>
            <span className="stat-row__value">{money(row.points)}</span>
          </div>
        ))}
        <Div className="craft-hint">
          Очки - за каждые сутки владения (клетка 1, рудник 2, цитадель ещё 3) и за славу месяца.
          Лучшая гильдия получает венец сезона, титул и самоцветы в казну.
        </Div>
      </Group>
    </>
  );
}

// --- Вкладка -----------------------------------------------------------------------

export default function GuildTab() {
  const [state, setState] = useState(null);
  const [status, setStatus] = useState('loading');
  const [section, setSection] = useState('overview');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    setStatus('loading');
    getGuild().then((data) => { setState(data); setStatus('ready'); }).catch(() => setStatus('error'));
  }, []);

  useEffect(() => { load(); }, [load]);

  const run = useCallback(async (action, params = {}, okText = null) => {
    setBusy(true);
    try {
      const data = await guildAction(action, params);
      setState(data);
      setNotice(okText ? { ok: true, text: okText } : null);
    } catch (err) {
      setNotice({ ok: false, text: err.message === 'bad_response' ? 'Сервер не ответил.' : err.message });
    } finally {
      setBusy(false);
    }
  }, []);

  if (status === 'loading') {
    return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}><Spinner size="l" /></Div>;
  }
  if (status === 'error' || !state) {
    return (
      <Placeholder action={<Button onClick={load}>Попробовать снова</Button>}>
        Не удалось открыть гильдию.
      </Placeholder>
    );
  }

  const noticeBox = notice && (
    <Div className={`craft-notice ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`} onClick={() => setNotice(null)}>
      {notice.text}
    </Div>
  );

  if (!state.in_guild) {
    return <>{noticeBox}<NoGuild state={state} run={run} busy={busy} /></>;
  }

  return (
    <>
      <Group>
        <Tabs className="guild-tabs">
          {SECTIONS.map((s) => (
            <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>{s.label}</TabsItem>
          ))}
        </Tabs>
      </Group>
      {noticeBox}
      {section === 'overview' && <Overview state={state} run={run} busy={busy} />}
      {section === 'members' && <Members state={state} run={run} busy={busy} />}
      {section === 'quests' && <Quests state={state} />}
      {section === 'treasury' && <Treasury state={state} run={run} busy={busy} />}
      {section === 'lands' && <Lands state={state} run={run} busy={busy} />}
      {section === 'tree' && <GuildTree onChanged={setState} />}
      {section === 'war' && <War state={state} run={run} busy={busy} />}
    </>
  );
}
