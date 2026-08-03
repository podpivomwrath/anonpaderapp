import { useCallback, useEffect, useState } from 'react';
import { Panel, PanelHeader, Tabbar, TabbarItem, Placeholder, Spinner, Div, Button } from '@vkontakte/vkui';
import { getCharacter } from '../api.js';
import CharacterTab from './CharacterTab.jsx';
import DailiesTab from './DailiesTab.jsx';
import InventoryTab from './InventoryTab.jsx';
import StubTab from './StubTab.jsx';

// Патч 14, ч.1: было 5 вкладок (Характеристики/Инвентарь/Пресеты/Испытания/
// Биржа) — Характеристики+Пресеты+Испытания объединены в «Персонаж».
// Патч 23: + «Задания» (сюжет/ежедневки/вход).
const TABS = [
  { id: 'character', label: 'Персонаж', icon: '🎭' },
  { id: 'dailies', label: 'Задания', icon: '📜' },
  { id: 'inventory', label: 'Инвентарь', icon: '🎒' },
  { id: 'exchange', label: 'Биржа', icon: '💱' },
];

export default function Hub() {
  const [activeTab, setActiveTab] = useState('stats');
  const [character, setCharacter] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error

  const load = useCallback(() => {
    setStatus('loading');
    getCharacter()
      .then((data) => {
        setCharacter(data);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (status === 'loading') {
    return (
      <Panel>
        <PanelHeader>Монолит</PanelHeader>
        <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
          <Spinner size="l" />
        </Div>
      </Panel>
    );
  }

  if (status === 'error' || !character) {
    return (
      <Panel>
        <PanelHeader>Монолит</PanelHeader>
        <Placeholder
          icon={<div style={{ fontSize: 48 }}>🩸</div>}
          action={
            <Button size="m" mode="secondary" onClick={load}>
              Попробовать снова
            </Button>
          }
        >
          Не удалось открыть хаб персонажа. Проверь, что мини-апп открыт из ВКонтакте.
        </Placeholder>
      </Panel>
    );
  }

  return (
    <Panel>
      <PanelHeader>Персонаж</PanelHeader>
      <div className="hub-banner">
        <p className="hub-banner__name">
          {character.name}
          {character.title ? ` «${character.title}»` : ''}
        </p>
        <p className="hub-banner__meta">
          {character.base_class_title}
          {character.subclass ? ` · ${character.subclass}` : ''} · {character.region_title} · Ур.{' '}
          {character.level}
        </p>
        {character.farm_currency !== null && (
          <p className="hub-banner__meta">
            💰 Золото: {character.farm_currency} · 💎 Самоцветы: {character.donate_currency}
          </p>
        )}
      </div>

      <div className="hub-content">
        {activeTab === 'character' && (
          <CharacterTab character={character} onCharacterUpdate={setCharacter} />
        )}
        {activeTab === 'dailies' && <DailiesTab />}
        {activeTab === 'inventory' && <InventoryTab />}
        {activeTab === 'exchange' && (
          <StubTab text="Торговцы душами ещё не открыли лавку. Скоро." />
        )}
      </div>

      <Tabbar>
        {TABS.map((tab) => (
          <TabbarItem
            key={tab.id}
            selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            label={tab.label}
            aria-label={tab.label}
          >
            <span style={{ fontSize: 22 }} aria-hidden="true">
              {tab.icon}
            </span>
          </TabbarItem>
        ))}
      </Tabbar>
    </Panel>
  );
}
