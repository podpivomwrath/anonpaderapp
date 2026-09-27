import { useEffect, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, Spinner, Text,
} from '@vkontakte/vkui';
import { equipItem, getCharacter, getInventory } from '../api.js';
import ItemIcon from './ItemIcon.jsx';

// Патч 74: вместо одного плоского списка - «Надето» отдельно и сумка,
// свёрнутая по слотам. Плоский список рос вместе с дропом и превращался в
// стену одинаковых строк, где надетое терялось среди лишнего.

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
  return parts.join(' · ');
}

export default function InventoryTab({ onCharacterUpdate }) {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState('loading');
  const [equippingId, setEquippingId] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);
  const [openSlot, setOpenSlot] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  function load() {
    setStatus('loading');
    getInventory()
      .then((res) => {
        setItems(res.items);
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
      setItems(res.items);
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

  if (items.length === 0) {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🎒</div>}>Твоя сумка пока пуста.</Placeholder>;
  }

  const equipped = items.filter((i) => i.equipped);
  const spare = items.filter((i) => !i.equipped);
  const slots = SLOT_ORDER
    .map((slot) => ({
      slot,
      title: (items.find((i) => i.slot === slot) || {}).slot_title || slot,
      rows: spare.filter((i) => i.slot === slot),
    }))
    .filter((group) => group.rows.length > 0);

  const craftButton = (item) => item.craftable && (
    <Button
      mode="outline" size="s"
      onClick={() => window.dispatchEvent(new CustomEvent('open-craft'))}
    >
      В мастерскую
    </Button>
  );

  // Команду передачи с номером экземпляра собирает сервер (transfer_command);
  // здесь только копирование. В ВК буфер обмена надёжен лишь через мост:
  // navigator.clipboard в веб-вью клиента часто запрещён.
  const copyTransfer = async (item) => {
    const text = item.transfer_command;
    try {
      await bridge.send('VKWebAppCopyText', { text });
    } catch {
      try { await navigator.clipboard.writeText(text); } catch { /* показ ниже всё равно поможет */ }
    }
    setCopiedId(item.id);
    setTimeout(() => setCopiedId((cur) => (cur === item.id ? null : cur)), 2500);
  };

  const transferButton = (item) => item.transfer_command && (
    <button
      type="button"
      className="copy-transfer"
      title="Скопировать команду передачи"
      aria-label="Скопировать команду передачи"
      onClick={() => copyTransfer(item)}
    >
      {copiedId === item.id ? <CheckIcon /> : <CopyIcon />}
    </button>
  );

  return (
    <>
      {errorMsg && (
        <Div><Text style={{ color: '#c81e3a' }}>{errorMsg}</Text></Div>
      )}

      <Group header={<Header>Надето</Header>}>
        {equipped.length === 0 && <Div>Ничего не надето.</Div>}
        {SLOT_ORDER.map((slot) => equipped.find((i) => i.slot === slot)).filter(Boolean).map((item) => (
          <SimpleCell
            key={item.id}
            multiline
            before={<ItemIcon icon={item.icon} rarity={item.rarity} alt={item.name} />}
            after={craftButton(item)}
            subtitle={itemSubtitle(item)}
          >
            {item.name}
          </SimpleCell>
        ))}
      </Group>

      <Group header={<Header>В сумке ({spare.length})</Header>}>
        {slots.length === 0 && <Div>Сумка пуста - всё на тебе.</Div>}
        {slots.map((group) => (
          <div key={group.slot}>
            <SimpleCell
              onClick={() => setOpenSlot((cur) => (cur === group.slot ? null : group.slot))}
              after={openSlot === group.slot ? '▴' : `${group.rows.length} ▾`}
            >
              {group.title}
            </SimpleCell>
            {openSlot === group.slot && (
              <div className="craft-expand">
                {group.rows.map((item) => (
                  <SimpleCell
                    key={item.id}
                    multiline
                    before={<ItemIcon icon={item.icon} rarity={item.rarity} alt={item.name} />}
                    subtitle={itemSubtitle(item)}
                    after={
                      <div className="inventory-actions">
                        {craftButton(item)}
                        {transferButton(item)}
                        <Button
                          mode="secondary" size="s"
                          loading={equippingId === item.id}
                          onClick={() => handleEquip(item.id)}
                        >
                          Надеть
                        </Button>
                      </div>
                    }
                  >
                    {item.name}
                  </SimpleCell>
                ))}
              </div>
            )}
          </div>
        ))}
      </Group>
    </>
  );
}
