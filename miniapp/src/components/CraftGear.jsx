import { useState } from 'react';
import { Button } from '@vkontakte/vkui';
import { makeGear } from '../api.js';
import { Sheet } from './ui.jsx';
import Sparks from './Sparks.jsx';

// Страница ремесла на вкладке «Герой» (2026-10-23): уровень и два слота
// инструментов. Инструмент не ломается и не передаётся; новая ковка тира
// выше заменяет старую. Сервер - bot/miniapp_gear_api.py.

const ROMAN = ['', 'I', 'II', 'III', 'IV', 'V'];

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
  if (tool.source === 'charges') return `Собрать: +${next.yield} зарядов`;
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

function ToolCard({ tool, onOpen, flash }) {
  const tierMark = tool.owned && tool.source !== 'drop' && tool.source !== 'stock' ? ROMAN[tool.tier] : null;
  return (
    <div className={`gear-tool${tool.owned ? ' gear-tool--owned' : ''}`}>
      <div className="gear-tool__icon" aria-hidden="true">
        <span>{tool.emoji}</span>
        {tierMark && <i className="gear-tool__tier">{tierMark}</i>}
        <Sparks burst={flash} />
      </div>
      <div className="gear-tool__text">
        <b>
          {tool.title}
          {tool.owned && (tool.source === 'charges' || tool.source === 'stock') ? ` · ${tool.count}` : ''}
        </b>
        <small>{tool.owned ? tool.effect : (tool.hint || tool.next?.effect || '')}</small>
        {tool.soon && <small className="gear-tool__soon">Скоро</small>}
        {!tool.owned && !tool.soon && tool.source === 'drop' && <small className="gear-tool__soon">Нет</small>}
      </div>
      {tool.next && (
        <button type="button" className="pill-btn" onClick={onOpen}>
          {tool.owned && tool.source !== 'charges' && tool.source !== 'stock' ? '▲' : '+'}
        </button>
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
      <div className="gear-page__head">
        <span className="gear-page__emoji" aria-hidden="true">{craft.emoji}</span>
        <div>
          <b className="gear-page__title">{craft.level} уровень</b>
          <small>Инструменты не ломаются и остаются с тобой</small>
        </div>
      </div>
      <div className="gear-page__tools">
        {craft.tools.map((t) => (
          <ToolCard key={t.id} tool={t} flash={flashes[t.id] || 0} onOpen={() => setOpen(t.id)} />
        ))}
      </div>
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
