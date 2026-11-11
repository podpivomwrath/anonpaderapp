import { useMemo, useState } from 'react';
import { Group, Header, Button, Div, Text, Caption } from '@vkontakte/vkui';
import {
  computeDerived, damageStatValue, primaryThreshold, PRIMARY_STAT_BY_CLASS,
} from '../formulas.js';
import { submitStats } from '../api.js';
import StatRadar from './StatRadar.jsx';

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

// Тёмный мистик бьёт от Воли, Интеллект вторичный (2026-10-29).
function damageSource(c) {
  if (c.subclass === 'dark_mystic') return '1,2 за каждое очко Воли и 0,8 за каждое очко Интеллекта';
  return PRIMARY_HINT[c.base_class] || 'основная характеристика';
}

// Порог урона (stat_model.primary_value): у Тёмного мистика он считается не
// от Воли, а от смеси Воли и Интеллекта (2026-11-09, Илья Лут: подсказка
// сравнивала порог с полной Волей и пугала урезанием). Числа - из formulas.js.
function damageCapLine(c, st) {
  const stat = PRIMARY_STAT_BY_CLASS[c.base_class];
  const cap = Math.round(primaryThreshold(c.level, stat));
  const mystic = c.subclass === 'dark_mystic';
  const value = Math.round(damageStatValue(c.subclass, stat, st));
  const what = mystic
    ? `В урон идёт 0,6 Воли и 0,4 Интеллекта с вещами, у вас это ${value}.`
    : `В урон идёт основная характеристика с вещами, у вас ${value}.`;
  const tail = value > cap
    ? ` Сверх порога каждое очко считается примерно на треть: в урон сейчас идут ${cap} полностью и ещё ${value - cap} на треть.`
    : ' Сверх порога каждое очко будет считаться примерно на треть, а пока всё идёт полностью.';
  return `${what} Полностью считается до порога 30 + 2 за уровень${c.base_class === 'rogue' ? ', у Ловкости он на треть выше' : ''}: у вас ${cap}.${tail}`;
}

const DERIVED_DEFS = [
  {
    key: 'max_hp', clientKey: 'maxHp', label: 'Макс. HP', format: (v) => Math.round(v),
    hint: (c) => 'Здоровье: 60 база, +22 за уровень, +8 за каждое очко Выносливости и надбавка ранга уровня.'
      + (c.base_class === 'warrior' && !c.subclass ? ' Воин до выбора подкласса получает ещё +10%.' : ''),
  },
  {
    key: 'damage', clientKey: 'damage', label: '⚔️ Урон', format: (v) => (v + EPS).toFixed(1),
    hint: (c, _d, st) => `Сила обычной атаки: база ранга уровня + ${damageSource(c)}. `
      + damageCapLine(c, st)
      + ' Навыки бьют на свой процент от этого числа, крит - в 1,5 раза сильнее.',
  },
  {
    key: 'crit_chance',
    clientKey: 'critChance',
    label: '💥 Шанс крита',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: (c) => 'От Ловкости: первые очки дают больше всего. 100 Ловкости - 20%, 200 - 30%, выше 60% не бывает. '
      + 'Крит бьёт в 1,5 раза сильнее.'
      + (c.base_class === 'rogue' && !c.subclass ? ' Разбойник до выбора подкласса получает ещё +10%.' : '')
      + (c.subclass === 'shadow_blade' ? ' Ваш подкласс даёт ещё +15%.' : '')
      + (c.subclass === 'poisoner' ? ' Ваш подкласс даёт ещё +10%.' : ''),
  },
  {
    // патч 14, ч.2.2: «Митигация» переименована в понятное «Снижение урона»
    key: 'mitigation',
    clientKey: 'mitigation',
    label: '🛡️ Снижение урона',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: () => 'От Выносливости: 100 очков - 14%, 250 - 25%, выше 50% не бывает. На столько меньше урона '
      + 'вы получаете от любых ударов - и мобов, и игроков.',
  },
  {
    key: 'control_resist',
    clientKey: 'controlResist',
    label: '🧿 Сопротивление контролю (PvP)',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: () => 'Растёт от Воли, но каждое следующее очко даёт меньше: 50 Воли - 37%, 100 - 50%, 200 - 60%, '
      + 'больше 75% не бывает. Нужно только в PvP: это шанс устоять, когда игрок '
      + 'оглушает или замораживает навыком. Каждый следующий контроль подряд проверяется удвоенной Волей. '
      + 'Мобы контроль не накладывают, а рейдовые механики Воля не отражает.',
  },
  {
    key: 'crit_resist',
    clientKey: 'critResist',
    label: '🪨 Стойкость к крит-урону',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: () => 'На столько меньше прибавка крита, когда бьют по вам: при 100% крит прошёл бы как обычный удар. '
      + 'От Выносливости: 100 очков - 5%, '
      + '200 - 7,5%, 400 - 10%, выше 15% не бывает. Сверху - руна «Закалка» и кованые вещи: '
      + 'их сумма до 15% идёт полностью, всё сверху - вполовину, и не больше 30%.',
  },
  {
    key: 'accuracy',
    clientKey: 'accuracy',
    label: '🎯 Меткость',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: () => 'На столько процентов меньше уворот того, кого вы бьёте: при 20% уворот 25% становится 20%. Дают руна «Верный глаз» и кованые вещи. '
      + 'Сумма до 15% идёт полностью, всё сверху - вполовину, и не больше 30%.',
  },
  {
    key: 'dot_resist',
    clientKey: 'dotResist',
    label: '🧪 Стойкость к периодическому урону',
    format: (v) => `${(v * 100 + EPS).toFixed(1)}%`,
    hint: () => 'На столько слабее яд и горение по вам. Дают руна «Горькая кровь» и кованые вещи. '
      + 'Сумма до 15% идёт полностью, всё сверху - вполовину, и не больше 30%.',
  },
  {
    key: 'support_power',
    clientKey: 'supportPower',
    label: '✨ Сила поддержки',
    // Доля от макс. HP, а не плоское число: в виде 0.37 было непонятно, что
    // это и к чему применяется. С 2026-10-29 - с убывающей отдачей от Воли.
    format: (v) => `${(v * 100 + EPS).toFixed(1)}% HP`,
    hint: (c, d) => 'Растёт от Воли, но каждое следующее очко даёт меньше: 80 Воли - около 39% макс. HP, '
      + '200 - около 62%. Сейчас работает только у Тёмного мистика: Оберег '
      + 'ставит щит на 85% этой доли, Круг тьмы лечит каждого в группе, включая самого мистика, на 60% этой доли от его собственного здоровья, в одиночку - на 36%.'
      + (c.subclass === 'dark_mystic'
        ? ` У вас без баффов: щит ~${Math.round(d.maxHp * d.supportPower * 0.85)} HP, `
          + `круг вам ~${Math.round(d.maxHp * d.supportPower * 0.6)} HP в группе, ~${Math.round(d.maxHp * d.supportPower * 0.36)} HP в одиночку.`
        : ''),
  },
  {
    key: 'poison_power',
    clientKey: 'poisonPower',
    label: '☠ Сила яда за ход',
    // Урон ядом идёт мимо обычного урона и зависит от Воли и Ловкости, поэтому
    // по остальным строкам его не видно. С рунами-навыками яд у любого класса.
    format: (v) => (v + EPS).toFixed(1),
    hint: () => 'Урон яда «Отравленного клинка» за ход при 3 зарядах: 0,95 за каждое очко Воли '
      + 'и 0,65 за каждое очко Ловкости. Отравитель бьёт ядом на 25% сильнее.',
  },
  {
    key: 'dot_power',
    clientKey: 'dotPower',
    label: '🔥 Периодический урон',
    format: (v) => `+${(v * 100 + EPS).toFixed(1)}%`,
    hint: () => 'Прибавка к периодическому урону (горение и другое) от Воли: +0,6% за каждое очко. '
      + 'Яду она не прибавляется: Воля уже входит в силу яда.',
  },
];

const DODGE_HINT = 'От Воли: 100 очков - 13%, 250 - 22%, выше 45% не бывает. Это шанс целиком избежать '
  + 'обычной атаки; от навыков вы уклоняетесь вчетверо реже (число в скобках). Клинок теней и Отравитель '
  + 'получают ещё +5% от подкласса. Эликсиры и баффы добавляют сверху, общий потолок 80%.';

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
  nothing_to_apply: 'Нечего применять: сначала распределите очки.',
  invalid_increment: 'Некорректное распределение.',
  character_not_found: 'Персонаж не найден.',
};

export default function StatsTab({ character, onCharacterUpdate }) {
  const [pending, setPending] = useState(EMPTY_PENDING);
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [openHint, setOpenHint] = useState(null);
  const [saved, setSaved] = useState(0);

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
      stats: previewStats, gearBonus: character.gear_bonus, mods: character.derived_mods,
    }),
    [character.level, character.base_class, character.subclass, previewStats, character.gear_bonus,
      character.derived_mods],
  );

  const withGear = (stats) => Object.fromEntries(
    Object.entries(stats).map(([k, v]) => [k, v + (character.gear_bonus?.[k] || 0)]),
  );
  const barScale = Math.max(1, ...STAT_DEFS.map((d) => previewStats[d.key] + (character.gear_bonus?.[d.key] || 0)));

  function increment(key) {
    if (remaining <= 0) return;
    setPending((p) => ({ ...p, [key]: p[key] + 1 }));
  }

  function decrement(key) {
    if (pending[key] <= 0) return;
    setPending((p) => ({ ...p, [key]: p[key] - 1 }));
  }

  // Ввод числом (2026-10-24, владелец): нажал на значение - пишешь, сколько
  // вложить; больше свободных очков не встанет.
  const [editing, setEditing] = useState(null);
  const [draft, setDraft] = useState('');
  function startEdit(key) {
    if (character.unspent_points <= 0) return;
    setEditing(key);
    setDraft(pending[key] ? String(pending[key]) : '');
  }
  function commitEdit() {
    if (editing === null) return;
    const key = editing;
    const wanted = Math.max(0, Math.floor(Number(draft) || 0));
    const cap = remaining + pending[key];
    setPending((p) => ({ ...p, [key]: Math.min(wanted, cap) }));
    setEditing(null);
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
      setSaved((n) => n + 1);
    } catch (err) {
      setErrorMsg(SAVE_ERRORS[err?.message] || 'Не удалось сохранить распределение. Попробуйте ещё раз.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Group header={<Header>Свободных очков: {remaining}</Header>}>
        <StatRadar current={withGear(character.stats)} preview={withGear(previewStats)} burst={saved} />
        {STAT_DEFS.map((stat) => (
          <div className={pending[stat.key] ? 'stat-row stat-row--stat stat-row--pending' : 'stat-row stat-row--stat'} key={stat.key}>
            <span className="stat-row__bar" aria-hidden="true">
              <i style={{ width: `${(100 * (previewStats[stat.key] + (character.gear_bonus?.[stat.key] || 0))) / barScale}%` }} />
            </span>
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
              {editing === stat.key ? (
                <input
                  className="stat-row__input" type="number" inputMode="numeric" min="0"
                  max={remaining + pending[stat.key]} placeholder="+?" autoFocus aria-label={`Сколько вложить: ${stat.label}`}
                  value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commitEdit}
                  onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') setEditing(null); }}
                />
              ) : (
                <span
                  className={character.unspent_points > 0 ? 'stat-row__value stat-row__value--editable' : 'stat-row__value'}
                  role={character.unspent_points > 0 ? 'button' : undefined}
                  tabIndex={character.unspent_points > 0 ? 0 : undefined}
                  title={character.unspent_points > 0 ? 'Нажмите, чтобы ввести число' : undefined}
                  onClick={() => startEdit(stat.key)}
                  onKeyDown={(e) => { if (e.key === 'Enter') startEdit(stat.key); }}
                >
                  {previewStats[stat.key]}
                  {character.gear_bonus?.[stat.key] ? (
                    // Итог рядом с прибавкой (2026-10-29, баг-репорт: суммы не было видно).
                    <span className="stat-row__gear" title="от снаряжения">
                      {' '}+{character.gear_bonus[stat.key]} = {previewStats[stat.key] + character.gear_bonus[stat.key]}
                    </span>
                  ) : null}
                </span>
              )}
              <Button mode="secondary" size="s" disabled={remaining <= 0} onClick={() => increment(stat.key)}>
                +
              </Button>
            </div>
          </div>
        ))}
      </Group>

      {/* Рыбалка и горное дело (2026-10-21) - во вкладке «Ремёсла». */}

      <Group header={<Header>Предпросмотр</Header>}>
        <Caption level="1" className="stat-row__hint">Числа - как в бою: с вещами, активным пресетом и едой.</Caption>
        {DERIVED_DEFS.filter((row) => (!row.onlyFor || row.onlyFor === character.subclass) && row.notFor !== character.subclass).map((row) => {
          const before = character.derived[row.key];
          const after = previewDerived[row.clientKey];
          const changed = totalPending > 0 && row.format(before) !== row.format(after);
          return (
            <DerivedRow
              key={row.key} label={row.label} open={openHint === row.key}
              onToggle={() => setOpenHint(openHint === row.key ? null : row.key)}
              value={changed ? `${row.format(before)} → ${row.format(after)}` : row.format(before)}
              changed={changed} hint={row.hint(character, previewDerived, withGear(previewStats))}
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
    </>
  );
}
