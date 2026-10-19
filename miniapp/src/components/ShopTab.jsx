import { useEffect, useRef, useState } from 'react';
import { Button, Div, Group, Header, Placeholder, Spinner } from '@vkontakte/vkui';
import { IN_VK, buyShop, buyShopRename, createPayment, getPayments, getShop } from '../api.js';

/**
 * Магазин (2026-10-13): товары за самоцветы квадратными карточками. Нажатие
 * на карточку открывает окно покупки снизу; у Метки Хранителя там ползунок
 * срока - чем дольше, тем дешевле день. Цены приходят с сервера на каждый
 * срок, и при покупке сервер считает цену заново.
 */

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');

// Картинки карточек (2026-10-18): src/assets/shop/<id товара или пакета>.webp.
// Нет файла - остаётся эмодзи, так что картинки можно добавлять по одной.
const SHOP_IMAGES = import.meta.glob('../assets/shop/*.webp', { eager: true, import: 'default' });

function ShopIcon({ id, emoji }) {
  const src = SHOP_IMAGES[`../assets/shop/${id}.webp`];
  if (src) return <img className="shop-card__img" src={src} alt="" aria-hidden="true" />;
  return <span className="shop-card__emoji" aria-hidden="true">{emoji}</span>;
}

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

// Набор за фиксированную цену (2026-10-19: набор зелий) - список содержимого
// и покупка в два нажатия.
function BundleSheet({ item, gems, onClose, onBought }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const enough = gems >= item.price;

  const buy = async () => {
    setBusy(true);
    setError(null);
    try {
      onBought(await buyShop(item.id));
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
          <ShopIcon id={item.id} emoji={item.emoji} />
          <div>
            <b className="shop-sheet__title">{item.title}</b>
          </div>
        </div>
        <ul className="shop-sheet__perks">
          {item.perks.map((perk) => <li key={perk}>{perk}</li>)}
        </ul>
        <p className="craft-hint">{item.note}</p>
        {error && <p className="shop-sheet__error">{error}</p>}
        {!enough && <p className="shop-sheet__error">Не хватает самоцветов: у тебя 💎 {money(gems)}.</p>}
        <div className="shop-sheet__actions">
          {confirming ? (
            <>
              <Button size="l" stretched disabled={busy} onClick={buy}>
                {busy ? 'Покупаем…' : `Да, купить за 💎 ${money(item.price)}`}
              </Button>
              <Button size="l" mode="secondary" stretched disabled={busy} onClick={() => setConfirming(false)}>Отмена</Button>
            </>
          ) : (
            <Button size="l" stretched disabled={!enough} onClick={() => setConfirming(true)}>
              Купить за 💎 {money(item.price)}
            </Button>
          )}
        </div>
      </div>
    </>
  );
}

// Смена ника / названия фирмы (2026-10-16): ввести новое имя, подтвердить -
// самоцветы списываются в тот же момент, что и меняется имя. Не подошло
// (занято, неверные символы) - ничего не списано, ошибка в окне.
function RenameSheet({ item, gems, onClose, onBought }) {
  const [name, setName] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const clean = name.trim().replace(/\s+/g, ' ');
  const enough = gems >= item.price;
  const valid = clean.length >= item.min_len && clean.length <= item.max_len && clean !== item.current;

  const buy = async () => {
    setBusy(true);
    setError(null);
    try {
      onBought(await buyShopRename(item.id, clean));
    } catch (err) {
      setError(err.message || 'Не удалось.');
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
            {item.current && <p className="shop-sheet__active">Сейчас: {item.current}</p>}
          </div>
        </div>
        {item.available === false ? (
          <p className="shop-sheet__error">{item.unavailable}</p>
        ) : (
          <>
            <input
              className="guild-input shop-sheet__input" placeholder="Новое имя" maxLength={item.max_len}
              value={name} disabled={busy}
              onChange={(e) => { setName(e.target.value); setConfirming(false); setError(null); }}
            />
            <p className="craft-hint">{item.rules} Самоцветы списываются только при успешной смене.</p>
          </>
        )}
        {error && <p className="shop-sheet__error">{error}</p>}
        {!enough && <p className="shop-sheet__error">Не хватает самоцветов: у тебя 💎 {money(gems)}.</p>}
        <div className="shop-sheet__actions">
          {confirming ? (
            <>
              <Button size="l" stretched disabled={busy} onClick={buy}>
                {busy ? 'Меняем…' : `Да, «${clean}» за 💎 ${money(item.price)}`}
              </Button>
              <Button size="l" mode="secondary" stretched disabled={busy} onClick={() => setConfirming(false)}>Отмена</Button>
            </>
          ) : (
            <Button size="l" stretched disabled={!enough || !valid || item.available === false}
              onClick={() => setConfirming(true)}>
              Сменить за 💎 {money(item.price)}
            </Button>
          )}
        </div>
      </div>
    </>
  );
}

// Самоцветы за рубли (ЮKassa, 2026-10-15): пакет -> страница оплаты ЮKassa.
// Самоцветы приходят, когда ЮKassa подтвердит оплату, - бот пишет об этом.
function GemPacks() {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  // Ссылка на оплату кнопкой (2026-10-18): в мобильном VK (iOS и Android)
  // window.open после ожидания ответа сервера молча блокируется - нажатие
  // по настоящей ссылке телефон не блокирует.
  const [payLink, setPayLink] = useState(null);
  const payRef = useRef(null);
  useEffect(() => {
    if (payLink) payRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [payLink]);
  const returned = !IN_VK && new URLSearchParams(window.location.search).has('paid');

  useEffect(() => {
    getPayments().then(setData).catch(() => setData(null));
  }, []);

  if (!data) return null;

  const buy = async (packId) => {
    setBusy(packId);
    setError(null);
    setPayLink(null);
    try {
      const { url } = await createPayment(packId);
      if (IN_VK) {
        setPayLink({ url, pack: data.packs.find((p) => p.id === packId) });
        try { window.open(url, '_blank'); } catch { /* откроют кнопкой */ }
      } else window.location.href = url;
    } catch (e) {
      setError(e.message || 'Не удалось начать оплату.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <Group header={<Header>💎 Самоцветы</Header>}>
      <Div>
        <p className="craft-hint">1 самоцвет = 1 ₽. Оплата через ЮKassa, самоцветы приходят сразу после оплаты.</p>
        {returned && <p className="shop-notice">Оплата обрабатывается - как только ЮKassa её подтвердит, бот напишет в сообщения.</p>}
        {!data.enabled && <p className="craft-hint">Покупка за рубли скоро откроется.</p>}
        {error && <p style={{ color: 'var(--vkui--color_text_negative)' }}>{error}</p>}
        {payLink && (
          <p className="shop-notice" ref={payRef}>
            Если страница оплаты не открылась сама:{' '}
            <a href={payLink.url} target="_blank" rel="noopener noreferrer" onClick={() => setPayLink(null)}>
              <b>перейти к оплате{payLink.pack ? ` · ${money(payLink.pack.rub)} ₽` : ''}</b>
            </a>
          </p>
        )}
      </Div>
      <div className="shop-grid">
        {data.packs.map((p) => (
          <button
            type="button" key={p.id} className="shop-card"
            disabled={!data.enabled || busy !== null}
            onClick={() => buy(p.id)}
          >
            <ShopIcon id={p.id} emoji="💎" />
            <b className="shop-card__title">{p.name}</b>
            <span className="shop-card__price">{money(p.gems)} 💎 · {money(p.rub)} ₽</span>
            {busy === p.id && <Spinner size="s" />}
          </button>
        ))}
      </div>
      {data.history.length > 0 && (
        <Div>
          <p className="craft-hint"><b>Твои покупки</b></p>
          {data.history.map((h, i) => (
            <p key={i} className="craft-hint">
              {new Date(h.at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
              {' · '}{money(h.gems)} 💎 за {money(h.rub)} ₽ · {h.credited ? 'зачислено' : (h.status === 'canceled' ? 'отменено' : 'ждёт подтверждения')}
            </p>
          ))}
        </Div>
      )}
    </Group>
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
              <ShopIcon id={i.id} emoji={i.emoji} />
              <b className="shop-card__title">{i.title}</b>
              <span className="shop-card__price">
                {i.kind === 'days' ? `от 💎 ${money(i.prices[i.min])}` : `💎 ${money(i.price)}`}
              </span>
              {i.active_until && <span className="shop-card__badge">активна</span>}
            </button>
          ))}
        </div>
      </Group>
      <GemPacks />
      {item && item.kind === 'rename' && (
        <RenameSheet
          item={item}
          gems={data.gems}
          onClose={() => setOpen(null)}
          onBought={(res) => {
            setData(res);
            setOpen(null);
            onWallet?.({ donate_currency: res.gems });
            setNotice(`${item.emoji} Готово: «${res.done.old}» → «${res.done.name}».`);
            onBought?.();
          }}
        />
      )}
      {item && item.kind === 'bundle' && (
        <BundleSheet
          item={item}
          gems={data.gems}
          onClose={() => setOpen(null)}
          onBought={(res) => {
            setData(res);
            setOpen(null);
            onWallet?.({ donate_currency: res.gems });
            setNotice(`${item.emoji} ${item.title} в сумке: ${res.done.contents.join(', ')}.`);
            onBought?.();
          }}
        />
      )}
      {item && item.kind === 'days' && (
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
