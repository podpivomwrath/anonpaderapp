import { useMemo, useState } from 'react';
import { Group, Header, Button, Div, Text, Caption } from '@vkontakte/vkui';
import { computeDerived } from '../formulas.js';
import { submitStats } from '../api.js';

// toFixed режет 0.075 -> "0.07" из-за бинарного представления числа —
// небольшой эпсилон убирает эту ложную "не докрутку" в отображении.
const EPS = 1e-9;

const STAT_DEFS = [
  { key: 'str', label: '💪 Сила' },
  { key: 'agi', label: '🏃 Ловкость' },
  { key: 'int', label: '🧠 Интеллект' },
  { key: 'vit', label: '❤️ Выносливость' },
  { key: 'wil', label: '✨ Воля' },
];

const DERIVED_DEFS = [
  { key: 'max_hp', clientKey: 'maxHp', label: 'Макс. HP', format: (v) => Math.round(v) },
  { key: 'damage', clientKey: 'damage', label: 'Урон', format: (v) => (v + EPS).toFixed(1) },
  {
    key: 'crit_chance',
    clientKey: 'critChance',
    label: 'Шанс крита',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
  },
  {
    key: 'mitigation',
    clientKey: 'mitigation',
    label: 'Митигация',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
  },
  {
    key: 'control_resist',
    clientKey: 'controlResist',
    label: 'Резист контроля',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
  },
  {
    key: 'support_power',
    clientKey: 'supportPower',
    label: 'Сила саппорта',
    format: (v) => (v + EPS).toFixed(2),
  },
];

const EMPTY_PENDING = { str: 0, agi: 0, int: 0, vit: 0, wil: 0 };

export default function StatsTab({ character, onCharacterUpdate }) {
  const [pending, setPending] = useState(EMPTY_PENDING);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  const totalPending = Object.values(pending).reduce((a, b) => a + b, 0);
  const remaining = character.unspent_points - totalPending;

  const previewStats = useMemo(
    () => ({
      str: character.stats.str + pending.str,
      agi: character.stats.agi + pending.agi,
      int: character.stats.int + pending.int,
      vit: character.stats.vit + pending.vit,
      wil: character.stats.wil + pending.wil,
    }),
    [character.stats, pending],
  );

  const previewDerived = useMemo(
    () => computeDerived({ level: character.level, baseClass: character.base_class, stats: previewStats }),
    [character.level, character.base_class, previewStats],
  );

  function increment(key) {
    if (remaining <= 0) return;
    setPending((p) => ({ ...p, [key]: p[key] + 1 }));
  }

  function decrement(key) {
    if (pending[key] <= 0) return;
    setPending((p) => ({ ...p, [key]: p[key] - 1 }));
  }

  function reset() {
    setPending(EMPTY_PENDING);
    setConfirming(false);
    setErrorMsg(null);
  }

  async function confirmSubmit() {
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const updated = await submitStats(pending);
      onCharacterUpdate(updated);
      setPending(EMPTY_PENDING);
      setConfirming(false);
    } catch (err) {
      setErrorMsg('Не удалось сохранить распределение. Попробуй ещё раз.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Group header={<Header>Свободных очков: {remaining}</Header>}>
        {STAT_DEFS.map((stat) => (
          <div className="stat-row" key={stat.key}>
            <span className="stat-row__label">{stat.label}</span>
            <div className="stat-row__controls">
              <Button
                mode="secondary"
                size="s"
                disabled={pending[stat.key] <= 0}
                onClick={() => decrement(stat.key)}
              >
                −
              </Button>
              <span className="stat-row__value">{previewStats[stat.key]}</span>
              <Button mode="secondary" size="s" disabled={remaining <= 0} onClick={() => increment(stat.key)}>
                +
              </Button>
            </div>
          </div>
        ))}
      </Group>

      <Group header={<Header>Предпросмотр</Header>}>
        {DERIVED_DEFS.map((row) => {
          const before = character.derived[row.key];
          const after = previewDerived[row.clientKey];
          const changed = totalPending > 0 && row.format(before) !== row.format(after);
          return (
            <div className="stat-row" key={row.key}>
              <span className="stat-row__label">{row.label}</span>
              <span className={changed ? 'derived-delta derived-delta--changed' : 'derived-delta'}>
                {changed ? `${row.format(before)} → ${row.format(after)}` : row.format(before)}
              </span>
            </div>
          );
        })}
      </Group>

      {errorMsg && (
        <Div>
          <Text style={{ color: '#c81e3a' }}>{errorMsg}</Text>
        </Div>
      )}

      {confirming ? (
        <div className="confirm-warning">
          <Text>Вложенные очки нельзя будет перераспределить бесплатно. Продолжить?</Text>
          <div className="confirm-warning__actions">
            <Button mode="primary" loading={submitting} onClick={confirmSubmit}>
              Да, подтвердить
            </Button>
            <Button mode="secondary" disabled={submitting} onClick={() => setConfirming(false)}>
              Отмена
            </Button>
          </div>
        </div>
      ) : (
        <Div style={{ display: 'flex', gap: 8 }}>
          <Button mode="secondary" disabled={totalPending === 0} onClick={reset} stretched>
            Сбросить
          </Button>
          <Button
            mode="primary"
            disabled={totalPending === 0}
            onClick={() => setConfirming(true)}
            stretched
          >
            Подтвердить
          </Button>
        </Div>
      )}
      <Caption level="1" style={{ padding: '0 16px 16px', opacity: 0.7 }}>
        Распределение статов постоянно. Сброс появится позже как платная операция.
      </Caption>
    </>
  );
}
