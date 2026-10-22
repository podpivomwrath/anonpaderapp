import { useEffect, useMemo, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';
import {
  Button, Group, Placeholder,
} from '@vkontakte/vkui';
import { IN_VK, eatFood, getInventory, openChest } from '../api.js';
import { itemIcon } from '../itemIcons.js';
import ChestRoulette from './ChestRoulette.jsx';
import ItemIcon from './ItemIcon.jsx';
import Skeleton from './Skeleton.jsx';
import { Empty, SectionHead } from './ui.jsx';

// Патч 74: вместо одного плоского списка - сумка, свёрнутая по слотам.
// Плоский список рос вместе с дропом и превращался в стену одинаковых строк.
// Надетое и само надевание (2026-10-22) - во вкладке «Персонаж → Герой».
//
// Реликвии и расходники - в той же сумке, а не отдельные вкладки: одно
// место, где лежит всё, что у персонажа есть.
//
// 2026-10-22: сумка - сетка ячеек с рамкой редкости и фильтры значками;
// группы по слотам ушли, порядок внутри - слот, редкость, сила.

const STAT_ICONS = { str: '💪', agi: '🏃', int: '🧠', vit: '❤️', wil: '✨' };

const STAT_NAMES = {
  str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Выносливость', wil: 'Воля',
};

// Порядок сверху вниз, как надевают. Слоты приходят с сервера уже с
// названиями (slot_title), здесь только очерёдность показа.
const SLOT_ORDER = ['weapon', 'helmet', 'armor', 'legs', 'boots'];

// Иконки нарисованы здесь, а не взяты из @vkontakte/icons: пакета нет в
// зависимостях мини-аппа, он приезжает только транзитом через VKUI.
export function CopyIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="7" y="7" width="9.5" height="9.5" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M13 4.8V4.5A1.5 1.5 0 0 0 11.5 3h-7A1.5 1.5 0 0 0 3 4.5v7A1.5 1.5 0 0 0 4.5 13h.3"
        stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function CheckIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d="M4.5 10.5l3.5 3.5 7.5-8" stroke="currentColor" strokeWidth="1.8"
        strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function statsLine(baseStats) {
  return Object.entries(baseStats || {})
    .sort((a, b) => b[1] - a[1])
    .map(([key, amount]) => `${STAT_NAMES[key] || key} +${amount}`)
    .join(', ');
}

export function itemSubtitle(item) {
  const parts = [];
  // Редкость словом. Эмодзи-кружок из названия убран (патч 79): цвет теперь
  // несёт свечение рамки, а в подписи слово читается быстрее оттенка.
  if (item.rarity_title) parts.push(item.rarity_title);
  if (item.craft_efficiency) parts.push(`${item.craft_efficiency}%`);
  else if (item.ilvl) parts.push(`ур. ${item.ilvl}`);
  const stats = statsLine(item.base_stats);
  if (stats) parts.push(stats);
  if (item.need_level && !item.equipped) parts.push(`🔒 надеть с ${item.need_level} ур.`);
  return parts.join(' · ');
}

// Буфер обмена в ВК надёжен только через мост: navigator.clipboard в
// веб-вью клиента часто запрещён. На сайте моста нет - его вызов не
// завершался, и копирование молча не происходило; там пишем напрямую,
// а если браузер запретил - через скрытое поле и execCommand.
function legacyCopy(text) {
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  try { document.execCommand('copy'); } catch { /* текст всё равно виден в окне */ }
  area.remove();
}

export async function copyText(text) {
  if (!IN_VK) {
    try { await navigator.clipboard.writeText(text); } catch { legacyCopy(text); }
    return;
  }
  try {
    await bridge.send('VKWebAppCopyText', { text });
  } catch {
    try { await navigator.clipboard.writeText(text); } catch { legacyCopy(text); }
  }
}

// --- Подсказка о предмете ---------------------------------------------------
// Шторка снизу поверх страницы (как выбор рамки венца): список под ней не
// перерисовывается и не теряет раскрытую группу.

function detailRows(entry) {
  const { kind, data } = entry;
  if (kind === 'gear') {
    const rows = [];
    if (data.rarity_title) rows.push(['Редкость', data.rarity_title]);
    rows.push(['Слот', data.slot_title]);
    if (data.ilvl) rows.push(['Уровень', data.ilvl]);
    if (data.craft_efficiency) rows.push(['Эффективность', `${data.craft_efficiency}%`]);
    Object.entries(data.base_stats || {})
      .sort((a, b) => b[1] - a[1])
      .forEach(([key, amount]) => rows.push([STAT_NAMES[key] || key, `+${amount}`]));
    rows.push(['Сумма характеристик', data.power]);
    if (data.equipped) rows.push(['Состояние', 'Надето']);
    if (data.bound) rows.push(['Передача', 'Привязано к хозяину']);
    return rows;
  }
  if (kind === 'chest') {
    return [['В сумке', `×${data.count}`]].concat(
      (data.grades || []).map((g) => [`${g.name} ларец`, `${g.chance}%`]),
    );
  }
  if (kind === 'fish') {
    return [
      ['Градация', data.grade_title],
      ['Вес', data.weight],
      ['Иргал даст', `${data.price} зол.`],
    ];
  }
  if (kind === 'ore') {
    return [
      ['Градация', data.grade_title],
      ['В сумке', `×${data.count}`],
    ];
  }
  if (kind === 'food') {
    return [
      ['Рыба', data.grade_title],
      ['Действие', data.effect],
      ['В сумке', `×${data.count}`],
    ];
  }
  if (kind === 'herb') {
    return [
      ['Тир', data.tier],
      ['В сумке', `×${data.count}`],
    ];
  }
  if (kind === 'trophy') {
    return [
      ['Редкость', data.rarity_title || '-'],
      ['В сумке', `×${data.count}`],
      ['Иргал даёт за штуку', `${data.price} зол.`],
      ['За всё', `${data.price_total} зол.`],
    ];
  }
  return [
    ['Тип', data.category_title],
    ['В сумке', `×${data.count}`],
  ];
}

// Разница с надетым в том же слоте: «💪 +3 · 🧠 -2».
function CompareLine({ item, worn }) {
  const keys = ['str', 'agi', 'int', 'vit', 'wil'];
  const diff = keys
    .map((k) => [k, (item.base_stats?.[k] || 0) - (worn?.base_stats?.[k] || 0)])
    .filter(([, d]) => d !== 0);
  return (
    <div className="item-compare">
      <span className="item-compare__label">{worn ? `против «${worn.name}»` : 'слот пуст'}</span>
      <span className="item-compare__chips">
        {diff.length === 0 && <span className="gear-chip gear-chip--same">=</span>}
        {diff.map(([k, d]) => (
          <span key={k} className={d > 0 ? 'gear-chip gear-chip--up' : 'gear-chip gear-chip--down'}>
            {STAT_ICONS[k]} {d > 0 ? `+${d}` : d}
          </span>
        ))}
      </span>
    </div>
  );
}

export function ItemSheet({ entry, onClose, worn, compare = false, actions = null }) {
  const { kind, data } = entry;
  const NOTES = {
    trophy: 'Цена - у скупщика в своём городе, в чужом он платит меньше. Реликвии не передаются.',
    fish: 'Цена - у Иргала в своём городе. Рыбак у воды в глубоких кольцах платит больше.',
    food: 'Есть можно только вне боя. Действует одно блюдо: новое заменяет старое. Бафф не пропадает после смерти.',
    herb: 'Из трав варят зелья на алхимическом столе и готовят блюда в печи - для этого нужен дом.',
    ore: 'Руда идёт на ковку в мастерской и не теряется при смерти. Лишнее железо и кварц дёшево берёт Иргал.',
  };
  const note = NOTES[kind] || null;
  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet item-sheet" role="dialog" aria-label={data.name}>
        <div className="item-sheet__head">
          <ItemIcon icon={data.icon} rarity={data.rarity} alt={data.name} size={96} />
          <div className="item-sheet__title">
            <b>{data.name}</b>
            {kind !== 'fish' && data.count > 1 && <small>×{data.count}</small>}
          </div>
        </div>
        {data.description && <p className="item-sheet__desc">{data.description}</p>}
        <dl className="item-sheet__rows">
          {detailRows(entry).map(([label, value]) => (
            <div key={label} className="item-sheet__row">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        {compare && <CompareLine item={data} worn={worn} />}
        {note && <p className="item-sheet__note">{note}</p>}
        {actions && <div className="item-sheet__actions">{actions}</div>}
        <Button mode="secondary" size="l" stretched onClick={onClose}>Закрыть</Button>
      </div>
    </>
  );
}

// --- Сколько передать -------------------------------------------------------

export function QuantitySheet({ entry, onClose, onCopied }) {
  const max = Math.max(1, entry.count);
  const [qty, setQty] = useState(1);
  const clamp = (value) => Math.min(max, Math.max(1, Math.round(Number(value) || 1)));

  async function confirm() {
    const amount = clamp(qty);
    await copyText(`${entry.transfer_prefix} ${amount}`);
    onCopied(entry.id);
    onClose();
  }

  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet item-sheet" role="dialog" aria-label="Сколько передать">
        <div className="item-sheet__head">
          <ItemIcon icon={entry.icon} alt={entry.name} size={48} />
          <div className="item-sheet__title">
            <b>{entry.name}</b>
            <small>Сколько передать? В сумке ×{entry.count}</small>
          </div>
        </div>
        <div className="qty-picker">
          <input
            type="range" min={1} max={max} step={1} value={clamp(qty)}
            onChange={(e) => setQty(e.target.value)}
            aria-label="Количество"
          />
          <input
            type="number" inputMode="numeric" min={1} max={max} value={qty}
            // Больше, чем есть в сумке, сразу становится максимумом; пустое
            // поле не трогаем, пока игрок печатает.
            onChange={(e) => setQty(e.target.value === '' ? '' : String(Math.min(max, Number(e.target.value))))}
            onBlur={() => setQty(clamp(qty))}
            className="qty-picker__input"
            aria-label="Количество числом"
          />
        </div>
        <p className="item-sheet__note">
          Скопируется: {entry.transfer_prefix} {clamp(qty)}
        </p>
        <div className="qty-picker__buttons">
          <Button mode="secondary" size="l" stretched onClick={onClose}>Отменить</Button>
          <Button mode="primary" size="l" stretched onClick={confirm}>ОК</Button>
        </div>
      </div>
    </>
  );
}


// --- Сумка сеткой (2026-10-22) ------------------------------------------------
// Ячейки с картинкой и рамкой редкости, сверху фильтры значками. Нажатие на
// ячейку - шторка вещи, все действия (передать, съесть, открыть) там.

const FILTERS = [
  { id: 'all', icon: '🎒', title: 'Всё' },
  { id: 'gear', icon: '⚔️', title: 'Снаряжение' },
  { id: 'chest', icon: '🗃️', title: 'Ларцы' },
  { id: 'trophy', icon: '🏺', title: 'Реликвии' },
  { id: 'consumable', icon: '🧪', title: 'Расходники' },
  { id: 'food', icon: '🍲', title: 'Еда' },
];

// Что игрок уже видел: новые вещи помечены точкой, пока их не открыли.
// Только в этом браузере - удобство, а не данные игры.
const SEEN_KEY = 'pines:bag-seen';

function loadSeen() {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    return raw ? new Set(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

function saveSeen(set) {
  try { localStorage.setItem(SEEN_KEY, JSON.stringify([...set].slice(-600))); } catch { /* без памяти - без точек */ }
}

// Вещь без своей картинки (админская, свежая) - значок слота, а не пустая ячейка.
const SLOT_EMOJI = { weapon: '⚔️', helmet: '🪖', armor: '🛡️', legs: '👖', boots: '👢' };
// Те же запасные картинки, что у ItemIcon: ларцы, свитки, уникальные и кованые.
const hasPicture = (icon) => Boolean(icon) && (Boolean(itemIcon(icon))
  || ['chest:', 'elixir:scroll_', 'unique:', 'craft:'].some((p) => icon.startsWith(p)));

const RARITY_RANK = { unique: 5, legendary: 4, epic: 3, rare: 2, uncommon: 1, common: 0 };

function BagCell({ entry, isNew, onOpen }) {
  const { data } = entry;
  const count = entry.kind === 'gear' ? null : data.count;
  const rar = data.rarity || 'common';
  return (
    <button
      type="button"
      className={`bag-cell bag-cell--${rar}${data.need_level ? ' bag-cell--locked' : ''}`}
      onClick={onOpen}
      aria-label={data.name}
    >
      {hasPicture(data.icon)
        ? <ItemIcon icon={data.icon} rarity={data.rarity} alt="" size={56} />
        : <span className="bag-cell__emoji" aria-hidden="true">{data.emoji || SLOT_EMOJI[data.slot] || '❔'}</span>}
      {count > 1 && <span className="bag-cell__count">{count > 999 ? '999+' : count}</span>}
      {entry.better && <span className="bag-cell__up" aria-hidden="true">▲</span>}
      {data.need_level && <span className="bag-cell__lock" aria-hidden="true">🔒</span>}
      {isNew && <span className="bag-cell__new" aria-hidden="true" />}
    </button>
  );
}

export default function InventoryTab({ onOpenTab }) {
  const [items, setItems] = useState(null);
  const [trophies, setTrophies] = useState([]);
  const [consumables, setConsumables] = useState([]);
  const [status, setStatus] = useState('loading');
  const [errorMsg, setErrorMsg] = useState(null);
  const [filter, setFilter] = useState('all');
  const [copiedId, setCopiedId] = useState(null);
  const [detail, setDetail] = useState(null);      // {kind, data}
  const [qtyEntry, setQtyEntry] = useState(null);  // расходник, для которого выбираем количество
  const [chests, setChests] = useState([]);
  const [food, setFood] = useState([]);
  const [foodBuff, setFoodBuff] = useState(null);
  const [eating, setEating] = useState(null);
  const [opening, setOpening] = useState(false);
  const [roulette, setRoulette] = useState(null);  // ответ сервера на открытие ларца
  const [seen, setSeen] = useState(null);

  function apply(res) {
    setItems(res.items);
    setTrophies(res.trophies || []);
    setConsumables(res.consumables || []);
    setChests(res.chests || []);
    setFood(res.food || []);
    setFoodBuff(res.food_buff || null);
  }

  // Еда (2026-10-21): только вне боя - сервер откажет, если бой идёт.
  async function handleEat(entry) {
    if (eating) return;
    setEating(entry.id);
    setErrorMsg(null);
    try {
      apply(await eatFood(entry.dish, entry.grade));
      setDetail(null);
    } catch (err) {
      setErrorMsg(err?.message?.includes(' ') ? err.message : 'Не удалось поесть.');
    } finally {
      setEating(null);
    }
  }

  async function handleOpenChest(kind) {
    if (opening) return;
    setOpening(true);
    setErrorMsg(null);
    try {
      setRoulette(await openChest(kind));
      setDetail(null);
    } catch (err) {
      setErrorMsg(err?.message === 'no_chest' ? 'Ларцов в сумке больше нет.' : 'Не удалось открыть ларец.');
    } finally {
      setOpening(false);
    }
  }

  function closeRoulette() {
    // Сумка обновляется после рулетки, а не до: иначе стопка ларцов и
    // награда в группах менялись бы, пока игрок ещё смотрит на ленту.
    if (roulette?.inventory) apply(roulette.inventory);
    setRoulette(null);
  }

  function load() {
    setStatus('loading');
    getInventory()
      .then((res) => {
        apply(res);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }

  useEffect(load, []);

  // Надевают и снимают во вкладке «Персонаж → Герой» (2026-10-22): здесь
  // надетое не показываем вовсе, сумка - только то, что лежит.
  const worn = useMemo(
    () => Object.fromEntries((items || []).filter((i) => i.equipped).map((i) => [i.slot, i])),
    [items],
  );
  const entries = useMemo(() => {
    if (!items) return [];
    const gear = items
      .filter((i) => !i.equipped)
      .sort((a, b) => SLOT_ORDER.indexOf(a.slot) - SLOT_ORDER.indexOf(b.slot)
        || (RARITY_RANK[b.rarity] || 0) - (RARITY_RANK[a.rarity] || 0) || b.power - a.power)
      .map((i) => ({
        kind: 'gear', key: `gear:${i.id}`, data: i,
        better: !i.need_level && i.power > (worn[i.slot]?.power || 0),
      }));
    const stack = (kind, rows) => rows.map((r) => ({ kind, key: `${kind}:${r.id}`, data: r }));
    return [
      ...stack('chest', chests), ...gear, ...stack('trophy', trophies),
      ...stack('consumable', consumables), ...stack('food', food),
    ];
  }, [items, worn, chests, trophies, consumables, food]);

  // Первый заход в этом браузере - всё уже «видено», точек нет.
  useEffect(() => {
    if (status !== 'ready') return;
    const stored = loadSeen();
    if (stored) {
      setSeen(stored);
    } else {
      const all = new Set(entries.map((e) => e.key));
      saveSeen(all);
      setSeen(all);
    }
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (status === 'loading') {
    return (
      <Skeleton />
    );
  }

  if (status === 'error') {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🎒</div>}>Не удалось загрузить инвентарь.</Placeholder>;
  }

  const markCopied = (key) => {
    setCopiedId(key);
    setTimeout(() => setCopiedId((cur) => (cur === key ? null : cur)), 2500);
  };

  const openEntry = (entry) => {
    setDetail(entry);
    if (seen && !seen.has(entry.key)) {
      const next = new Set(seen);
      next.add(entry.key);
      saveSeen(next);
      setSeen(next);
    }
  };

  const counts = Object.fromEntries(FILTERS.map((f) => [
    f.id, f.id === 'all' ? entries.length : entries.filter((e) => e.kind === f.id).length,
  ]));
  const shown = filter === 'all' ? entries : entries.filter((e) => e.kind === filter);
  const newCount = seen ? entries.filter((e) => !seen.has(e.key)).length : 0;

  // Действия вещи - в её шторке.
  const sheetActions = (entry) => {
    const { kind, data } = entry;
    const out = [];
    if (kind === 'gear') {
      out.push(
        <button key="hero" type="button" className="pill-btn" onClick={() => onOpenTab?.('character')}>
          🧍 Надеть в «Герое»
        </button>,
      );
      if (data.craftable) {
        out.push(
          <button key="craft" type="button" className="pill-btn"
            onClick={() => window.dispatchEvent(new CustomEvent('open-craft'))}>
            ⚒ В мастерскую
          </button>,
        );
      }
      // Команду передачи с номером экземпляра собирает сервер (transfer_command).
      if (data.transfer_command) {
        out.push(
          <button key="copy" type="button" className="pill-btn"
            onClick={async () => { await copyText(data.transfer_command); markCopied(entry.key); }}>
            {copiedId === entry.key ? <CheckIcon /> : <CopyIcon />} Команда передачи
          </button>,
        );
      }
    }
    if (kind === 'chest') {
      out.push(
        <button key="open" type="button" className="pill-btn pill-btn--main" disabled={opening}
          onClick={() => handleOpenChest(data.kind)}>
          🗝 Открыть
        </button>,
      );
    }
    if (kind === 'food') {
      out.push(
        <button key="eat" type="button" className="pill-btn pill-btn--main" disabled={eating === data.id}
          onClick={() => handleEat(data)}>
          🍴 Съесть
        </button>,
      );
    }
    // У штучного количество выбирается ползунком, поэтому кнопка открывает окно.
    if ((kind === 'consumable' || kind === 'food') && data.transfer_prefix) {
      out.push(
        <button key="qty" type="button" className="pill-btn" onClick={() => { setQtyEntry(data); setDetail(null); }}>
          {copiedId === `stack:${data.id}` ? <CheckIcon /> : <CopyIcon />} Передать
        </button>,
      );
    }
    return out.length ? out : null;
  };

  return (
    <>
      <SectionHead
        kind="inventory" icon="🎒" value={entries.length}
        label={newCount > 0 ? `в сумке · новых ${newCount}` : 'в сумке'}
        aside={foodBuff && (
          <span className="bag-buff" title={foodBuff.effect}>
            {foodBuff.emoji} {foodBuff.minutes_left} мин<br /><small>{foodBuff.name}</small>
          </span>
        )}
      />

      {errorMsg && <p className="tab-error">{errorMsg}</p>}

      <Group>
        <div className="filter-chips" role="tablist">
          {FILTERS.filter((f) => f.id === 'all' || counts[f.id] > 0).map((f) => (
            <button
              type="button" key={f.id} role="tab" aria-selected={filter === f.id}
              className={`filter-chip${filter === f.id ? ' filter-chip--on' : ''}`}
              onClick={() => setFilter(f.id)} title={f.title} aria-label={f.title}
            >
              <span aria-hidden="true">{f.icon}</span>
              <small>{counts[f.id]}</small>
            </button>
          ))}
        </div>
        {shown.length === 0 ? (
          <Empty icon="🎒">Сумка пуста. Вещи падают с мобов, из ларцов и рейдов.</Empty>
        ) : (
          <div className="bag-grid" key={filter}>
            {shown.map((entry) => (
              <BagCell
                key={entry.key} entry={entry} isNew={seen ? !seen.has(entry.key) : false}
                onOpen={() => openEntry(entry)}
              />
            ))}
          </div>
        )}
        {foodBuff && (
          <p className="bag-buff-line">{foodBuff.emoji} {foodBuff.name}: {foodBuff.effect}. Ещё {foodBuff.minutes_left} мин.</p>
        )}
      </Group>

      {detail && (
        <ItemSheet
          entry={detail}
          onClose={() => setDetail(null)}
          compare={detail.kind === 'gear'}
          worn={detail.kind === 'gear' ? worn[detail.data.slot] : null}
          actions={sheetActions(detail)}
        />
      )}
      {roulette && (
        <ChestRoulette
          strip={roulette.strip}
          winIndex={roulette.win_index}
          result={roulette.result}
          onClose={closeRoulette}
        />
      )}
      {qtyEntry && (
        <QuantitySheet
          entry={qtyEntry}
          onClose={() => setQtyEntry(null)}
          onCopied={(id) => markCopied(`stack:${id}`)}
        />
      )}
    </>
  );
}
