import { Button } from '@vkontakte/vkui';

// Окно направления (город или караван): что там продают и покупают, по
// каким ценам сейчас, сколько ехать и насколько опасно. Открывается
// нажатием на строку в «Куда везти» - в одну строку товары не помещались.

const money = (v) => Number(v ?? 0).toLocaleString('ru-RU');
const TIER_CLASS = { 1: '', 2: 'trade-tier--2', 3: 'trade-tier--3', 4: 'trade-tier--4' };

function duration(seconds) {
  return seconds >= 60 ? `~${Math.round(seconds / 60)} мин` : `~${Math.round(seconds)} сек`;
}

function GoodRow({ g, price, note, have }) {
  return (
    <div className="trade-dest__row">
      <span className={`trade-dest__good ${TIER_CLASS[g.tier]}`}>{g.emoji} {g.name}</span>
      <span className="trade-dest__note">
        {note}
        {have ? <span className="trade-dest__have"> · у тебя {have}</span> : null}
      </span>
      <b className="trade-dest__price">{money(price)}</b>
    </div>
  );
}

export default function TradeDestination({ dest, cargo, canGo, busy, onGo, onClose }) {
  const have = (id) => cargo.find((c) => c.id === id)?.count || 0;
  const isCaravan = dest.kind === 'caravan';
  const route = dest.route;
  const here = route && route.cells === 0;

  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet trade-dest" role="dialog" aria-label={dest.title}>
        <div className="trade-dest__title">
          <b>{dest.title}</b>
          <span className="craft-hint">({dest.x}; {dest.y})</span>
        </div>
        <p className="craft-hint">
          {here
            ? 'Ты здесь.'
            : route
              ? `${route.cells} клеток · ${duration(route.seconds)} · нападение в пути ~${Math.round(route.ambush * 100)}%`
              : ''}
          {isCaravan ? ` · уйдёт через ${dest.minutes_left} мин` : ''}
        </p>

        <div className="trade-dest__section">{isCaravan ? 'Отдаёт дешевле города' : 'Продаёт - свой товар'}</div>
        {dest.sells.length === 0 && <p className="craft-hint">Ничего.</p>}
        {dest.sells.map((g) => (
          <GoodRow
            key={g.id}
            g={g}
            price={g.price}
            note={isCaravan ? `осталось ${g.left}` : g.locked ? `с ${g.min_level} ур. торговли` : g.tier_name}
          />
        ))}

        <div className="trade-dest__section">{isCaravan ? 'Берёт дороже города' : 'Покупает'}</div>
        {dest.buys.map((g) => (
          <GoodRow
            key={g.id}
            g={g}
            price={g.price}
            have={have(g.id)}
            note={isCaravan ? `нужно ещё ${g.left}` : g.deficit ? <span className="trade-dest__deficit">дефицит</span> : g.city_title}
          />
        ))}
        <p className="craft-hint">Цены - на сейчас и за первый ящик: каждая сделка двигает рынок.</p>

        <div className="trade-dest__actions">
          {canGo && !here && (
            <Button size="l" stretched disabled={busy} onClick={onGo}>В путь</Button>
          )}
          <Button size="l" stretched mode="secondary" onClick={onClose}>Закрыть</Button>
        </div>
      </div>
    </>
  );
}
