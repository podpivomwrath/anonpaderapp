import { useCallback, useEffect, useRef, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';
import ClassIcon from './ClassIcon.jsx';
import IntroScene from './IntroScene.jsx';
import TabHint, { TAB_HINTS } from './TabHint.jsx';
import Tour from './Tour.jsx';
import { playTab, setSoundEnabled, unlock } from '../sound.js';
import CrownPicker from './CrownPicker.jsx';
import TitlePicker from './TitlePicker.jsx';
import {
  Panel, PanelHeader, PanelHeaderButton, Placeholder, Spinner, Div, Button,
} from '@vkontakte/vkui';
import { getCharacter, saveUi } from '../api.js';
import NavIcon from './NavIcon.jsx';
import AdminTab from './AdminTab.jsx';
import CharacterTab from './CharacterTab.jsx';
import CraftTab from './CraftTab.jsx';
import DailiesTab from './DailiesTab.jsx';
import ExchangeTab from './ExchangeTab.jsx';
import TradeTab from './TradeTab.jsx';
import GuildTab from './GuildTab.jsx';
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
  { id: 'guild', label: 'Гильдия' },
  { id: 'tops', label: 'Топы' },
  { id: 'trade', label: 'Торговля' },
  { id: 'exchange', label: 'Биржа' },
];

// Общий справочник по игре - статья в группе. Ссылка наружу, а не раздел:
// текст правится в редакторе статей VK без пересборки мини-аппа.
const GUIDE_URL = 'https://vk.com/@-240167847-putevoditel-mechenogo';

const GUILD_MIN_LEVEL = 20;

// Вступление показывается, пока ui.intro меньше этой версии: поднять число -
// и все увидят его снова (так оно и показано всем после обновления).
const INTRO_VERSION = 1;

/** Лёгкий отклик телефона на смену раздела. Вне ВК - молча ничего. */
function haptic() {
  bridge.send('VKWebAppTapticImpactOccurred', { style: 'light' }).catch(() => {});
}

/** Из чего сложилась Мощь - подсказка к числу в шапке. */
function powerHint(parts) {
  if (!parts) return 'Мощь';
  const bonuses = [];
  if (parts.subclass_pct) bonuses.push(`подкласс +${parts.subclass_pct}%`);
  if (parts.buffs) bonuses.push(`микробаффы ${parts.buffs} × ${parts.buff_pct}%`);
  return `Статы ${parts.stats} + вещи ${parts.gear}` + (bonuses.length ? `, ${bonuses.join(', ')}` : '');
}

/** Числа с разрядами: без них четырёхзначное золото читается как каша. */
function money(value) {
  return Number(value ?? 0).toLocaleString('ru-RU');
}


export default function Hub() {
  const [activeTab, setActiveTab] = useState('character');
  const [menuOpen, setMenuOpen] = useState(false);
  const [crownOpen, setCrownOpen] = useState(false);
  const [titleOpen, setTitleOpen] = useState(false);
  const [character, setCharacter] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [ban, setBan] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  // Мини-апп: что уже видел (вступление, тур, подсказки) и звук - с сервера.
  const [ui, setUi] = useState(null);
  const [soundOn, setSoundOn] = useState(true);

  const persistUi = useCallback((body) => {
    saveUi(body).then((res) => res?.ui && setUi(res.ui)).catch(() => {});
  }, []);

  const activeRef = useRef(activeTab);
  useEffect(() => { activeRef.current = activeTab; }, [activeTab]);
  const openTab = useCallback((id) => {
    if (activeRef.current !== id) {
      playTab(id);
      haptic();
    }
    setActiveTab(id);
    setMenuOpen(false);
  }, []);

  useEffect(() => {
    const onBan = (event) => setBan(event.detail);
    window.addEventListener('account-banned', onBan);
    return () => window.removeEventListener('account-banned', onBan);
  }, []);

  // Фон живёт вне хаба (BackgroundScene) и должен знать, какой экран открыт.
  useEffect(() => {
    document.body.dataset.view = activeTab;
  }, [activeTab]);

  // Патч 72: из инвентаря можно прыгнуть сразу в мастерскую - событие вместо
  // проброса колбэка через три слоя. Раздел один, слушатель один.
  useEffect(() => {
    const open = () => openTab('craft');
    window.addEventListener('open-craft', open);
    return () => window.removeEventListener('open-craft', open);
  }, [openTab]);

  // silent=true - обновление на месте: экран не гасим и спиннер вместо всего
  // хаба не показываем, иначе кнопка «обновить» каждый раз мигала бы пустотой.
  const load = useCallback((options = {}) => {
    const silent = options.silent === true;
    if (!silent) setStatus('loading');
    setBan(null);
    return getCharacter()
      .then((data) => {
        setCharacter(data);
        setUi((prev) => prev || data.ui || {});
        setStatus('ready');
      })
      .catch(() => {
        if (!silent) setStatus('error');
      });
  }, []);

  // Фон может попросить перечитать персонажа (у него появился титул).
  useEffect(() => {
    const onRefresh = () => load({ silent: true });
    window.addEventListener('character-refresh', onRefresh);
    return () => window.removeEventListener('character-refresh', onRefresh);
  }, [load]);

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

  useEffect(() => {
    if (!ui) return;
    const on = ui.sound !== false;
    setSoundOn(on);
    setSoundEnabled(on);
  }, [ui?.sound]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleSound = () => {
    unlock();
    const on = !soundOn;
    setSoundOn(on);
    setSoundEnabled(on);
    setUi((prev) => ({ ...(prev || {}), sound: on }));
    persistUi({ set: { sound: on } });
  };

  const showIntro = Boolean(ui) && (ui.intro || 0) < INTRO_VERSION;
  const showTour = Boolean(ui) && !showIntro && !ui.tour;
  const finishIntro = (withSound) => {
    unlock();
    setSoundEnabled(withSound);
    setUi((prev) => ({ ...(prev || {}), intro: INTRO_VERSION, sound: withSound }));
    persistUi({ set: { intro: INTRO_VERSION, sound: withSound } });
  };
  const finishTour = () => {
    setUi((prev) => ({ ...(prev || {}), tour: 1 }));
    persistUi({ set: { tour: 1 } });
  };
  const hintSeen = (tab) => {
    setUi((prev) => ({ ...(prev || {}), hints: [...((prev && prev.hints) || []), tab] }));
    persistUi({ hint: tab });
  };

  // Гильдии - с 20 уровня; кто уже в гильдии, видит вкладку всегда.
  const guildOpen = character && (character.level >= GUILD_MIN_LEVEL || character.in_guild);
  const visible = guildOpen ? SECTIONS : SECTIONS.filter((s) => s.id !== 'guild');
  const sections = character?.is_admin
    ? [...visible, { id: 'admin', label: 'Админ' }]
    : visible;
  const current = sections.find((s) => s.id === activeTab) || sections[0];

  // Бургер слева, «обновить» рядом с заголовком: справа шапку перекрывают
  // крестик ВК и меню приложения - на телефоне туда просто не попасть.
  const header = (title) => (
    <PanelHeader
      before={
        <span data-tour="menu">
          <PanelHeaderButton aria-label="Разделы" onClick={() => setMenuOpen((open) => !open)}>
            <span aria-hidden="true" style={{ fontSize: 20 }}>{menuOpen ? '✕' : '☰'}</span>
          </PanelHeaderButton>
        </span>
      }
    >
      <span className="hub-brand" aria-hidden="true">Монолит</span>
      <span className="hub-header">
        {title}
        <span className="hub-tools" data-tour="tools">
        <PanelHeaderButton aria-label="Обновить" disabled={refreshing} onClick={refresh}>
          {refreshing ? <Spinner size="s" /> : <span aria-hidden="true">🔄</span>}
        </PanelHeaderButton>
        <PanelHeaderButton
          aria-label={soundOn ? 'Выключить звук' : 'Включить звук'}
          title={soundOn ? 'Звук включён' : 'Звук выключен'}
          onClick={toggleSound}
        >
          <span aria-hidden="true">{soundOn ? '🔊' : '🔇'}</span>
        </PanelHeaderButton>
        <PanelHeaderButton
          aria-label="Путеводитель"
          title="Путеводитель Меченого"
          href={GUIDE_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          <span aria-hidden="true">📖</span>
        </PanelHeaderButton>
        </span>
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
                onClick={() => openTab(section.id)}
              >
                <NavIcon id={section.id} />
                <span className="nav-drawer__label">{section.label}</span>
              </button>
            ))}
          </nav>
        </>
      )}

      {titleOpen && (
        <TitlePicker
          titles={character.titles || []}
          onChange={(res) => setCharacter((prev) => ({ ...prev, ...res }))}
          onClose={() => setTitleOpen(false)}
        />
      )}

      {crownOpen && (
        <CrownPicker
          menu={character.crown_menu || []}
          current={character.crown_frame || null}
          onChange={(res) => setCharacter((prev) => ({ ...prev, ...res }))}
          onClose={() => setCrownOpen(false)}
        />
      )}

      {/* Карта - на всю площадь страницы: карточка персонажа там только
          отнимала бы место у мира. */}
      {activeTab !== 'map' && (
      <div className="hub-banner" data-tour="banner">
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
          {/* Титул - кнопка, когда есть из чего выбирать (как эмблема венца).
              Без активного титула, но с открытыми - тусклая подсказка, иначе
              снятый титул нечем было бы вернуть. */}
          {character.titles?.length ? (
            <>
              {' '}
              <button
                type="button"
                className={`hub-banner__title title-tier title-tier--${character.title ? character.title_tier : 'none'}`}
                onClick={() => setTitleOpen(true)}
              >
                {character.title ? `«${character.title}»` : '«без титула»'}
              </button>
            </>
          ) : character.title ? ` «${character.title}»` : ''}
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
        {/* Патч 111: Мощь - одно число силы персонажа. Состав - в подсказке:
            формула на сервере (power_service), здесь только её части. */}
        {character.power != null && (
          <div className="hub-banner__power" title={powerHint(character.power_parts)}>
            <span className="hub-banner__power-label">Мощь</span>
            <span className="hub-banner__power-value">{money(character.power)}</span>
          </div>
        )}
      </div>
      )}

      {/* Карте ширина нужна вся: она рисует сетку мира, и в узкой колонке
          видно несколько клеток вместо области вокруг игрока. Остальные
          разделы - списки, им 560 в самый раз. */}
      <div
        className={
          activeTab === 'map'
            ? 'hub-content hub-content--drawer hub-content--wide'
            : activeTab === 'tops'
              ? 'hub-content hub-content--drawer hub-content--tops'
              : 'hub-content hub-content--drawer'
        }
        key={reloadKey}
      >
        {!showIntro && !showTour && TAB_HINTS[activeTab] && !(ui?.hints || []).includes(activeTab) && (
          <TabHint tab={activeTab} onClose={() => hintSeen(activeTab)} />
        )}
        {/* Раздел появляется плавно: ключ по разделу перезапускает анимацию. */}
        <div key={activeTab} className="tab-enter">
        {activeTab === 'character' && (
          <CharacterTab character={character} onCharacterUpdate={setCharacter} />
        )}
        {activeTab === 'dailies' && <DailiesTab />}
        {activeTab === 'inventory' && <InventoryTab onCharacterUpdate={setCharacter} />}
        {activeTab === 'craft' && <CraftTab />}
        {activeTab === 'map' && <MapTab />}
        {activeTab === 'tops' && <TopsTab />}
        {activeTab === 'guild' && <GuildTab />}
        {activeTab === 'trade' && (
          <TradeTab onWallet={(w) => setCharacter((prev) => ({ ...prev, ...w }))} />
        )}
        {activeTab === 'exchange' && (
          <ExchangeTab onWallet={(w) => setCharacter((prev) => ({ ...prev, ...w }))} />
        )}
        {activeTab === 'admin' && character.is_admin && <AdminTab />}
        </div>
      </div>

      {showIntro && <IntroScene onDone={finishIntro} />}
      {showTour && <Tour onDone={finishTour} />}
    </Panel>
  );
}
