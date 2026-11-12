import { useCallback, useState } from 'react';

/**
 * Вкладка внутри раздела, которую помнит браузер (2026-11-12): как и сам
 * раздел (Hub.jsx), «Рынок -> Биржа» или «Персонаж -> Характеристики»
 * открываются там, где из них вышли. Только localStorage - бот и сервер ни
 * при чём. ids - допустимые вкладки: запомненная, которой больше нет
 * (раздел переделали), уступает fallback.
 */
export function useSavedTab(scope, ids, fallback) {
  const key = `pines:sub:${scope}`;
  const [value, setValue] = useState(() => {
    try {
      const saved = window.localStorage.getItem(key);
      return ids.includes(saved) ? saved : fallback;
    } catch {
      return fallback;
    }
  });
  const set = useCallback((next) => {
    setValue(next);
    try {
      window.localStorage.setItem(key, next);
    } catch {
      // хранилище закрыто - вкладка просто не запомнится
    }
  }, [key]);
  return [value, set];
}
