import { useMemo, useState } from 'react';
import { Group, Header, Button, Div, Text, Caption } from '@vkontakte/vkui';
import { computeDerived } from '../formulas.js';
import { submitStats } from '../api.js';

// toFixed режет 0.075 -> "0.07" из-за бинарного представления числа -
// небольшой эпсилон убирает эту ложную "не докрутку" в отображении.
const EPS = 1e-9;

const STAT_DEFS = [
  { key: 'str', label: '💪 Сила' },
  { key: 'agi', label: '🏃 Ловкость' },
  { key: 'int', label: '🧠 Интеллект' },
  { key: 'vit', label: '❤️ Выносливость' },
  { key: 'wil', label: '✨ Воля' },
];

// Каждая строка предпросмотра раскрывается по нажатию (2026-10-16, просьба
// владельца): откуда берётся число и где оно работает. Числа в текстах - те
// же, что в formulas.js (а там - зеркало game/combat/balance_config.py).
const PRIMARY_HINT = {
  warrior: '2 за каждое очко Силы',
  mage: '2 за каждое очко Интеллекта',
  rogue: '1,5 за каждое очко Ловкости',
};

const DERIVED_DEFS = [
  {
    key: 'max_hp', clientKey: 'maxHp', label: 'Макс. HP', format: (v) => Math.round(v),
    hint: (c) => 'Здоровье: 60 база, +22 за уровень, +8 за каждое очко Выносливости и надбавка ранга уровня.'
      + (c.base_class === 'warrior' && !c.subclass ? ' Воин до выбора подкласса получает ещё +10%.' : ''),
  },
  {
    key: 'damage', clientKey: 'damage', label: '⚔️ Урон', format: (v) => (v + EPS).toFixed(1),
    hint: (c) => `Сила обычной атаки: база ранга уровня + ${PRIMARY_HINT[c.base_class] || 'основной стат'}. `
      + 'Навыки бьют на свой процент от этого числа, крит - в 1,5 раза сильнее.',
  },
  {
    key: 'crit_chance',
    clientKey: 'critChance',
    label: '💥 Шанс крита',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: (c) => '0,3% за каждое очко Ловкости, не больше 60%. Крит бьёт в 1,5 раза сильнее.'
      + (c.base_class === 'rogue' && !c.subclass ? ' Разбойник до выбора подкласса получает ещё +10%.' : ''),
  },
  {
    // патч 14, ч.2.2: «Митигация» переименована в понятное «Снижение урона»
    key: 'mitigation',
    clientKey: 'mitigation',
    label: '🛡️ Снижение урона',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: () => '0,2% за каждое очко Выносливости, не больше 50%. На столько меньше урона ты получаешь '
      + 'от любых ударов - и мобов, и игроков.',
  },
  {
    key: 'control_resist',
    clientKey: 'controlResist',
    label: '🧿 Сопротивление контролю (PvP)',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: () => '1% за каждое очко Воли, не больше 75%. Нужно только в PvP: это шанс устоять, когда игрок '
      + 'оглушает или замораживает навыком. Каждый следующий контроль подряд проверяется удвоенной Волей. '
      + 'Мобы контроль не накладывают, а рейдовые механики Воля не отражает.',
  },
  {
    key: 'support_power',
    clientKey: 'supportPower',
    label: '✨ Сила поддержки',
    // Доля от макс. HP (0.005 за очко Воли), а не плоское число: в виде 0.37
    // было непонятно, что это и к чему применяется.
    format: (v) => `${(v * 100 + EPS).toFixed(1)}% HP`,
    hint: (c, d) => '0,5% от макс. HP за каждое очко Воли. Сейчас работает только у Тёмного мистика: Оберег '
      + 'ставит щит на 85% этой доли, Круг тьмы лечит каждого в группе, включая самого мистика, на 150%.'
      + (c.subclass === 'dark_mystic'
        ? ` У тебя без бонусов талантов: щит ~${Math.round(d.maxHp * d.supportPower * 0.85)} HP, `
          + `круг ~${Math.round(d.maxHp * d.supportPower * 1.5)} HP.`
        : ''),
  },
  {
    key: 'poison_power',
    clientKey: 'poisonPower',
    label: '☠ Сила яда за ход',
    // Урон ядом идёт мимо обычного урона и зависит от Воли и Ловкости, поэтому
    // по остальным строкам его не видно. Показываем только тем, кому он нужен.
    onlyFor: 'poisoner',
    format: (v) => (v + EPS).toFixed(1),
    hint: () => 'Урон яда за ход на полных 3 стаках: 0,95 за каждое очко Воли и 0,65 за каждое очко Ловкости.',
  },
];

const DODGE_HINT = '0,3% за каждое очко Ловкости, не больше 60%. Это шанс целиком избежать обычной атаки; '
  + 'от навыков ты уклоняешься вчетверо реже (число в скобках). Эликсиры и баффы добавляют сверху, общий '
  + 'потолок 80%.';

function DerivedRow({ label, value, changed, hint, open, onToggle }) {
  return (
    <>
      <div className="stat-row stat-row--toggle" role="button" tabIndex={0} aria-expanded={open}
        onClick={onToggle} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onToggle(); }}>
        <span className="stat-row__label">{label} <span className="stat-row__chevron">{open ? '▾' : '▸'}</span></span>
        <span className={changed ? 'derived-delta derived-delta--changed' : 'derived-delta'}>{value}</span>
      </div>
      {open && <Caption level="1" className="stat-row__hint">{hint}</Caption>}
    </>
  );
}

// Патч 34, ч.1: уворот - составная строка (от атак + от способностей вместе),
// генерическому DERIVED_DEFS не подходит (там один ключ = одно значение).
function formatDodge(dodge, abilityDodge) {
  return `${(dodge * 100 + EPS).toFixed(1)}% (от способностей: ${(abilityDodge * 100 + EPS).toFixed(1)}%)`;
}

const EMPTY_PENDING = { str: 0, agi: 0, int: 0, vit: 0, wil: 0 };

// Сервер отвечает конкретным кодом, а экран показывал «попробуй ещё раз» -
// для «не хватает очков» это прямая неправда: повтор ничего не изменит.
const SAVE_ERRORS = {
  not_enough_points: 'Не хватает свободных очков.',
  nothing_to_apply: 'Нечего применять: сначала распредели очки.',
  invalid_increment: 'Некорректное распределение.',
  character_not_found: 'Персонаж не найден.',
};

export default function StatsTab({ character, onCharacterUpdate }) {
  const [pending, setPending] = useState(EMPTY_PENDING);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [openHint, setOpenHint] = useState(null);

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
    () => computeDerived({
      level: character.level, baseClass: character.base_class, subclass: character.subclass,
      stats: previewStats, gearBonus: character.gear_bonus,
    }),
    [character.level, character.base_class, character.subclass, previewStats, character.gear_bonus],
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
      setErrorMsg(SAVE_ERRORS[err?.message] || 'Не удалось сохранить распределение. Попробуй ещё раз.');
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
              <span className="stat-row__value">
                {previewStats[stat.key]}
                {character.gear_bonus?.[stat.key] ? (
                  <span className="stat-row__gear" title="от снаряжения"> +{character.gear_bonus[stat.key]}</span>
                ) : null}
              </span>
              <Button mode="secondary" size="s" disabled={remaining <= 0} onClick={() => increment(stat.key)}>
                +
              </Button>
            </div>
          </div>
        ))}
        {Object.values(character.gear_bonus || {}).some(Boolean) && (
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            Зелёное <span className="stat-row__gear">+N</span> - от надетого снаряжения. Оно уже учтено в
            предпросмотре ниже и в бою: урон и навыки растут от основного стата, здоровье - от выносливости.
          </Caption>
        )}
      </Group>

      {character.fishing && (
        <Group header={<Header>🎣 Рыбалка</Header>}>
          <div className="stat-row">
            <span className="stat-row__label">Уровень</span>
            <span className="stat-row__value">{character.fishing.level}</span>
          </div>
          <div className="stat-row">
            <span className="stat-row__label">Опыт</span>
            <span className="stat-row__value">
              {character.fishing.xp} / {character.fishing.xp_to_next}
            </span>
          </div>
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            У уровня рыбалки нет потолка. Он повышает шанс на крупную рыбу,
            снижает обрыв лески и увеличивает садок.
          </Caption>
        </Group>
      )}

      {character.mining && (
        <Group header={<Header>⛏ Горное дело</Header>}>
          <div className="stat-row">
            <span className="stat-row__label">Уровень</span>
            <span className="stat-row__value">{character.mining.level}</span>
          </div>
          <div className="stat-row">
            <span className="stat-row__label">Опыт</span>
            <span className="stat-row__value">
              {character.mining.xp} / {character.mining.xp_to_next}
            </span>
          </div>
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            Потолка нет. Уровень ускоряет добычу и повышает шанс на редкую руду.
          </Caption>
        </Group>
      )}

      <Group header={<Header>Предпросмотр</Header>}>
        {DERIVED_DEFS.filter((row) => !row.onlyFor || row.onlyFor === character.subclass).map((row) => {
          const before = character.derived[row.key];
          const after = previewDerived[row.clientKey];
          const changed = totalPending > 0 && row.format(before) !== row.format(after);
          return (
            <DerivedRow
              key={row.key} label={row.label} open={openHint === row.key}
              onToggle={() => setOpenHint(openHint === row.key ? null : row.key)}
              value={changed ? `${row.format(before)} → ${row.format(after)}` : row.format(before)}
              changed={changed} hint={row.hint(character, previewDerived)}
            />
          );
        })}
        {(() => {
          const before = formatDodge(character.derived.dodge_chance, character.derived.ability_dodge_chance);
          const after = formatDodge(previewDerived.dodgeChance, previewDerived.abilityDodgeChance);
          const changed = totalPending > 0 && before !== after;
          return (
            <DerivedRow
              label="🌀 Уклонение" open={openHint === 'dodge'}
              onToggle={() => setOpenHint(openHint === 'dodge' ? null : 'dodge')}
              value={changed ? `${before} → ${after}` : before} changed={changed} hint={DODGE_HINT}
            />
          );
        })()}
        <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
          Нажми на строку - покажу, откуда берётся число и где оно работает.
        </Caption>
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
