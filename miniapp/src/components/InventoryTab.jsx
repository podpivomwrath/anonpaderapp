import { useEffect, useState } from 'react';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, Spinner, Text,
} from '@vkontakte/vkui';
import { equipItem, getCharacter, getInventory } from '../api.js';

// Патч 74: вместо одного плоского списка - «Надето» отдельно и сумка,
// свёрнутая по слотам. Плоский список рос вместе с дропом и превращался в
// стену одинаковых строк, где надетое терялось среди лишнего.

const STAT_NAMES = {
  str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Выносливость', wil: 'Воля',
};

// Порядок сверху вниз, как надевают. Слоты приходят с сервера уже с
// названиями (slot_title), здесь только очерёдность показа.
const SLOT_ORDER = ['weapon', 'helmet', 'armor', 'legs', 'boots'];

function statsLine(baseStats) {
  return Object.entries(baseStats || {})
    .sort((a, b) => b[1] - a[1])
    .map(([key, amount]) => `${STAT_NAMES[key] || key} +${amount}`)
    .join(', ');
}

function itemSubtitle(item) {
  const parts = [];
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
            after={craftButton(item)}
            subtitle={itemSubtitle(item)}
          >
            {`${item.rarity_emoji} ${item.name}`}
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
                    subtitle={itemSubtitle(item)}
                    after={
                      <div className="inventory-actions">
                        {craftButton(item)}
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
                    {`${item.rarity_emoji} ${item.name}`}
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
