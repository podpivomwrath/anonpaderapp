import { useCallback, useEffect, useState } from 'react';
import { getPlayerLook } from '../api.js';
import { silhouetteUrl } from '../silhouettes.js';
import { itemIcon } from '../itemIcons.js';
import ItemIcon from './ItemIcon.jsx';
import { RuneIcon } from './RunesPage.jsx';
import { SLOTS, SLOT_TITLES, STAT_ICONS, STAT_NAMES, SlotCaption, SlotGlyph } from './HeroTab.jsx';
import { Sheet } from './ui.jsx';

// Окно чужого игрока (2026-11-14, владелец): нажал на имя в топе или на
// доске - небольшое окно поверх раздела с силуэтом, надетыми вещами и рунами.
// Только надетое: ни сумки, ни золота, ни места на карте, ни ссылки на
// страницу (сервер их и не отдаёт - bot/miniapp_look_api.py).

const STEPS = ['', 'I', 'II', 'III', 'IV'];
const STAT_ORDER = ['str', 'agi', 'int', 'vit', 'wil'];

function statsLine(stats) {
  return STAT_ORDER.filter((k) => stats?.[k]).map((k) => `${STAT_ICONS[k]} ${STAT_NAMES[k]} +${stats[k]}`).join(' · ');
}

function RuneChip({ rune, note }) {
  const rar = rune.rarity;
  return (
    <span className="look-rune">
      <RuneIcon rune={rune} size={28} />
      <span className="look-rune__text">
        <span className={`rarity-text--${rar}`}>{rune.name}</span>
        <small>{note ? `${note} · ` : ''}{rune.efficiency}%</small>
      </span>
    </span>
  );
}

function LookBody({ data }) {
  const [picked, setPicked] = useState(null);
  const bySlot = Object.fromEntries(data.items.map((i) => [i.slot, i]));
  const url = silhouetteUrl(data.subclass, data.base_class, data.gender || 'm');
  const item = picked === 'ring' ? null : bySlot[picked];
  const itemRar = item?.rarity;
  const { hero, abilities, gear } = data.runes;

  const slotButton = ({ slot, y }) => {
    const it = bySlot[slot];
    const rar = it?.rarity;
    return (
      <button
        type="button" key={slot}
        className={`gear-slot${it ? ` gear-slot--filled gear-slot--${rar}` : ''}${picked === slot ? ' gear-slot--picked' : ''}`}
        style={{ top: `${y}%` }}
        onClick={() => setPicked(it ? slot : null)}
        aria-label={it ? `${SLOT_TITLES[slot]}: ${it.name}` : SLOT_TITLES[slot]}
      >
        {it ? <ItemIcon icon={it.icon} rarity={it.rarity} alt="" size={44} /> : <SlotGlyph slot={slot} />}
        {it && <SlotCaption item={it} />}
      </button>
    );
  };

  return (
    <>
      <p className="look-sub">
        {data.class_title} · {data.level} ур.
        {data.title && <span className={`title-tier title-tier--${data.title_tier || 'common'}`}> · «{data.title}»</span>}
      </p>
      <div className="hero-stage look-stage">
        <div className="hero-row">
          <div className="hero-col hero-col--left">
            {SLOTS.filter((x) => x.side === 'left').map(slotButton)}
            {data.ring && (
              <button type="button" className="gear-slot gear-slot--filled gear-slot--legendary" style={{ top: '72%' }}
                onClick={() => setPicked('ring')} aria-label={data.ring.name}>
                <img src={itemIcon(data.ring.icon)} alt="" className="gear-slot__ring" />
              </button>
            )}
          </div>
          <div className="hero-figure">
            <img className="hero-figure__img" src={url} alt="" draggable="false" />
          </div>
          <div className="hero-col hero-col--right">
            {SLOTS.filter((x) => x.side === 'right').map(slotButton)}
          </div>
        </div>
      </div>
      {item && (
        <div className="look-item">
          <b className={`rarity-text--${itemRar}`}>{item.name}</b>
          <small>{[item.rarity_title, item.ilvl ? `ур. ${item.ilvl}` : null].filter(Boolean).join(' · ')}</small>
          <span>{statsLine(item.base_stats)}</span>
        </div>
      )}
      {picked === 'ring' && data.ring && (
        <div className="look-item">
          <b>{data.ring.name}</b>
          <span>{data.ring.effect}</span>
        </div>
      )}
      {!picked && <p className="look-hint">Нажмите на вещь, чтобы увидеть её характеристики.</p>}

      {abilities.length > 0 && (
        <div className="look-runes">
          <span className="look-runes__title">Навыки</span>
          {abilities.map((a) => (
            <div key={a.rune.id} className="look-runes__row">
              <RuneChip rune={a.rune} note={a.step ? `ступень ${STEPS[a.step]}` : null} />
              {a.facets.map((f) => <RuneChip key={f.id} rune={f} note="огранка" />)}
            </div>
          ))}
        </div>
      )}
      {hero.length > 0 && (
        <div className="look-runes">
          <span className="look-runes__title">Руны героя</span>
          <div className="look-runes__row">{hero.map((r, i) => <RuneChip key={`${r.id}${i}`} rune={r} />)}</div>
        </div>
      )}
      {gear.map((g) => (
        <div key={g.title} className="look-runes">
          <span className="look-runes__title">{g.title}</span>
          <div className="look-runes__row">{g.runes.map((r, i) => <RuneChip key={`${r.id}${i}`} rune={r} />)}</div>
        </div>
      ))}
      {!abilities.length && !hero.length && !gear.length && <p className="look-hint">Рун не надето.</p>}
    </>
  );
}

export function PlayerLook({ id, name, onClose }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    getPlayerLook(id).then((res) => { if (!cancelled) setData(res); }).catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [id]);
  return (
    <Sheet title={data?.name || name || 'Игрок'} icon="👤" onClose={onClose} className="look-sheet">
      {failed && <p className="look-hint">Не удалось загрузить.</p>}
      {!failed && !data && <div className="hero-figure skeleton look-skeleton" />}
      {data && <LookBody data={data} />}
    </Sheet>
  );
}

/** [открыть(id, имя), окно] - окно ставится в разметку раздела. */
export function usePlayerLook() {
  const [who, setWho] = useState(null);
  const open = useCallback((id, name) => { if (id) setWho({ id, name }); }, []);
  const close = useCallback(() => setWho(null), []);
  const sheet = who ? <PlayerLook id={who.id} name={who.name} onClose={close} /> : null;
  return [open, sheet];
}
