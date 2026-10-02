import { useCallback, useEffect, useState } from 'react';
import { Button, Div, Group, Header, Placeholder, SimpleCell, Spinner } from '@vkontakte/vkui';
import { getTrade, tradeAction } from '../api.js';
import TradeDestination from './TradeDestination.jsx';

// Торговля: повозка, Торговый дом города (или караван), куда везти.
// Цены и правила считает сервер (services/trade_service.py) - здесь только
// показ готовых чисел и кнопки. Повозка едет по клеткам, как маунт: путь и
// значок - на вкладке «Карта».

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');
const TIER_CLASS = { 1: '', 2: 'trade-tier--2', 3: 'trade-tier--3', 4: 'trade-tier--4' };

function minutes(seconds) {
  return seconds >= 60 ? `~${Math.round(seconds / 60)} мин` : `~${Math.round(seconds)} сек`;
}

export default function TradeTab({ onWallet }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [counts, setCounts] = useState({});
  const [dest, setDest] = useState(null);

  const load = useCallback(() => {
    getTrade().then((d) => { setData(d); setStatus('ready'); }).catch(() => setStatus('error'));
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (action, params) => {
    setBusy(true);
    try {
      const d = await tradeAction(action, params);
      setData(d);
      onWallet?.({ farm_currency: d.gold });
      setNotice({ ok: true, text: d.done });
    } catch (err) {
      setNotice({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  if (status === 'loading') {
    return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}><Spinner size="l" /></Div>;
  }
  if (status === 'error' || !data) {
    return <Placeholder action={<Button onClick={load}>Ещё раз</Button>}>Не удалось открыть торговлю.</Placeholder>;
  }

  const { cart, place } = data;
  const count = (id) => counts[id] || 1;
  const setCount = (id, n) => setCounts({ ...counts, [id]: Math.max(1, Math.min(50, n)) });

  const noticeBlock = notice && (
    <Div className={`craft-notice ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`} onClick={() => setNotice(null)}>
      {notice.text}
    </Div>
  );

  if (!cart) {
    return (
      <>
        {noticeBlock}
        <Group header={<Header>🐂 Торговый обоз</Header>}>
          <Div>
            <p className="guild-line">
              Покупай товар там, где его производят, и вези туда, где его не хватает. Повозка едет по клеткам
              сама; в пути на неё нападают, а в глубине мира (кольца 3-5) её могут ограбить игроки.
            </p>
            {data.level < data.min_level ? (
              <p className="craft-hint">Торговля открывается с {data.min_level} уровня.</p>
            ) : place?.kind === 'city' ? (
              <Button size="l" stretched disabled={busy || data.gold < data.cart_price} onClick={() => act('buy_cart')}>
                Купить повозку за {money(data.cart_price)} золота
              </Button>
            ) : (
              <p className="craft-hint">Повозку продают в Торговом доме любого города.</p>
            )}
          </Div>
        </Group>
      </>
    );
  }

  const free = cart.capacity - cart.crates;

  return (
    <>
      {noticeBlock}

      <Group header={<Header>🐂 Повозка · торговля {cart.trade_level} ур.</Header>}>
        <Div>
          <div className="trade-xp">
            <div className="trade-xp__bar" style={{ width: `${Math.round((100 * cart.trade_xp) / cart.xp_next)}%` }} />
          </div>
          <p className="craft-hint">
            Опыт {cart.trade_xp} / {cart.xp_next} · прибыль за всё время {money(cart.profit_total)} · у тебя 💰 {money(data.gold)}
          </p>
          <p className="guild-line">
            {cart.traveling
              ? 'Повозка в пути - следи за ней на карте.'
              : cart.here
                ? `Повозка с тобой, (${cart.x}; ${cart.y}).`
                : `Повозка стоит в (${cart.x}; ${cart.y}) - торговать можно только рядом с ней.`}
          </p>
          <p className="guild-line">
            📦 Груз {cart.crates} / {cart.capacity} · 🛡 Обшивка {cart.durability} / {cart.max_durability}
            {' · '}⚠ Нападение за переход к соседу ~{Math.round(cart.trip_ambush * 100)}%
          </p>
          {cart.cargo.length > 0 ? (
            <div className="trade-cargo">
              {cart.cargo.map((g) => (
                <span key={g.id} className={`trade-chip ${TIER_CLASS[g.tier]}`}>
                  {g.emoji} {g.name} ×{g.count}
                </span>
              ))}
            </div>
          ) : (
            <p className="craft-hint">Кузов пуст.</p>
          )}
        </Div>
      </Group>

      {place && cart.here && (
        <Group header={<Header>{place.kind === 'city' ? '🏛' : '🐪'} {place.title}</Header>}>
          {place.kind === 'caravan' && <Div><p className="craft-hint">Караван покупает дороже города и продаёт дешевле, но ненадолго и немного.</p></Div>}
          {place.offers.map((o) => {
            const inCart = cart.cargo.find((g) => g.id === o.id)?.count || 0;
            const n = count(o.id);
            return (
              <Div key={o.id} className="trade-offer">
                <div className="trade-offer__head">
                  <span className={`trade-offer__name ${TIER_CLASS[o.tier]}`}>{o.emoji} {o.name}</span>
                  <span className="craft-hint">
                    {o.tier_name} · {o.city_title}
                    {o.deficit ? ' · дефицит' : ''}
                    {o.stock != null ? ` · осталось ${o.stock}` : ''}
                  </span>
                </div>
                <div className="trade-offer__row">
                  <div className="exchange-lots">
                    <Button size="s" mode="secondary" disabled={n <= 1} onClick={() => setCount(o.id, n - 1)}>−</Button>
                    <span className="exchange-lots__value">{n}</span>
                    <Button size="s" mode="secondary" onClick={() => setCount(o.id, n + 1)}>+</Button>
                  </div>
                  {o.buy != null && (
                    <Button
                      size="s"
                      disabled={busy || o.locked || free < n || data.gold < o.buy * n}
                      onClick={() => act('buy', { good: o.id, count: n })}
                    >
                      {o.locked ? `с ${o.min_level} ур. торговли` : `Купить · ${money(o.buy)}/ящ`}
                    </Button>
                  )}
                  {o.sell != null && (
                    <Button
                      size="s"
                      mode="secondary"
                      disabled={busy || inCart < n}
                      onClick={() => act('sell', { good: o.id, count: n })}
                    >
                      Продать · {money(o.sell)}/ящ{inCart ? ` (есть ${inCart})` : ''}
                    </Button>
                  )}
                </div>
              </Div>
            );
          })}
          <Div><p className="craft-hint">Цена за несколько ящиков считается по каждому: продажи насыщают рынок, и цена ползёт вниз, а покупки поднимают её. Рынок отходит за несколько часов.</p></Div>
        </Group>
      )}

      <Group header={<Header>🧭 Куда везти</Header>}>
        {data.cities.map((c) => (
          <SimpleCell
            key={c.region}
            onClick={() => setDest({ ...c, kind: 'city' })}
            subtitle={c.route?.cells === 0 ? 'ты здесь' : `${c.route?.cells} клеток · ${minutes(c.route?.seconds || 0)} · ждёт: ${c.wants}`}
            after="›"
          >
            {c.title}
          </SimpleCell>
        ))}
        {data.caravans.map((c) => (
          <SimpleCell
            key={c.id}
            onClick={() => setDest({ ...c, kind: 'caravan', title: '🐪 Караван' })}
            subtitle={`${c.route?.cells} клеток · ${minutes(c.route?.seconds || 0)} · уйдёт через ${c.minutes_left} мин`}
            after="›"
          >
            🐪 Караван ({c.x}; {c.y})
          </SimpleCell>
        ))}
        <Div><p className="craft-hint">Нажми на город или караван - что там продают и покупают. Путь напрямик через центр короче, но опаснее.</p></Div>
      </Group>

      {dest && (
        <TradeDestination
          dest={dest}
          cargo={cart.cargo}
          canGo={cart.here}
          busy={busy}
          onGo={async () => { await act('send', { x: dest.x, y: dest.y }); setDest(null); }}
          onClose={() => setDest(null)}
        />
      )}

      {cart.here && place?.kind === 'city' && (
        <Group header={<Header>🔧 Мастерская повозок</Header>}>
          {cart.parts.map((p) => (
            <SimpleCell
              key={p.id}
              multiline
              subtitle={
                p.cost
                  ? `→ ${p.next_value} ${p.unit} · ${money(p.cost.gold)} золота + ${p.cost.ore} ×${p.cost.ore_count} (есть ${p.cost.ore_have})`
                  : 'предел'
              }
              after={p.cost && (
                <Button
                  size="s"
                  mode="secondary"
                  disabled={busy || data.gold < p.cost.gold || p.cost.ore_have < p.cost.ore_count}
                  onClick={() => act('upgrade', { part: p.id })}
                >
                  Улучшить
                </Button>
              )}
            >
              {p.emoji} {p.name} {p.level}/{p.max}: {p.value} {p.unit}
            </SimpleCell>
          ))}
          {cart.repair_cost > 0 && (
            <Div>
              <Button size="m" stretched mode="secondary" disabled={busy || data.gold < cart.repair_cost} onClick={() => act('repair')}>
                Починить обшивку за {money(cart.repair_cost)} золота
              </Button>
            </Div>
          )}
        </Group>
      )}

    </>
  );
}
