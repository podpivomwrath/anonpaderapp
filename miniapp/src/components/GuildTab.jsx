import { useCallback, useEffect, useState } from 'react';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, TabsItem,
} from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { getGuild, guildAction } from '../api.js';
import GuildTree from './GuildTree.jsx';
import ItemIcon from './ItemIcon.jsx';
import { itemSubtitle } from './InventoryTab.jsx';
import Skeleton from './Skeleton.jsx';
import ClassIcon from './ClassIcon.jsx';
import { Bar as UiBar, Empty } from './ui.jsx';

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
  { id: 'directory', label: 'Гильдии' },
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

// Ник согильдейца ведёт на его страницу VK; клик не раскрывает строку.
function PlayerLink({ id, name }) {
  if (!id) return name;
  return (
    <a href={`https://vk.com/id${id}`} target="_blank" rel="noopener noreferrer"
      onClick={(e) => e.stopPropagation()}>{name}</a>
  );
}

function Bar({ value, max, tone = 'gold' }) {
  return <UiBar value={value} max={max} tone={tone} />;
}

// Герб гильдии (2026-10-22): щит с тегом, цвет - от тега, у гильдии с
// венцом сезона - корона над щитом. Картинок нет: щит рисует CSS.
function crestHue(tag) {
  let h = 0;
  for (const ch of tag || '') h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

export function GuildCrest({ tag, crown = false, size = 44 }) {
  return (
    <span className={`guild-crest${crown ? ' guild-crest--crown' : ''}`}
      style={{ '--crest-h': crestHue(tag), '--crest-size': `${size}px` }} aria-hidden="true">
      <span className="guild-crest__tag">{tag}</span>
    </span>
  );
}

const MEDALS = ['🥇', '🥈', '🥉'];

// Был в сети: «в сети» - последние 15 минут.
function seenText(iso) {
  if (!iso) return null;
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 15) return { online: true, text: 'в сети' };
  if (min < 60) return { online: false, text: `был ${min} мин назад` };
  const h = Math.floor(min / 60);
  if (h < 24) return { online: false, text: `был ${h} ч назад` };
  return { online: false, text: `был ${Math.floor(h / 24)} д назад` };
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
  { id: 'new', label: 'Новые', key: (g) => (g.created ? new Date(g.created).getTime() : 0) },
];

// Список гильдий: без гильдии - с кнопкой «Проситься», в гильдии - только
// посмотреть топы и новые (2026-10-18), своя отмечена.
function Directory({ directory, ownId, run, busy }) {
  const [sort, setSort] = useState('members');
  const key = DIRECTORY_SORTS.find((s) => s.id === sort).key;
  const sorted = [...directory].sort((a, b) => key(b) - key(a) || b.fame_total - a.fame_total);
  return (
    <Group header={<Header>🏆 Топ гильдий</Header>}>
      <Tabs className="guild-tabs">
        {DIRECTORY_SORTS.map((s) => (
          <TabsItem key={s.id} selected={sort === s.id} onClick={() => setSort(s.id)}>{s.label}</TabsItem>
        ))}
      </Tabs>
      {directory.length === 0 && <Empty icon="🏰">Гильдий пока нет - стань первым.</Empty>}
      {sorted.map((g, i) => (
        <SimpleCell
          key={g.id}
          multiline
          before={<GuildCrest tag={g.tag} crown={g.crown} size={40} />}
          subtitle={
            `${g.level} ур. · 👥 ${g.members}/${g.cap} · ⚔️ PvE ${money(g.pve)} · 🩸 PvP ${money(g.pvp)}`
            + (sort === 'new' && g.created ? ` · основана ${new Date(g.created).toLocaleDateString('ru-RU')}` : '')
          }
          after={ownId == null ? (
            <Button size="s" mode="secondary" disabled={busy || g.members >= g.cap}
              onClick={() => run('apply', { guild_id: g.id }, 'Заявка отправлена.')}>
              Проситься
            </Button>
          ) : (g.id === ownId ? 'ваша' : null)}
        >
          {MEDALS[i] || `${i + 1}.`} {g.name}
        </SimpleCell>
      ))}
      <Div className="craft-hint">
        PvE - сколько мобов убили все участники вместе, PvP - сколько побед у всех вместе.
      </Div>
    </Group>
  );
}

function NoGuild({ state, run, busy }) {
  const [name, setName] = useState('');
  const [tag, setTag] = useState('');
  const canFound = state.level >= state.found_min_level && state.gems >= state.found_cost;
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
      <Directory directory={state.directory} run={run} busy={busy} />
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
  const [bossLevel, setBossLevel] = useState(1);
  const perms = me.perms;
  const bossPick = (boss.difficulties || []).find((d) => d.level === bossLevel);
  return (
    <>
      <Group>
        <div className="guild-hero" style={{ '--crest-h': crestHue(guild.tag) }}>
          <GuildCrest tag={guild.tag} crown={guild.crown} size={72} />
          <div className="guild-hero__text">
            <b className="guild-hero__name">{guild.name}</b>
            <small className="guild-hero__sub">
              {guild.level} уровень · ты - {me.rank_title.toLowerCase()}
              {guild.season_wins ? ` · побед в сезонах: ${guild.season_wins}` : ''}
            </small>
            <span className="guild-hero__fame">
              <Bar value={guild.fame} max={guild.fame_next} />
              <small>слава {money(guild.fame)} / {money(guild.fame_next)}</small>
            </span>
          </div>
        </div>
        <div className="tile-grid guild-tiles">
          <div className="tile"><span className="tile__icon">👥</span><b className="tile__value">{guild.members}/{guild.cap}</b><small className="tile__label">участников</small></div>
          <div className="tile"><span className="tile__icon">💰</span><b className="tile__value">{money(guild.treasury_gold)}</b><small className="tile__label">казна · 💎 {money(guild.treasury_gems)}</small></div>
          <div className="tile"><span className="tile__icon">⭐</span><b className="tile__value">{money(me.contribution_week)}</b><small className="tile__label">твой вклад</small></div>
          {state.season.place && (
            <div className="tile"><span className="tile__icon">👑</span><b className="tile__value">{state.season.place}</b><small className="tile__label">место в сезоне</small></div>
          )}
        </div>
      </Group>

      <Group header={<Header>Бонусы гильдии</Header>}>
        {guild.effects.length === 0
          ? <Empty icon="🌳">Пока нет: их дают узлы древа.</Empty>
          : <div className="effect-chips">{guild.effects.map((e) => <span key={e} className="effect-chip">{e}</span>)}</div>}
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
            {me.chapel_on_map && (
              <label className="guild-check">
                <input type="checkbox" checked={me.respawn_at_chapel} disabled={busy}
                  onChange={(e) => run('respawn_pref', { on: e.target.checked })} />
                Возрождаться у часовни, а не в городе
              </label>
            )}
          </Div>
        )}
      </Group>

      <Group header={<Header>🗿 Страж</Header>}>
        <Div>
          {boss.active ? (
            <>
              <p className="guild-line">
                {boss.difficulty ? `${boss.difficulty}. ` : ''}
                {boss.court ? 'Призван во Дворе' : `Призван на (${boss.x}; ${boss.y})`}: {money(boss.hp)} / {money(boss.max_hp)}, уйдёт через {timeLeft(boss.expires_at)}.
              </p>
              <Bar value={boss.hp} max={boss.max_hp} tone="red" />
              <p className="craft-hint">
                {boss.court ? 'Бить - в чате, из любого города: напиши «/страж».' : 'Бить - в чате, на клетке цитадели или из любого города: напиши «/страж».'}
              </p>
            </>
          ) : (
            <>
              <p className="craft-hint">
                Призыв раз в неделю, цена и награда - по сложности. Бойцам - золото и опыт по урону.
                {boss.has_citadel
                  ? ' Встанет в цитадели - бить там или из любого города, награда полная.'
                  : ` Без цитадели - из Двора: бить из любого города, награда ${boss.court_reward_pct}%.`}
              </p>
              {boss.cooldown_hours > 0 && <p className="guild-line">Наберётся сил через {boss.cooldown_hours} ч.</p>}
              {perms.treasury && (boss.difficulties || []).length > 0 && (
                <>
                  <p className="craft-hint">Сложность: чем сильнее страж, тем больше здоровья и награды. Недобитый платит по доле снятого здоровья.</p>
                  <div className="guild-boss-levels">
                    {boss.difficulties.map((d) => (
                      <button type="button" key={d.level}
                        className={`guild-boss-level${d.level === bossLevel ? ' guild-boss-level--on' : ''}`}
                        onClick={() => setBossLevel(d.level)}>
                        {d.name}
                      </button>
                    ))}
                  </div>
                  {bossPick && (
                    <>
                      <p className="guild-line">
                        Призыв: {money(bossPick.summon_gold)} золота и {bossPick.summon_ore} ×{bossPick.summon_ore_count} со склада.
                      </p>
                      <p className="guild-line">
                        Здоровье {money(bossPick.hp)}. За убитого: {money(bossPick.reward_gold)} золота в казну
                        и {bossPick.reward_ore} ×{bossPick.reward_ore_count} на склад
                        {boss.has_citadel ? '' : ` (из Двора - ${boss.court_reward_pct}%)`}.
                      </p>
                    </>
                  )}
                </>
              )}
              {perms.treasury && (
                <Button size="m" disabled={busy || boss.cooldown_hours > 0}
                  onClick={() => run('summon_boss', { difficulty: bossLevel }, 'Страж призван!')}>
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
            )}><PlayerLink id={a.vk_id} name={a.name} /></SimpleCell>
          ))}
        </Group>
      )}
      <Group header={<Header>Участники ({members.length})</Header>}>
        {members.map((m) => {
          const seen = m.id === me.id ? null : seenText(m.seen_at);
          return (
          <div key={m.id} className={`member-card${m.id === me.id ? ' member-card--me' : ''}`}>
            <button type="button" className="member-card__row" onClick={() => setOpen(open === m.id ? null : m.id)}>
              <span className="member-card__icon">
                <ClassIcon subclass={m.subclass} baseClass={m.base_class} size={40} />
                {seen?.online && <i className="member-card__online" />}
              </span>
              <span className="member-card__text">
                <span className="member-card__name"><PlayerLink id={m.vk_id} name={m.name} /></span>
                <small className="member-card__meta">
                  <span className={`rank-chip rank-chip--${m.rank}`}>{m.rank_title}</span>
                  {' '}{m.level} ур. {m.class || ''}
                </small>
                {seen && <small className={seen.online ? 'member-card__seen member-card__seen--on' : 'member-card__seen'}>{seen.text}</small>}
              </span>
              <span className="member-card__week">
                <b>{money(m.week)}</b>
                <small>{m.id === me.id ? 'ты' : 'за неделю'}</small>
              </span>
            </button>
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
          );
        })}
      </Group>
      <Group header={<Header>Топ вклада</Header>}>
        <Tabs>
          <TabsItem selected={topMode === 'week'} onClick={() => setTopMode('week')}>Неделя</TabsItem>
          <TabsItem selected={topMode === 'total'} onClick={() => setTopMode('total')}>Всё время</TabsItem>
        </Tabs>
        {(tops[topMode] || []).length === 0 && <Empty icon="⭐">Вклада пока нет.</Empty>}
        {(tops[topMode] || []).map((row, i) => (
          <div className="stat-row" key={row.id}>
            <span className="stat-row__label">{MEDALS[i] || `${i + 1}.`} {row.name}</span>
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
    <div className={`daily-card${q.completed ? ' daily-card--done' : ''}`}>
      <span className="daily-card__mark" aria-hidden="true">{q.completed ? '✓' : ''}</span>
      <div className="daily-card__body">
        <b className="daily-card__title">{q.title}</b>
        <small className="daily-card__how">{q.label}</small>
        <span className="daily-card__progress">
          <Bar value={q.progress} max={q.target} tone={q.completed ? 'green' : 'gold'} />
          <span className="daily-card__count">{money(Math.min(q.progress, q.target))}/{money(q.target)}</span>
        </span>
        <small className="daily-card__how">🎁 {q.reward}{extra ? ` · ${extra}` : ''}</small>
      </div>
    </div>
  );
}

function Quests({ state }) {
  const { quests } = state;
  return (
    <>
      <Group header={<Header>Личные - на сегодня</Header>}>
        <div className="card-list">{quests.dailies.map((q) => <QuestRow key={q.metric} q={q} />)}</div>
      </Group>
      <Group header={<Header>Общие - на неделю</Header>}>
        <div className="card-list">{quests.weekly.map((q) => <QuestRow key={q.metric} q={q} extra={`твой вклад ${money(q.mine)}`} />)}</div>
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
  const [tax, setTax] = useState(null);
  const [counts, setCounts] = useState({});
  const target = to ? Number(to) : undefined;
  const amount = (key, fallback) => counts[key] ?? String(fallback);
  const setAmount = (key, v) => setCounts({ ...counts, [key]: v });

  const header = (
    <Group>
      <div className="tile-grid guild-tiles">
        <div className="tile"><span className="tile__icon">💰</span><b className="tile__value">{money(guild.treasury_gold)}</b><small className="tile__label">золото</small></div>
        <div className="tile"><span className="tile__icon">💎</span><b className="tile__value">{money(guild.treasury_gems)}</b><small className="tile__label">самоцветы</small></div>
        <div className="tile"><span className="tile__icon">🪙</span><b className="tile__value">{guild.gold_tax}%</b><small className="tile__label">налог</small></div>
      </div>
      <Div>
        <div className="milestone milestone--flat">
          <span className="milestone__head">
            <span>📦 Склад руды{warehouse.items.length ? ` · вещей ${warehouse.items.length}` : ''}</span>
            <span>{warehouse.ore_total}/{warehouse.capacity.ore}</span>
          </span>
          <Bar value={warehouse.ore_total} max={warehouse.capacity.ore} tone={warehouse.ore_full ? 'red' : 'blue'} thin />
          {warehouse.ore_full && <small className="milestone__reward">Склад полон, шахты стоят.</small>}
        </div>
        <p className="craft-hint">
          🪙 Налог гильдии: {guild.gold_tax}% с любого золота участников (собрано всего {money(guild.tax_collected)}).
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
            <p className="craft-hint">
              У тебя: 💰 {money(me.gold)} · 💎 {money(me.gems)}. Взнос - от {state.config.deposit_min_gold} золота
              или от {state.config.deposit_min_gems} самоцветов, виден в журнале.
            </p>
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
      </>
    );
  }

  const canGive = me.perms.treasury;
  return (
    <>
      {header}
      {canGive && (
        <Group header={<Header>🪙 Налог гильдии</Header>}>
          <Div className="guild-form">
            <p className="craft-hint">
              Доля любого золота, которое получают участники (добыча, продажа, награды; при передаче - с получателя; с торговли - только с прибыли рейса),
              уходит в казну. Выдачи из казны налогом не облагаются.
            </p>
            <div className="guild-row">
              <NumberInput value={tax ?? String(guild.gold_tax)} onChange={setTax} placeholder="%" />
              <span className="guild-line">% (0-{state.config.tax_max})</span>
              <Button size="m" disabled={busy || tax === null || Number(tax) === guild.gold_tax}
                onClick={() => { run('tax', { percent: Number(tax) }, 'Налог назначен.'); setTax(null); }}>
                Назначить
              </Button>
            </div>
          </Div>
        </Group>
      )}
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
      {warehouse.items.length > 0 && (
      <Group header={<Header>Снаряжение на складе</Header>}>
        {groupItems(warehouse.items).map((g) => (
          <Folder key={g.id} title={g.title} count={g.rows.length}>
            {g.rows.map((i) => (
              <SimpleCell key={i.id} multiline before={<ItemIcon icon={i.icon} rarity={i.rarity} alt={i.name} />}
                subtitle={itemSubtitle(i)} after={canGive && (
                  <Button size="s" mode="secondary" disabled={busy} onClick={() => run('withdraw_item', { item_id: i.id, to: target }, 'Выдано.')}>Выдать</Button>
                )}>{i.name}</SimpleCell>
            ))}
          </Folder>
        ))}
        {!canGive && <Div className="craft-hint">Выдают со склада глава и казначеи.</Div>}
      </Group>
      )}
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
            {here.banner.peaceful && (
              <p className="craft-hint">🕊 Мирное кольцо: здесь гильдия держит только одну клетку, зато её нельзя осадить.</p>
            )}
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
        {here.siege && here.siege.peaceful && (
          <p className="craft-hint">🕊 Мирное кольцо - эту землю не осаждают.</p>
        )}
        {here.siege && !here.siege.peaceful && (
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
              {g.title || `(${g.x}; ${g.y})`}
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
          `${cell.base_title} · кольцо ${cell.ring}${cell.peaceful ? ' 🕊 мирная' : ''}`,
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
              {b.building === 'shaft' && b.level > 0 && state.warehouse.ore_full && (
                <p className="guild-tree__card-lack">📦 Склад полон - шахта стоит. Потратьте руду или постройте склад.</p>
              )}
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

// Двор гильдии (2026-10-17): не на карте, не осаждается. Постройки на всю
// гильдию - до court.max; на базах карты те же - выше, действует лучший уровень.
function Court({ state, run, busy }) {
  const { court, me } = state;
  const building = court.buildings.some((b) => b.upgrading_to);
  return (
    <Group header={<Header>🏛 Двор гильдии</Header>}>
      <Div className="guild-form">
        <p className="craft-hint">
          Двор есть у каждой гильдии: он не на карте, его не осадить. Кузня, Часовня и Склад здесь растут до {court.max} уровня
          и действуют на всю гильдию. На базе на карте они строятся до 10 - берётся лучший уровень, склады складываются.
        </p>
        {court.buildings.map((b) => (
          <div key={b.building} className="guild-building">
            <p className="guild-line">
              {b.emoji} <b>{b.title}</b> {b.built ? `${b.level}/${b.max}` : '- не построена'}
              {b.upgrading_to ? ` · строится ${b.upgrading_to} ур., ещё ${timeLeft(b.done_at)}` : ''}
            </p>
            {b.next && me.perms.treasury && !b.upgrading_to && (
              <div className="guild-row">
                <span className="craft-hint">
                  {money(b.next.gold)} 💰 · {b.next.ore} ×{b.next.ore_count} · {b.next.hours} ч
                </span>
                <Button size="s" disabled={busy || building}
                  onClick={() => run('court_build', { building: b.building }, 'Стройка во Дворе началась.')}>
                  {b.built ? 'Улучшить' : 'Построить'}
                </Button>
              </div>
            )}
          </div>
        ))}
      </Div>
    </Group>
  );
}

function Lands({ state, run, busy }) {
  const { slots, cells } = state;
  return (
    <>
      <Court state={state} run={run} busy={busy} />
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
            Во втором кольце - одна клетка на гильдию, зато её не осаждают. Осада дороже, чем больше земли у
            осаждающих. Потерял базу - остальные клетки 3 суток под щитом.
          </p>
        </Div>
        {cells.length === 0 && <Empty icon="🚩">Земли пока нет. Знамя ставят на свободной клетке.</Empty>}
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
        {sieges.length === 0 && <Empty icon="🏰">Осад не было.</Empty>}
        <div className="card-list">
          {sieges.map((s) => (
            <div key={s.id} className={`siege-card siege-card--${s.role} siege-card--${s.status}`}>
              <span className="siege-card__icon" aria-hidden="true">{s.role === 'attack' ? '⚔️' : '🛡'}</span>
              <span className="siege-card__text">
                <b>{s.role === 'attack' ? 'Штурм' : 'Оборона'} ({s.x}; {s.y}) · {s.enemy}</b>
                <small>{s.result || `${SIEGE_STATUS[s.status]} · ${when(s.starts_at)} МСК`}</small>
              </span>
              {(s.status === 'scheduled' || s.status === 'running') && (
                <span className="siege-card__when">{s.status === 'running' ? 'идёт' : timeLeft(s.starts_at)}</span>
              )}
            </div>
          ))}
        </div>
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
        {season.top.length === 0 && <Empty icon="👑">Очков пока ни у кого.</Empty>}
        {season.top.map((row, i) => (
          <div className="stat-row" key={row.tag}>
            <span className="stat-row__label season-guild">
              <span className="top-rank">{MEDALS[i] || i + 1}</span>
              <GuildCrest tag={row.tag} size={32} /> {row.name}
            </span>
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
    return <Skeleton />;
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
        {/* Вкладок больше, чем влезает: на компьютере колесо и стрелки
            листают их вбок, на телефоне - палец (2026-10-20). */}
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
      {section === 'directory' && <Directory directory={state.directory || []} ownId={state.guild.id} />}
    </>
  );
}
