import { useCallback, useEffect, useState } from 'react';
import { Button, Div, Group, Header, Placeholder, SimpleCell, Spinner } from '@vkontakte/vkui';
import { exchangeTrade, getExchange } from '../api.js';

// Биржа самоцветов. Игра - дилер: курс считает сервер по формуле
// (game/economy/exchange.py) от того, сколько самоцветов игроки купили и
// продали. Торгуют лотами по 100. Клиент только показывает готовые цены -
// цены 1..10 лотов подряд приходят с сервера, каждый лот сдвигает курс.

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');
const MAX_PREVIEW = 10;

function when(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
}

/** График курса по дням: точка - закрытие дня (снимок раз в сутки).
 *  Наведение или касание точки показывает цены лота в тот день. */
function DailyChart({ days }) {
  const [active, setActive] = useState(null);
  if (days.length === 0) {
    return <p className="craft-hint">График появится завтра: точка дня ставится после полуночи по Москве.</p>;
  }
  const w = 320;
  const h = 140;
  const pad = 10;
  const values = days.flatMap((d) => [d.buy, d.sell]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x = (i) => (days.length === 1 ? w / 2 : pad + (i / (days.length - 1)) * (w - 2 * pad));
  const y = (v) => pad + (1 - (v - min) / span) * (h - 2 * pad);
  const line = (key) => days.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(d[key]).toFixed(1)}`).join(' ');
  const cur = active !== null ? days[active] : null;
  const label = (iso) => new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' });
  return (
    <div className="exchange-chart" onMouseLeave={() => setActive(null)}>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <path className="exchange-chart__buy" d={line('buy')} />
        <path className="exchange-chart__sell" d={line('sell')} />
        {days.map((d, i) => (
          <g key={d.day}>
            <circle className="exchange-chart__dot exchange-chart__dot--buy" cx={x(i)} cy={y(d.buy)} r={active === i ? 4 : 2.6} />
            <circle className="exchange-chart__dot exchange-chart__dot--sell" cx={x(i)} cy={y(d.sell)} r={active === i ? 4 : 2.6} />
            {/* Широкая невидимая полоса - по точке легко попасть пальцем. */}
            <rect x={x(i) - Math.max((w - 2 * pad) / days.length / 2, 4)} y={0}
              width={Math.max((w - 2 * pad) / days.length, 8)} height={h} fill="transparent"
              onMouseEnter={() => setActive(i)} onClick={() => setActive(i)} />
          </g>
        ))}
      </svg>
      <div className="exchange-chart__axis">
        <span>{label(days[0].day)}</span>
        <span>{money(min)} - {money(max)} за лот</span>
        <span>{label(days[days.length - 1].day)}</span>
      </div>
      {cur ? (
        <div className="exchange-chart__tip">
          <b>{label(cur.day)}</b>: покупка лота <b className="exchange-chart__buy-text">{money(cur.buy)}</b>,
          продажа <b className="exchange-chart__sell-text">{money(cur.sell)}</b>.
          За день куплено лотов: {cur.bought}, продано: {cur.sold}.
        </div>
      ) : (
        <div className="exchange-chart__tip craft-hint">Наведи на точку или нажми на неё - покажу курс того дня.</div>
      )}
    </div>
  );
}

export default function ExchangeTab({ onWallet }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [lots, setLots] = useState(1);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    getExchange().then((d) => { setData(d); setStatus('ready'); }).catch(() => setStatus('error'));
  }, []);
  useEffect(() => { load(); }, [load]);

  const trade = async (direction) => {
    setBusy(true);
    try {
      const d = await exchangeTrade(direction, lots);
      setData(d);
      onWallet?.({ farm_currency: d.gold, donate_currency: d.gems });
      const done = d.done;
      setNotice({
        ok: true,
        text: direction === 'buy'
          ? `Куплено ${money(done.gems)} 💎 за ${money(done.gold)} золота.`
          : `Продано ${money(done.gems)} 💎 за ${money(done.gold)} золота`
            + (done.net !== undefined && done.net !== done.gold ? ` (после налога гильдии ${money(done.net)})` : '') + '.',
      });
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
    return <Placeholder action={<Button onClick={load}>Ещё раз</Button>}>Не удалось открыть биржу.</Placeholder>;
  }

  const buyCost = data.buy_series[lots - 1];
  const sellGain = data.sell_series[lots - 1];
  const gems = lots * data.lot;
  const net = data.tax ? sellGain - Math.floor((sellGain * data.tax) / 100) : sellGain;

  return (
    <>
      <Group header={<Header>💱 Курс за {data.lot} 💎</Header>}>
        <Div>
          <div className="exchange-rates">
            <div className="exchange-rate">
              <span className="craft-hint">Купить</span>
              <b>{money(data.buy_lot)}</b>
            </div>
            <div className="exchange-rate">
              <span className="craft-hint">Продать</span>
              <b>{money(data.sell_lot)}</b>
            </div>
          </div>
          <p className="craft-hint">
            Начальная цена - {money(data.start_lot)} за {data.lot} 💎. Каждый купленный лот поднимает цену
            следующего на {data.growth_pct}%, каждый проданный - опускает: курс складывается из сделок всех
            игроков. Продажа на {data.spread_pct}% дешевле покупки, поэтому перепродать с выгодой нельзя.
          </p>
          <p className="guild-line">У тебя: 💰 {money(data.gold)} · 💎 {money(data.gems)}</p>
        </Div>
      </Group>

      {notice && (
        <Div className={`craft-notice ${notice.ok ? 'craft-notice--ok' : 'craft-notice--bad'}`} onClick={() => setNotice(null)}>
          {notice.text}
        </Div>
      )}

      <Group header={<Header>Сделка</Header>}>
        <Div className="guild-form">
          <div className="exchange-lots">
            <Button size="m" mode="secondary" disabled={lots <= 1} onClick={() => setLots(lots - 1)}>−</Button>
            <span className="exchange-lots__value">{lots} × {data.lot} = {money(gems)} 💎</span>
            <Button size="m" mode="secondary" disabled={lots >= MAX_PREVIEW} onClick={() => setLots(lots + 1)}>+</Button>
          </div>
          <Button size="l" stretched disabled={busy || data.gold < buyCost} onClick={() => trade('buy')}>
            Купить {money(gems)} 💎 за {money(buyCost)} золота
          </Button>
          <Button size="l" stretched mode="secondary" disabled={busy || data.gems < gems} onClick={() => trade('sell')}>
            Продать {money(gems)} 💎 за {money(sellGain)} золота
          </Button>
          {data.tax > 0 && (
            <p className="craft-hint">Налог гильдии {data.tax}%: с продажи на руки придёт {money(net)}.</p>
          )}
          {lots > 1 && (
            <p className="craft-hint">Цена за несколько лотов уже учитывает сдвиг курса после каждого лота.</p>
          )}
        </Div>
      </Group>

      <Group header={<Header>📈 Курс по дням</Header>}>
        <Div><DailyChart days={data.chart} /></Div>
      </Group>

      {data.mine.length > 0 && (
        <Group header={<Header>Мои сделки</Header>}>
          {data.mine.map((o, i) => (
            <SimpleCell key={i} subtitle={when(o.at)} after={`${money(o.gold)} 💰`}>
              {o.direction === 'buy' ? 'Купил' : 'Продал'} {money(o.gems)} 💎
            </SimpleCell>
          ))}
        </Group>
      )}
    </>
  );
}
