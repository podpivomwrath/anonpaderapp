import { useState } from 'react';
import { Button } from '@vkontakte/vkui';
import { makeGear, setAlmanacHerbs } from '../api.js';
import { itemIcon } from '../itemIcons.js';
import { SectionHead, Sheet } from './ui.jsx';
import Sparks from './Sparks.jsx';

// Страница ремесла на вкладке «Герой» (2026-10-23): уровень и два слота
// инструментов. Инструмент не ломается и не передаётся; новая ковка тира
// выше заменяет старую. Сервер - bot/miniapp_gear_api.py.

const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V'];

function chargesWord(n) {
  const d = n % 10;
  if (d === 1 && n % 100 !== 11) return 'заряд';
  return d >= 2 && d <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'заряда' : 'зарядов';
}

function kg(grams) {
  return `${Math.round(grams / 100) / 10} кг`;
}

function needsLines(next) {
  const out = [];
  if (next.needs.ore) out.push([`⛏ Руда ${next.ore_tier} тира`, next.needs.ore, next.have.ore || 0]);
  if (next.needs.herbs) out.push([`🌿 Трава ${next.tier} тира`, next.needs.herbs, next.have.herbs || 0]);
  if (next.needs.fish_g) {
    out.push(['🐟 Любая рыба', next.needs.fish_g, next.have.fish_g || 0, kg]);
  }
  return out;
}

function actionLabel(tool, next) {
  if (tool.source === 'charges') return `Собрать: +${next.yield} ${chargesWord(next.yield)}`;
  if (tool.source === 'stock') return `Сделать: +${next.yield} шт.`;
  if (tool.source === 'herbs') return tool.owned ? `Сплести ${ROMAN[next.tier]} тир` : 'Сплести';
  return tool.owned ? `Перековать в ${ROMAN[next.tier]} тир` : 'Сковать';
}

function MakeSheet({ tool, level, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const { next } = tool;
  const lowLevel = level < next.need_level;

  const make = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await makeGear(tool.id, next.tier));
    } catch (err) {
      setError(err.details?.error || err.message || 'Не вышло.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet title={tool.title} icon={tool.emoji} onClose={onClose}>
      <p className="gear-sheet__effect">{next.effect}</p>
      <div className="gear-sheet__needs">
        {needsLines(next).map(([label, need, have, fmt = (x) => x]) => (
          <div key={label} className={`gear-need${have >= need ? ' gear-need--ok' : ''}`}>
            <span>{label}</span>
            <b>{fmt(Math.min(have, need))} / {fmt(need)}</b>
          </div>
        ))}
        <div className={`gear-need${lowLevel ? '' : ' gear-need--ok'}`}>
          <span>Уровень ремесла</span>
          <b>{level} / {next.need_level}</b>
        </div>
      </div>
      {tool.owned && tool.source !== 'charges' && tool.source !== 'stock' && (
        <p className="craft-hint">Нынешний инструмент заменится новым.</p>
      )}
      {tool.source === 'charges' && tool.owned && tool.tier !== next.tier && (
        <p className="craft-hint">Набор другого тира заменит нынешний вместе с зарядами.</p>
      )}
      {error && <p className="shop-sheet__error">{error}</p>}
      <Button size="l" stretched disabled={busy || !next.can} onClick={make}>
        {busy ? 'Работаем…' : actionLabel(tool, next)}
      </Button>
    </Sheet>
  );
}

// Окно альманаха (2026-10-29, просьба игрока): найденные страницы, запас
// подсказок и галочки: какую траву подсказывать (по траве - 2026-10-29).
function AlmanacSheet({ tool, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const a = tool.almanac;
  const on = a.herbs.filter((h) => h.on).map((h) => h.id);
  const save = async (ids) => {
    setBusy(true);
    setError(null);
    try {
      onDone(await setAlmanacHerbs(ids));
    } catch (err) {
      setError(err.details?.error || err.message || 'Не вышло.');
    } finally {
      setBusy(false);
    }
  };
  const toggle = (id) => save(on.includes(id) ? on.filter((x) => x !== id) : [...on, id]);
  return (
    <Sheet title={tool.title} icon={tool.emoji} onClose={onClose}>
      <p className="craft-hint">
        Найдено страниц: {a.pages}. Подсказок до зарядки: {a.uses}, каждая страница добавляет {a.per_page}.
      </p>
      {tool.status && <p className="craft-hint">{tool.status}</p>}
      <p className="craft-hint">Какую траву подсказывать:</p>
      <div className="almanac-herbs">
        {a.herbs.map((h) => (
          <label key={h.id} className="almanac-herb">
            <input type="checkbox" checked={h.on} disabled={busy} onChange={() => toggle(h.id)} />
            <span>{h.emoji} {h.name}</span>
            <i>{ROMAN[h.tier]}</i>
          </label>
        ))}
      </div>
      <div className="filter-chips">
        <button type="button" disabled={busy} className="filter-chip" onClick={() => save(null)}>
          Отметить все
        </button>
        <button type="button" disabled={busy} className="filter-chip" onClick={() => save([])}>
          Снять все
        </button>
      </div>
      <p className="craft-hint">
        {on.length
          ? 'Подсказка тратится, только когда рядом нашлась отмеченная трава.'
          : 'Ничего не отмечено: альманах молчит и подсказки не тратит.'}
      </p>
      {error && <p className="shop-sheet__error">{error}</p>}
    </Sheet>
  );
}

function ToolCard({ tool, onOpen, flash }) {
  // Картинка - когда нарисуют (tools/craft_gear_art_prompts.md), пока эмодзи.
  const art = itemIcon(`gear:${tool.id}`);
  const tierMark = tool.owned && tool.source !== 'drop' && tool.source !== 'stock' ? ROMAN[tool.tier] : null;
  return (
    <div className={`gear-tool${tool.owned ? ' gear-tool--owned' : ''}`}>
      <div className="gear-tool__icon" aria-hidden="true">
        {art ? <img src={art} alt="" draggable="false" /> : <span>{tool.emoji}</span>}
        {tierMark && <i className="gear-tool__tier">{tierMark}</i>}
        <Sparks burst={flash} />
      </div>
      <div className="gear-tool__text">
        <b>
          {tool.title}
          {tool.owned && (tool.source === 'charges' || tool.source === 'stock') ? ` · ${tool.count}` : ''}
        </b>
        <small>{tool.owned ? tool.effect : (tool.about || tool.next?.effect || '')}</small>
        {!tool.owned && tool.hint && <small>{tool.hint}</small>}
        {tool.status && <small>{tool.status}</small>}
        {tool.soon && <small className="gear-tool__soon">Скоро</small>}
        {!tool.owned && !tool.soon && tool.source === 'drop' && <small className="gear-tool__soon">Нет</small>}
      </div>
      {tool.next && (
        <button type="button" className="pill-btn" onClick={onOpen}>
          {tool.owned && tool.source !== 'charges' && tool.source !== 'stock' ? '▲' : '+'}
        </button>
      )}
      {tool.almanac && (
        <button type="button" className="pill-btn" onClick={onOpen} aria-label="Настроить альманах">⚙</button>
      )}
    </div>
  );
}

export default function CraftGear({ craft, onUpdate }) {
  const [open, setOpen] = useState(null);
  const [flashes, setFlashes] = useState({});
  const tool = open ? craft.tools.find((t) => t.id === open) : null;

  return (
    <div className="gear-page">
      {/* Шапка с картинкой ремесла - assets/sections/gear_<ремесло>.webp. */}
      <SectionHead
        kind={`gear_${craft.id}`} icon={craft.emoji} value={`${craft.level} уровень`}
        label="Инструменты не ломаются и остаются с тобой"
      />
      <div className="gear-page__tools">
        {craft.tools.map((t) => (
          <ToolCard key={t.id} tool={t} flash={flashes[t.id] || 0} onOpen={() => setOpen(t.id)} />
        ))}
      </div>
      {tool && tool.almanac && (
        <AlmanacSheet tool={tool} onClose={() => setOpen(null)} onDone={onUpdate} />
      )}
      {tool && tool.next && (
        <MakeSheet
          tool={tool} level={craft.level} onClose={() => setOpen(null)}
          onDone={(res) => {
            setOpen(null);
            setFlashes((f) => ({ ...f, [tool.id]: (f[tool.id] || 0) + 1 }));
            onUpdate(res);
          }}
        />
      )}
    </div>
  );
}
