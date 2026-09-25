import { useState } from 'react';
import { setCrownFrame } from '../api.js';
import { itemIcon } from '../itemIcons.js';

/**
 * Выбор рамки венца (патч 92).
 *
 * Открывается нажатием на эмблему класса в шапке — она видна из любой
 * вкладки, поэтому и бонусы венцов оказываются под рукой откуда угодно.
 *
 * Открывается и при единственном венце: рамку можно снять, а описание
 * бонуса всё равно нужно где-то держать.
 *
 * Бонусы тут не выбираются. Действуют ВСЕ венцы сразу, выбирается только
 * вид рамки — поэтому строка эффекта стоит у каждого пункта, включая те,
 * что сейчас не надеты.
 */
export default function CrownPicker({ menu, current, onChange, onClose }) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function pick(board) {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      const res = await setCrownFrame(board);
      onChange(res);
      onClose();
    } catch {
      // Венец могли отобрать, пока подменю открыто: сервер такой выбор
      // отклоняет. Молча закрывать нельзя - игрок решит, что нажал мимо.
      setFailed(true);
      setBusy(false);
    }
  }

  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet" role="dialog" aria-label="Рамка">
        {menu.map((crown) => {
          const frame = itemIcon(`crown:${crown.board}`);
          const active = crown.board === current;
          return (
            <button
              type="button"
              key={crown.board}
              className={active ? 'crown-sheet__item crown-sheet__item--active' : 'crown-sheet__item'}
              onClick={() => pick(crown.board)}
              disabled={busy}
            >
              <span className="crown-sheet__frame">
                {frame && <img src={frame} alt="" aria-hidden="true" />}
              </span>
              <span className="crown-sheet__text">
                <b>{crown.title}</b>
                <small>
                  {crown.board_title} · {crown.effect}
                </small>
              </span>
              {active && <span className="crown-sheet__mark">✓</span>}
            </button>
          );
        })}

        <button
          type="button"
          className={current ? 'crown-sheet__item' : 'crown-sheet__item crown-sheet__item--active'}
          onClick={() => pick(null)}
          disabled={busy}
        >
          <span className="crown-sheet__frame" />
          <span className="crown-sheet__text">
            <b>Без рамки</b>
          </span>
          {!current && <span className="crown-sheet__mark">✓</span>}
        </button>

        {failed && <p className="crown-sheet__error">Не вышло. Попробуй ещё раз.</p>}
      </div>
    </>
  );
}
