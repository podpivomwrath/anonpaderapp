import { useEffect, useRef } from 'react';
import bridge from '@vkontakte/vk-bridge';

/**
 * «Назад» телефона внутри мини-аппа (2026-11-12). Своей истории переходов у
 * мини-аппа не было, и кнопка «назад» на Android сворачивала его целиком,
 * даже когда хотелось закрыть окно предмета. Теперь каждое окно и каждый
 * переход по разделам кладёт запись в историю браузера: «назад» закрывает
 * верхнее окно или возвращает на прошлый раздел, а когда записей нет - ВК
 * сворачивает мини-апп, как раньше.
 *
 * Айфон: свайп «назад» ВК включается, только пока есть что закрывать, и не
 * на карте и в гильдии - там палец таскает карту и древо (2026-10-13 свайп
 * сворачивал мини-апп посреди перетаскивания карты).
 */
const stack = [];
let skip = 0; // сколько popstate наших собственных history.back() ещё придёт
let queued = 0; // записи, которые надо положить после этих popstate
let dragScreen = false;
let swipeOn = null;

function syncSwipe() {
  const want = stack.length > 0 && !dragScreen;
  if (want === swipeOn) return;
  swipeOn = want;
  bridge.send('VKWebAppSetSwipeSettings', { history: want }).catch(() => {});
}

function pushEntry() {
  if (skip > 0) queued += 1;
  else window.history.pushState({ pines: stack.length }, '');
}

window.addEventListener('popstate', () => {
  if (skip > 0) {
    skip -= 1;
    if (skip === 0) {
      for (; queued > 0; queued -= 1) window.history.pushState({ pines: stack.length }, '');
    }
    return;
  }
  const top = stack.pop();
  syncSwipe();
  if (top) top.close();
});

/** Положить запись: close() вызовется по «назад». Возвращает release() - снять
 *  запись, когда окно закрыли сами (крестиком, по фону). */
export function pushBack(close) {
  const entry = { close };
  stack.push(entry);
  pushEntry();
  syncSwipe();
  return () => {
    const i = stack.indexOf(entry);
    if (i === -1) return;
    stack.splice(i, 1);
    if (queued > 0) queued -= 1;
    else {
      skip += 1;
      window.history.back();
    }
    syncSwipe();
  };
}

/** Окно, которое живёт, пока смонтировано: «назад» зовёт onClose. */
export function useBackClose(onClose, active = true) {
  const ref = useRef(onClose);
  ref.current = onClose;
  useEffect(() => {
    if (!active) return undefined;
    let closedByBack = false;
    const release = pushBack(() => {
      closedByBack = true;
      ref.current?.();
    });
    return () => {
      if (!closedByBack) release();
    };
  }, [active]);
}

/** Карта и древо гильдии: свайп айфона не трогаем вовсе. */
export function setDragScreen(on) {
  dragScreen = on;
  syncSwipe();
}
