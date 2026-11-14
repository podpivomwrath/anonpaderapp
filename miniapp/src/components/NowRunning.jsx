import { useEffect, useRef, useState } from 'react';
import { getNowRunning } from '../api.js';

// «Сейчас идёт» (2026-11-14, владелец): всё запущенное и когда кончится -
// поездка, долгий путь, исследование, варка, повозки, мировой босс. Раньше
// за каждым сроком шли в чат. Пусто - блока нет совсем.

function left(seconds) {
  if (seconds <= 0) return 'уже скоро';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h} ч ${String(m).padStart(2, '0')} мин`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function NowRunning() {
  const [data, setData] = useState(null);
  const [tick, setTick] = useState(0);
  const loadedAt = useRef(0);
  const askedAt = useRef(0);

  const load = () => {
    askedAt.current = Date.now();
    getNowRunning()
      .then((res) => { loadedAt.current = Date.now(); setData(res); })
      .catch(() => { /* блок просто не покажется */ });
  };

  useEffect(load, []);
  useEffect(() => {
    if (!data?.items?.some((i) => i.ends_at)) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [data]);

  // Что-то закончилось - спросить сервер заново, но не чаще раза в 30 с:
  // итог (исследование, бой) может прийти позже срока.
  useEffect(() => {
    if (!data?.items || Date.now() - askedAt.current < 30000) return;
    const nowServer = data.now + (Date.now() - loadedAt.current) / 1000;
    if (data.items.some((i) => i.ends_at && i.ends_at - nowServer < -2)) load();
  }, [tick, data]);

  if (!data?.items?.length) return null;
  const nowServer = data.now + (Date.now() - loadedAt.current) / 1000;

  return (
    <div className="now-running" data-tick={tick}>
      <span className="now-running__title">Сейчас идёт</span>
      {data.items.map((item) => (
        <div className="now-running__row" key={item.id}>
          <span className="now-running__icon" aria-hidden="true">{item.icon}</span>
          <span className="now-running__name">
            {item.title}
            {item.note && <small className="now-running__note"> · {item.note}</small>}
          </span>
          {item.ends_at && <span className="now-running__left">{left(item.ends_at - nowServer)}</span>}
        </div>
      ))}
    </div>
  );
}
