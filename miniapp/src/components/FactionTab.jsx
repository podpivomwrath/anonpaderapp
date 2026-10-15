import { useCallback, useEffect, useState } from 'react';
import { Button, Div, Group, Header, Placeholder, Spinner, Tabs, TabsItem } from '@vkontakte/vkui';
import { getTrade, tradeAction } from '../api.js';
import { itemIcon } from '../itemIcons.js';
import ItemIcon from './ItemIcon.jsx';

// Вкладка «Фракция» (2026-10-15): торговая фирма и процветание городов.
// Цены, пути, шансы и правила считает сервер (services/trade_service.py,
// services/faction_service.py) - здесь только показ готовых чисел и кнопки.
// Повозки ездят сами: игрок только отправляет каждую на одно плечо.

const SECTIONS = [
  { id: 'trade', title: '🐂 Торговля' },
  { id: 'factions', title: '🏛 Фракции' },
];
const TIER_CLASS = { 1: '', 2: 'trade-tier--2', 3: 'trade-tier--3', 4: 'trade-tier--4' };

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');

function duration(seconds) {
  const m = Math.max(Math.round(seconds / 60), 1);
  const h = Math.floor(m / 60);
  return h ? `${h} ч ${m % 60} мин` : `${m} мин`;
}

function ago(minutes) {
  if (minutes < 1) return 'только что';
  if (minutes < 60) return `${minutes} мин назад`;
  const h = Math.floor(minutes / 60);
  return h < 24 ? `${h} ч назад` : `${Math.floor(h / 24)} дн назад`;
}

// Товар: картинка, а пока её нет - эмодзи.
function GoodName({ g, size = 22, count }) {
  const key = `good:${g.id}`;
  return (
    <span className={`trade-good ${TIER_CLASS[g.tier]}`}>
      {itemIcon(key) ? <ItemIcon icon={key} size={size} /> : g.emoji}
      <span>{g.name}{count != null ? ` ×${count}` : ''}</span>
    </span>
  );
}

function NameForm({ busy, min, max, label, onSubmit }) {
  const [name, setName] = useState('');
  const clean = name.trim();
  return (
    <div className="guild-row">
      <input
        className="guild-input" placeholder="Название фирмы" maxLength={max} value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <Button size="m" disabled={busy || clean.length < min} onClick={() => onSubmit(clean)}>{label}</Button>
    </div>
  );
}

// --- Отправка повозки ---------------------------------------------------------

function DispatchSheet({ cart, gold, routeTitles, orders, busy, onSend, onClose }) {
  const [dest, setDest] = useState(cart.destinations[0]?.city);
  const [route, setRoute] = useState('safe');
  const [counts, setCounts] = useState({});
  const target = cart.destinations.find((d) => d.city === dest);
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const free = cart.capacity - total;
  const cost = cart.goods.reduce((sum, g) => sum + (counts[g.id] || 0) * g.price, 0);
  const orderFor = (city, goodId) => orders.find((o) => o.city === city && o.good.id === goodId);
  // Ящики по заказу - по цене заказа, остальные - по цене города.
  const revenue = cart.goods.reduce((sum, g) => {
    const n = counts[g.id] || 0;
    const o = orderFor(dest, g.id);
    const byOrder = o ? Math.min(n, o.left) : 0;
    return sum + (o ? byOrder * o.price : 0) + (n - byOrder) * (target?.prices[g.id] || 0);
  }, 0);
  const set = (id, n) => setCounts({ ...counts, [id]: Math.max(0, n) });
  const info = target?.routes[route];
  const goods = Object.fromEntries(Object.entries(counts).filter(([, n]) => n > 0));

  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet trade-dest" role="dialog" aria-label="Отправить повозку">
        <div className="trade-dest__title"><b>🐂 Повозка №{cart.slot}</b><span className="craft-hint">из {cart.city_title}</span></div>

        <div className="trade-dest__section">Куда</div>
        <div className="faction-choice">
          {cart.destinations.map((d) => (
            <button key={d.city} type="button"
              className={`faction-choice__item${d.city === dest ? ' faction-choice__item--active' : ''}`}
              onClick={() => setDest(d.city)}>
              {d.title}
              <span className="craft-hint">
                {d.kind === 'deficit' ? 'сосед, нехватка' : 'напротив, дальний рынок'}
                {cart.goods.some((g) => orderFor(d.city, g.id)) ? ' · 📜 заказ' : ''}
              </span>
            </button>
          ))}
        </div>

        <div className="trade-dest__section">Путь</div>
        <div className="faction-choice">
          {target && Object.entries(target.routes).map(([id, r]) => (
            <button key={id} type="button"
              className={`faction-choice__item${id === route ? ' faction-choice__item--active' : ''}`}
              onClick={() => setRoute(id)}>
              {routeTitles[id]}
              <span className="craft-hint">{duration(r.seconds)} · нападение ~{Math.round(r.ambush * 100)}%</span>
            </button>
          ))}
        </div>

        <div className="trade-dest__section">Закупить здесь · кузов {total}/{cart.capacity}</div>
        {cart.goods.map((g) => {
          const n = counts[g.id] || 0;
          return (
            <div key={g.id} className="trade-dest__row">
              <span className="trade-dest__good">
                <GoodName g={g} />
                <span className="trade-dest__note">
                  {' '}{g.locked ? `с ${g.min_level} ур. торговли` : `${money(g.price)} → ${money(target?.prices[g.id])}`}
                  {!g.locked && orderFor(dest, g.id)
                    ? ` · 📜 заказ: ещё ${orderFor(dest, g.id).left} ящ. по ${money(orderFor(dest, g.id).price)}` : ''}
                </span>
              </span>
              {!g.locked && (
                <div className="faction-qty">
                  <Button size="s" mode="secondary" disabled={n <= 0} onClick={() => set(g.id, n - 1)}>−</Button>
                  <span className="faction-qty__value">{n}</span>
                  <Button size="s" mode="secondary" disabled={free <= 0} onClick={() => set(g.id, n + 1)}>+</Button>
                  <Button size="s" mode="tertiary" disabled={free <= 0} onClick={() => set(g.id, n + free)}>все</Button>
                </div>
              )}
            </div>
          );
        })}
        <p className="craft-hint">
          Закупка ~{money(cost)} · выручка там сейчас ~{money(revenue)}
          {cost ? ` · прибыль ~${money(revenue - cost)}` : ''}. Цена ползёт с каждым ящиком, а продажа - по цене
          на момент прибытия. Пустую повозку можно перегнать порожняком.
        </p>
        {info && <p className="craft-hint">В пути {duration(info.seconds)}, шанс нападения ~{Math.round(info.ambush * 100)}%.</p>}

        <div className="trade-dest__actions">
          <Button size="l" stretched disabled={busy || cost > gold || !target}
            onClick={() => onSend({ slot: cart.slot, to: dest, route, goods })}>
            {cost > gold ? 'Не хватает золота' : 'Отправить'}
          </Button>
          <Button size="l" stretched mode="secondary" onClick={onClose}>Закрыть</Button>
        </div>
      </div>
    </>
  );
}

// --- Повозка --------------------------------------------------------------------

function CartCard({ cart, gold, busy, act, onDispatch }) {
  const [workshop, setWorkshop] = useState(false);
  const traveling = cart.status === 'traveling';
  return (
    <Group header={<Header>🐂 Повозка №{cart.slot} · {traveling ? `в пути в ${cart.to_title}` : cart.city_title}</Header>}>
      <Div>
        {traveling ? (
          <p className="guild-line">
            Прибудет через ~{duration(cart.seconds_left)} · путь {cart.route === 'safe' ? 'безопасный' : 'короткий'}
          </p>
        ) : (
          <p className="guild-line">Стоит в городе и ждёт.</p>
        )}
        <p className="guild-line">
          📦 {traveling ? `Груз ${cart.crates}/${cart.capacity}` : `Кузов ${cart.capacity} ящ.`}
          {' · '}🛡 Обшивка {cart.durability}/{cart.max_durability}
        </p>
        {cart.cargo.length > 0 && (
          <div className="trade-cargo">
            {cart.cargo.map((g) => <span key={g.id} className="trade-chip"><GoodName g={g} size={20} count={g.count} /></span>)}
          </div>
        )}
        {!traveling && (
          <div className="guild-row">
            {cart.durability > 0 ? (
              <Button size="m" disabled={busy} onClick={() => onDispatch(cart)}>Отправить</Button>
            ) : (
              <span className="craft-hint">Обшивка выбита - почини.</span>
            )}
            {cart.repair_cost > 0 && (
              <Button size="m" mode="secondary" disabled={busy || gold < cart.repair_cost}
                onClick={() => act('repair', { slot: cart.slot })}>
                Починить · {money(cart.repair_cost)}
              </Button>
            )}
            <Button size="m" mode="tertiary" onClick={() => setWorkshop(!workshop)}>
              {workshop ? 'Скрыть мастерскую' : '🔧 Мастерская'}
            </Button>
          </div>
        )}
        {!traveling && workshop && cart.parts.map((p) => (
          <div key={p.id} className="trade-dest__row">
            <span className="trade-dest__good">
              {p.emoji} {p.name} {p.level}/{p.max}: {p.value} {p.unit}
              <span className="trade-dest__note">
                {p.cost ? ` → ${p.next_value} · ${money(p.cost.gold)} + ${p.cost.ore} ×${p.cost.ore_count} (есть ${p.cost.ore_have})` : ' · предел'}
              </span>
            </span>
            {p.cost && (
              <Button size="s" mode="secondary"
                disabled={busy || gold < p.cost.gold || p.cost.ore_have < p.cost.ore_count}
                onClick={() => act('upgrade', { slot: cart.slot, part: p.id })}>
                Улучшить
              </Button>
            )}
          </div>
        ))}
      </Div>
    </Group>
  );
}

function Orders({ data, busy, act }) {
  const { firm } = data;
  return (
    <Group header={<Header>📜 Срочные заказы</Header>}>
      <Div>
        {data.orders.length === 0 ? (
          <p className="craft-hint">Сейчас заказов нет. Новые появляются раз в несколько часов.</p>
        ) : data.orders.map((o) => (
          <div key={o.id} className="trade-dest__row">
            <span className="trade-dest__good">
              {o.title}: <GoodName g={o.good} />
              <span className="trade-dest__note"> · ещё {o.left} из {o.total} ящ. · {duration(o.minutes_left * 60)}</span>
            </span>
            <b className="trade-dest__price">{money(o.price)}</b>
          </div>
        ))}
        <p className="craft-hint">
          Город платит на {data.order_bonus_pct}% дороже и вдвое больше процветания. Заказ общий: кто довёз первым,
          тот и получил. Если заказ закрыли, пока повозка в пути, груз уйдёт по обычной цене.
        </p>
        {firm?.name && (
          <label className="guild-check">
            <input type="checkbox" checked={firm.notify_orders} disabled={busy}
              onChange={(e) => act('notify', { orders: e.target.checked })} />
            Сообщать в чат о новых заказах
          </label>
        )}
      </Div>
    </Group>
  );
}

function Trade({ data, busy, act }) {
  const [dispatching, setDispatching] = useState(null);
  const { firm } = data;

  if (!firm) {
    return (
      <Group header={<Header>🏛 Торговая фирма</Header>}>
        <Div>
          <div className="trade-intro">
            <ItemIcon icon="trade:cart" size={64} />
            <p className="guild-line">
              Открой фирму, и её повозки будут возить товар между городами сами: закупаешь товар там, где его
              делают, выбираешь город и путь, а по прибытии повозка продаёт груз. Ты в это время свободен.
            </p>
          </div>
          {data.level < data.min_level ? (
            <p className="craft-hint">Торговля открывается с {data.min_level} уровня.</p>
          ) : (
            <>
              <p className="craft-hint">Фирма стоит {money(data.firm_price)} золота. Название дашь сразу после покупки.</p>
              <Button size="l" stretched disabled={busy || data.gold < data.firm_price} onClick={() => act('buy_firm')}>
                Открыть фирму за {money(data.firm_price)}
              </Button>
            </>
          )}
        </Div>
      </Group>
    );
  }

  if (!firm.name) {
    return (
      <Group header={<Header>{firm.migrated ? '🏛 Твоя повозка стала фирмой' : '🏛 Название фирмы'}</Header>}>
        <Div>
          {firm.migrated && (
            <p className="guild-line">
              Торговля теперь идёт удалённо: повозки ездят сами, а ты отправляешь их из этой вкладки. Улучшения и
              уровень торговли сохранились, груз возмещён золотом.
            </p>
          )}
          <p className="guild-line">
            Дай фирме название: {data.name_min}-{data.name_max} символов, уникальное, сменить его пока нельзя. Без
            названия повозки не отправить.
          </p>
          <NameForm busy={busy} min={data.name_min} max={data.name_max} label="Назвать"
            onSubmit={(name) => act('name_firm', { name })} />
        </Div>
      </Group>
    );
  }

  return (
    <>
      <Group header={<Header>🏛 «{firm.name}» · торговля {firm.trade_level} ур.{firm.sell_bonus_pct ? ` · +${firm.sell_bonus_pct}% к выручке` : ''}</Header>}>
        <Div>
          <div className="trade-xp">
            <div className="trade-xp__bar" style={{ width: `${Math.round((100 * firm.trade_xp) / firm.xp_next)}%` }} />
          </div>
          <p className="craft-hint">
            Опыт {firm.trade_xp} / {firm.xp_next} · прибыль за всё время {money(firm.profit_total)} · у тебя 💰 {money(data.gold)}
          </p>
          <p className="guild-line">
            🏛 Процветание {data.home_title}: сегодня ты принёс {firm.today_points} из {firm.daily_cap} очков.
          </p>
          <label className="guild-check">
            <input type="checkbox" checked={firm.notify_arrival} disabled={busy}
              onChange={(e) => act('notify', { arrival: e.target.checked })} />
            Сообщать в чат, когда повозка доехала
          </label>
        </Div>
      </Group>

      <Orders data={data} busy={busy} act={act} />

      {data.carts.map((cart) => (
        <CartCard key={cart.slot} cart={cart} gold={data.gold} busy={busy} act={act} onDispatch={setDispatching} />
      ))}

      {firm.next_cart && (
        <Group>
          <Div>
            {firm.trade_level < firm.next_cart.level ? (
              <p className="craft-hint">Повозка №{firm.next_cart.slot} - с {firm.next_cart.level} уровня торговли за {money(firm.next_cart.gold)} золота.</p>
            ) : (
              <Button size="m" stretched disabled={busy || data.gold < firm.next_cart.gold} onClick={() => act('buy_cart')}>
                Купить повозку №{firm.next_cart.slot} за {money(firm.next_cart.gold)}
              </Button>
            )}
          </Div>
        </Group>
      )}

      <Group header={<Header>📜 Журнал рейсов</Header>}>
        {data.trips.length === 0 ? (
          <Div><p className="craft-hint">Рейсов ещё не было.</p></Div>
        ) : (
          <Div>
            {data.trips.map((t) => (
              <div key={t.id} className="trade-dest__row">
                <span className="trade-dest__good">
                  №{t.slot} {t.from_title} → {t.to_title}
                  <span className="trade-dest__note">
                    {' · '}{t.crates ? `${t.crates} ящ.` : 'порожняком'}
                    {t.ambushes ? ` · ⚔ ${t.ambushes}` : ''}
                    {t.lost ? ` · 💥 ${t.lost}` : ''}
                    {t.order_crates ? ` · 📜 по заказу ${t.order_crates}` : ''}
                    {' · '}{ago(t.minutes_ago)}
                    {t.event ? <><br />🛤 {t.event}</> : null}
                  </span>
                </span>
                <b className={`trade-dest__price ${t.profit >= 0 ? 'faction-plus' : 'faction-minus'}`}>
                  {t.crates ? `${t.profit >= 0 ? '+' : ''}${money(t.profit)}` : '-'}
                </b>
              </div>
            ))}
          </Div>
        )}
      </Group>

      {dispatching && (
        <DispatchSheet
          cart={dispatching} gold={data.gold} routeTitles={data.routes} orders={data.orders} busy={busy}
          onSend={async (params) => { if (await act('dispatch', params)) setDispatching(null); }}
          onClose={() => setDispatching(null)}
        />
      )}
    </>
  );
}

// --- Фракции -------------------------------------------------------------------

function pct(v) {
  return v > 0 ? `+${v}%` : `${v}%`;
}

function Factions({ data }) {
  return (
    <>
      {data.factions.map((f) => {
        const lo = f.tier.min_points;
        const hi = f.next ? f.next.min_points : f.max;
        const fill = Math.min(100, Math.round((100 * (f.points - lo)) / Math.max(hi - lo, 1)));
        const home = f.city === data.home;
        return (
          <Group key={f.city} header={<Header>{f.title}{home ? ' · твой город' : ''}</Header>}>
            <Div>
              <p className="guild-line"><b>{f.tier.emoji} {f.tier.name}</b> · {money(f.points)} очков</p>
              <div className="guild-bar"><div className="guild-bar__fill" style={{ width: `${fill}%` }} /></div>
              <p className="craft-hint">
                {f.next ? `До ступени «${f.next.name}» - ${money(f.next.min_points - f.points)} очков.` : 'Высшая ступень.'}
                {' '}Сегодня торговцы принесли +{money(f.today)}, падение за сутки ~{money(f.decay_day)}.
              </p>
              {f.first_supplier && <p className="guild-line">🏆 Первый поставщик недели: <b>{f.first_supplier}</b></p>}
              {f.week_top.length > 0 && (
                <p className="craft-hint">
                  Лидеры этой недели: {f.week_top.map((w, i) => `${i + 1}. ${w.name} (${money(w.points)})`).join(', ')}
                </p>
              )}
              <p className="guild-line">
                {f.tier.elixir_pct || f.tier.relic_pct
                  ? `Зелья в лавке ${pct(f.tier.elixir_pct)}, реликвии у скупщика ${pct(f.tier.relic_pct)}.`
                  : 'Цены лавки и скупщика обычные.'}
              </p>
            </Div>
          </Group>
        );
      })}
      <Group>
        <details className="board-rules">
          <summary>Как растёт процветание</summary>
          <div className="craft-hint">
            <p>Каждый проданный повозкой ящик приносит очки родному городу торговца, куда бы он ни возил. У одного
              торговца есть дневной потолок, он растёт с уровнем торговли. Без торговли процветание медленно падает:
              за пару недель город теряет половину.</p>
            <p>Скидки и надбавки действуют для всех, кто покупает и продаёт в этом городе.</p>
            <p>Каждый понедельник подводятся итоги недели. Первый поставщик фракции получает по 2 Пепельных ларца,
              Ларца руды и Ларца расходников, второй - по одному, третий - Пепельный ларец. Первый поставщик всю
              следующую неделю получает долю налога с переводов игрокам своей фракции.</p>
            {data.tiers.map((t) => (
              <p key={t.id}>{t.emoji} {t.name} - от {money(t.min_points)}: зелья {pct(t.elixir_pct)}, реликвии {pct(t.relic_pct)}</p>
            ))}
          </div>
        </details>
      </Group>
    </>
  );
}

export default function FactionTab({ onWallet }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [section, setSection] = useState('trade');

  const load = useCallback(() => {
    getTrade().then((d) => { setData(d); setStatus('ready'); }).catch(() => setStatus('error'));
  }, []);
  useEffect(() => { load(); }, [load]);

  // Повозка в пути: перечитать, когда ближайшая должна доехать (и раз в минуту).
  useEffect(() => {
    const left = (data?.carts || []).filter((c) => c.status === 'traveling').map((c) => c.seconds_left);
    if (!left.length) return undefined;
    const wait = Math.min(Math.min(...left) + 20, 60) * 1000;
    const id = setTimeout(load, wait);
    return () => clearTimeout(id);
  }, [data, load]);

  const act = async (action, params) => {
    setBusy(true);
    try {
      const d = await tradeAction(action, params);
      setData(d);
      onWallet?.({ farm_currency: d.gold });
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
    return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}><Spinner size="l" /></Div>;
  }
  if (status === 'error' || !data) {
    return <Placeholder action={<Button onClick={load}>Ещё раз</Button>}>Не удалось открыть вкладку.</Placeholder>;
  }

  return (
    <>
      <Tabs>
        {SECTIONS.map((s) => (
          <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>{s.title}</TabsItem>
        ))}
      </Tabs>
      {notice && (
        <Div className={`craft-notice ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`} onClick={() => setNotice(null)}>
          {notice.text}
        </Div>
      )}
      {section === 'trade' ? <Trade data={data} busy={busy} act={act} /> : <Factions data={data} />}
    </>
  );
}
