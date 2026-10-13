import { useEffect, useState } from 'react';
import { Button, Div, Group, Header, Placeholder, Spinner } from '@vkontakte/vkui';
import { buyShop, getShop } from '../api.js';

/**
 * Магазин (2026-10-13): товары за самоцветы квадратными карточками. Нажатие
 * на карточку открывает окно покупки снизу; у Метки Хранителя там ползунок
 * срока - чем дольше, тем дешевле день. Цены приходят с сервера на каждый
 * срок, и при покупке сервер считает цену заново.
 */

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');

function daysWord(n) {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return 'день';
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return 'дня';
  return 'дней';
}

function untilText(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleString('ru-RU', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' });
}

function BuySheet({ item, gems, onClose, onBought }) {
  const [days, setDays] = useState(Math.min(7, item.max));
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const price = item.prices[days];
  const perDay = Math.round((price / days) * 10) / 10;
  const firstDay = item.prices[item.min];
  const saving = Math.round((1 - price / (firstDay * days)) * 100);
  const enough = gems >= price;

  const buy = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await buyShop(item.id, days);
      onBought(res);
    } catch (err) {
      setError(err.details?.error || 'Не удалось купить.');
      setConfirming(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet shop-sheet" role="dialog" aria-label={item.title}>
        <div className="shop-sheet__head">
          <span className="shop-sheet__emoji" aria-hidden="true">{item.emoji}</span>
          <div>
            <b className="shop-sheet__title">{item.title}</b>
            {item.active_until && (
              <p className="shop-sheet__active">Активна до {untilText(item.active_until)} - новый срок прибавится сверху</p>
            )}
          </div>
        </div>
        <ul className="shop-sheet__perks">
          {item.perks.map((perk) => <li key={perk}>{perk}</li>)}
        </ul>
        <p className="craft-hint">{item.note}</p>

        <div className="shop-sheet__slider">
          <div className="shop-sheet__days">
            <b>{days} {daysWord(days)}</b>
            <span>💎 {money(price)}</span>
          </div>
          <input
            type="range"
            min={item.min}
            max={item.max}
            step={1}
            value={days}
            onChange={(e) => { setDays(Number(e.target.value)); setConfirming(false); }}
            aria-label="Срок"
          />
          <div className="shop-sheet__scale">
            <span>{item.min} {daysWord(item.min)}</span>
            <span>{item.max} {daysWord(item.max)}</span>
          </div>
          <p className="craft-hint">
            {perDay} 💎 за день{saving > 0 ? ` · выгода ${saving}% против покупки по дню` : ''}
          </p>
        </div>

        {error && <p className="shop-sheet__error">{error}</p>}
        {!enough && <p className="shop-sheet__error">Не хватает самоцветов: у тебя 💎 {money(gems)}.</p>}
        <div className="shop-sheet__actions">
          {confirming ? (
            <>
              <Button size="l" stretched disabled={busy} onClick={buy}>
                {busy ? 'Покупаем…' : `Да, купить за 💎 ${money(price)}`}
              </Button>
              <Button size="l" mode="secondary" stretched disabled={busy} onClick={() => setConfirming(false)}>Отмена</Button>
            </>
          ) : (
            <Button size="l" stretched disabled={!enough} onClick={() => setConfirming(true)}>
              Купить за 💎 {money(price)}
            </Button>
          )}
        </div>
      </div>
    </>
  );
}

export default function ShopTab({ onWallet, onBought }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [open, setOpen] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = () => {
    getShop()
      .then((d) => { setData(d); setStatus('ready'); onWallet?.({ donate_currency: d.gems }); })
      .catch(() => setStatus('error'));
  };
  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (status === 'loading') {
    return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}><Spinner size="l" /></Div>;
  }
  if (status === 'error' || !data) {
    return <Placeholder action={<Button onClick={load}>Ещё раз</Button>}>Магазин не открылся.</Placeholder>;
  }

  const item = open ? data.items.find((i) => i.id === open) : null;

  return (
    <>
      <Group header={<Header>🛒 Магазин</Header>}>
        <Div>
          <p className="guild-line">У тебя: 💎 {money(data.gems)}</p>
          {notice && <p className="shop-notice">{notice}</p>}
        </Div>
        <div className="shop-grid">
          {data.items.map((i) => (
            <button type="button" key={i.id} className="shop-card" onClick={() => setOpen(i.id)}>
              <span className="shop-card__emoji" aria-hidden="true">{i.emoji}</span>
              <b className="shop-card__title">{i.title}</b>
              <span className="shop-card__price">от 💎 {money(i.prices[i.min])}</span>
              {i.active_until && <span className="shop-card__badge">активна</span>}
            </button>
          ))}
        </div>
      </Group>
      {item && (
        <BuySheet
          item={item}
          gems={data.gems}
          onClose={() => setOpen(null)}
          onBought={(res) => {
            setData(res);
            setOpen(null);
            onWallet?.({ donate_currency: res.gems });
            setNotice(`${item.emoji} ${item.title} - до ${untilText(res.done.until)}.`);
            onBought?.();
          }}
        />
      )}
    </>
  );
}
