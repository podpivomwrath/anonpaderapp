import bridge from '@vkontakte/vk-bridge';

/**
 * Свёрнут ли мини-апп (2026-11-12). Опросы сервера (карта, заказы) на это
 * время замирают: раньше карта спрашивала бота раз в 5 секунд, даже когда
 * игрок ушёл в чат. Браузер сообщает о скрытии через visibilitychange, VK -
 * своими событиями VKWebAppViewHide/Restore (вебвью Android не всегда
 * шлёт первое).
 */
let vkHidden = false;
const listeners = new Set();

export function appHidden() {
  return vkHidden || document.hidden;
}

function notify() {
  listeners.forEach((fn) => fn(appHidden()));
}

document.addEventListener('visibilitychange', notify);
bridge.subscribe((event) => {
  const type = event?.detail?.type;
  if (type === 'VKWebAppViewHide') {
    vkHidden = true;
    notify();
  } else if (type === 'VKWebAppViewRestore') {
    vkHidden = false;
    notify();
  }
});

/** fn(hidden) на каждое сворачивание и разворачивание. Возвращает отписку. */
export function onAppVisibility(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
