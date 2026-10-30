import { useEffect, useState } from 'react';
import { Button, Div, Group, Header, Placeholder } from '@vkontakte/vkui';
import { contractAction, getContracts } from '../api.js';
import ClassIcon from './ClassIcon.jsx';
import Skeleton from './Skeleton.jsx';
import { Bar, Empty, SectionHead } from './ui.jsx';

/**
 * «Заказы» на «Доске» (2026-10-16): анонимный заказ убийств игрока за
 * самоцветы. Правила и проверки - на сервере (services/contract_service.py),
 * здесь - список, форма и кнопки.
 */

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');

function left(minutes) {
  const h = Math.floor(minutes / 60);
  return h ? `${h} ч ${minutes % 60} мин` : `${minutes} мин`;
}

function OrderForm({ data, busy, act }) {
  const { rules } = data;
  const [name, setName] = useState('');
  const [kills, setKills] = useState(1);
  const [price, setPrice] = useState(String(rules.min_price));
  const [confirming, setConfirming] = useState(false);
  const priceNum = parseInt(price, 10) || 0;
  const total = kills * priceNum;
  const valid = name.trim().length >= 3 && priceNum >= rules.min_price;

  const submit = async () => {
    const ok = await act('create', { name: name.trim(), kills, price: priceNum });
    setConfirming(false);
    if (ok) { setName(''); setKills(1); setPrice(String(rules.min_price)); }
  };

  return (
    <Group header={<Header>📜 Оформить заказ</Header>}>
      <Div>
        <div className="guild-row">
          <input className="guild-input" placeholder="Ник цели" maxLength={16} value={name}
            onChange={(e) => { setName(e.target.value); setConfirming(false); }} />
        </div>
        <div className="contract-kills">
          <span className="craft-hint">Убийств:</span>
          {Array.from({ length: rules.max_kills - rules.min_kills + 1 }, (_, i) => rules.min_kills + i).map((n) => (
            <button key={n} type="button"
              className={`faction-choice__item contract-kills__n${n === kills ? ' faction-choice__item--active' : ''}`}
              onClick={() => { setKills(n); setConfirming(false); }}>{n}</button>
          ))}
        </div>
        <div className="guild-row">
          <span className="craft-hint">💎 за одно убийство:</span>
          <input className="guild-input guild-input--short" type="number" min={rules.min_price} value={price}
            onChange={(e) => { setPrice(e.target.value); setConfirming(false); }} />
        </div>
        <p className="craft-hint">
          Итого 💎{money(total)} (у тебя 💎{money(data.gems)}), списываются сразу. Заказ висит {rules.hours} ч,
          невыполненный остаток сгорает. Цель - с {rules.target_min_level} уровня. Кто заказал, не узнает никто;
          цели придёт весть, что на неё заказ.
        </p>
        {confirming ? (
          <div className="guild-row">
            <Button size="m" disabled={busy} onClick={submit}>Да, заказать за 💎{money(total)}</Button>
            <Button size="m" mode="secondary" disabled={busy} onClick={() => setConfirming(false)}>Отмена</Button>
          </div>
        ) : (
          <Button size="m" disabled={busy || !valid || total > data.gems} onClick={() => setConfirming(true)}>
            {total > data.gems ? 'Не хватает самоцветов' : `Заказать за 💎${money(total)}`}
          </Button>
        )}
      </Div>
    </Group>
  );
}

export default function ContractsSection() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  useEffect(() => {
    getContracts().then((d) => { setData(d); setStatus('ready'); }).catch(() => setStatus('error'));
  }, []);

  // Взял заказ - «📍 где цель» обновляется сама (2026-10-30): раньше клетка
  // оставалась той, что была при открытии, а цель уже уехала.
  const tracking = Boolean(data?.contracts?.some((c) => c.where));
  useEffect(() => {
    if (!tracking) return undefined;
    const id = setInterval(() => {
      getContracts().then(setData).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [tracking]);

  const act = async (action, params) => {
    setBusy(true);
    try {
      const d = await contractAction(action, params);
      setData(d);
      setNotice({ ok: true, text: d.done });
      return true;
    } catch (err) {
      setNotice({ ok: false, text: err.message });
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (status === 'loading') {
    return <Skeleton />;
  }
  if (status === 'error' || !data) return <Placeholder>Не удалось загрузить заказы.</Placeholder>;

  return (
    <>
      {notice && (
        <Div className={`craft-notice ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`} onClick={() => setNotice(null)}>
          {notice.text}
        </Div>
      )}
      <SectionHead
        kind="board" icon="🎯" value={data.contracts.length} label="открытых заказов"
        aside={<>💎 {money(data.gems)}<br /><small>у тебя</small></>}
      />
      <Group header={<Header>🎯 Открытые заказы</Header>}>
        {data.contracts.length === 0 && <Empty icon="🎯">Сейчас заказов нет.</Empty>}
        <div className="card-list">
          {data.contracts.map((c) => (
            <div className={`contract-card${c.on_me ? ' contract-card--me' : ''}`} key={c.id}>
              <ClassIcon subclass={c.subclass} baseClass={c.base_class} crown={c.crown_frame || null} size={48} />
              <div className="contract-card__body">
                <b className="contract-card__name">{c.name}</b>
                <small className="contract-card__meta">{c.level} ур. · мощь {money(c.power)} · ещё {left(c.minutes_left)}</small>
                {c.where && <small className="contract-card__meta">📍 {c.where}</small>}
                <span className="daily-card__progress">
                  <Bar value={c.kills_total - c.kills_left} max={c.kills_total} tone="red" thin />
                  <span className="daily-card__count">{c.kills_total - c.kills_left}/{c.kills_total}</span>
                </span>
                {c.hunters ? <small className="contract-card__meta">взяли: {c.hunters}</small> : null}
              </div>
              <span className="contract-card__side">
                <b className="contract-card__price">💎{money(c.price)}</b>
                {c.on_me ? <small>на тебя</small>
                  : c.mine ? <small>твой заказ</small>
                    : c.taken ? <small>взят</small>
                      : c.guildmate ? <small>согильдиец</small>
                        : <button type="button" className="pill-btn pill-btn--main" disabled={busy} onClick={() => act('take', { id: c.id })}>Взять</button>}
              </span>
            </div>
          ))}
        </div>
        <Div>
          <p className="craft-hint">
            Цена - за одно убийство, охотник получает её за вычетом комиссии 10%. Взявшие видят цель на карте и находят
            её даже в АФК и на озере: там нападение обрывает рыбалку. На руднике цель не тронут, пока она внутри штольни. Не тронут и в городе, у Монолита и у мирового босса.
            Убили вместе - награда делится поровну между теми, кто взял заказ и бил цель.
            Клейма за такое убийство нет. Где цели - команда /заказ.
          </p>
        </Div>
      </Group>
      <OrderForm data={data} busy={busy} act={act} />
    </>
  );
}
