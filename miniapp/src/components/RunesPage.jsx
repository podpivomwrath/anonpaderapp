import { useState } from 'react';
import { TabsItem } from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { Bar, Sheet } from './ui.jsx';
import { runeAction } from '../api.js';
import { RUNE_ART, RUNE_ICONS } from '../runeIcons.js';

/**
 * Руны (2026-10-31, владелец): страница на вкладке «Герой». Подвкладки, все
 * слоты сразу; закрытый слот - под замком, нажатие предлагает купить.
 * Менять руны можно только в родном городе. Мастерство - у игрока: лишние
 * копии впитываются, эффективность растёт по порогам.
 *
 * Руны-навыки (2026-11-10): навык - это руна. Три слота навыков, в каждой
 * руне-навыке гнёзда огранок (второе - со ступени II), ступени I-IV и
 * развилка на ступени III.
 */

const KINDS = [
  { id: 'ability', title: 'Навыки' },
  { id: 'hero', title: 'Героя' },
  { id: 'gear', title: 'Экипировки' },
];
const SOCKET_ART = { hero: 'socket_hero', gear: 'socket_gear', skill: 'socket_skill', ability: 'socket_ability' };
const PVP = { full: 'в PvP в полную силу', half: 'в PvP вполсилы', none: 'в PvP не действует' };
const STEP_NAMES = ['', 'I', 'II', 'III', 'IV'];

function copiesWord(n) {
  const d = n % 10;
  if (d === 1 && n % 100 !== 11) return 'копия';
  return d >= 2 && d <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'копии' : 'копий';
}

const gold = (n) => n.toLocaleString('ru-RU');

export function RuneIcon({ rune, size = 48 }) {
  const url = rune && RUNE_ICONS[rune.id];
  const rar = rune?.rarity;
  if (!url) {
    // Картинки рун-навыков ещё нет - первая буква названия на камне.
    if (rune?.kind === 'ability') {
      const letter = rune.name.slice(0, 1);
      const cls = `rune-icon rune-icon--empty rune-icon--letter rune-icon--${rar}`;
      return <span className={cls} style={{ width: size, height: size }}>{letter}</span>;
    }
    return <span className="rune-icon rune-icon--empty" style={{ width: size, height: size }} />;
  }
  return <img className={`rune-icon rune-icon--${rar}`} src={url} alt="" width={size} height={size} draggable="false" />;
}

// Под гнездом - подпись места и название вставленной руны (2026-11-06,
// предложение игрока: картинки мелкие и похожи, без приближения не отличить).
function Socket({ kind, socket, onPick, label }) {
  const art = RUNE_ART[socket.open ? SOCKET_ART[kind] : 'socket_lock'] || RUNE_ART.socket_skill;
  return (
    <div className="rune-cell">
      <button type="button" className={`rune-socket${socket.open ? '' : ' rune-socket--locked'}`} onClick={() => onPick(socket, kind)}
        aria-label={socket.rune ? socket.rune.name : socket.open ? 'Пустой слот' : 'Закрытый слот'}>
        <img className="rune-socket__bg" src={art} alt="" draggable="false" />
        {socket.rune && <span className="rune-socket__rune"><RuneIcon rune={socket.rune} size={40} /></span>}
      </button>
      {label && <small className="rune-cell__label">{label}</small>}
      {socket.rune && <b className="rune-cell__name">{socket.rune.name}</b>}
      {!socket.open && socket.price && <small className="rune-cell__label">💰 {gold(socket.price)}</small>}
      {!socket.open && socket.need_step && <small className="rune-cell__label">ступень {STEP_NAMES[socket.need_step]}</small>}
    </div>
  );
}

function fits(rune, kind, slot, data, ability) {
  if (rune.kind !== kind || rune.count < 1) return false;
  if (kind === 'gear') {
    const place = slot.split(':')[0];
    return rune.place === 'weapon' ? place === 'weapon' : place !== 'weapon';
  }
  if (kind === 'skill') return !rune.tag_id || ability?.skill?.tags.includes(rune.tag_id);
  if (kind === 'ability') return !data.abilities.some((a) => a.rune?.id === rune.id);
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
      {rune.summary && <p className="rune-info__text">{rune.summary}</p>}
      {rune.scaling_text && <p className="rune-info__text">Бьёт от характеристик: {rune.scaling_text}.</p>}
      <p className="rune-info__text">{rune.kind === 'ability' ? `Сила навыка ${rune.efficiency}%.` : rune.text}</p>
      <small className="rune-info__meta">
        {rune.rarity_title}{rune.kind === 'ability' ? '' : `, ${PVP[rune.pvp]}`}
        {rune.tag ? `, только в ${rune.tag}` : ''}
        {rune.place ? `, ${rune.place === 'weapon' ? 'в оружие' : 'в доспех'}` : ''}
        {rune.kind === 'ability' && rune.step ? `, ступень ${STEP_NAMES[rune.step]}` : ''}
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
          <p className="rune-absorb__hint">Впитанная копия исчезает и навсегда поднимает ваше мастерство этой руны.</p>
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

/** Ступени руны-навыка: что даёт каждая и сколько копий до неё. Развилку
 * ступени III выбирают дома, менять бесплатно. Пробуждение видит только сам
 * игрок. */
function StepsSheet({ ability, data, busy, onFork, onClose }) {
  const absorbed = ability.rune.absorbed;
  return (
    <Sheet title={ability.skill.name} icon={<RuneIcon rune={ability.rune} size={28} />} onClose={onClose}>
      <p className="rune-info__text">{ability.summary}</p>
      <p className="rune-sheet__sub">Ступени навыка. Мастерство: {gold(absorbed)} {copiesWord(absorbed)}.</p>
      <ol className="rune-steps">
        {ability.steps.map((st) => (
          <li key={st.n} className={`rune-step${st.done ? ' rune-step--done' : ''}`}>
            <div className="rune-step__head">
              <b>Ступень {STEP_NAMES[st.n]}{st.n === 4 ? ' - пробуждение' : ''}</b>
              <small>{st.done ? 'открыта' : `ещё ${gold(Math.max(st.need - absorbed, 0))} ${copiesWord(Math.max(st.need - absorbed, 0))}`}</small>
            </div>
            {st.text && <p>{st.text}</p>}
            {st.fork && (
              <div className="rune-fork">
                {st.fork.map((text, i) => (
                  <button key={text} type="button" disabled={busy || !st.done || !data.home}
                    className={`rune-fork__opt${st.chosen === i + 1 ? ' rune-fork__opt--chosen' : ''}`}
                    onClick={() => onFork(i + 1)}>
                    <b>{i === 0 ? 'а' : 'б'}</b> {text}
                  </button>
                ))}
                {st.done && !st.chosen && <small>Выберите одно - менять можно дома, бесплатно.</small>}
              </div>
            )}
            {st.pvp_note && <small>{st.pvp_note}</small>}
          </li>
        ))}
      </ol>
    </Sheet>
  );
}

function SocketSheet({ kind, socket, data, ability, busy, onEquip, onUnequip, onBuy, onClose }) {
  if (!socket.open) {
    return (
      <Sheet title="Закрытый слот" icon="🔒" onClose={onClose}>
        {socket.need_step ? (
          <p>Второе гнездо огранки откроется на ступени {STEP_NAMES[socket.need_step]} этого навыка.</p>
        ) : socket.price ? (
          <>
            <p>Открыть слот за 💰 {gold(socket.price)}? У вас 💰 {gold(data.gold)}.</p>
            <button type="button" className="pill-btn" disabled={busy || data.gold < socket.price} onClick={onBuy}>
              Открыть за {gold(socket.price)}
            </button>
          </>
        ) : <p>Сначала откройте предыдущий слот.</p>}
      </Sheet>
    );
  }
  const options = data.runes.filter((r) => fits(r, kind, socket.slot, data, ability) && r.id !== socket.rune?.id);
  const empty = kind === 'ability' ? 'В сумке нет других рун-навыков.' : 'В сумке нет подходящих рун.';
  return (
    <Sheet title={socket.rune ? socket.rune.name : 'Пустой слот'} icon={socket.rune ? <RuneIcon rune={socket.rune} size={28} /> : '◯'} onClose={onClose}>
      {!data.home && <p className="rune-warn">Менять руны можно только в родном городе.</p>}
      {socket.rune && (
        <>
          <RuneInfo rune={socket.rune} />
          <button type="button" className="pill-btn" disabled={busy || !data.home} onClick={onUnequip}>Снять в сумку</button>
          {kind === 'ability' && <p className="rune-hint">Огранки этого навыка при замене вернутся в сумку.</p>}
        </>
      )}
      <p className="rune-sheet__sub">{options.length ? (socket.rune ? 'Заменить на:' : 'Вставить:') : empty}</p>
      <div className="rune-options">
        {options.map((r) => (
          <button key={r.id} type="button" className="rune-option" disabled={busy || !data.home} onClick={() => onEquip(r.id)}>
            <RuneIcon rune={r} size={36} />
            <span className="rune-option__main"><b>{r.name}</b><small>{r.summary || r.text}{r.scaling_text ? ` ${r.scaling_text}.` : ''}</small></span>
            <small className="rune-option__count">×{r.count}</small>
          </button>
        ))}
      </div>
    </Sheet>
  );
}

/** Слот руны-навыка: сама руна, ступень, гнёзда огранок, кнопка ступеней. */
function AbilityCard({ ability, index, onPick, onSteps }) {
  return (
    <div className="rune-ability">
      <div className="rune-ability__main">
        <Socket kind="ability" socket={ability} onPick={onPick} label={`Навык ${index + 1}`} />
        {ability.rune ? (
          <div className="rune-ability__info">
            <small>перезарядка {ability.skill.cd} · сила {ability.rune.efficiency}%</small>
            <p>{ability.summary}</p>
            {ability.scaling?.length > 0 && (
              // От каких характеристик бьёт навык (2026-11-11, владелец): так виден билд.
              <small className="rune-ability__scale">
                {ability.scaling.map((x) => `${x.pct}% ${x.title} (у вас ${x.have})`).join(' и ')}
                {ability.damage ? ` → урон ${ability.damage}` : ''}
              </small>
            )}
            <button type="button" className="pill-btn pill-btn--small" onClick={() => onSteps(ability)}>
              {/* Пробуждение видит только сам игрок - значок на его же карточке. */}
              {ability.step === 4 && RUNE_ART.awakened && <img className="rune-awakened" src={RUNE_ART.awakened} alt="" />}
              {ability.step ? `Ступень ${STEP_NAMES[ability.step]}` : 'Ступени'}
            </button>
          </div>
        ) : <p className="rune-hint">Пустой слот: вставьте руну-навык, и навык появится в бою.</p>}
      </div>
      {ability.rune && (
        <div className="rune-ability__facets">
          {ability.facets.map((s, i) => (
            <Socket key={s.slot} kind="skill" socket={s} onPick={onPick} label={`Огранка ${i + 1}`} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function RunesPage({ data, onData, kind, onKind }) {
  const [openSocket, setOpenSocket] = useState(null);
  const [openRune, setOpenRune] = useState(null);
  const [steps, setSteps] = useState(null);
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
  const tab = KINDS.some((k) => k.id === kind) ? kind : 'ability';
  const open = openSocket;
  // Надетые - первыми и в зелёной рамке (репорт 340): в общей куче их было не найти.
  // На подвкладке навыков - и руны-навыки, и огранки.
  const bagKinds = tab === 'ability' ? ['ability', 'skill'] : [tab];
  const bag = data.runes.filter((r) => bagKinds.includes(r.kind))
    .sort((x, y) => Number(Boolean(y.equipped)) - Number(Boolean(x.equipped)) || x.kind.localeCompare(y.kind));
  const abilityOf = (slot) => data.abilities.find((a) => a.skill && slot.startsWith(`${a.skill.id}:`));
  const liveSteps = steps && data.abilities.find((a) => a.slot === steps.slot && a.rune);

  return (
    <div className="runes">
      <Tabs>
        {KINDS.map((k) => (
          <TabsItem key={k.id} selected={tab === k.id} onClick={() => onKind(k.id)}>{k.title}</TabsItem>
        ))}
      </Tabs>
      {!data.home && <p className="rune-warn">Смотреть можно везде, менять руны - только в родном городе.</p>}

      {tab === 'ability' && (
        <div className="rune-abilities">
          {data.passive ? (
            <div className="rune-passive">
              <b>Пассивка: {data.passive.title}</b>
              {data.passive.lines.map((line) => <small key={line}>{line}</small>)}
            </div>
          ) : (
            <p className="rune-hint">Навыки - это руны: любой навык подходит любому классу. Подкласс на 30 уровне добавит пассивку.</p>
          )}
          {data.abilities.map((a, i) => (
            <AbilityCard key={a.slot} ability={a} index={i} onPick={(s, k) => setOpenSocket({ ...s, kind: k })}
              onSteps={setSteps} />
          ))}
        </div>
      )}
      {tab === 'hero' && (
        <div className="rune-grid">
          {data.hero.map((s) => <Socket key={s.slot} kind="hero" socket={s} onPick={(x, k) => setOpenSocket({ ...x, kind: k })} />)}
        </div>
      )}
      {tab === 'gear' && (
        <>
          <div className="rune-grid rune-grid--gear">
            {data.gear.map((p) => p.slots.map((s) => (
              <Socket key={s.slot} kind="gear" socket={s} onPick={(x, k) => setOpenSocket({ ...x, kind: k })} label={p.title} />
            )))}
          </div>
          <p className="rune-hint">Ещё два слота в каждой вещи откроются с заточкой.</p>
        </>
      )}
      {error && <p className="hero-error">{error}</p>}

      <h3 className="rune-bag__title">Ваши руны</h3>
      {bag.length === 0 && <p className="rune-hint">Руны падают с мобов, в руинах и разломах. Их можно купить и продать на рынке.</p>}
      <div className="rune-bag">
        {bag.map((r) => (
          <button key={r.id} type="button" className={`rune-bag__item${r.equipped ? ' rune-bag__item--worn' : ''}`} onClick={() => setOpenRune(r.id)}>
            <RuneIcon rune={r} size={40} />
            <span className="rune-bag__main">
              <b>{r.name}</b>
              <small>{r.kind === 'skill' ? 'огранка · ' : ''}{r.efficiency}% · в сумке {r.count}</small>
              <Bar value={r.absorbed} max={r.next} thin />
            </span>
          </button>
        ))}
      </div>

      {open && (
        <SocketSheet
          kind={open.kind} socket={open} data={data} ability={open.kind === 'skill' ? abilityOf(open.slot) : null} busy={busy}
          onClose={() => setOpenSocket(null)}
          onBuy={() => act('buy_hero', {}, () => setOpenSocket(null))}
          onEquip={(rune) => act('equip', { kind: open.kind, slot: open.slot, rune }, () => setOpenSocket(null))}
          onUnequip={() => act('unequip', { kind: open.kind, slot: open.slot }, () => setOpenSocket(null))}
        />
      )}
      {liveSteps && (
        <StepsSheet ability={liveSteps} data={data} busy={busy} onClose={() => setSteps(null)}
          onFork={(fork) => act('fork', { skill: liveSteps.skill.id, fork })} />
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

// Эллипс нарисованного круга в долях блока (2.4:1): центр, полуоси.
const RING = { cx: 50, cy: 46, rx: 37, ry: 24, aspect: 2.4 };

/** n точек по эллипсу на РАВНЫХ расстояниях по линии, а не по равным углам:
 * на сплюснутом эллипсе равные углы сбивают гнёзда в кучу по бокам. */
function ringPoints(n) {
  const steps = 720;
  const rx = RING.rx;
  const ry = RING.ry / RING.aspect; // в тех же единицах, что ширина
  const pts = [];
  const acc = [0];
  for (let k = 0; k <= steps; k += 1) {
    const t = -Math.PI / 2 + (Math.PI * 2 * k) / steps;
    pts.push([Math.cos(t), Math.sin(t)]);
    if (k) acc.push(acc[k - 1] + Math.hypot(rx * (pts[k][0] - pts[k - 1][0]), ry * (pts[k][1] - pts[k - 1][1])));
  }
  const total = acc[steps];
  const out = [];
  let k = 0;
  for (let i = 0; i < n; i += 1) {
    const want = (total * i) / n;
    while (acc[k] < want) k += 1;
    out.push([RING.cx + RING.rx * pts[k][0], RING.cy + RING.ry * pts[k][1]]);
  }
  return out;
}

/** Круг рун героя под ногами силуэта: 12 гнёзд по эллипсу картинки. */
export function RuneRing({ data, onOpen }) {
  if (!data) return null;
  return (
    <button type="button" className="rune-ring" onClick={onOpen} aria-label="Руны героя">
      <img className="rune-ring__bg" src={RUNE_ART.circle} alt="" draggable="false" />
      {ringPoints(data.hero.length).map(([x, y], i) => {
        const s = data.hero[i];
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
