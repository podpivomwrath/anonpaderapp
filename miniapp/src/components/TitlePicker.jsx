import { useState } from 'react';
import { setTitle } from '../api.js';

/**
 * Выбор титула. Открывается нажатием на титул в шапке профиля - как выбор
 * рамки венца нажатием на эмблему (CrownPicker), и выглядит так же.
 *
 * Цвет - тир титула, по аналогии с редкостью предметов: синий - редкий,
 * фиолетовый - эпический, жёлтый - легендарный.
 */
const TIER_LABELS = {
  common: 'Обычный',
  rare: 'Редкий',
  epic: 'Эпический',
  legendary: 'Легендарный',
};

export default function TitlePicker({ titles, onChange, onClose }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const current = titles.find((t) => t.active)?.id ?? null;

  async function pick(titleId) {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      onChange(await setTitle(titleId));
      onClose();
    } catch {
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet" role="dialog" aria-label="Титул">
        {titles.map((title) => (
          <button
            type="button"
            key={title.id}
            className={title.active ? 'crown-sheet__item crown-sheet__item--active' : 'crown-sheet__item'}
            onClick={() => pick(title.id)}
            disabled={busy}
          >
            <span className="crown-sheet__text">
              <b className={`title-tier title-tier--${title.tier}`}>«{title.name}»</b>
              <small>{TIER_LABELS[title.tier] || ''}</small>
            </span>
            {title.active && <span className="crown-sheet__mark">✓</span>}
          </button>
        ))}

        <button
          type="button"
          className={current ? 'crown-sheet__item' : 'crown-sheet__item crown-sheet__item--active'}
          onClick={() => pick(null)}
          disabled={busy}
        >
          <span className="crown-sheet__text">
            <b>Без титула</b>
          </span>
          {!current && <span className="crown-sheet__mark">✓</span>}
        </button>

        {failed && <p className="crown-sheet__error">Не вышло. Попробуй ещё раз.</p>}
      </div>
    </>
  );
}
