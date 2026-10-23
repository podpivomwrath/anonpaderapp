import { useEffect, useMemo, useState } from 'react';
import { Group, Header, SimpleCell, Switch } from '@vkontakte/vkui';
import {
  equipItem, getCharacter, getGear, getInventory, getTrophies, setGender, setNoImages, setShortLog, unequipItem,
} from '../api.js';
import CraftGear from './CraftGear.jsx';
import { silhouetteUrl } from '../silhouettes.js';
import { itemIcon } from '../itemIcons.js';
import ItemIcon from './ItemIcon.jsx';
import Sparks from './Sparks.jsx';
import { Sheet } from './ui.jsx';

// Вкладка «Герой» (2026-10-22): силуэт персонажа, по бокам окна слотов
// (линии от окна к телу владелец убрал - и так понятно). Нажал окно - снизу список вещей из сумки для
// этого слота, с разницей к надетой. Под силуэтом - бонус снаряжения и полка
// трофеев. Окна сперва лежали прямо на теле - владельцу не понравилось.

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
const STAT_ORDER = ['str', 'agi', 'int', 'vit', 'wil'];

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
                      : <DiffChips diff={statDiff(item, current)} />}
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

function TrophyShelf({ trophies }) {
  const [picked, setPicked] = useState(null);
  if (!trophies) return null;
  const tiles = [
    ['⚔️', trophies.mobs_killed.toLocaleString('ru-RU'), 'мобов'],
    ['🩸', trophies.pvp_wins.toLocaleString('ru-RU'), 'побед PvP'],
    [trophies.best_fish?.emoji || '🎣', trophies.best_fish?.weight || '-', 'рекорд улова'],
    ['👑', `${trophies.titles_open}/${trophies.titles_total}`, 'титулов'],
  ];
  const relic = trophies.raids.find((r) => r.raid === picked);
  return (
    <Group header={<Header>Трофеи</Header>}>
      <div className="relic-row">
        {trophies.raids.map((r) => (
          <button
            type="button" key={r.raid}
            className={`relic${r.won ? ' relic--won' : ''}${picked === r.raid ? ' relic--picked' : ''}`}
            onClick={() => setPicked(picked === r.raid ? null : r.raid)}
            aria-label={r.name}
          >
            {itemIcon(r.icon) ? <img src={itemIcon(r.icon)} alt="" /> : <span>?</span>}
          </button>
        ))}
      </div>
      {relic && (
        <p className="relic-caption">
          {relic.name}{relic.won ? '' : ' - ещё не добыто'}
        </p>
      )}
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

// «Убрать картинки в игре» (2026-10-22): бот шлёт сообщения без картинок -
// некоторым так удобнее (bot/no_images.py).
function Settings({ character, onCharacterUpdate }) {
  const [off, setOff] = useState(Boolean(character.ui?.no_images));
  const toggle = (next) => {
    setOff(next);
    setNoImages(next)
      .then(() => onCharacterUpdate((prev) => ({ ...prev, ui: { ...(prev.ui || {}), no_images: next } })))
      .catch(() => setOff(!next));
  };
  // Короткий боевой лог (2026-10-22, bot/short_log.py).
  const [short, setShort] = useState(Boolean(character.ui?.short_log));
  const toggleShort = (next) => {
    setShort(next);
    setShortLog(next)
      .then(() => onCharacterUpdate((prev) => ({ ...prev, ui: { ...(prev.ui || {}), short_log: next } })))
      .catch(() => setShort(!next));
  };
  return (
    <Group header={<Header>Настройки</Header>}>
      <SimpleCell
        Component="label" multiline
        subtitle="Бот будет присылать сообщения без картинок."
        after={<Switch checked={off} onChange={(e) => toggle(e.target.checked)} />}
      >
        Убрать картинки в игре
      </SimpleCell>
      <SimpleCell
        Component="label" multiline
        subtitle="В бою только здоровье с изменением за ход и значки эффектов. Весь лог хода - кнопкой «📜 Сводка»."
        after={<Switch checked={short} onChange={(e) => toggleShort(e.target.checked)} />}
      >
        Короткий лог боя
      </SimpleCell>
      {short && (
        <p className="tab-notice short-log-legend">
          🔥 горит · ☠️ яд · ❄️ скован · 🧊 после контроля · 💢 уязвимость · 🥀 ослаблен ·
          🎯 метки · 🩸 печать крови · ⚔️ 🌀 🗡 🌋 урон выше · 💨 уклонение · 🧱 глухая оборона ·
          🪨 предел урона · 🪞 отражение · ✨ не берёт контроль · 💀 последний вздох ·
          📣 провокация · 🛡️ щит
        </p>
      )}
    </Group>
  );
}

// Надетое списком (2026-10-23, жалоба игрока: «вижу только итог бонусов, чтобы
// понять, что качать, прокликиваю каждую вещь»): по слоту - вещь, уровень,
// ковка и её статы. Нажатие открывает слот, как окно у силуэта.
function WornList({ equipped, onOpen }) {
  return (
    <div className="worn-list">
      {SLOTS.map(({ slot }) => {
        const item = equipped[slot];
        const marks = item ? [
          item.ilvl ? `ур. ${item.ilvl}` : null,
          item.craft_efficiency ? `⚒ ${item.craft_efficiency}%` : null,
        ].filter(Boolean) : [];
        return (
          <button type="button" key={slot} className="worn-row" onClick={() => onOpen(slot)}>
            {item
              ? <ItemIcon icon={item.icon} rarity={item.rarity} alt={item.name} size={36} />
              : <span className="worn-row__empty"><SlotGlyph slot={slot} /></span>}
            <span className="worn-row__text">
              <span className={item ? rarityText(item.rarity) : 'worn-row__none'}>
                {item ? item.name : `${SLOT_TITLES[slot]}: пусто`}
              </span>
              {item && (
                <span className="worn-row__meta">
                  {marks.join(' · ')}
                  {STAT_ORDER.filter((k) => item.base_stats?.[k]).map((k) => (
                    <span key={k} className="gear-chip">{STAT_ICONS[k]} +{item.base_stats[k]}</span>
                  ))}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

// Окно кольца (2026-10-23): под оружием. Кольцо одно и снимать его незачем -
// по нажатию только что оно даёт. Пустое окно молчит.
function RingSlot({ ring }) {
  const [open, setOpen] = useState(false);
  const art = itemIcon('special:ring');
  return (
    <>
      <button
        type="button" data-slot="ring"
        className={`gear-slot${ring ? ' gear-slot--filled gear-slot--legendary' : ''}`}
        style={{ top: '72%' }}
        onClick={() => ring && setOpen(true)}
        aria-label={ring ? ring.name : 'Кольцо'}
      >
        {ring && art ? <img src={art} alt="" className="gear-slot__ring" /> : (
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"
            aria-hidden="true"><circle cx="12" cy="14" r="6" /><path d="M9 6l3-3 3 3-3 2z" /></svg>
        )}
      </button>
      {open && ring && (
        <Sheet title={ring.name} icon="💍" onClose={() => setOpen(false)}>
          <p className="gear-sheet__effect">{ring.effect}.</p>
        </Sheet>
      )}
    </>
  );
}

export function GenderChoice({ character, onPick, busy }) {
  return (
    <Group>
      <div className="gender-choice">
        <p className="gender-choice__title">Выбери облик</p>
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
    <div className="gender-gate" role="dialog" aria-label="Выбери облик">
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
  // Страницы: 0 - снаряжение, дальше ремёсла (2026-10-23, стрелкой вправо).
  const [page, setPage] = useState(0);
  const [gear, setGear] = useState(null);
  const [choosing, setChoosing] = useState(false);
  // Облик могли выбрать на экране выбора при входе (GenderGate) - подхватить.
  useEffect(() => {
    if (character.gender) setGenderState(character.gender);
  }, [character.gender]);

  useEffect(() => {
    getInventory().then((res) => setItems(res.items)).catch(() => setFailed(true));
    getTrophies().then(setTrophies).catch(() => {});
    getGear().then(setGear).catch(() => {});
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
        <Sparks burst={flashes[slot] || 0} />
      </button>
    );
  };

  const pages = 1 + (gear?.crafts?.length || 0);
  const craft = page > 0 ? gear?.crafts?.[page - 1] : null;
  const pageTitle = craft ? `${craft.emoji} ${craft.title}` : '🛡 Снаряжение';
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
        {craft ? <CraftGear key={craft.id} craft={craft} onUpdate={setGear} /> : (
        <div className={`hero-stage hero-stage--${path}`}>
          <div className="hero-row">
            <div className="hero-col hero-col--left">
              {SLOTS.filter((x) => x.side === 'left').map(slotButton)}
              <RingSlot ring={character.ring} />
            </div>
            <div className="hero-figure">
              <img key={url} className="hero-figure__img" src={url} alt="" draggable="false" />
            </div>
            <div className="hero-col hero-col--right">{SLOTS.filter((x) => x.side === 'right').map(slotButton)}</div>
          </div>
          {bonus.length > 0 && (
            <div className="hero-bonus">
              {bonus.map((k) => (
                <span key={k} className="gear-chip">{STAT_ICONS[k]} +{character.gear_bonus[k]}</span>
              ))}
            </div>
          )}
          {error && <p className="hero-error">{error}</p>}
          <WornList equipped={equipped} onOpen={setOpenSlot} />
        </div>
        )}
      </Group>

      <TrophyShelf trophies={trophies} />
      <Settings character={character} onCharacterUpdate={onCharacterUpdate} />

      {openSlot && (
        <SlotSheet
          slot={openSlot} items={items} busyId={busyId}
          onClose={() => setOpenSlot(null)} onEquip={handleEquip} onUnequip={handleUnequip}
        />
      )}
    </>
  );
}
