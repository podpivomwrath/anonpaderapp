import { useState } from 'react';
import { TabsItem } from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { Bar, Sheet } from './ui.jsx';
import { runeAction } from '../api.js';
import { RUNE_ART, RUNE_ICONS } from '../runeIcons.js';

/**
 * Руны (2026-10-31, владелец): страница на вкладке «Герой». Три подвкладки,
 * все слоты сразу; закрытый слот - под замком, нажатие предлагает купить.
 * Менять руны можно только в родном городе. Мастерство - у игрока: лишние
 * копии впитываются, эффективность растёт по порогам.
 */

const KINDS = [
  { id: 'hero', title: 'Героя' },
  { id: 'gear', title: 'Экипировки' },
  { id: 'skill', title: 'Навыков' },
];
const SOCKET_ART = { hero: 'socket_hero', gear: 'socket_gear', skill: 'socket_skill' };
const PVP = { full: 'в PvP в полную силу', half: 'в PvP вполсилы', none: 'в PvP не действует' };

function copiesWord(n) {
  const d = n % 10;
  if (d === 1 && n % 100 !== 11) return 'копия';
  return d >= 2 && d <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'копии' : 'копий';
}

const gold = (n) => n.toLocaleString('ru-RU');

export function RuneIcon({ rune, size = 48 }) {
  const url = rune && RUNE_ICONS[rune.id];
  if (!url) return <span className="rune-icon rune-icon--empty" style={{ width: size, height: size }} />;
  const rar = rune.rarity;
  return <img className={`rune-icon rune-icon--${rar}`} src={url} alt="" width={size} height={size} draggable="false" />;
}

function Socket({ kind, socket, onPick, label }) {
  const art = RUNE_ART[socket.open ? SOCKET_ART[kind] : 'socket_lock'];
  return (
    <button type="button" className={`rune-socket${socket.open ? '' : ' rune-socket--locked'}`} onClick={() => onPick(socket)}
      aria-label={socket.rune ? socket.rune.name : socket.open ? 'Пустой слот' : 'Закрытый слот'}>
      <img className="rune-socket__bg" src={art} alt="" draggable="false" />
      {socket.rune && <span className="rune-socket__rune"><RuneIcon rune={socket.rune} size={40} /></span>}
      {!socket.open && socket.price && <small className="rune-socket__price">💰 {gold(socket.price)}</small>}
      {label && <small className="rune-socket__label">{label}</small>}
    </button>
  );
}

function fits(rune, kind, slot, data, skill) {
  if (rune.kind !== kind || rune.count < 1) return false;
  if (kind === 'gear') {
    const place = slot.split(':')[0];
    if (rune.classes.length && !rune.classes.includes(data.base_class)) return false;
    return rune.place === 'weapon' ? place === 'weapon' : place !== 'weapon';
  }
  if (kind === 'skill') return !rune.tag_id || skill?.tags.includes(rune.tag_id);
  return true;
}

function Mastery({ rune }) {
  const left = Math.max(rune.next - rune.absorbed, 0);
  return (
    <div className="rune-mastery">
      <div className="rune-mastery__row">
        <b>{rune.efficiency}%</b>
        <small>до {rune.next_pct}% - ещё {gold(left)} {copiesWord(left)}</small>
      </div>
      <Bar value={rune.absorbed} max={rune.next} thin />
    </div>
  );
}

function RuneInfo({ rune }) {
  return (
    <div className="rune-info">
      <p className="rune-info__text">{rune.text}</p>
      <small className="rune-info__meta">
        {rune.rarity_title}, {PVP[rune.pvp]}
        {rune.tag ? `, только в ${rune.tag}` : ''}
        {rune.place ? `, ${rune.place === 'weapon' ? 'в оружие' : 'в доспех'}` : ''}
      </small>
      {!rune.ready && <small className="rune-info__soon">Пока не действует - подключим в ближайших обновлениях.</small>}
      <Mastery rune={rune} />
    </div>
  );
}

function RuneSheet({ rune, busy, onAbsorb, onClose }) {
  const [count, setCount] = useState(1);
  const max = rune.count;
  return (
    <Sheet title={rune.name} icon={<RuneIcon rune={rune} size={28} />} onClose={onClose}>
      <RuneInfo rune={rune} />
      <p className="rune-sheet__have">В сумке: {rune.count}</p>
      {max > 0 && (
        <div className="rune-absorb">
          <p className="rune-absorb__hint">Впитанная копия исчезает и навсегда поднимает твоё мастерство этой руны.</p>
          <div className="rune-absorb__row">
            <input type="range" min={1} max={max} value={Math.min(count, max)} onChange={(e) => setCount(Number(e.target.value))} />
            <b>{Math.min(count, max)}</b>
          </div>
          <button type="button" className="pill-btn" disabled={busy} onClick={() => onAbsorb(rune.id, Math.min(count, max))}>
            Впитать {Math.min(count, max)} {copiesWord(Math.min(count, max))}
          </button>
        </div>
      )}
    </Sheet>
  );
}

function SocketSheet({ kind, socket, data, skill, busy, onEquip, onUnequip, onBuy, onClose }) {
  if (!socket.open) {
    return (
      <Sheet title="Закрытый слот" icon="🔒" onClose={onClose}>
        {socket.price ? (
          <>
            <p>Открыть слот за 💰 {gold(socket.price)}? У тебя 💰 {gold(data.gold)}.</p>
            <button type="button" className="pill-btn" disabled={busy || data.gold < socket.price} onClick={onBuy}>
              Открыть за {gold(socket.price)}
            </button>
          </>
        ) : <p>Сначала открой предыдущий слот.</p>}
      </Sheet>
    );
  }
  const options = data.runes.filter((r) => fits(r, kind, socket.slot, data, skill) && r.id !== socket.rune?.id);
  return (
    <Sheet title={socket.rune ? socket.rune.name : 'Пустой слот'} icon={socket.rune ? <RuneIcon rune={socket.rune} size={28} /> : '◯'} onClose={onClose}>
      {!data.home && <p className="rune-warn">Менять руны можно только в родном городе.</p>}
      {socket.rune && (
        <>
          <RuneInfo rune={socket.rune} />
          <button type="button" className="pill-btn" disabled={busy || !data.home} onClick={onUnequip}>Снять в сумку</button>
        </>
      )}
      <p className="rune-sheet__sub">{options.length ? (socket.rune ? 'Заменить на:' : 'Вставить:') : 'В сумке нет подходящих рун.'}</p>
      <div className="rune-options">
        {options.map((r) => (
          <button key={r.id} type="button" className="rune-option" disabled={busy || !data.home} onClick={() => onEquip(r.id)}>
            <RuneIcon rune={r} size={36} />
            <span className="rune-option__main"><b>{r.name}</b><small>{r.text}</small></span>
            <small className="rune-option__count">×{r.count}</small>
          </button>
        ))}
      </div>
    </Sheet>
  );
}

export default function RunesPage({ data, onData, kind, onKind }) {
  const [openSocket, setOpenSocket] = useState(null);
  const [openRune, setOpenRune] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function act(action, params, after) {
    setBusy(true);
    setError(null);
    try {
      const next = await runeAction(action, params);
      onData(next);
      after?.(next);
    } catch (err) {
      setError(err?.message?.includes(' ') ? err.message : 'Не получилось.');
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <p className="hero-error">Загружаем руны...</p>;
  const open = openSocket;
  const bag = data.runes.filter((r) => r.kind === kind);
  const skillOf = (slot) => data.skills.find((s) => slot.startsWith(`${s.id}:`));

  return (
    <div className="runes">
      <Tabs>
        {KINDS.map((k) => (
          <TabsItem key={k.id} selected={kind === k.id} onClick={() => onKind(k.id)}>{k.title}</TabsItem>
        ))}
      </Tabs>
      {!data.home && <p className="rune-warn">Смотреть можно везде, менять руны - только в родном городе.</p>}

      {kind === 'hero' && (
        <div className="rune-grid">
          {data.hero.map((s) => <Socket key={s.slot} kind="hero" socket={s} onPick={setOpenSocket} />)}
        </div>
      )}
      {kind === 'gear' && (
        <>
          <div className="rune-grid rune-grid--gear">
            {data.gear.map((p) => p.slots.map((s) => <Socket key={s.slot} kind="gear" socket={s} onPick={setOpenSocket} label={p.title} />))}
          </div>
          <p className="rune-hint">Ещё два слота в каждой вещи откроются с заточкой.</p>
        </>
      )}
      {kind === 'skill' && (
        <div className="rune-skills">
          {data.skills.map((sk) => (
            <div key={sk.id} className="rune-skill">
              <b className="rune-skill__name">{sk.name}</b>
              <div className="rune-skill__slots">
                {sk.slots.map((s) => <Socket key={s.slot} kind="skill" socket={s} onPick={setOpenSocket} />)}
              </div>
            </div>
          ))}
        </div>
      )}
      {error && <p className="hero-error">{error}</p>}

      <h3 className="rune-bag__title">Твои руны</h3>
      {bag.length === 0 && <p className="rune-hint">Руны падают с мобов. Их можно купить и продать на рынке.</p>}
      <div className="rune-bag">
        {bag.map((r) => (
          <button key={r.id} type="button" className="rune-bag__item" onClick={() => setOpenRune(r.id)}>
            <RuneIcon rune={r} size={40} />
            <span className="rune-bag__main">
              <b>{r.name}</b>
              <small>{r.efficiency}% · в сумке {r.count}</small>
              <Bar value={r.absorbed} max={r.next} thin />
            </span>
          </button>
        ))}
      </div>

      {open && (
        <SocketSheet
          kind={kind} socket={open} data={data} skill={kind === 'skill' ? skillOf(open.slot) : null} busy={busy}
          onClose={() => setOpenSocket(null)}
          onBuy={() => act(kind === 'hero' ? 'buy_hero' : 'buy_skill', kind === 'skill' ? { skill: open.slot.split(':')[0] } : {}, () => setOpenSocket(null))}
          onEquip={(rune) => act('equip', { kind, slot: open.slot, rune }, () => setOpenSocket(null))}
          onUnequip={() => act('unequip', { kind, slot: open.slot }, () => setOpenSocket(null))}
        />
      )}
      {openRune && data.runes.find((r) => r.id === openRune) && (
        <RuneSheet
          rune={data.runes.find((r) => r.id === openRune)} busy={busy}
          onClose={() => setOpenRune(null)}
          onAbsorb={(rune, count) => act('absorb', { rune, count })}
        />
      )}
    </div>
  );
}

/** Круг рун героя под ногами силуэта: 12 гнёзд по эллипсу картинки. */
export function RuneRing({ data, onOpen }) {
  if (!data) return null;
  return (
    <button type="button" className="rune-ring" onClick={onOpen} aria-label="Руны героя">
      <img className="rune-ring__bg" src={RUNE_ART.circle} alt="" draggable="false" />
      {data.hero.map((s, i) => {
        const angle = (Math.PI * 2 * i) / data.hero.length - Math.PI / 2;
        const x = 50 + 37 * Math.cos(angle);
        const y = 46 + 24 * Math.sin(angle);
        return (
          <span key={s.slot} className={`rune-ring__dot${s.open ? '' : ' rune-ring__dot--locked'}`} style={{ left: `${x}%`, top: `${y}%` }}>
            <img src={RUNE_ART[s.open ? 'socket_hero' : 'socket_lock']} alt="" draggable="false" />
            {s.rune && <RuneIcon rune={s.rune} size={22} />}
          </span>
        );
      })}
    </button>
  );
}
