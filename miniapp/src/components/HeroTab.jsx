import { useEffect, useMemo, useState } from 'react';
import { Group, Header } from '@vkontakte/vkui';
import {
  equipItem, getCharacter, getGear, getInventory, getRunes, getTrophies, ringAction, setGender, unequipItem,
} from '../api.js';
import CraftGear from './CraftGear.jsx';
import RunesPage, { RuneRing } from './RunesPage.jsx';
import { silhouetteUrl } from '../silhouettes.js';
import { itemIcon } from '../itemIcons.js';
import ItemIcon from './ItemIcon.jsx';
import Sparks from './Sparks.jsx';
import { Sheet } from './ui.jsx';
import { useBackClose } from '../backStack.js';

// Вкладка «Герой» (2026-10-22): силуэт персонажа, по бокам окна слотов
// (линии от окна к телу владелец убрал - и так понятно). Нажал окно - снизу список вещей из сумки для
// этого слота, с разницей к надетой. Под силуэтом - что дают вещи.
// 2026-11-12 (владелец): список надетого под силуэтом убран - уровень и
// статы вещи подписаны прямо под её окном; полки трофеев больше нет,
// настройки переехали в свой раздел (шестерёнка в шапке).

// Окна: слева оружие (оно у всех 18 силуэтов в руке слева), справа броня
// сверху вниз. y - высота окна в долях кадра силуэта, на уровне своей части
// тела. Кадр у всех картинок общий: tools/silhouette_assets.py выравнивает
// их по капюшону и подошвам.
const SLOTS = [
  { slot: 'weapon', side: 'left', y: 46 },
  { slot: 'helmet', side: 'right', y: 9 },
  { slot: 'armor', side: 'right', y: 31 },
  { slot: 'legs', side: 'right', y: 60 },
  { slot: 'boots', side: 'right', y: 89 },
];

const SLOT_TITLES = {
  weapon: 'Оружие', helmet: 'Шлем', armor: 'Нагрудник', legs: 'Штаны', boots: 'Сапоги',
};

export const STAT_ICONS = { str: '💪', agi: '🏃', int: '🧠', vit: '❤️', wil: '✨' };
const STAT_NAMES = { str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Выносливость', wil: 'Воля' };
const STAT_ORDER = ['str', 'agi', 'int', 'vit', 'wil'];
// Значки сопротивлений - те же, что в «Характеристиках».
const RESIST_CHIPS = [
  ['crit_resist', '🪨', 'Стойкость к крит-урону'],
  ['accuracy', '🎯', 'Меткость'],
  ['dot_resist', '🧪', 'Стойкость к периодическому урону'],
];

// Значки слотов - для пустого окна: подпись словом там была бы лишней.
function SlotGlyph({ slot }) {
  const common = {
    width: 26, height: 26, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
    strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true,
  };
  if (slot === 'helmet') {
    return <svg {...common}><path d="M4 15a8 8 0 0 1 16 0v3H4z" /><path d="M12 7v8M8 18v2M16 18v2" /></svg>;
  }
  if (slot === 'armor') {
    return <svg {...common}><path d="M8 3l4 2 4-2 4 4-3 3v10H7V10L4 7z" /><path d="M12 5v15" /></svg>;
  }
  if (slot === 'legs') {
    return <svg {...common}><path d="M6 3h12l-1 18h-4l-1-11-1 11H7z" /></svg>;
  }
  if (slot === 'boots') {
    return <svg {...common}><path d="M7 3h6v11l6 3v3H5v-3l2-1z" /></svg>;
  }
  return <svg {...common}><path d="M19 3l-9 9M14 3h5v5M5 15l4 4M3 21l4-4M8 12l4 4" /></svg>;
}

function statDiff(item, current) {
  const keys = new Set([...Object.keys(item?.base_stats || {}), ...Object.keys(current?.base_stats || {})]);
  return STAT_ORDER.filter((k) => keys.has(k))
    .map((k) => [k, (item?.base_stats?.[k] || 0) - (current?.base_stats?.[k] || 0)])
    .filter(([, d]) => d !== 0);
}

// Сопротивление кованой вещи (2026-11-02) - плашкой рядом со статами:
// 🪨 к критам, 🎯 меткость, 🧪 к периодическому урону; полная строка - в подсказке.
function ResistChip({ item }) {
  const chip = item?.resist_chip;
  if (!chip) return null;
  return <span className="gear-chip gear-chip--resist" title={item.resist}>{chip.emoji} +{chip.pct}%</span>;
}

function DiffChips({ diff }) {
  if (!diff.length) return <span className="gear-chip gear-chip--same">=</span>;
  return diff.map(([k, d]) => (
    <span key={k} className={d > 0 ? 'gear-chip gear-chip--up' : 'gear-chip gear-chip--down'}>
      {STAT_ICONS[k]} {d > 0 ? `+${d}` : d}
    </span>
  ));
}

// Класс CSS по редкости: id идёт в имя класса, а не в текст на экране.
const rarityText = (rarity) => `slot-row__name rarity-text--${rarity}`;

function SlotSheet({ slot, items, onClose, onEquip, onUnequip, busyId }) {
  // «Назад» телефона закрывает окно (2026-11-12).
  useBackClose(onClose);
  const current = items.find((i) => i.slot === slot && i.equipped) || null;
  const spare = items
    .filter((i) => i.slot === slot && !i.equipped)
    .sort((a, b) => Boolean(a.need_level) - Boolean(b.need_level) || b.power - a.power);
  const best = spare.find((i) => !i.need_level && i.power > (current?.power || 0));
  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet slot-sheet" role="dialog" aria-label={SLOT_TITLES[slot]}>
        <div className="slot-sheet__head">
          <span className="slot-sheet__glyph"><SlotGlyph slot={slot} /></span>
          <b>{SLOT_TITLES[slot]}</b>
        </div>
        {current && (
          <div className="slot-row slot-row--current">
            <ItemIcon icon={current.icon} rarity={current.rarity} alt={current.name} size={44} />
            <div className="slot-row__text">
              <span className={rarityText(current.rarity)}>{current.name}</span>
              <span className="slot-row__chips">
                {STAT_ORDER.filter((k) => current.base_stats?.[k]).map((k) => (
                  <span key={k} className="gear-chip">{STAT_ICONS[k]} +{current.base_stats[k]}</span>
                ))}
                <ResistChip item={current} />
              </span>
            </div>
            <button
              type="button" className="slot-row__off" disabled={busyId === current.id}
              onClick={() => onUnequip(current.id)} aria-label="Снять"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          </div>
        )}
        <div className="slot-sheet__list">
          {spare.length === 0 && <p className="slot-sheet__empty">В сумке нет вещей для этого слота.</p>}
          {spare.map((item) => {
            const locked = Boolean(item.need_level);
            return (
              <button
                type="button" key={item.id}
                className={`slot-row${locked ? ' slot-row--locked' : ''}${item === best ? ' slot-row--best' : ''}`}
                disabled={locked || busyId != null}
                onClick={() => onEquip(item.id)}
              >
                <ItemIcon icon={item.icon} rarity={item.rarity} alt={item.name} size={44} />
                <span className="slot-row__text">
                  <span className={rarityText(item.rarity)}>
                    {item === best && <span className="slot-row__best" aria-label="лучше надетого">▲</span>}
                    {item.name}
                  </span>
                  <span className="slot-row__chips">
                    {locked
                      ? <span className="gear-chip gear-chip--lock">🔒 {item.need_level}</span>
                      : <><DiffChips diff={statDiff(item, current)} /><ResistChip item={item} /></>}
                  </span>
                </span>
                {busyId === item.id && <span className="slot-row__spin" aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

// «Дар первопроходцев» (2026-10-29): все дорелизные бонусы. 2026-11-12
// (владелец): в профиле одна плашка, сам список - по нажатию.
function GiftCard({ gift }) {
  const [open, setOpen] = useState(false);
  if (!gift) return null;
  return (
    <>
      <button type="button" className="gift-plaque" onClick={() => setOpen(true)}>
        <span className="gift-plaque__icon" aria-hidden="true">{gift.emoji}</span>
        <span className="gift-plaque__title">{gift.title}</span>
        <span className="gift-plaque__more" aria-hidden="true">›</span>
      </button>
      {open && (
        <Sheet title={gift.title} icon={gift.emoji} onClose={() => setOpen(false)}>
          <div className="gift-card">
            <p className="craft-hint">{gift.about}</p>
            <ul className="gift-card__list">
              {gift.lines.map((line) => <li key={line}>{line}</li>)}
            </ul>
          </div>
        </Sheet>
      )}
    </>
  );
}

// Счёт персонажа (2026-11-12): полку трофеев владелец убрал, цифры остались.
function Score({ trophies }) {
  if (!trophies) return null;
  const tiles = [
    ['⚔️', trophies.mobs_killed.toLocaleString('ru-RU'), 'мобов убито'],
    ['🩸', trophies.pvp_wins.toLocaleString('ru-RU'), 'побед в PvP'],
    [trophies.best_fish?.emoji || '🎣', trophies.best_fish?.weight || '-', 'рекорд улова'],
    ['👑', `${trophies.titles_open}/${trophies.titles_total}`, 'титулов'],
  ];
  return (
    <Group header={<Header>Счёт</Header>}>
      <div className="trophy-tiles">
        {tiles.map(([icon, value, label]) => (
          <div className="trophy-tile" key={label}>
            <span className="trophy-tile__icon" aria-hidden="true">{icon}</span>
            <b className="trophy-tile__value">{value}</b>
            <small className="trophy-tile__label">{label}</small>
          </div>
        ))}
      </div>
    </Group>
  );
}

// Подпись под окном надетой вещи (2026-11-12): уровень и два главных стата.
// Раньше то же самое дублировал список под силуэтом (жалоба 2026-10-23:
// «чтобы понять, что качать, прокликиваю каждую вещь»).
function SlotCaption({ item }) {
  const stats = STAT_ORDER.filter((k) => item.base_stats?.[k])
    .sort((a, b) => item.base_stats[b] - item.base_stats[a]);
  return (
    <span className="gear-slot__caption" aria-hidden="true">
      {item.ilvl ? <span className="gear-slot__lvl">ур. {item.ilvl}</span> : null}
      <span className="gear-slot__stats">
        {stats.slice(0, 2).map((k) => <span key={k}>{STAT_ICONS[k]}{item.base_stats[k]}</span>)}
        {stats.length > 2 && <span>+{stats.length - 2}</span>}
      </span>
    </span>
  );
}

// Окно кольца (2026-10-23): под оружием. Кольцо одно и снимать его незачем -
// по нажатию только что оно даёт. Пустое окно молчит.
function leftText(until, now) {
  const min = Math.ceil((new Date(until).getTime() - now) / 60000);
  if (min <= 0) return null;
  return min >= 120 ? `${Math.floor(min / 60)} ч ${min % 60} мин` : `${min} мин`;
}

function fightsText(n) {
  const d = n % 10;
  const word = d === 1 && n % 100 !== 11 ? 'бой' : d >= 2 && d <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'боя' : 'боёв';
  return `${n} ${word}`;
}

// Действующие баффы (2026-10-23): еда, прикормка, молитва, настойка, эффекты
// событий. Сервер - services/buffs_service.py, приходит вместе со страницами
// ремёсел. 2026-11-12: строкой над силуэтом - слева над оружием плашки
// заходили на рисунок и обрезали название («Метка падаль...»).
function BuffList({ buffs }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);
  const shown = (buffs || [])
    .map((b) => ({ ...b, left: b.until ? leftText(b.until, now) : fightsText(b.fights) }))
    .filter((b) => b.left);
  const [open, setOpen] = useState(false);
  if (!shown.length) return null;
  // В строке три плашки; остальное - в списке по нажатию.
  const more = shown.length > BUFFS_SHOWN ? shown.length - (BUFFS_SHOWN - 1) : 0;
  const row = (b) => (
    <li key={b.id} className={`hero-buff${b.bad ? ' hero-buff--bad' : ''}`}>
      <b>{b.emoji} {b.name}</b>
      <span>{b.value}{b.value ? ' · ' : ''}<small>{b.left}</small></span>
    </li>
  );
  return (
    <>
      <button type="button" className="hero-buffs" onClick={() => setOpen(true)} aria-label="Действующие баффы">
        <ul>
          {(more ? shown.slice(0, BUFFS_SHOWN - 1) : shown).map(row)}
          {more > 0 && <li className="hero-buff hero-buff--more">+ ещё {more}</li>}
        </ul>
      </button>
      {open && (
        <Sheet title="Действует сейчас" icon="✨" onClose={() => setOpen(false)}>
          <ul className="hero-buffs-sheet">{shown.map(row)}</ul>
        </Sheet>
      )}
    </>
  );
}

const BUFFS_SHOWN = 3;
const PAGE_KEY = 'pines:sub:hero';

// Слот кольца (2026-11-03, владелец: «слот кольца только один»). Как
// у вещей: на пальце одно кольцо, остальные в сумке - снять, надеть,
// поменять на другое. slot - {worn, bag} с сервера (ring_slot_service).
function RingSlot({ slot, onAction }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const worn = slot?.worn || null;
  const bag = slot?.bag || [];
  const art = worn ? itemIcon(worn.icon) : null;

  async function act(action, ring = null) {
    setBusy(true);
    setError(null);
    try {
      await onAction(action, ring);
      setOpen(false);
    } catch (err) {
      setError(err?.message?.includes(' ') ? err.message : 'Не вышло.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button" data-slot="ring"
        className={`gear-slot${worn ? ' gear-slot--filled gear-slot--legendary' : ''}`}
        style={{ top: '72%' }}
        onClick={() => slot && setOpen(true)}
        aria-label={worn ? worn.name : 'Кольцо'}
      >
        {worn && art ? <img src={art} alt="" className="gear-slot__ring" /> : (
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
            aria-hidden="true"><circle cx="12" cy="14" r="6" /><path d="M9 6l3-3 3 3-3 2z" /></svg>
        )}
      </button>
      {open && slot && (
        <Sheet title={worn ? worn.name : 'Кольцо'} icon="💍" onClose={() => setOpen(false)}>
          {worn ? (
            <>
              <p className="gear-sheet__effect">{worn.effect}.</p>
              {worn.flavor && <p className="gear-sheet__flavor">{worn.flavor}</p>}
              <button type="button" className="pill-btn" disabled={busy} onClick={() => act('remove')}>
                Снять в сумку
              </button>
            </>
          ) : <p className="gear-sheet__flavor">Палец свободен.</p>}
          {bag.length > 0 && <p className="gear-sheet__flavor">В сумке:</p>}
          {bag.map((r) => (
            <div key={r.id} className="ring-choice">
              <ItemIcon icon={r.icon} alt="" size={40} />
              <div className="ring-choice__text">
                <b>{r.name}{r.count > 1 ? ` ×${r.count}` : ''}</b>
                <span>{r.effect}.</span>
                {r.tradable && <span className="ring-choice__note">Лишние можно передать или продать на рынке.</span>}
              </div>
              <button type="button" className="pill-btn pill-btn--main" disabled={busy} onClick={() => act('wear', r.id)}>
                {worn ? 'Надеть вместо' : 'Надеть'}
              </button>
            </div>
          ))}
          {error && <p className="hero-error">{error}</p>}
        </Sheet>
      )}
    </>
  );
}

export function GenderChoice({ character, onPick, busy }) {
  return (
    <Group>
      <div className="gender-choice">
        <p className="gender-choice__title">Выберите облик</p>
        <div className="gender-choice__row">
          {[['m', 'Мужской'], ['f', 'Женский']].map(([g, label]) => (
            <button
              type="button" key={g} className="gender-choice__card" disabled={busy}
              onClick={() => onPick(g)} aria-label={label}
            >
              <img src={silhouetteUrl(character.subclass, character.base_class, g)} alt="" draggable="false" />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </div>
    </Group>
  );
}

// Выбор облика поверх всего при первом входе (2026-10-22): раньше он
// появлялся только во вкладке «Герой», и тур с подсказками в это время
// подсвечивал окна слотов, которых ещё не было на экране.
export function GenderGate({ character, onCharacterUpdate }) {
  const [busy, setBusy] = useState(false);
  async function pick(next) {
    setBusy(true);
    try {
      const res = await setGender(next);
      onCharacterUpdate((prev) => ({ ...prev, gender: res.gender }));
    } catch (err) {
      // Уже выбран (с другого устройства) - сервер вернул какой.
      if (err?.details?.gender) onCharacterUpdate((prev) => ({ ...prev, gender: err.details.gender }));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="gender-gate" role="dialog" aria-label="Выберите облик">
      <div className="gender-gate__card">
        <GenderChoice character={character} onPick={pick} busy={busy} />
      </div>
    </div>
  );
}

export function HeroSkeleton() {
  return (
    <Group>
      <div className="hero-stage">
        <div className="hero-figure skeleton" />
      </div>
    </Group>
  );
}

export default function HeroTab({ character, onCharacterUpdate }) {
  const [items, setItems] = useState(null);
  const [trophies, setTrophies] = useState(null);
  const [failed, setFailed] = useState(false);
  const [openSlot, setOpenSlot] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState(null);
  // Сколько раз в слот надевали вещь - каждое надевание даёт вспышку искр.
  const [flashes, setFlashes] = useState({});
  const [gender, setGenderState] = useState(character.gender || null);
  // Страницы: 0 - снаряжение, 1 - руны (2026-10-31), дальше ремёсла
  // (2026-10-23, стрелкой вправо).
  // 2026-11-12: «Снаряжение» или «Руны» - где вышли, там и откроется.
  const [page, setPageState] = useState(() => {
    try { return window.localStorage.getItem(PAGE_KEY) === '1' ? 1 : 0; } catch { return 0; }
  });
  const setPage = (next) => setPageState((prev) => {
    const value = typeof next === 'function' ? next(prev) : next;
    try { window.localStorage.setItem(PAGE_KEY, value === 1 ? '1' : '0'); } catch { /* не запомнится */ }
    return value;
  });
  const [gear, setGear] = useState(null);
  const [runes, setRunes] = useState(null);
  const [runeKind, setRuneKind] = useState('ability');
  const [choosing, setChoosing] = useState(false);
  // Облик могли выбрать на экране выбора при входе (GenderGate) - подхватить.
  useEffect(() => {
    if (character.gender) setGenderState(character.gender);
  }, [character.gender]);

  useEffect(() => {
    getInventory().then((res) => setItems(res.items)).catch(() => setFailed(true));
    getTrophies().then(setTrophies).catch(() => {});
    getGear().then(setGear).catch(() => {});
    getRunes().then(setRunes).catch(() => {});
  }, []);

  const equipped = useMemo(
    () => Object.fromEntries((items || []).filter((i) => i.equipped).map((i) => [i.slot, i])),
    [items],
  );
  // Есть ли в сумке вещь сильнее надетой - зелёная метка на окне слота.
  const upgrades = useMemo(() => {
    const out = {};
    for (const item of items || []) {
      if (item.equipped || item.need_level) continue;
      if (item.power > (equipped[item.slot]?.power || 0)) out[item.slot] = true;
    }
    return out;
  }, [items, equipped]);

  async function refreshCharacter() {
    try { onCharacterUpdate(await getCharacter()); } catch { /* шапка подтянется позже */ }
  }

  // Ошибку показывает шторка кольца, поэтому здесь её не ловим.
  async function handleRing(action, ring) {
    const res = await ringAction(action, ring);
    onCharacterUpdate((prev) => ({ ...prev, ring_slot: res.ring_slot }));
    refreshCharacter();
  }

  async function handleEquip(itemId) {
    const slot = openSlot;
    setBusyId(itemId);
    setError(null);
    try {
      const res = await equipItem(itemId);
      setItems(res.items);
      setOpenSlot(null);
      setFlashes((f) => ({ ...f, [slot]: (f[slot] || 0) + 1 }));
      refreshCharacter();
    } catch (err) {
      setError(err?.message?.includes(' ') ? err.message : 'Не удалось надеть.');
    } finally {
      setBusyId(null);
    }
  }

  async function handleUnequip(itemId) {
    setBusyId(itemId);
    setError(null);
    try {
      const res = await unequipItem(itemId);
      setItems(res.items);
      refreshCharacter();
    } catch {
      setError('Не удалось снять.');
    } finally {
      setBusyId(null);
    }
  }

  // Пол выбирается один раз (2026-10-22, владелец), сменить пока нельзя.
  async function pickGender(next) {
    setChoosing(true);
    try {
      const res = await setGender(next);
      setGenderState(res.gender);
      onCharacterUpdate((prev) => ({ ...prev, gender: res.gender }));
    } catch (err) {
      // Уже выбран (с другого устройства) - сервер вернул какой.
      if (err?.details?.gender) setGenderState(err.details.gender);
    } finally {
      setChoosing(false);
    }
  }


  if (failed) return <Group><p className="hero-error">Не удалось загрузить снаряжение.</p></Group>;
  if (!gender) return <GenderChoice character={character} onPick={pickGender} busy={choosing} />;
  if (!items) return <HeroSkeleton />;

  const url = silhouetteUrl(character.subclass, character.base_class, gender);
  const path = character.subclass || character.base_class;
  const bonus = STAT_ORDER.filter((k) => character.gear_bonus?.[k]);
  // Сопротивления героя итогом (2026-11-02): Выносливость, руны, вещи, перстень.
  const resists = RESIST_CHIPS.filter(([k]) => character.derived?.[k] > 0);

  const slotButton = ({ slot, y }) => {
    const item = equipped[slot];
    const rar = item?.rarity;
    return (
      <button
        type="button" key={slot} data-slot={slot}
        className={`gear-slot${item ? ` gear-slot--filled gear-slot--${rar}` : ''}`}
        style={{ top: `${y}%` }}
        onClick={() => setOpenSlot(slot)}
        aria-label={item ? `${SLOT_TITLES[slot]}: ${item.name}` : SLOT_TITLES[slot]}
      >
        {item
          ? <ItemIcon icon={item.icon} rarity={item.rarity} alt="" size={48} />
          : <SlotGlyph slot={slot} />}
        {upgrades[slot] && <span className="gear-slot__up" aria-hidden="true">▲</span>}
        {item && <SlotCaption item={item} />}
        <Sparks burst={flashes[slot] || 0} />
      </button>
    );
  };

  const pages = 2 + (gear?.crafts?.length || 0);
  const craft = page > 1 ? gear?.crafts?.[page - 2] : null;
  const pageTitle = craft ? `${craft.emoji} ${craft.title}` : page === 1 ? '🪨 Руны' : '🛡 Снаряжение';
  const turn = (step) => setPage((p) => (p + step + pages) % pages);

  return (
    <>
      <Group>
        {pages > 1 && (
          <div className="hero-pager">
            <button type="button" className="hero-pager__arrow" onClick={() => turn(-1)} aria-label="Назад">‹</button>
            <span className="hero-pager__title">{pageTitle}</span>
            <button type="button" className="hero-pager__arrow" onClick={() => turn(1)} aria-label="Дальше">›</button>
          </div>
        )}
        {page === 1 ? (
          <RunesPage data={runes} onData={setRunes} kind={runeKind} onKind={setRuneKind} />
        ) : craft ? <CraftGear key={craft.id} craft={craft} onUpdate={setGear} /> : (
        <div className={`hero-stage hero-stage--${path}`}>
          <BuffList buffs={gear?.buffs} />
          <div className="hero-row">
            <div className="hero-col hero-col--left">
              {SLOTS.filter((x) => x.side === 'left').map(slotButton)}
              <RingSlot slot={character.ring_slot} onAction={handleRing} />
            </div>
            <div className="hero-figure">
              <img key={url} className="hero-figure__img" src={url} alt="" draggable="false" />
            </div>
            <div className="hero-col hero-col--right">
              {SLOTS.filter((x) => x.side === 'right').map(slotButton)}
            </div>
          </div>
          <RuneRing data={runes} onOpen={() => { setRuneKind('hero'); setPage(1); }} />
          {/* Подписано словами (2026-11-12): одни значки «🏃 +1 ❤️ +1 🪨 1.5%»
              игроки не понимали. Сопротивления не только от вещей - от
              Выносливости, рун и перстня тоже, поэтому отдельной строкой. */}
          {bonus.length > 0 && (
            <div className="hero-bonus">
              <span className="hero-bonus__label">Вещи дают:</span>
              {bonus.map((k) => (
                <span key={k} className="gear-chip">{STAT_ICONS[k]} {STAT_NAMES[k]} +{character.gear_bonus[k]}</span>
              ))}
            </div>
          )}
          {resists.length > 0 && (
            <div className="hero-bonus">
              <span className="hero-bonus__label">Сопротивления:</span>
              {resists.map(([k, emoji, title]) => (
                <span key={k} className="gear-chip gear-chip--resist">
                  {emoji} {title} {(character.derived[k] * 100).toFixed(1)}%
                </span>
              ))}
            </div>
          )}
          {error && <p className="hero-error">{error}</p>}
        </div>
        )}
      </Group>

      <GiftCard gift={trophies?.gift} />
      <Score trophies={trophies} />

      {openSlot && (
        <SlotSheet
          slot={openSlot} items={items} busyId={busyId}
          onClose={() => setOpenSlot(null)} onEquip={handleEquip} onUnequip={handleUnequip}
        />
      )}
    </>
  );
}
