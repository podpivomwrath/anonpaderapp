import { useEffect, useState } from 'react';

/**
 * Общие куски разделов (2026-10-22, разделы до уровня «Героя»): шапка
 * раздела, пустой экран, полоска прогресса, шторка снизу и пьедестал.
 * Стили - tabs.css.
 */

// Картинки шапок: assets/sections/<раздел>.webp. Пока картинки нет, шапка
// рисуется градиентом своего цвета - ничего не ломается.
const ART = Object.fromEntries(
  Object.entries(import.meta.glob('../assets/sections/*.webp', { eager: true, query: '?url', import: 'default' }))
    .map(([path, url]) => [path.split('/').pop().replace('.webp', ''), url]),
);

/** Шапка раздела: значок, главная цифра раздела и подпись к ней. */
export function SectionHead({ kind, icon, value, label, aside }) {
  const art = ART[kind];
  return (
    <div className={`section-head section-head--${kind}${art ? ' section-head--art' : ''}`} style={art ? { '--section-art': `url(${art})` } : undefined}>
      <span className="section-head__icon" aria-hidden="true">{icon}</span>
      <span className="section-head__main">
        <b className="section-head__value">{value}</b>
        {label && <small className="section-head__label">{label}</small>}
      </span>
      {aside && <span className="section-head__aside">{aside}</span>}
    </div>
  );
}

/** Пустой экран: рисунок, строка и, если есть куда вести, кнопка. */
export function Empty({ icon, children, action, onAction }) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon" aria-hidden="true">{icon}</span>
      <p className="empty-state__text">{children}</p>
      {action && onAction && (
        <button type="button" className="pill-btn" onClick={onAction}>{action}</button>
      )}
    </div>
  );
}

/** Полоска прогресса. tone - цвет: gold, red, green, blue. */
export function Bar({ value, max, tone = 'gold', thin = false }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <span className={`bar bar--${tone}${thin ? ' bar--thin' : ''}`} role="progressbar" aria-valuenow={value} aria-valuemax={max}>
      <i style={{ width: `${pct}%` }} />
    </span>
  );
}

/** Шторка снизу - одна на все разделы, как окно слота в «Герое». */
export function Sheet({ title, icon, onClose, className = '', children }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className={`crown-sheet ui-sheet ${className}`} role="dialog" aria-label={typeof title === 'string' ? title : undefined}>
        {title && (
          <div className="ui-sheet__head">
            {icon && <span className="ui-sheet__icon" aria-hidden="true">{icon}</span>}
            <b className="ui-sheet__title">{title}</b>
            <button type="button" className="ui-sheet__close" onClick={onClose} aria-label="Закрыть">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
            </button>
          </div>
        )}
        <div className="ui-sheet__body">{children}</div>
      </div>
    </>
  );
}

/**
 * Пьедестал первой тройки: второй слева, первый в центре и выше, третий
 * справа. renderBadge(entry, place) рисует значок, value - подпись под именем.
 */
export function Podium({ entries, renderBadge, onPick }) {
  const order = [entries[1], entries[0], entries[2]];
  return (
    <div className="podium">
      {order.map((e, i) => {
        if (!e) return <span key={i} className="podium__slot podium__slot--empty" />;
        const place = [2, 1, 3][i];
        return (
          <button
            type="button" key={e.key ?? place} className={`podium__slot podium__slot--${place}`}
            onClick={onPick ? () => onPick(e) : undefined} disabled={!onPick}
          >
            <span className="podium__badge">{renderBadge(e, place)}</span>
            <span className="podium__name">{e.name}</span>
            {e.sub && <span className="podium__sub">{e.sub}</span>}
            <b className="podium__value">{e.value}</b>
            <span className="podium__step" aria-hidden="true">{place}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Отсчёт до момента: «5ч 12м», каждую минуту сам. */
export function useCountdown(seconds) {
  const [left, setLeft] = useState(seconds);
  useEffect(() => {
    setLeft(seconds);
    if (seconds == null) return undefined;
    const started = Date.now();
    const id = setInterval(() => setLeft(Math.max(0, seconds - Math.floor((Date.now() - started) / 1000))), 30000);
    return () => clearInterval(id);
  }, [seconds]);
  return left;
}

export function hm(seconds) {
  if (seconds == null) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}ч ${m}м` : `${m}м`;
}
