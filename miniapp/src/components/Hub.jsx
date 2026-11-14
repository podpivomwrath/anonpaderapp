import {
  Suspense, lazy, useCallback, useEffect, useRef, useState,
} from 'react';
import bridge from '@vkontakte/vk-bridge';
import XpEmblem from './XpEmblem.jsx';
import AshLayer from './AshLayer.jsx';
import NewPlayer from './NewPlayer.jsx';
import TabHint from './TabHint.jsx';
import { TAB_HINTS } from './tabHints.js';
import { GenderGate } from './HeroTab.jsx';
import { guideSteps } from './guide.js';
import { pushBack, setDragScreen, useBackClose } from '../backStack.js';
import { playTab, preloadTab, setSoundEnabled, unlock } from '../sound.js';
import CountUp from './CountUp.jsx';
import CrownPicker from './CrownPicker.jsx';
import TitlePicker from './TitlePicker.jsx';
import {
  Panel, PanelHeader, PanelHeaderButton, Placeholder, Spinner, Div, Button,
} from '@vkontakte/vkui';
import { acceptTerms, clearCache, getCharacter, saveUi } from '../api.js';
import NavIcon from './NavIcon.jsx';
import CharacterTab from './CharacterTab.jsx';
import DailiesTab from './DailiesTab.jsx';
import InventoryTab from './InventoryTab.jsx';
import Skeleton from './Skeleton.jsx';

// Разделы, которые открывают не каждый раз, грузятся отдельно при первом
// открытии (2026-10-21): основной файл мини-аппа был больше 500 КБ, и на
// телефоне в слабой сети персонаж открывался долго.
const AdminTab = lazy(() => import('./AdminTab.jsx'));
const CraftTab = lazy(() => import('./CraftTab.jsx'));
const MarketTab = lazy(() => import('./MarketTab.jsx'));
const ShopTab = lazy(() => import('./ShopTab.jsx'));
const FactionTab = lazy(() => import('./FactionTab.jsx'));
const GuildTab = lazy(() => import('./GuildTab.jsx'));
const MapTab = lazy(() => import('./MapTab.jsx'));
const TopsTab = lazy(() => import('./TopsTab.jsx'));
const BoardTab = lazy(() => import('./BoardTab.jsx'));
// Путеводитель (2026-10-23): свой раздел, не в меню - открывается книгой в шапке.
const HandbookTab = lazy(() => import('./HandbookTab.jsx'));
// Настройки (2026-11-12): тоже не в меню - шестерёнкой в шапке.
const SettingsTab = lazy(() => import('./SettingsTab.jsx'));
// Вступление, тур и полный гайд нужны раз в жизни - отдельными файлами
// (2026-11-12), основной файл мини-аппа от них легче.
const IntroScene = lazy(() => import('./IntroScene.jsx'));
const Tour = lazy(() => import('./Tour.jsx'));
const Spotlight = lazy(() => import('./Spotlight.jsx'));

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
//
// 2026-11-12 (владелец): под каждым пунктом - что внутри. «Ремесла» у
// персонажа путали с «Мастерской», а «Фракция» открывалась торговлей.
const SECTIONS = [
  { id: 'character', label: 'Персонаж', hint: 'снаряжение, руны, характеристики, уровни ремёсел' },
  { id: 'dailies', label: 'Задания', hint: 'сюжет, ежедневные, награда за вход' },
  { id: 'inventory', label: 'Инвентарь', hint: 'вещи, зелья, ларцы' },
  { id: 'craft', label: 'Мастерская', hint: 'ковка, улучшение и заточка вещей' },
  { id: 'map', label: 'Карта', hint: 'мир, маунты, разломы' },
  { id: 'guild', label: 'Гильдия', hint: 'состав, казна, земли' },
  { id: 'tops', label: 'Топы', hint: 'рейтинги игроков' },
  { id: 'board', label: 'Доска', hint: 'клеймёные убийцы, заказы, сезон PvP' },
  { id: 'trade', label: 'Фракция', hint: 'торговые повозки и фракции городов' },
  // Рынок (2026-10-23): заявки, витрина и биржа - вкладками внутри.
  { id: 'market', label: 'Рынок', hint: 'заявки, витрина, биржа' },
  { id: 'shop', label: 'Магазин', hint: 'самоцветы, Метка и Клеймо' },
];

// Разделы не из меню: открываются значками в шапке.
const EXTRA_TABS = ['handbook', 'settings'];

// Раздел, на котором вышли (2026-11-12, жалоба игрока): VK то держит мини-апп
// в памяти, то открывает заново - и после выхода с карты попадали то на карту,
// то на персонажа. Раздел помнит браузер (localStorage) - бот и сервер ни при
// чём. Админку не восстанавливаем: до загрузки персонажа она недоступна.
const TAB_KEY = 'pines:tab';

function savedTab() {
  try {
    const id = window.localStorage.getItem(TAB_KEY);
    return SECTIONS.some((s) => s.id === id) || EXTRA_TABS.includes(id) ? id : 'character';
  } catch {
    return 'character';
  }
}

const GUILD_MIN_LEVEL = 20;

// Вступление показывается, пока ui.intro меньше этой версии: поднять число -
// и все увидят его снова (так оно и показано всем после обновления).
const INTRO_VERSION = 1;

/** Лёгкий отклик телефона на смену раздела. Вне ВК - молча ничего. */
function haptic() {
  bridge.send('VKWebAppTapticImpactOccurred', { style: 'light' }).catch(() => {});
}

/** Числа с разрядами: без них четырёхзначное золото читается как каша. */
function money(value) {
  return Number(value ?? 0).toLocaleString('ru-RU');
}


export default function Hub() {
  const [activeTab, setActiveTab] = useState(savedTab);
  const [menuOpen, setMenuOpen] = useState(false);
  const [crownOpen, setCrownOpen] = useState(false);
  const [titleOpen, setTitleOpen] = useState(false);
  const [character, setCharacter] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error | newbie
  // Персонажа нет (или создание брошено): страница новичка, а не ошибка.
  const [newbie, setNewbie] = useState({ inCreation: false, checking: false });
  const [ban, setBan] = useState(null);
  // Пользовательское соглашение (2026-10-15): без согласия - только окно
  // с документами и кнопкой «Принимаю», остальное недоступно.
  const [terms, setTerms] = useState(null);
  const [termsBusy, setTermsBusy] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  // Мини-апп: что уже видел (вступление, тур, подсказки) и звук - с сервера.
  const [ui, setUi] = useState(null);
  const [soundOn, setSoundOn] = useState(true);

  const persistUi = useCallback((body) => {
    saveUi(body).then((res) => res?.ui && setUi(res.ui)).catch(() => {});
  }, []);

  // Шторка уезжает, а не пропадает: сначала класс закрытия, потом снятие.
  const [menuClosing, setMenuClosing] = useState(false);
  const closeTimer = useRef(0);
  const closeMenu = useCallback(() => {
    setMenuClosing(true);
    clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => {
      setMenuOpen(false);
      setMenuClosing(false);
    }, 180);
  }, []);
  useBackClose(closeMenu, menuOpen && !menuClosing);
  const toggleMenu = () => {
    if (menuOpen && !menuClosing) closeMenu();
    else {
      clearTimeout(closeTimer.current);
      setMenuClosing(false);
      setMenuOpen(true);
      preloadTab();
    }
  };

  // «?» в шапке - полный гайд: сам ходит по разделам, подсвечивает и
  // объясняет. {from, steps}; по окончании - обратно в раздел, откуда начали.
  const [guide, setGuide] = useState(null);
  // «?» (2026-10-22): сначала короткие озвученные подсказки раздела, из них
  // «Подробнее» ведёт в полный гайд без озвучки.
  const [quickHelp, setQuickHelp] = useState(null);
  // Клетка, которую карта покажет при открытии (цель задания); после
  // ухода с карты сбрасывается.
  const [mapFocus, setMapFocus] = useState(null);

  // Раздел въезжает с той стороны, где он стоит в меню: ниже по списку -
  // справа, выше - слева. Так переход читается как движение по меню.
  const [direction, setDirection] = useState('fwd');
  const activeRef = useRef(activeTab);
  useEffect(() => {
    activeRef.current = activeTab;
    if (activeTab !== 'map') setMapFocus(null);
  }, [activeTab]);
  const openTab = useCallback((id) => {
    const prev = activeRef.current;
    if (prev !== id) {
      playTab();
      haptic();
      const order = [...SECTIONS.map((s) => s.id), 'admin', ...EXTRA_TABS];
      setDirection(order.indexOf(id) < order.indexOf(prev) ? 'back' : 'fwd');
      // «Назад» телефона возвращает в прошлый раздел (2026-11-12).
      pushBack(() => {
        setDirection('back');
        activeRef.current = prev;
        setActiveTab(prev);
      });
    }
    setActiveTab(id);
    closeMenu();
  }, [closeMenu]);

  // Плашка «нет связи» (2026-11-12): запросы теперь ждут не дольше 15 секунд.
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const down = () => setOffline(true);
    const up = () => setOffline(false);
    window.addEventListener('net-down', down);
    window.addEventListener('net-up', up);
    return () => {
      window.removeEventListener('net-down', down);
      window.removeEventListener('net-up', up);
    };
  }, []);

  useEffect(() => {
    const onBan = (event) => setBan(event.detail);
    window.addEventListener('account-banned', onBan);
    const onTerms = (event) => setTerms(event.detail);
    window.addEventListener('terms-required', onTerms);
    return () => {
      window.removeEventListener('account-banned', onBan);
      window.removeEventListener('terms-required', onTerms);
    };
  }, []);

  // Новый уровень - волна света по шапке. Только при росте уровня за время
  // открытого мини-аппа: при загрузке сравнивать не с чем.
  const [levelUp, setLevelUp] = useState(false);
  const [levelBursts, setLevelBursts] = useState(0);
  const lastLevel = useRef(null);
  const level = character?.level;
  useEffect(() => {
    if (level == null) return undefined;
    const before = lastLevel.current;
    lastLevel.current = level;
    if (before == null || level <= before) return undefined;
    setLevelUp(true);
    setLevelBursts((n) => n + 1);
    const timer = setTimeout(() => setLevelUp(false), 1800);
    return () => clearTimeout(timer);
  }, [level]);

  // Фон живёт вне хаба (BackgroundScene) и должен знать, какой экран открыт.
  useEffect(() => {
    document.body.dataset.view = activeTab;
    // На карте и в гильдии (древо) палец таскает картинку - свайп «назад»
    // айфона там не включаем.
    setDragScreen(activeTab === 'map' || activeTab === 'guild');
    try {
      window.localStorage.setItem(TAB_KEY, activeTab);
    } catch {
      // хранилище закрыто (приватный режим) - откроется «Персонаж», как раньше
    }
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
      .catch((err) => {
        if (err?.message === 'character_not_found') {
          setNewbie((prev) => ({
            inCreation: Boolean(err.details?.in_creation), checking: false, stillMissing: prev.checking,
          }));
          setStatus('newbie');
          return;
        }
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
    clearCache();
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
  // Облик (пол) выбирают сразу после вступления, до тура и подсказок
  // (2026-10-22): иначе подсказки «Героя» показывали на пустой экран выбора.
  const showGender = Boolean(ui) && !showIntro && Boolean(character) && !character.gender;
  const showTour = Boolean(ui) && !showIntro && !showGender && !ui.tour;
  const firstVisit = TAB_HINTS[activeTab] && !(ui?.hints || []).includes(activeTab);
  const showHint = Boolean(ui) && !showIntro && !showGender && !showTour && !guide && !quickHelp && firstVisit;
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

  // Гильдии - с 20 уровня; кто уже в гильдии, видит вкладку всегда. До 20
  // (2026-11-12) пункт в меню есть, но закрыт - с подписью, с какого уровня.
  const guildOpen = character && (character.level >= GUILD_MIN_LEVEL || character.in_guild);
  const sections = character?.is_admin
    ? [...SECTIONS, { id: 'admin', label: 'Админ' }]
    : SECTIONS;
  const locked = (id) => (id === 'guild' && !guildOpen ? `с ${GUILD_MIN_LEVEL} уровня` : null);
  // Отметки в меню (2026-11-12): очки характеристик и несделанные задания.
  const badges = {
    character: character?.unspent_points > 0 ? `+${character.unspent_points}` : null,
    dailies: character?.dailies_left > 0 ? String(character.dailies_left) : null,
    // 2026-11-14: в сумке вещь сильнее надетой - как ▲ на окне слота у «Героя».
    inventory: character?.better_items > 0 ? '▲' : null,
  };
  const current = activeTab === 'handbook'
    ? { id: 'handbook', label: 'Путеводитель' }
    : activeTab === 'settings'
      ? { id: 'settings', label: 'Настройки' }
      : sections.find((s) => s.id === activeTab) || sections[0];

  // Гайд переключает разделы молча (без звука и вибрации) и заодно
  // засчитывает короткие подсказки этих разделов - он их уже объяснил.
  const guideNavigate = (tab) => {
    const prev = activeRef.current;
    if (prev === tab) return;
    const order = [...SECTIONS.map((s) => s.id), 'admin', ...EXTRA_TABS];
    setDirection(order.indexOf(tab) < order.indexOf(prev) ? 'back' : 'fwd');
    activeRef.current = tab;
    setActiveTab(tab);
    if (TAB_HINTS[tab] && !(ui?.hints || []).includes(tab)) hintSeen(tab);
  };
  const startGuide = () => {
    if (menuOpen) closeMenu();
    setQuickHelp(null);
    setGuide({
      from: activeRef.current,
      started: Date.now(),
      steps: (() => {
        const steps = guideSteps(activeRef.current, {
          inGuild: character?.in_guild,
          hasPath: Boolean(character?.subclass || character?.subclass_declined),
        });
        return steps.length ? steps : [{ target: null, title: 'Гайд', text: 'Для этого раздела гайда пока нет.' }];
      })(),
    });
  };
  const startHelp = () => {
    if (menuOpen) closeMenu();
    const tab = activeRef.current;
    if (!TAB_HINTS[tab]) {
      startGuide();
      return;
    }
    setQuickHelp({ tab, started: Date.now() });
  };
  const endHelp = () => {
    const tab = quickHelp?.tab;
    setQuickHelp(null);
    if (tab && !(ui?.hints || []).includes(tab)) hintSeen(tab);
  };
  const endGuide = () => {
    const from = guide?.from;
    setGuide(null);
    if (from) guideNavigate(from);
  };

  // Бургер слева, «обновить» рядом с заголовком: справа шапку перекрывают
  // крестик ВК и меню приложения - на телефоне туда просто не попасть.
  const header = (title) => (
    <PanelHeader
      before={
        <span data-tour="menu">
          <PanelHeaderButton aria-label="Разделы" onClick={toggleMenu}>
            <span aria-hidden="true" className="menu-glyph" key={menuOpen && !menuClosing ? 'x' : 'm'}>
              <NavIcon id={menuOpen && !menuClosing ? 'close' : 'menu'} className="hub-icon" />
            </span>
          </PanelHeaderButton>
        </span>
      }
    >
      <span className="hub-brand" aria-hidden="true">Монолит</span>
      <span className="hub-header">
        {title}
        <span className="hub-tools" data-tour="tools">
        <PanelHeaderButton aria-label="Обновить" disabled={refreshing} onClick={refresh}>
          {refreshing ? <Spinner size="s" /> : <NavIcon id="refresh" className="hub-icon" />}
        </PanelHeaderButton>
        {/* На узком экране правый угол шапки закрыт кнопками ВК - «?» здесь. */}
        <span className="help-btn help-btn--inline" data-tour="help">
          <PanelHeaderButton aria-label="Гайд по мини-аппу" title="Гайд по мини-аппу" onClick={() => startHelp()}>
            <NavIcon id="help" className="hub-icon" />
          </PanelHeaderButton>
        </span>
        <PanelHeaderButton
          aria-label="Путеводитель"
          title="Путеводитель Меченого"
          onClick={() => openTab('handbook')}
        >
          <NavIcon id="guide" className="hub-icon" />
        </PanelHeaderButton>
        <PanelHeaderButton
          aria-label="Настройки"
          title="Настройки: звук, сообщения бота, чат игроков"
          onClick={() => openTab('settings')}
        >
          <NavIcon id="settings" className="hub-icon" />
        </PanelHeaderButton>
        </span>
      </span>
      {/* «?» в правом углу на высоте «Монолита» - где угол свободен. */}
      <span className="help-btn help-btn--corner" data-tour="help">
        <PanelHeaderButton aria-label="Гайд по мини-аппу" title="Гайд по мини-аппу" onClick={() => startHelp()}>
          <NavIcon id="help" className="hub-icon" />
        </PanelHeaderButton>
      </span>
    </PanelHeader>
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!SECTIONS.some((s) => s.id === activeTab) && !EXTRA_TABS.includes(activeTab)
      && !(activeTab === 'admin' && character?.is_admin)) {
      setActiveTab('character');
    }
  }, [activeTab, character?.is_admin]);

  // Запомнили «Гильдию», а из гильдии с тех пор вышли (и уровень ниже 20) -
  // вкладки в меню нет, открываем «Персонажа».
  useEffect(() => {
    if (character && !guildOpen && activeTab === 'guild') setActiveTab('character');
  }, [character, guildOpen, activeTab]);

  if (terms) {
    const accept = async () => {
      setTermsBusy(true);
      try {
        await acceptTerms();
        setTerms(null);
        load();
      } finally {
        setTermsBusy(false);
      }
    };
    return <Panel disableBackground>{header('Монолит')}<Placeholder
      action={<Button size="l" loading={termsBusy} onClick={accept}>✅ Принимаю</Button>}
    >
      <b>📜 Прежде чем продолжить</b>
      <p>Нажимая «Принимаю», вы подтверждаете, что вам исполнилось 18 лет, и принимаете условия игры:</p>
      {(terms.docs || []).map((d) => (
        <p key={d.url}><a href={d.url} target="_blank" rel="noopener noreferrer">{d.title}</a></p>
      ))}
      <p>Без согласия играть нельзя.</p>
    </Placeholder></Panel>;
  }

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

  if (status === 'newbie') {
    return (
      <NewPlayer
        inCreation={newbie.inCreation}
        checking={newbie.checking}
        stillMissing={newbie.stillMissing}
        onRetry={() => {
          setNewbie((prev) => ({ ...prev, checking: true }));
          load({ silent: true });
        }}
      />
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
          Не удалось открыть хаб персонажа. Проверьте, что мини-апп открыт из ВКонтакте.
        </Placeholder>
      </Panel>
    );
  }

  return (
    <Panel disableBackground>
      {header(current.label)}

      {menuOpen && (
        <div className={menuClosing ? 'nav-layer nav-layer--closing' : 'nav-layer'}>
          <div className="nav-scrim" onClick={closeMenu} aria-hidden="true" />
          <nav className="nav-drawer" aria-label="Разделы">
            {sections.map((section, index) => {
              const lock = locked(section.id);
              const badge = badges[section.id];
              return (
                <button
                  type="button"
                  key={section.id}
                  style={{ '--i': index }}
                  disabled={Boolean(lock)}
                  className={[
                    'nav-drawer__item',
                    section.id === activeTab && 'nav-drawer__item--active',
                    lock && 'nav-drawer__item--locked',
                  ].filter(Boolean).join(' ')}
                  onClick={() => openTab(section.id)}
                >
                  <NavIcon id={section.id} />
                  <span className="nav-drawer__label">
                    {section.label}
                    {(lock || section.hint) && <small className="nav-drawer__hint">{lock ? `🔒 ${lock}` : section.hint}</small>}
                  </span>
                  {badge && !lock && <span className="nav-drawer__badge">{badge}</span>}
                </button>
              );
            })}
          </nav>
        </div>
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
      {offline && (
        <p className="net-banner" role="status">Нет связи с сервером. Проверьте интернет - мини-апп повторит запрос сам.</p>
      )}

      {/* 2026-11-12 (владелец): полная шапка - только на «Персонаже», на
          остальных разделах узкая строка (имя, золото, самоцветы): она
          занимала пятую часть экрана в каждом разделе. */}
      {activeTab !== 'map' && (
      <div
        className={['hub-banner', levelUp && 'hub-banner--levelup', activeTab !== 'character' && 'hub-banner--slim']
          .filter(Boolean).join(' ')}
        data-tour="banner"
      >
        {/* Пепел за шапкой (2026-10-22). На слабом устройстве - нет. */}
        {!document.body.classList.contains('lite') && (
          <AshLayer className="hub-banner__ash" density={4} ember={0.3} />
        )}
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
            <XpEmblem character={character} burst={levelBursts} />
          </button>
        ) : (
          <XpEmblem character={character} burst={levelBursts} />
        )}
        <div className="hub-banner__text">
        <p className="hub-banner__name">
          {character.badge && <span className="hub-banner__badge">{character.badge} </span>}
          {character.name}
          {activeTab !== 'character' ? null : (<>
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
          </>)}
        </p>
        {activeTab === 'character' && (
          <p className="hub-banner__meta">
            {character.base_class_title}
            {character.subclass_title ? ` · ${character.subclass_title}` : ''} · {character.region_title}
          </p>
        )}
        {character.farm_currency !== null && (
          <p className="hub-banner__meta">
            {/* Патч 74: разряды и без подписей. Подписи занимали половину
                строки, а «Золото»/«Самоцветы» и так читаются по значку. */}
            💰 <CountUp value={character.farm_currency} format={money} /> · 💎{' '}
            <CountUp value={character.donate_currency} format={money} />
          </p>
        )}
        </div>
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
        {/* Раздел появляется плавно: ключ по разделу перезапускает анимацию. */}
        <div key={activeTab} className={`tab-enter tab-enter--${direction}`}>
        <Suspense fallback={<Skeleton />}>
        {activeTab === 'character' && (
          <CharacterTab character={character} onCharacterUpdate={setCharacter} />
        )}
        {activeTab === 'dailies' && (
          <DailiesTab onShowOnMap={(cell) => { setMapFocus(cell); openTab('map'); }} />
        )}
        {activeTab === 'inventory' && <InventoryTab onOpenTab={openTab} />}
        {activeTab === 'craft' && <CraftTab />}
        {activeTab === 'map' && <MapTab focus={mapFocus} />}
        {activeTab === 'tops' && <TopsTab />}
        {activeTab === 'board' && <BoardTab />}
        {activeTab === 'guild' && <GuildTab />}
        {activeTab === 'trade' && (
          <FactionTab onWallet={(w) => setCharacter((prev) => ({ ...prev, ...w }))} />
        )}
        {activeTab === 'market' && (
          <MarketTab onWallet={(w) => setCharacter((prev) => ({ ...prev, ...w }))} />
        )}
        {activeTab === 'shop' && (
          <ShopTab
            onWallet={(w) => setCharacter((prev) => ({ ...prev, ...w }))}
            onBought={() => load({ silent: true })}
          />
        )}
        {activeTab === 'admin' && character.is_admin && <AdminTab />}
        {activeTab === 'handbook' && <HandbookTab />}
        {activeTab === 'settings' && (
          <SettingsTab
            character={character} onCharacterUpdate={setCharacter}
            soundOn={soundOn} onToggleSound={toggleSound}
          />
        )}
        </Suspense>
        </div>
      </div>

      <Suspense fallback={null}>
      {showIntro && <IntroScene onDone={finishIntro} />}
      {showGender && <GenderGate character={character} onCharacterUpdate={setCharacter} />}
      {showTour && <Tour onDone={finishTour} />}
      {showHint && (
        <TabHint
          tab={activeTab}
          onClose={() => hintSeen(activeTab)}
          onMore={() => { hintSeen(activeTab); startGuide(); }}
        />
      )}
      {quickHelp && (
        <TabHint
          key={quickHelp.started}
          tab={quickHelp.tab}
          onClose={endHelp}
          onMore={() => { endHelp(); startGuide(); }}
        />
      )}
      {guide && (
        <Spotlight
          key={guide.started}
          steps={guide.steps}
          onNavigate={guideNavigate}
          onDone={endGuide}
          label="Гайд по мини-аппу"
        />
      )}
      </Suspense>
    </Panel>
  );
}
