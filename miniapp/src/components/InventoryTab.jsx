import { useEffect, useState } from 'react';
import { Group, Header, Div, Text, Spinner, Placeholder, Button } from '@vkontakte/vkui';
import { getInventory, equipItem } from '../api.js';

const STAT_NAMES = { str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Выносливость', wil: 'Воля' };

function statsLine(baseStats) {
  return Object.entries(baseStats)
    .map(([key, amount]) => `${STAT_NAMES[key] || key} +${amount}`)
    .join(', ');
}

export default function InventoryTab() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [equippingId, setEquippingId] = useState(null);

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
    try {
      const res = await equipItem(itemId);
      setItems(res.items);
    } catch (err) {
      setStatus('error');
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

  return (
    <Group header={<Header>Инвентарь ({items.length})</Header>}>
      {items.map((item) => (
        <div className="stat-row" key={item.id}>
          <div>
            <div className="stat-row__label">
              {item.rarity_emoji} {item.name}
              {item.equipped ? ' (надето)' : ''}
            </div>
            <Text style={{ opacity: 0.7, fontSize: 13 }}>
              {item.slot_title}, ур. {item.ilvl} — {statsLine(item.base_stats)}
            </Text>
          </div>
          {!item.equipped && (
            <Button
              mode="secondary"
              size="s"
              loading={equippingId === item.id}
              onClick={() => handleEquip(item.id)}
            >
              Надеть
            </Button>
          )}
        </div>
      ))}
    </Group>
  );
}
