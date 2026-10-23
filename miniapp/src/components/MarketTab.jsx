import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Div, Group, Header, Placeholder, TabsItem } from '@vkontakte/vkui';
import { getMarket, getMarketGood, marketAction } from '../api.js';
import ExchangeTab from './ExchangeTab.jsx';
import ItemIcon from './ItemIcon.jsx';
import PriceChart from './PriceChart.jsx';
import Tabs from './ScrollTabs.jsx';
import Skeleton from './Skeleton.jsx';
import { SectionHead, Sheet } from './ui.jsx';
import '../market.css';

// Рынок (2026-10-23): заявки на товары («продам/куплю по цене», сходятся -
// сделка сама), витрина некованых уникальных вещей, свои заявки и ящик
// купленного, биржа самоцветов. Сервер - bot/miniapp_market_api.py.

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');

const SECTIONS = [
  { id: 'goods', title: 'Товары' },
  { id: 'showcase', title: 'Витрина' },
  { id: 'mine', title: 'Мои заявки' },
  { id: 'exchange', title: 'Биржа' },
];

function Icon({ icon, emoji, size = 32 }) {
  const img = icon ? <ItemIcon icon={icon} alt="" size={size} /> : null;
  return img || <span className="market-emoji" aria-hidden="true">{emoji}</span>;
}

function NumberField({ label, value, onChange, max }) {
  return (
    <label className="market-field">
      <span>{label}</span>
      <input
        type="number" inputMode="numeric" min="1" max={max} value={value}
        onChange={(e) => onChange(Math.max(0, Math.floor(Number(e.target.value) || 0)))}
      />
    </label>
  );
}

function GoodSheet({ good, rules, gold, onClose, act, busy }) {
  const [info, setInfo] = useState(null);
  const [side, setSide] = useState('buy');
  const [qty, setQty] = useState(1);
  const [price, setPrice] = useState(good.sell || good.buy || good.last || 100);

  useEffect(() => {
    getMarketGood(good.key).then(setInfo).catch(() => setInfo({ book: { sells: [], buys: [] }, history: [], have: 0 }));
  }, [good.key]);

  const total = qty * price;
  const fee = Math.max(1, Math.round(total * rules.listing_fee_pct / 100));
  const net = total - Math.round(total * rules.sale_fee_pct / 100);
  const have = info?.have || 0;
  const tooSmall = total < rules.min_gold;
  const cant = side === 'sell' ? qty > have : total + fee > gold;
  const points = (info?.history || []).map(([t, avg]) => ({ t, buy: avg, sell: avg }));

  return (
    <Sheet title={good.name} icon={good.emoji} onClose={onClose} className="market-sheet">
      <div className="market-book">
        <div>
          <b>Продают</b>
          {(info?.book.sells || []).map(([p, q]) => (
            <button key={p} type="button" onClick={() => { setSide('buy'); setPrice(p); }}>{money(p)} <small>×{q}</small></button>
          ))}
          {info && !info.book.sells.length && <small className="market-muted">никто</small>}
        </div>
        <div>
          <b>Покупают</b>
          {(info?.book.buys || []).map(([p, q]) => (
            <button key={p} type="button" onClick={() => { setSide('sell'); setPrice(p); }}>{money(p)} <small>×{q}</small></button>
          ))}
          {info && !info.book.buys.length && <small className="market-muted">никто</small>}
        </div>
      </div>
      {points.length > 0 && <PriceChart points={points} />}

      <div className="market-switch">
        <button type="button" className={side === 'buy' ? 'is-on' : ''} onClick={() => setSide('buy')}>Купить</button>
        <button type="button" className={side === 'sell' ? 'is-on' : ''} onClick={() => setSide('sell')}>
          Продать{have ? ` (у тебя ${have})` : ''}
        </button>
      </div>
      <div className="market-form">
        <NumberField label="Сколько" value={qty} onChange={setQty} max={side === 'sell' ? have : undefined} />
        <NumberField label="Цена за штуку" value={price} onChange={setPrice} />
      </div>
      <p className="craft-hint">
        {side === 'buy'
          ? `Спишется ${money(total)} + ${money(fee)} за заявку. Найдётся дешевле - разница вернётся сразу.`
          : `Получишь ${money(net)} (минус ${rules.sale_fee_pct}%), за заявку - ${money(fee)}.`}
        {' '}Заявка висит {rules.hours} ч.
        {tooSmall && ` Заявка - от ${rules.min_gold} золота.`}
      </p>
      <Button
        size="l" stretched disabled={busy || !qty || !price || tooSmall || cant}
        onClick={() => act(side, { good: good.key, qty, price }, onClose)}
      >
        {side === 'buy' ? `Купить ×${qty} по ${money(price)}` : `Продать ×${qty} по ${money(price)}`}
      </Button>
    </Sheet>
  );
}

function Goods({ data, act, busy }) {
  const [category, setCategory] = useState(data.categories[0].id);
  const [open, setOpen] = useState(null);
  const goods = data.goods.filter((g) => g.category === category);
  // Сначала то, чем торгуют и что есть у игрока.
  const sorted = useMemo(() => [...goods].sort((a, b) => {
    const score = (g) => (g.sell || g.buy ? 2 : 0) + (data.have[g.key] ? 1 : 0);
    return score(b) - score(a);
  }), [goods, data.have]);
  const good = open ? data.goods.find((g) => g.key === open) : null;

  return (
    <Group>
      <div className="market-cats">
        {data.categories.map((c) => (
          <button key={c.id} type="button" className={c.id === category ? 'is-on' : ''} onClick={() => setCategory(c.id)}>
            {c.title}
          </button>
        ))}
      </div>
      <div className="market-list">
        {sorted.map((g) => (
          <button key={g.key} type="button" className="market-row" onClick={() => setOpen(g.key)}>
            <Icon icon={g.icon} emoji={g.emoji} />
            <span className="market-row__text">
              <b>{g.name}</b>
              <small>
                {g.sell ? `продают от ${money(g.sell)}` : 'не продают'}
                {' · '}
                {g.buy ? `покупают до ${money(g.buy)}` : 'не покупают'}
                {data.have[g.key] ? ` · у тебя ${data.have[g.key]}` : ''}
              </small>
            </span>
          </button>
        ))}
      </div>
      {good && (
        <GoodSheet good={good} rules={data.rules} gold={data.gold} busy={busy} act={act} onClose={() => setOpen(null)} />
      )}
    </Group>
  );
}

function Stats({ stats }) {
  const names = { str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Выносливость', wil: 'Воля' };
  return <small>{Object.entries(stats).map(([k, v]) => `${names[k] || k} +${v}`).join(' · ')}</small>;
}

function Showcase({ data, act, busy }) {
  const [listing, setListing] = useState(null);
  const [price, setPrice] = useState(1000);
  return (
    <>
      <Group header={<Header>🛡 На витрине</Header>}>
        {!data.showcase.length && <Div className="market-muted">Пока ничего не выставлено.</Div>}
        <div className="market-list">
          {data.showcase.map((o) => (
            <div key={o.id} className="market-row market-row--static">
              <Icon icon={o.item.icon} emoji="🔴" size={40} />
              <span className="market-row__text">
                <b>{o.item.label}</b>
                <Stats stats={o.item.stats} />
              </span>
              {o.mine
                ? <small className="market-muted">твой лот</small>
                : (
                  <Button size="s" disabled={busy || data.gold < o.price} onClick={() => act('buy_item', { order_id: o.id })}>
                    {money(o.price)}
                  </Button>
                )}
            </div>
          ))}
        </div>
      </Group>
      <Group header={<Header>Выставить свою вещь</Header>}>
        <Div className="craft-hint">
          Только некованые уникальные вещи. За выставление {data.rules.listing_fee_pct}% цены,
          с продажи {data.rules.sale_fee_pct}%. Лот висит {data.rules.hours} ч.
        </Div>
        {!data.my_items.length && <Div className="market-muted">Таких вещей в сумке нет.</Div>}
        <div className="market-list">
          {data.my_items.map((i) => (
            <button key={i.id} type="button" className="market-row" onClick={() => setListing(i)}>
              <Icon icon={i.icon} emoji="🔴" size={40} />
              <span className="market-row__text"><b>{i.label}</b><Stats stats={i.stats} /></span>
            </button>
          ))}
        </div>
      </Group>
      {listing && (
        <Sheet title={listing.label} icon="🛡" onClose={() => setListing(null)}>
          <div className="market-form"><NumberField label="Цена" value={price} onChange={setPrice} /></div>
          <Button
            size="l" stretched disabled={busy || price < data.rules.min_gold}
            onClick={() => act('list_item', { item_id: listing.id, price }, () => setListing(null))}
          >
            Выставить за {money(price)}
          </Button>
        </Sheet>
      )}
    </>
  );
}

function left(iso) {
  const h = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3600000));
  return `${h} ч`;
}

function Mine({ data, act, busy }) {
  return (
    <>
      <Group header={<Header>📦 Куплено</Header>}>
        {!data.inbox.length && <Div className="market-muted">Ящик пуст.</Div>}
        {data.inbox.map((r) => <Div key={r.good} className="market-line">{r.name} ×{r.qty}</Div>)}
        {data.inbox.length > 0 && (
          <Div>
            <Button size="l" stretched disabled={busy || !data.in_city} onClick={() => act('claim')}>Забрать</Button>
            {!data.in_city && <p className="craft-hint">Купленное забирают в городе - в любом.</p>}
          </Div>
        )}
      </Group>
      <Group header={<Header>Мои заявки · {data.orders.length} из {data.rules.max_orders}</Header>}>
        {!data.orders.length && <Div className="market-muted">Открытых заявок нет.</Div>}
        {data.orders.map((o) => (
          <div key={o.id} className="market-row market-row--static market-row--noicon">
            <span className="market-row__text">
              <b>{o.side === 'sell' ? 'Продаю' : 'Куплю'}: {o.name}</b>
              <small>×{o.qty_left}{o.qty_left !== o.qty_total ? ` из ${o.qty_total}` : ''} по {money(o.price)} · ещё {left(o.expires_at)}</small>
            </span>
            <Button size="s" mode="secondary" disabled={busy} onClick={() => act('cancel', { order_id: o.id })}>Снять</Button>
          </div>
        ))}
      </Group>
      {data.trades.length > 0 && (
        <Group header={<Header>Сделки</Header>}>
          {data.trades.map((t, i) => (
            <Div key={i} className="market-line">
              {t.side === 'buy' ? '🛒' : '💰'} {t.name} ×{t.qty} по {money(t.price)}
            </Div>
          ))}
        </Group>
      )}
    </>
  );
}

export default function MarketTab({ onWallet }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [section, setSection] = useState('goods');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    getMarket().then((d) => { setData(d); setStatus('ready'); }).catch(() => setStatus('error'));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (action, params = {}, after) => {
    setBusy(true);
    try {
      const d = await marketAction(action, params);
      setData(d);
      onWallet?.({ farm_currency: d.gold });
      const done = d.done || {};
      const text = {
        sell: done.filled ? `Продано сразу ${done.filled} шт., остальное - в заявке.` : 'Заявка на продажу выставлена.',
        buy: done.filled ? `Куплено сразу ${done.filled} шт. - забери в городе.` : 'Заявка на покупку выставлена.',
        list_item: 'Вещь на витрине.',
        buy_item: 'Куплено - забери в городе.',
        cancel: 'Заявка снята.',
        claim: `Забрано: ${(done.lines || []).join(', ')}.`,
      }[action];
      setNotice({ ok: true, text });
      after?.();
    } catch (err) {
      setNotice({ ok: false, text: err.details?.error || err.message || 'Не вышло.' });
    } finally {
      setBusy(false);
    }
  };

  if (section === 'exchange') {
    return (
      <>
        <MarketTabs section={section} setSection={setSection} />
        <ExchangeTab onWallet={onWallet} />
      </>
    );
  }
  if (status === 'loading') return <Skeleton />;
  if (status === 'error' || !data) {
    return <Placeholder action={<Button onClick={load}>Ещё раз</Button>}>Не удалось открыть рынок.</Placeholder>;
  }

  return (
    <>
      <SectionHead
        kind="market" icon="🏪" value={money(data.gold)} label="золота"
        aside={data.inbox.length ? <>📦 {data.inbox.length}<br /><small>в ящике</small></> : null}
      />
      <MarketTabs section={section} setSection={setSection} />
      {notice && (
        <Div className={`craft-notice ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`} onClick={() => setNotice(null)}>
          {notice.text}
        </Div>
      )}
      {section === 'goods' && <Goods data={data} act={act} busy={busy} />}
      {section === 'showcase' && <Showcase data={data} act={act} busy={busy} />}
      {section === 'mine' && <Mine data={data} act={act} busy={busy} />}
    </>
  );
}

function MarketTabs({ section, setSection }) {
  return (
    <Tabs>
      {SECTIONS.map((s) => (
        <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>{s.title}</TabsItem>
      ))}
    </Tabs>
  );
}
