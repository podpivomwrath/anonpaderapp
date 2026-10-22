import { useCallback, useEffect, useState } from 'react';
import { Button, Div, Group, Header, Placeholder, SimpleCell } from '@vkontakte/vkui';
import { exchangeTrade, getExchange } from '../api.js';
import PriceChart from './PriceChart.jsx';
import Skeleton from './Skeleton.jsx';
import { SectionHead } from './ui.jsx';

// Биржа самоцветов. Игра - дилер: курс считает сервер по формуле
// (game/economy/exchange.py) от того, сколько самоцветов игроки купили и
// продали. Торгуют лотами по 100. Клиент только показывает готовые цены -
// цены 1..10 лотов подряд приходят с сервера, каждый лот сдвигает курс.

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');
const MAX_PREVIEW = 10;

// Изменение курса покупки за сутки: последняя точка графика не позже суток
// назад против нынешней цены. Нет такой точки - стрелки нет.
function dayChange(chart, now) {
  const dayAgo = Date.now() - 86_400_000;
  const old = [...(chart || [])].reverse().find((p) => new Date(p.t).getTime() <= dayAgo);
  if (!old || !old.buy) return null;
  return ((now - old.buy) / old.buy) * 100;
}

function when(iso) {
  return iso ? new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '';
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
          : `Продано ${money(done.gems)} 💎 за ${money(done.gold)} золота.`,
      });
    } catch (err) {
      setNotice({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  };

  if (status === 'loading') {
    return <Skeleton />;
  }
  if (status === 'error' || !data) {
    return <Placeholder action={<Button onClick={load}>Ещё раз</Button>}>Не удалось открыть биржу.</Placeholder>;
  }

  const buyCost = data.buy_series[lots - 1];
  const sellGain = data.sell_series[lots - 1];
  const gems = lots * data.lot;
  const change = dayChange(data.chart, data.buy_lot);

  return (
    <>
      <SectionHead
        kind="exchange" icon="💱" value={money(data.buy_lot)}
        label={(
          <>
            золота за {data.lot} 💎
            {change != null && Math.abs(change) >= 0.05 && (
              <span className={change > 0 ? 'rate-delta rate-delta--up' : 'rate-delta rate-delta--down'}>
                {' '}{change > 0 ? '▲' : '▼'} {Math.abs(change).toFixed(1)}% за сутки
              </span>
            )}
          </>
        )}
        aside={<>💰 {money(data.gold)}<br /><small>💎 {money(data.gems)}</small></>}
      />

      <Group header={<Header>📈 Курс лота</Header>}>
        <Div><PriceChart points={data.chart} /></Div>
      </Group>

      <Group header={<Header>💱 Курс за {data.lot} 💎</Header>}>
        <Div>
          <div className="exchange-rates">
            <div className="exchange-rate exchange-rate--buy">
              <span className="craft-hint">Купить</span>
              <b>{money(data.buy_lot)}</b>
            </div>
            <div className="exchange-rate exchange-rate--sell">
              <span className="craft-hint">Продать</span>
              <b>{money(data.sell_lot)}</b>
            </div>
          </div>
          <p className="craft-hint">
            Начальная цена - {money(data.start_lot)} за {data.lot} 💎. Каждый купленный лот поднимает цену
            следующего на {data.growth_pct}%, каждый проданный - опускает: курс складывается из сделок всех
            игроков. Продажа на {data.spread_pct}% дешевле покупки, поэтому перепродать с выгодой нельзя.
          </p>
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
          {lots > 1 && (
            <p className="craft-hint">Цена за несколько лотов уже учитывает сдвиг курса после каждого лота.</p>
          )}
        </Div>
      </Group>

      {data.mine.length > 0 && (
        <Group header={<Header>Мои сделки</Header>}>
          {data.mine.map((o, i) => (
            <SimpleCell
              key={i} subtitle={when(o.at)}
              before={<span className={`deal-mark deal-mark--${o.direction}`} aria-hidden="true">{o.direction === 'buy' ? '↓' : '↑'}</span>}
              after={<span className={`deal-gold deal-gold--${o.direction}`}>{o.direction === 'buy' ? '−' : '+'}{money(o.gold)} 💰</span>}
            >
              {o.direction === 'buy' ? 'Купил' : 'Продал'} {money(o.gems)} 💎
            </SimpleCell>
          ))}
        </Group>
      )}
    </>
  );
}
