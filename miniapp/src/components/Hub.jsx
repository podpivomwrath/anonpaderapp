import { useCallback, useEffect, useState } from 'react';
import ClassIcon from './ClassIcon.jsx';
import CrownPicker from './CrownPicker.jsx';
import {
  Panel, PanelHeader, PanelHeaderButton, Placeholder, Spinner, Div, Button,
} from '@vkontakte/vkui';
import { getCharacter } from '../api.js';
import NavIcon from './NavIcon.jsx';
import AdminTab from './AdminTab.jsx';
import CharacterTab from './CharacterTab.jsx';
import CraftTab from './CraftTab.jsx';
import DailiesTab from './DailiesTab.jsx';
import InventoryTab from './InventoryTab.jsx';
import MapTab from './MapTab.jsx';
import StubTab from './StubTab.jsx';
import TopsTab from './TopsTab.jsx';

// Патч 14, ч.1: было 5 вкладок (Характеристики/Инвентарь/Пресеты/Испытания/
// Биржа) - Характеристики+Пресеты+Испытания объединены в «Персонаж».
// Патч 23: + «Задания». Патч 29: + «Карта». Патч 27: + «Админ» - добавляется
// условно, только когда character.is_admin (сервер уже подтвердил права);
// это ТОЛЬКО видимость, реальная защита - на каждом /api/miniapp/admin/*.
//
// Патч 72: нижний Tabbar заменён шторкой по бургеру. Причина - разделов
// стало больше, чем помещается в ряд на телефоне: седьмая вкладка сжимала
// подписи до нечитаемых. В вертикальном списке места столько, сколько нужно,
// и новый раздел не требует переверстки остальных.
const SECTIONS = [
  { id: 'character', label: 'Персонаж' },
  { id: 'dailies', label: 'Задания' },
  { id: 'inventory', label: 'Инвентарь' },
  { id: 'craft', label: 'Мастерская' },
  { id: 'map', label: 'Карта' },
  { id: 'tops', label: 'Топы' },
  { id: 'exchange', label: 'Биржа' },
];

/** Числа с разрядами: без них четырёхзначное золото читается как каша. */
function money(value) {
  return Number(value ?? 0).toLocaleString('ru-RU');
}


export default function Hub() {
  const [activeTab, setActiveTab] = useState('character');
  const [menuOpen, setMenuOpen] = useState(false);
  const [crownOpen, setCrownOpen] = useState(false);
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

  // Патч 72: из инвентаря можно прыгнуть сразу в мастерскую - событие вместо
  // проброса колбэка через три слоя. Раздел один, слушатель один.
  useEffect(() => {
    const open = () => { setActiveTab('craft'); setMenuOpen(false); };
    window.addEventListener('open-craft', open);
    return () => window.removeEventListener('open-craft', open);
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

  const sections = character?.is_admin
    ? [...SECTIONS, { id: 'admin', label: 'Админ' }]
    : SECTIONS;
  const current = sections.find((s) => s.id === activeTab) || sections[0];

  // Бургер слева, «обновить» рядом с заголовком: справа шапку перекрывают
  // крестик ВК и меню приложения - на телефоне туда просто не попасть.
  const header = (title) => (
    <PanelHeader
      before={
        <PanelHeaderButton aria-label="Разделы" onClick={() => setMenuOpen((open) => !open)}>
          <span aria-hidden="true" style={{ fontSize: 20 }}>{menuOpen ? '✕' : '☰'}</span>
        </PanelHeaderButton>
      }
    >
      <span className="hub-header">
        {title}
        <PanelHeaderButton aria-label="Обновить" disabled={refreshing} onClick={refresh}>
          {refreshing ? <Spinner size="s" /> : <span aria-hidden="true">🔄</span>}
        </PanelHeaderButton>
      </span>
    </PanelHeader>
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!SECTIONS.some((s) => s.id === activeTab) && !(activeTab === 'admin' && character?.is_admin)) {
      setActiveTab('character');
    }
  }, [activeTab, character?.is_admin]);

  if (ban) {
    return <Panel disableBackground>{header('Монолит')}<Placeholder
      action={<Button onClick={() => load()}>Проверить доступ</Button>}
    >
      Доступ заблокирован администратором.
      {ban.reason && <p>Причина: {ban.reason}</p>}
      <p>{ban.until ? `До: ${new Date(ban.until).toLocaleString('ru-RU')}` : 'Срок: бессрочно'}</p>
    </Placeholder></Panel>;
  }

  if (status === 'loading') {
    return (
      <Panel disableBackground>
        {header('Монолит')}
        <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
          <Spinner size="l" />
        </Div>
      </Panel>
    );
  }

  if (status === 'error' || !character) {
    return (
      <Panel disableBackground>
        {header('Монолит')}
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
    <Panel disableBackground>
      {header(current.label)}

      {menuOpen && (
        <>
          <div className="nav-scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />
          <nav className="nav-drawer" aria-label="Разделы">
            {sections.map((section) => (
              <button
                type="button"
                key={section.id}
                className={
                  section.id === activeTab ? 'nav-drawer__item nav-drawer__item--active' : 'nav-drawer__item'
                }
                onClick={() => { setActiveTab(section.id); setMenuOpen(false); }}
              >
                <NavIcon id={section.id} />
                <span className="nav-drawer__label">{section.label}</span>
              </button>
            ))}
          </nav>
        </>
      )}

      {crownOpen && (
        <CrownPicker
          menu={character.crown_menu || []}
          current={character.crown_frame || null}
          onChange={(res) => setCharacter((prev) => ({ ...prev, ...res }))}
          onClose={() => setCrownOpen(false)}
        />
      )}

      <div className="hub-banner">
        {/* Эмблема пути. Стоит у имени, а не у слова «Тёмный мистик»:
            подкласс выбирают один раз и навсегда, и в шапке он часть того,
            КТО ты, а не ещё одна строка характеристик. */}
        {/* Нажатие открывает выбор рамки. Кнопкой эмблема становится только
            при наличии венца: выбирать иначе не из чего, а мнимая кнопка
            хуже её отсутствия. */}
        {character.crown_menu?.length ? (
          <button
            type="button"
            className="hub-banner__emblem"
            onClick={() => setCrownOpen(true)}
            aria-label="Рамка"
          >
            <ClassIcon
              subclass={character.subclass}
              baseClass={character.base_class}
              crown={character.crown_frame || null}
              size={44}
            />
          </button>
        ) : (
          <ClassIcon
            subclass={character.subclass}
            baseClass={character.base_class}
            crown={character.crown_frame || null}
            size={44}
          />
        )}
        <div className="hub-banner__text">
        <p className="hub-banner__name">
          {character.name}
          {character.title ? ` «${character.title}»` : ''}
        </p>
        <p className="hub-banner__meta">
          {character.base_class_title}
          {character.subclass_title ? ` · ${character.subclass_title}` : ''} · {character.region_title} · Ур.{' '}
          {character.level}
        </p>
        {character.farm_currency !== null && (
          <p className="hub-banner__meta">
            {/* Патч 74: разряды и без подписей. Подписи занимали половину
                строки, а «Золото»/«Самоцветы» и так читаются по значку. */}
            💰 {money(character.farm_currency)} · 💎 {money(character.donate_currency)}
          </p>
        )}
        </div>
      </div>

      {/* Карте ширина нужна вся: она рисует сетку мира, и в узкой колонке
          видно несколько клеток вместо области вокруг игрока. Остальные
          разделы - списки, им 560 в самый раз. */}
      <div
        className={
          activeTab === 'map'
            ? 'hub-content hub-content--drawer hub-content--wide'
            : 'hub-content hub-content--drawer'
        }
        key={reloadKey}
      >
        {activeTab === 'character' && (
          <CharacterTab character={character} onCharacterUpdate={setCharacter} />
        )}
        {activeTab === 'dailies' && <DailiesTab />}
        {activeTab === 'inventory' && <InventoryTab onCharacterUpdate={setCharacter} />}
        {activeTab === 'craft' && <CraftTab />}
        {activeTab === 'map' && <MapTab />}
        {activeTab === 'tops' && <TopsTab />}
        {activeTab === 'exchange' && (
          <StubTab text="Торговцы душами ещё не открыли лавку. Скоро." />
        )}
        {activeTab === 'admin' && character.is_admin && <AdminTab />}
      </div>
    </Panel>
  );
}
