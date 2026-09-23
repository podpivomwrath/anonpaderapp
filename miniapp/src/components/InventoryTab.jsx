import { useEffect, useState } from 'react';
import { Group, Header, Div, Text, Spinner, Placeholder, Button } from '@vkontakte/vkui';
import { getInventory, equipItem, getCharacter } from '../api.js';

const STAT_NAMES = { str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Выносливость', wil: 'Воля' };

function statsLine(baseStats) {
  return Object.entries(baseStats)
    .map(([key, amount]) => `${STAT_NAMES[key] || key} +${amount}`)
    .join(', ');
}

export default function InventoryTab({ onCharacterUpdate }) {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [equippingId, setEquippingId] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);

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

  return (
    <Group header={<Header>Инвентарь ({items.length})</Header>}>
      {errorMsg && (
        <Div>
          <Text style={{ color: '#c81e3a' }}>{errorMsg}</Text>
        </Div>
      )}
      {items.map((item) => (
        <div className="stat-row" key={item.id}>
          <div>
            <div className="stat-row__label">
              {item.rarity_emoji} {item.name}
              {item.equipped ? ' (надето)' : ''}
              {item.craft_efficiency ? ` · ${item.craft_efficiency}%` : ''}
            </div>
            <Text style={{ opacity: 0.7, fontSize: 13 }}>
              {item.slot_title}, ур. {item.ilvl} - {statsLine(item.base_stats)}
            </Text>
          </div>
          <div className="inventory-actions">
            {item.craftable && (
              // Патч 72: вход в мастерскую прямо с карточки - иначе игрок,
              // получивший боссовую вещь, не догадается, что с ней делать.
              <Button
                mode="outline"
                size="s"
                onClick={() => window.dispatchEvent(new CustomEvent('open-craft'))}
              >
                В мастерскую
              </Button>
            )}
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
        </div>
      ))}
    </Group>
  );
}
