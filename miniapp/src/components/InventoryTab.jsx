import { useEffect, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, Spinner, Text,
} from '@vkontakte/vkui';
import { equipItem, getCharacter, getInventory, openChest, unequipItem } from '../api.js';
import ChestRoulette from './ChestRoulette.jsx';
import ItemIcon from './ItemIcon.jsx';

// Патч 74: вместо одного плоского списка - «Надето» отдельно и сумка,
// свёрнутая по слотам. Плоский список рос вместе с дропом и превращался в
// стену одинаковых строк, где надетое терялось среди лишнего.
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
function CopyIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="7" y="7" width="9.5" height="9.5" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M13 4.8V4.5A1.5 1.5 0 0 0 11.5 3h-7A1.5 1.5 0 0 0 3 4.5v7A1.5 1.5 0 0 0 4.5 13h.3"
        stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function CheckIcon() {
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

function itemSubtitle(item) {
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
// веб-вью клиента часто запрещён.
async function copyText(text) {
  try {
    await bridge.send('VKWebAppCopyText', { text });
  } catch {
    try { await navigator.clipboard.writeText(text); } catch { /* текст всё равно виден в окне */ }
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

function ItemSheet({ entry, onClose, onUnequip, unequipping }) {
  const { kind, data } = entry;
  const note = kind === 'trophy'
    ? 'Цена - у скупщика в своём городе, в чужом он платит меньше. Реликвии не передаются.'
    : null;
  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet item-sheet" role="dialog" aria-label={data.name}>
        <div className="item-sheet__head">
          <ItemIcon icon={data.icon} rarity={data.rarity} alt={data.name} size={96} />
          <div className="item-sheet__title">
            <b>{data.name}</b>
            {data.count > 1 && <small>×{data.count}</small>}
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
        {kind === 'gear' && data.equipped && onUnequip && (
          <Button
            mode="outline" size="l" stretched loading={unequipping}
            onClick={() => onUnequip(data.id)}
            style={{ marginBottom: 8 }}
          >
            Снять
          </Button>
        )}
        <Button mode="secondary" size="l" stretched onClick={onClose}>Закрыть</Button>
      </div>
    </>
  );
}

// --- Сколько передать -------------------------------------------------------

function QuantitySheet({ entry, onClose, onCopied }) {
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

export default function InventoryTab({ onCharacterUpdate }) {
  const [items, setItems] = useState(null);
  const [trophies, setTrophies] = useState([]);
  const [consumables, setConsumables] = useState([]);
  const [status, setStatus] = useState('loading');
  const [equippingId, setEquippingId] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [openSlot, setOpenSlot] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [detail, setDetail] = useState(null);      // {kind, data}
  const [qtyEntry, setQtyEntry] = useState(null);  // расходник, для которого выбираем количество
  const [chests, setChests] = useState([]);
  const [opening, setOpening] = useState(false);
  const [roulette, setRoulette] = useState(null);  // ответ сервера на открытие ларца

  function apply(res) {
    setItems(res.items);
    setTrophies(res.trophies || []);
    setConsumables(res.consumables || []);
    setChests(res.chests || []);
  }

  async function handleOpenChest() {
    if (opening) return;
    setOpening(true);
    setErrorMsg(null);
    try {
      setRoulette(await openChest());
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

  async function handleEquip(itemId) {
    setEquippingId(itemId);
    setErrorMsg(null);
    try {
      const res = await equipItem(itemId);
      apply(res);
      // Надетая вещь меняет статы, а карточка персонажа лежит в Hub: без
      // этого вкладка «Характеристики» показывала старые цифры до перезапуска
      // мини-аппа - ровно тот же разрыв, что чинил патч 32 для предпросмотра.
      if (onCharacterUpdate) {
        try {
          onCharacterUpdate(await getCharacter());
        } catch {
          /* предмет уже надет; обновление карточки подтянется при следующем открытии */
        }
      }
    } catch (err) {
      // Раньше тут стоял setStatus('error') - одна неудачная экипировка
      // подменяла весь загруженный список сообщением «не удалось загрузить».
      setErrorMsg(err?.message || 'Не удалось надеть предмет.');
    } finally {
      setEquippingId(null);
    }
  }

  // Патч 111: снять надетую вещь. Как и после «Надеть» - перезапросить
  // персонажа: статы и Мощь в шапке зависят от того, что надето сейчас.
  async function handleUnequip(itemId) {
    setEquippingId(itemId);
    setErrorMsg(null);
    try {
      apply(await unequipItem(itemId));
      setDetail(null);
      if (onCharacterUpdate) {
        try {
          onCharacterUpdate(await getCharacter());
        } catch {
          /* вещь уже снята; шапка обновится при следующем открытии */
        }
      }
    } catch (err) {
      setErrorMsg(err?.message === 'cannot_unequip' ? 'Эта вещь уже не надета.' : (err?.message?.includes(' ') ? err.message : 'Не удалось снять предмет.'));
    } finally {
      setEquippingId(null);
    }
  }

  if (status === 'loading') {
    return (
      <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
        <Spinner size="l" />
      </Div>
    );
  }

  if (status === 'error') {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🎒</div>}>Не удалось загрузить инвентарь.</Placeholder>;
  }

  if (items.length === 0 && trophies.length === 0 && consumables.length === 0 && chests.length === 0) {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🎒</div>}>Твоя сумка пока пуста.</Placeholder>;
  }

  const markCopied = (key) => {
    setCopiedId(key);
    setTimeout(() => setCopiedId((cur) => (cur === key ? null : cur)), 2500);
  };

  const equipped = items.filter((i) => i.equipped);
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
    ])
    .filter((group) => group.rows.length > 0);
  const bagCount = spare.length + trophies.length + consumables.length + chests.length;

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
  // задевало «Надеть» и копирование в той же строке.
  const opener = (kind, data) => ({
    before: (
      <button type="button" className="item-open" onClick={() => setDetail({ kind, data })}
        aria-label={`Подробнее: ${data.name}`}>
        <ItemIcon icon={data.icon} rarity={data.rarity} alt={data.name} />
      </button>
    ),
    name: (
      <button type="button" className="item-open item-open--name" onClick={() => setDetail({ kind, data })}>
        {data.name}
      </button>
    ),
  });

  const gearRow = (item, inBag) => {
    const open = opener('gear', item);
    return (
      <SimpleCell
        key={item.id}
        multiline
        before={open.before}
        subtitle={itemSubtitle(item)}
        after={inBag ? (
          <div className="inventory-actions">
            {craftButton(item)}
            {transferButton(item)}
            <Button
              mode="secondary" size="s"
              loading={equippingId === item.id}
              disabled={Boolean(item.need_level)}
              onClick={() => handleEquip(item.id)}
            >
              Надеть
            </Button>
          </div>
        ) : (
          <div className="inventory-actions">
            {craftButton(item)}
            <Button
              mode="tertiary" size="s"
              loading={equippingId === item.id}
              onClick={() => handleUnequip(item.id)}
            >
              Снять
            </Button>
          </div>
        )}
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
    let after = null;
    if (kind === 'consumable') after = <div className="inventory-actions">{quantityButton(entry)}</div>;
    if (kind === 'chest') {
      after = (
        <Button mode="primary" size="s" loading={opening} onClick={handleOpenChest}>
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

      <Group header={<Header>Надето</Header>}>
        {equipped.length === 0 && <Div>Ничего не надето.</Div>}
        {SLOT_ORDER.map((slot) => equipped.find((i) => i.slot === slot)).filter(Boolean)
          .map((item) => gearRow(item, false))}
      </Group>

      <Group header={<Header>В сумке ({bagCount})</Header>}>
        {groups.length === 0 && <Div>Сумка пуста - всё на тебе.</Div>}
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
                {group.rows.map((row) => (group.kind === 'gear' ? gearRow(row, true) : stackRow(group.kind, row)))}
              </div>
            )}
          </div>
        ))}
      </Group>

      {detail && (
        <ItemSheet
          entry={detail} onClose={() => setDetail(null)}
          onUnequip={handleUnequip} unequipping={equippingId === detail.data?.id}
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
