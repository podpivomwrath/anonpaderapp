import { useEffect, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, Text,
} from '@vkontakte/vkui';
import { IN_VK, eatFood, getInventory, openChest } from '../api.js';
import { itemIcon } from '../itemIcons.js';
import ChestRoulette from './ChestRoulette.jsx';
import ItemIcon from './ItemIcon.jsx';
import Skeleton from './Skeleton.jsx';

// Патч 74: вместо одного плоского списка - сумка, свёрнутая по слотам.
// Плоский список рос вместе с дропом и превращался в стену одинаковых строк.
// Надетое и само надевание (2026-10-22) - во вкладке «Персонаж → Герой».
//
// Реликвии и расходники - такие же свёрнутые группы в той же сумке, а не
// отдельные вкладки: одно место, где лежит всё, что у персонажа есть.

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

export function ItemSheet({ entry, onClose }) {
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
        {note && <p className="item-sheet__note">{note}</p>}
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

export default function InventoryTab() {
  const [items, setItems] = useState(null);
  const [trophies, setTrophies] = useState([]);
  const [consumables, setConsumables] = useState([]);
  const [status, setStatus] = useState('loading');
  const [errorMsg, setErrorMsg] = useState(null);
  const [openSlot, setOpenSlot] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [detail, setDetail] = useState(null);      // {kind, data}
  const [qtyEntry, setQtyEntry] = useState(null);  // расходник, для которого выбираем количество
  const [chests, setChests] = useState([]);
  const [food, setFood] = useState([]);
  const [foodBuff, setFoodBuff] = useState(null);
  const [eating, setEating] = useState(null);
  const [opening, setOpening] = useState(false);
  const [roulette, setRoulette] = useState(null);  // ответ сервера на открытие ларца

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

  if (status === 'loading') {
    return (
      <Skeleton />
    );
  }

  if (status === 'error') {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🎒</div>}>Не удалось загрузить инвентарь.</Placeholder>;
  }

  // Рыба и руда (2026-10-21) - во вкладке «Персонаж → Ремёсла», здесь их нет.
  if (items.every((i) => i.equipped) && trophies.length === 0 && consumables.length === 0 && chests.length === 0
    && food.length === 0 && !foodBuff) {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🎒</div>}>Твоя сумка пока пуста.</Placeholder>;
  }

  const markCopied = (key) => {
    setCopiedId(key);
    setTimeout(() => setCopiedId((cur) => (cur === key ? null : cur)), 2500);
  };

  // Надевают и снимают во вкладке «Персонаж → Герой» (2026-10-22): здесь
  // надетое не показываем вовсе, сумка - только то, что лежит.
  const spare = items.filter((i) => !i.equipped);
  const groups = SLOT_ORDER
    .map((slot) => ({
      key: slot,
      kind: 'gear',
      title: (items.find((i) => i.slot === slot) || {}).slot_title || slot,
      rows: spare.filter((i) => i.slot === slot),
    }))
    .concat([
      { key: 'chests', kind: 'chest', title: 'Редкости', rows: chests },
      { key: 'trophies', kind: 'trophy', title: 'Реликвии', rows: trophies },
      { key: 'consumables', kind: 'consumable', title: 'Расходники', rows: consumables },
      { key: 'food', kind: 'food', title: 'Еда', rows: food },
    ])
    .filter((group) => group.rows.length > 0);
  const bagCount = spare.length + trophies.length + consumables.length + chests.length + food.length;

  const craftButton = (item) => item.craftable && (
    <Button
      mode="outline" size="s"
      onClick={() => window.dispatchEvent(new CustomEvent('open-craft'))}
    >
      В мастерскую
    </Button>
  );

  // Команду передачи с номером экземпляра собирает сервер (transfer_command);
  // здесь только копирование.
  const transferButton = (item) => item.transfer_command && (
    <button
      type="button"
      className="copy-transfer"
      title="Скопировать команду передачи"
      aria-label="Скопировать команду передачи"
      onClick={async () => { await copyText(item.transfer_command); markCopied(`gear:${item.id}`); }}
    >
      {copiedId === `gear:${item.id}` ? <CheckIcon /> : <CopyIcon />}
    </button>
  );

  // У штучного количество выбирается ползунком, поэтому кнопка открывает окно.
  const quantityButton = (entry) => entry.transfer_prefix && (
    <button
      type="button"
      className="copy-transfer"
      title="Скопировать команду передачи"
      aria-label="Скопировать команду передачи"
      onClick={() => setQtyEntry(entry)}
    >
      {copiedId === `stack:${entry.id}` ? <CheckIcon /> : <CopyIcon />}
    </button>
  );

  // Иконка и название открывают подсказку - кнопками, чтобы нажатие не
  // задевало копирование в той же строке.
  const opener = (kind, data) => ({
    before: (
      <button type="button" className="item-open" onClick={() => setDetail({ kind, data })}
        aria-label={`Подробнее: ${data.name}`}>
        {itemIcon(data.icon || '') || !data.emoji
          ? <ItemIcon icon={data.icon} rarity={data.rarity} alt={data.name} />
          : <span className="craft-emoji-icon" aria-hidden="true">{data.emoji}</span>}
      </button>
    ),
    name: (
      <button type="button" className="item-open item-open--name" onClick={() => setDetail({ kind, data })}>
        {data.name}
      </button>
    ),
  });

  const gearRow = (item) => {
    const open = opener('gear', item);
    return (
      <SimpleCell
        key={item.id}
        multiline
        before={open.before}
        subtitle={itemSubtitle(item)}
        // «В мастерскую» - строкой под описанием (2026-10-19): справа она
        // сжимала название и статы до столбика в одну букву.
        extraSubtitle={item.craftable ? <div className="inventory-craft">{craftButton(item)}</div> : undefined}
        after={item.transfer_command ? <div className="inventory-actions">{transferButton(item)}</div> : null}
      >
        {open.name}
      </SimpleCell>
    );
  };

  const stackRow = (kind, entry) => {
    const open = opener(kind, entry);
    let subtitle = `${entry.category_title} · ×${entry.count}`;
    if (kind === 'trophy') subtitle = [entry.rarity_title, `×${entry.count}`].filter(Boolean).join(' · ');
    if (kind === 'chest') subtitle = `×${entry.count}`;
    if (kind === 'food') subtitle = `${entry.grade_title} · ×${entry.count} · ${entry.effect}`;
    let after = null;
    if (kind === 'consumable') after = <div className="inventory-actions">{quantityButton(entry)}</div>;
    if (kind === 'food') {
      after = (
        <div className="inventory-actions">
          {quantityButton(entry)}
          <Button mode="primary" size="s" loading={eating === entry.id} onClick={() => handleEat(entry)}>
            Съесть
          </Button>
        </div>
      );
    }
    if (kind === 'chest') {
      after = (
        <Button mode="primary" size="s" loading={opening} onClick={() => handleOpenChest(entry.kind)}>
          Открыть
        </Button>
      );
    }
    return (
      <SimpleCell
        key={entry.id}
        multiline
        before={open.before}
        subtitle={subtitle}
        after={after}
      >
        {open.name}
      </SimpleCell>
    );
  };

  return (
    <>
      {errorMsg && (
        <Div><Text style={{ color: '#c81e3a' }}>{errorMsg}</Text></Div>
      )}

      {foodBuff && (
        <Group header={<Header>Сытость</Header>}>
          <Div>
            {foodBuff.emoji} {foodBuff.name}: {foodBuff.effect}. Еще {foodBuff.minutes_left} мин.
          </Div>
        </Group>
      )}

      <Group header={<Header>В сумке ({bagCount})</Header>}>
        {groups.length === 0 && <Div>Сумка пуста.</Div>}
        {groups.map((group) => (
          <div key={group.key}>
            <SimpleCell
              onClick={() => setOpenSlot((cur) => (cur === group.key ? null : group.key))}
              after={openSlot === group.key ? '▴' : `${group.rows.length} ▾`}
            >
              {group.title}
            </SimpleCell>
            {openSlot === group.key && (
              <div className="craft-expand">
                {group.rows.map((row) => (group.kind === 'gear' ? gearRow(row) : stackRow(group.kind, row)))}
              </div>
            )}
          </div>
        ))}
      </Group>

      {detail && (
        <ItemSheet entry={detail} onClose={() => setDetail(null)} />
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
