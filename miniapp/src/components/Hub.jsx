import { useCallback, useEffect, useState } from 'react';
import {
  Panel, PanelHeader, PanelHeaderButton, Tabbar, TabbarItem,
  Placeholder, Spinner, Div, Button,
} from '@vkontakte/vkui';
import { getCharacter } from '../api.js';
import AdminTab from './AdminTab.jsx';
import CharacterTab from './CharacterTab.jsx';
import DailiesTab from './DailiesTab.jsx';
import InventoryTab from './InventoryTab.jsx';
import MapTab from './MapTab.jsx';
import StubTab from './StubTab.jsx';

// Патч 14, ч.1: было 5 вкладок (Характеристики/Инвентарь/Пресеты/Испытания/
// Биржа) - Характеристики+Пресеты+Испытания объединены в «Персонаж».
// Патч 23: + «Задания» (сюжет/ежедневки/вход). Патч 29: + «Карта».
// Патч 27: + «Админ» - добавляется в TABS условно, только когда
// character.is_admin (сервер уже подтвердил права); это ТОЛЬКО видимость,
// реальная защита - на каждом /api/miniapp/admin/* эндпоинте отдельно.
const TABS = [
  { id: 'character', label: 'Персонаж', icon: '🎭' },
  { id: 'dailies', label: 'Задания', icon: '📜' },
  { id: 'inventory', label: 'Инвентарь', icon: '🎒' },
  { id: 'map', label: 'Карта', icon: '🗺️' },
  { id: 'exchange', label: 'Биржа', icon: '💱' },
];

export default function Hub() {
  const [activeTab, setActiveTab] = useState('character');
  const [character, setCharacter] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [ban, setBan] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const onBan = (event) => setBan(event.detail);
    window.addEventListener('account-banned', onBan);
    return () => window.removeEventListener('account-banned', onBan);
  }, []);

  // silent=true - обновление на месте: экран не гасим и спиннер вместо всего
  // хаба не показываем, иначе кнопка «обновить» каждый раз мигала бы пустотой.
  const load = useCallback((options = {}) => {
    const silent = options.silent === true;
    if (!silent) setStatus('loading');
    setBan(null);
    return getCharacter()
      .then((data) => {
        setCharacter(data);
        setStatus('ready');
      })
      .catch(() => {
        if (!silent) setStatus('error');
      });
  }, []);

  // Вкладки грузят свои данные сами при монтировании, поэтому обновление
  // карточки персонажа их не тронуло бы. Смена ключа перемонтирует активную
  // вкладку - и она перечитает своё.
  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await load({ silent: true });
      setReloadKey((key) => key + 1);
    } finally {
      setRefreshing(false);
    }
  }, [load]);

  const refreshButton = (
    <PanelHeaderButton aria-label="Обновить" disabled={refreshing} onClick={refresh}>
      {refreshing ? <Spinner size="s" /> : <span aria-hidden="true">🔄</span>}
    </PanelHeaderButton>
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!TABS.some((tab) => tab.id === activeTab) && !(activeTab === 'admin' && character?.is_admin)) {
      setActiveTab('character');
    }
  }, [activeTab, character?.is_admin]);

  if (ban) {
    return <Panel><PanelHeader after={refreshButton}>Монолит</PanelHeader><Placeholder
      action={<Button onClick={() => load()}>Проверить доступ</Button>}
    >
      Доступ заблокирован администратором.
      {ban.reason && <p>Причина: {ban.reason}</p>}
      <p>{ban.until ? `До: ${new Date(ban.until).toLocaleString('ru-RU')}` : 'Срок: бессрочно'}</p>
    </Placeholder></Panel>;
  }

  if (status === 'loading') {
    return (
      <Panel>
        <PanelHeader after={refreshButton}>Монолит</PanelHeader>
        <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
          <Spinner size="l" />
        </Div>
      </Panel>
    );
  }

  if (status === 'error' || !character) {
    return (
      <Panel>
        <PanelHeader after={refreshButton}>Монолит</PanelHeader>
        <Placeholder
          icon={<div style={{ fontSize: 48 }}>🩸</div>}
          action={
            <Button size="m" mode="secondary" onClick={() => load()}>
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
      <PanelHeader after={refreshButton}>Персонаж</PanelHeader>
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

      <div className="hub-content" key={reloadKey}>
        {activeTab === 'character' && (
          <CharacterTab character={character} onCharacterUpdate={setCharacter} />
        )}
        {activeTab === 'dailies' && <DailiesTab />}
        {activeTab === 'inventory' && <InventoryTab onCharacterUpdate={setCharacter} />}
        {activeTab === 'map' && <MapTab />}
        {activeTab === 'exchange' && (
          <StubTab text="Торговцы душами ещё не открыли лавку. Скоро." />
        )}
        {activeTab === 'admin' && character.is_admin && <AdminTab />}
      </div>

      <Tabbar>
        {(character.is_admin ? [...TABS, { id: 'admin', label: 'Админ', icon: '🛡️' }] : TABS).map((tab) => (
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
