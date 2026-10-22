import { useCallback, useEffect, useState } from 'react';
import {
  Button, Div, Group, Header, Placeholder, TabsItem,
} from '@vkontakte/vkui';
import Tabs from './ScrollTabs.jsx';
import { craftItem, craftTool, getCraft, upgradeCraft } from '../api.js';
import ItemIcon from './ItemIcon.jsx';
import Skeleton from './Skeleton.jsx';
import Sparks from './Sparks.jsx';
import { Empty, SectionHead, Sheet } from './ui.jsx';

// Патч 72: мастерская. Два подраздела - «Крафт» (сковать/перековать) и
// «Улучшение» (инструменты и ступени процентов).
//
// Патч 74: руда сворачивается ПО ВИДАМ. Плоский список давал 24 строки
// (6 видов x 4 градации) и повторялся дважды - разделы тонули в нём. Теперь
// видно шесть строк, а градации раскрываются по нажатию на вид.
//
// Чисел будущего предмета здесь НЕТ намеренно: игрок видит, куда целится
// специализация (полоски предрасположенности), но не что именно выпадет.

const STAT_TITLES = {
  str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Выносливость', wil: 'Воля',
  primary: 'Основной стат',
};

const SUBTABS = [
  { id: 'craft', label: 'Крафт' },
  { id: 'upgrade', label: 'Улучшение' },
];

// Порядок тот же, что в game/economy/mining_config.GRADES - от худшей к лучшей.
const GRADE_ORDER = ['common', 'rare', 'epic', 'legendary'];

function statLine(stats) {
  const entries = Object.entries(stats || {}).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return '-';
  return entries.map(([stat, value]) => `${STAT_TITLES[stat] || stat} +${value}`).join(' · ');
}

/** Плоский список руды -> сгруппированный по виду, градации внутри по порядку. */
function byOreType(rows) {
  const groups = new Map();
  rows.forEach((row) => {
    if (!groups.has(row.id)) {
      groups.set(row.id, { ...row, total: 0, grades: [] });
    }
    const group = groups.get(row.id);
    group.total += row.count;
    group.grades.push(row);
  });
  return [...groups.values()]
    .map((group) => ({
      ...group,
      grades: group.grades.sort(
        (a, b) => GRADE_ORDER.indexOf(a.grade) - GRADE_ORDER.indexOf(b.grade),
      ),
    }))
    .sort((a, b) => a.tier - b.tier);
}

// --- Ковка (2026-10-17): слоты «предмет + руда», ниже - что получится ---
// Пустые слоты нажимаются и открывают выбор снизу. Шансы статов считает
// сервер (miniapp_craft_api._chances) по градации выбранной руды: сменил
// руду - полоски сразу показывают, куда уйдут очки.

function PickSheet({ title, onClose, children }) {
  return (
    <>
      <div className="nav-scrim" onClick={onClose} aria-hidden="true" />
      <div className="crown-sheet" role="dialog" aria-label={title}>
        <div className="forge-sheet__title">{title}</div>
        {children}
      </div>
    </>
  );
}

function ForgeSlot({ label, filled, onClick, children }) {
  return (
    <button type="button" className={`forge-slot${filled ? ' forge-slot--filled' : ''}`} onClick={onClick}>
      {filled ? children : (
        <>
          <span className="forge-slot__plus">+</span>
          <span className="forge-slot__label">{label}</span>
        </>
      )}
    </button>
  );
}

// Наковальня между слотами (2026-10-22): раскаляется, когда всё выбрано, и
// принимает удар при ковке - strike растёт с каждой удачной операцией.
function Anvil({ hot, strike }) {
  return (
    <span className={`forge-anvil${hot ? ' forge-anvil--hot' : ''}`}>
      <svg key={strike} className={strike ? 'forge-anvil__svg forge-anvil__svg--strike' : 'forge-anvil__svg'} viewBox="0 0 64 48" width="56" height="42" aria-hidden="true">
        <path d="M6 10h40c6 0 12 3 14 8H46l-4 6H22l-4-6H10C8 18 6 14 6 10z" fill="currentColor" />
        <path d="M24 24h16l3 12H21z" fill="currentColor" opacity="0.85" />
        <path d="M16 36h32v6H16z" fill="currentColor" />
      </svg>
      <Sparks burst={strike} />
    </span>
  );
}

// Ступени эффективности: от минимума до потолка, пройденные залиты.
function EffLadder({ eff, now, next }) {
  const steps = [];
  for (let v = eff.min; v <= eff.max; v += eff.step) steps.push(v);
  return (
    <div className="eff-ladder">
      {steps.map((v) => (
        <span
          key={v}
          className={`eff-ladder__step${v <= now ? ' eff-ladder__step--done' : ''}${v === next ? ' eff-ladder__step--next' : ''}${v > eff.craft_max ? ' eff-ladder__step--over' : ''}`}
        >
          {v}
        </span>
      ))}
    </div>
  );
}

function ResultSheet({ result, onClose }) {
  const item = result.item;
  const rar = item?.rarity;
  const nameClass = `forge-result__name rarity-text--${rar || 'common'}`;
  return (
    <Sheet title="Готово" icon="⚒" onClose={onClose} className="forge-result">
      <div className="forge-result__stage">
        {item && <ItemIcon icon={item.icon} rarity={item.rarity} alt={item.name} size={112} />}
        {!item && result.ceiling && <ItemIcon icon={`tool:${result.ceiling}`} alt="Инструмент" size={112} />}
        <Sparks burst={1} instant />
      </div>
      {item && <b className={nameClass}>{item.name}</b>}
      {result.efficiency_after ? (
        <p className="forge-result__big">{result.efficiency_before}% → {result.efficiency_after}%</p>
      ) : item ? (
        <p className="forge-result__big">{item.efficiency}%</p>
      ) : (
        <p className="forge-result__big">Инструмент до {result.ceiling}%</p>
      )}
      {item && <p className="forge-result__stats">{statLine(item.stats)}</p>}
      <button type="button" className="pill-btn pill-btn--main forge-result__ok" onClick={onClose}>Забрать</button>
    </Sheet>
  );
}

function ChanceBars({ chances }) {
  return (
    <div className="craft-lean">
      {chances.map(({ stat, pct }) => (
        <div className="craft-lean__row" key={stat}>
          <span className="craft-lean__name">{STAT_TITLES[stat] || stat}</span>
          <span className="craft-lean__track">
            <span className="craft-lean__fill forge-fill" style={{ width: `${pct}%` }} />
          </span>
          <span className="forge-pct">{pct}%</span>
        </div>
      ))}
    </div>
  );
}

function Forge({ data, busy, run, strike }) {
  const [itemId, setItemId] = useState(null);
  const [ore, setOre] = useState(null); // {id, grade}
  const [spec, setSpec] = useState(null);
  const [picker, setPicker] = useState(null); // 'item' | 'ore'
  const [confirming, setConfirming] = useState(false);

  const item = data.items.find((i) => i.id === itemId) || null;
  const cost = item ? item.next_craft_cost : data.ore[0]?.craft_cost;
  const oreRow = ore ? data.ore.find((o) => o.id === ore.id && o.grade === ore.grade) : null;
  const specs = item ? (data.specs_by_source?.[item.source_id] ?? data.specs) : data.specs;
  const chosen = specs.find((s) => s.id === spec) || null;
  // 2026-10-17, решение владельца: в ковку - только ещё не кованые вещи.
  // Руда - все градации: тир задаёт стартовую эффективность, градация -
  // точность статов (подсказки в выборе руды и под шансами).
  const forgeable = data.items.filter((i) => !i.spec);
  const groups = byOreType(data.ore.filter((o) => o.craft_efficiency !== null));
  // Главный стат выбранного варианта и его шанс по градации - для подсказки в выборе руды.
  const topChance = (grade) => (chosen ? chosen.chances[grade]?.[0] : null);
  const reset = () => setConfirming(false);

  return (
    <>
      <Group header={<Header>Ковка</Header>}>
        <Div>
          <div className="forge-slots">
            <ForgeSlot label="Предмет" filled={!!item} onClick={() => { setPicker('item'); reset(); }}>
              <ItemIcon icon={item?.icon} rarity={item?.rarity} alt={item?.name} />
              <span className="forge-slot__name">{item?.name}</span>
              {item?.spec && <span className="forge-slot__sub">{item.spec_title} · {item.efficiency}%</span>}
            </ForgeSlot>
            <Anvil hot={Boolean(item && oreRow && chosen)} strike={strike} />
            <ForgeSlot label="Руда" filled={!!oreRow} onClick={() => { setPicker('ore'); reset(); }}>
              <ItemIcon icon={oreRow ? `ore:${oreRow.id}` : null} rarity={oreRow?.grade} alt={oreRow?.name} />
              <span className="forge-slot__name">{oreRow?.name}</span>
              {oreRow && <span className="forge-slot__sub">{oreRow.grade_name} · ×{cost}</span>}
            </ForgeSlot>
          </div>
          <p className="craft-hint">
            Выбери некованый предмет с рейд-босса и руду. Тир руды задаёт стартовую эффективность (80-100%),
            градация - точность: чем она выше, тем больше очков уходит в главные статы варианта.
          </p>
        </Div>
      </Group>

      <Group header={<Header>Что получится</Header>}>
        <Div>
          <div className="faction-choice">
            {specs.map((s) => (
              <button key={s.id} type="button"
                className={`faction-choice__item${s.id === spec ? ' faction-choice__item--active' : ''}`}
                onClick={() => { setSpec(s.id); reset(); }}>
                <b>{s.title}</b>
              </button>
            ))}
          </div>
          {chosen ? (
            <>
              <p className="guild-line"><b>{chosen.name}</b></p>
              {chosen.flavor && <p className="craft-hint">{chosen.flavor}</p>}
              <ChanceBars chances={chosen.chances[ore?.grade || 'common']} />
              <p className="craft-hint">
                {oreRow
                  ? `Шансы для руды «${oreRow.grade_name}», стартовая эффективность ${oreRow.craft_efficiency}%. `
                  : 'Шансы для обычной руды: редкая, эпическая и легендарная сдвигают их к главным статам. '}
                Процент - шанс каждой порции очков уйти в этот стат.
              </p>
            </>
          ) : (
            <p className="craft-hint">Выбери, во что ковать: танк, урон или поддержка.</p>
          )}
        </Div>
      </Group>

      <Div>
        {confirming ? (
          <div className="forge-confirm">
            <p className="guild-line">
              {item.spec ? 'Перековать' : 'Сковать'} «{item.name}» в «{chosen.name}» за {cost} × {oreRow.name} ({oreRow.grade_name})?{item.spec ? ' Эффективность сбросится, статы разыграются заново.' : ''}
            </p>
            <div className="guild-row">
              <Button size="m" disabled={busy}
                onClick={() => {
                  setConfirming(false);
                  run(() => craftItem(item.id, spec, ore.id, ore.grade));
                }}>
                Да, создать
              </Button>
              <Button size="m" mode="secondary" disabled={busy} onClick={reset}>Отмена</Button>
            </div>
          </div>
        ) : (
          <Button size="l" stretched mode="primary"
            disabled={busy || !item || !oreRow || !chosen || oreRow.count < cost}
            onClick={() => setConfirming(true)}>
            {!item ? 'Выбери предмет' : !oreRow ? 'Выбери руду' : !chosen ? 'Выбери результат'
              : oreRow.count < cost ? 'Не хватает руды' : 'Создать'}
          </Button>
        )}
      </Div>

      {picker === 'item' && (
        <PickSheet title="Предмет для ковки" onClose={() => setPicker(null)}>
          {forgeable.length === 0 && <p className="craft-hint">Некованых вещей нет - нужен новый предмет с рейд-босса.</p>}
          {forgeable.map((row) => (
            <button key={row.id} type="button"
              className={`crown-sheet__item${row.id === itemId ? ' crown-sheet__item--active' : ''}`}
              onClick={() => { setItemId(row.id); setSpec(null); setPicker(null); }}>
              <ItemIcon icon={row.icon} rarity={row.rarity} alt={row.name} />
              <span className="crown-sheet__text">
                <b>{row.name}</b>
                <small>
                  {row.spec ? `${row.spec_title} · ${row.efficiency}% · ` : 'не кован · '}
                  {statLine(row.stats)} · ковка {row.next_craft_cost} руды
                </small>
              </span>
            </button>
          ))}
        </PickSheet>
      )}

      {picker === 'ore' && (
        <PickSheet title={`Руда (нужно ${cost} шт.)`} onClose={() => setPicker(null)}>
          <p className="craft-hint forge-sheet__hint">
            Тир руды - стартовая эффективность. Градация - точность статов: обычная оставляет шансы как есть,
            редкая, эпическая и легендарная всё сильнее сдвигают очки в главные статы.
            {chosen ? '' : ' Выбери вариант ковки - и здесь будет видно, как градация меняет главный стат.'}
          </p>
          {groups.length === 0 && <p className="craft-hint">Подходящей руды нет: в ковку идёт руда первых трёх тиров.</p>}
          {groups.map((group) => group.grades.map((row) => {
            const enough = row.count >= cost;
            return (
              <button key={`${row.id}:${row.grade}`} type="button" disabled={!enough}
                className={`crown-sheet__item${ore?.id === row.id && ore?.grade === row.grade ? ' crown-sheet__item--active' : ''}`}
                onClick={() => { setOre({ id: row.id, grade: row.grade }); setPicker(null); }}>
                <ItemIcon icon={`ore:${row.id}`} rarity={row.grade} alt={row.name} />
                <span className="crown-sheet__text">
                  <b>{row.name} · {row.grade_name}</b>
                  <small>
                    старт {row.craft_efficiency}%
                    {topChance(row.grade) ? ` · ${STAT_TITLES[topChance(row.grade).stat] || topChance(row.grade).stat} ${topChance(row.grade).pct}%` : ''}
                    {' · '}у тебя {row.count}{enough ? '' : ' - не хватает'}
                  </small>
                </span>
              </button>
            );
          }))}
        </PickSheet>
      )}
    </>
  );
}

// --- Улучшение (2026-10-19): как ковка - слоты «предмет + инструмент»,
// ниже что получится, подтверждение и подсказки на каждом шаге. ---

// Выковка инструмента (2026-10-19): тот же формат - слот «Руда», под ним что
// получится, кнопка с подтверждением. Градация руды на инструмент не влияет,
// поэтому выбирается вид руды, а уходит самая простая градация, которой хватает.
function ToolForge({ data, busy, run, need, itemName }) {
  const [oreId, setOreId] = useState(null);
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const groups = byOreType(data.ore.filter((o) => o.tool_ceiling !== null));
  const group = groups.find((g) => g.id === oreId) || null;
  const pick = group ? group.grades.find((row) => row.count >= row.tool_cost) : null;
  const weak = (g) => need !== null && g.tool_ceiling < need;

  return (
    <>
      <Group header={<Header>Выковать инструмент</Header>}>
        <Div>
          <div className="forge-slots">
            <ForgeSlot label="Руда" filled={!!group} onClick={() => { setOpen(true); setConfirming(false); }}>
              <ItemIcon icon={group ? `ore:${group.id}` : null} rarity={group?.grades[group.grades.length - 1]?.grade} alt={group?.name} />
              <span className="forge-slot__name">{group?.name}</span>
              {group && <span className="forge-slot__sub">у тебя {group.total}</span>}
            </ForgeSlot>
            <span className="forge-plus">=</span>
            <ForgeSlot label="Инструмент" filled={!!group} onClick={() => { setOpen(true); setConfirming(false); }}>
              <ItemIcon icon={group ? `tool:${group.tool_ceiling}` : null} alt="Инструмент" />
              <span className="forge-slot__name">{group ? `До ${group.tool_ceiling}%` : ''}</span>
            </ForgeSlot>
          </div>
          {group ? (
            <p className="craft-hint">
              Получится инструмент, который качает до {group.tool_ceiling}%. Уйдёт {group.tool_cost} шт.
              {pick ? ` (${pick.grade_name.toLowerCase()})` : ''}, у тебя {group.total}.
              {weak(group) ? ` Для «${itemName}» он слабоват - нужен потолок от ${need}%.` : ''}
            </p>
          ) : (
            <p className="craft-hint">
              Положи руду - инструмент куётся из неё. Тир руды задаёт потолок: чем дороже руда, тем выше
              ступень он закроет.{need !== null ? ` Для «${itemName}» нужен потолок от ${need}%.` : ''}
            </p>
          )}
        </Div>
        <Div>
          {confirming ? (
            <div className="forge-confirm">
              <p className="guild-line">Выковать инструмент «до {group.tool_ceiling}%» из {group.tool_cost} × {group.name}?</p>
              <div className="guild-row">
                <Button size="m" disabled={busy}
                  onClick={() => { setConfirming(false); run(() => craftTool(pick.id, pick.grade)); }}>
                  Да, выковать
                </Button>
                <Button size="m" mode="secondary" disabled={busy} onClick={() => setConfirming(false)}>Отмена</Button>
              </div>
            </div>
          ) : (
            <Button size="l" stretched mode="secondary" disabled={busy || !group || !pick} onClick={() => setConfirming(true)}>
              {!group ? 'Выбери руду' : !pick ? 'Не хватает руды' : 'Выковать инструмент'}
            </Button>
          )}
        </Div>
      </Group>

      {open && (
        <PickSheet title="Руда для инструмента" onClose={() => setOpen(false)}>
          <p className="craft-hint forge-sheet__hint">
            Тир руды - потолок инструмента. Градация не важна: уйдёт самая простая, которой хватает.
            {need !== null ? ` Для «${itemName}» нужен потолок от ${need}%.` : ''}
          </p>
          {groups.length === 0 && <p className="craft-hint">Подходящей руды нет: нужна руда 1-5 тиров с рудников.</p>}
          {groups.map((g) => {
            const enough = g.grades.some((row) => row.count >= row.tool_cost);
            // Градации не смешиваются: считаем самую большую кучку одной
            // градации, а не всю руду (2026-10-22, жалоба: «нужно 8, у тебя 9
            // - не хватает»).
            const best = Math.max(0, ...g.grades.map((row) => row.count));
            return (
              <button key={g.id} type="button" disabled={!enough}
                className={`crown-sheet__item${g.id === oreId ? ' crown-sheet__item--active' : ''}`}
                onClick={() => { setOreId(g.id); setOpen(false); }}>
                <ItemIcon icon={`ore:${g.id}`} rarity={g.grades[g.grades.length - 1]?.grade} alt={g.name} />
                <span className="crown-sheet__text">
                  <b>{g.name} → до {g.tool_ceiling}%</b>
                  <small>
                    нужно {g.tool_cost} одной градации · у тебя {best}
                    {g.total > best ? ` (всего ${g.total}, градации не смешиваются)` : ''}
                    {enough ? '' : ' - не хватает'}
                    {weak(g) ? ' · слабоват для этой вещи' : ''}
                  </small>
                </span>
              </button>
            );
          })}
        </PickSheet>
      )}
    </>
  );
}

function Upgrade({ data, busy, run, strike }) {
  const [itemId, setItemId] = useState(null);
  const [ceiling, setCeiling] = useState(null);
  const [picker, setPicker] = useState(null); // 'item' | 'tool'
  const [confirming, setConfirming] = useState(false);

  const forged = data.items.filter((i) => i.spec);
  const item = forged.find((i) => i.id === itemId) || null;
  const tool = data.tools.find((t) => t.ceiling === ceiling) || null;
  const need = item?.next_efficiency ?? null;
  const fits = (t) => need !== null && t.ceiling >= need;
  const reset = () => setConfirming(false);

  let blocker = null;
  if (!item) blocker = 'Выбери предмет';
  else if (need === null) blocker = 'Уже потолок';
  else if (!tool) blocker = 'Выбери инструмент';
  else if (!fits(tool)) blocker = `Нужен инструмент до ${need}%`;

  return (
    <>
      <Group header={<Header>Улучшение</Header>}>
        <Div>
          <div className="forge-slots">
            <ForgeSlot label="Предмет" filled={!!item} onClick={() => { setPicker('item'); reset(); }}>
              <ItemIcon icon={item?.icon} rarity={item?.rarity} alt={item?.name} />
              <span className="forge-slot__name">{item?.name}</span>
              {item && <span className="forge-slot__sub">{item.spec_title} · {item.efficiency}%</span>}
            </ForgeSlot>
            <Anvil hot={Boolean(item && tool && need !== null && fits(tool))} strike={strike} />
            <ForgeSlot label="Инструмент" filled={!!tool} onClick={() => { setPicker('tool'); reset(); }}>
              <ItemIcon icon={tool ? `tool:${tool.ceiling}` : null} alt="Инструмент" />
              <span className="forge-slot__name">{tool ? `До ${tool.ceiling}%` : ''}</span>
              {tool && <span className="forge-slot__sub">у тебя ×{tool.count}</span>}
            </ForgeSlot>
          </div>
          <p className="craft-hint">
            Улучшение поднимает эффективность выкованной вещи на одну ступень (+10%, до 120%) - все её статы
            растут вместе с процентом. Каждая ступень тратит один инструмент, неудач не бывает.
          </p>
        </Div>
      </Group>

      <Group header={<Header>Что получится</Header>}>
        <Div>
          {!item && <p className="craft-hint">Выбери выкованную вещь - здесь будет видно, как вырастут статы.</p>}
          {item && need === null && <p className="craft-hint">«{item.name}» уже на {item.efficiency}% - это потолок.</p>}
          {item && data.efficiency && <EffLadder eff={data.efficiency} now={item.efficiency} next={need} />}
          {item && need !== null && (
            <>
              <p className="guild-line"><b>{item.efficiency}% → {need}%</b></p>
              <p className="craft-hint">Сейчас: {statLine(item.stats)}</p>
              <p className="craft-hint">Станет: {statLine(item.next_stats)}</p>
              <p className="craft-hint">
                {tool
                  ? (fits(tool)
                    ? `Подойдёт: инструмент качает до ${tool.ceiling}%.${tool.ceiling > need ? ' Он сильнее, чем нужно - можно сберечь его для ступени выше.' : ''}`
                    : `Этот инструмент качает только до ${tool.ceiling}% - для ступени ${need}% нужен потолок не ниже ${need}%.`)
                  : `Для ступени ${need}% нужен инструмент с потолком от ${need}%.`}
              </p>
            </>
          )}
        </Div>
      </Group>

      <Div>
        {confirming ? (
          <div className="forge-confirm">
            <p className="guild-line">
              Улучшить «{item.name}» до {need}%, потратив инструмент «до {tool.ceiling}%»?
            </p>
            <div className="guild-row">
              <Button size="m" disabled={busy}
                onClick={() => { setConfirming(false); run(() => upgradeCraft(item.id, tool.ceiling)); }}>
                Да, улучшить
              </Button>
              <Button size="m" mode="secondary" disabled={busy} onClick={reset}>Отмена</Button>
            </div>
          </div>
        ) : (
          <Button size="l" stretched mode="primary" disabled={busy || !!blocker} onClick={() => setConfirming(true)}>
            {blocker || 'Улучшить'}
          </Button>
        )}
      </Div>

      <ToolForge data={data} busy={busy} run={run} need={need} itemName={item?.name} />

      {picker === 'item' && (
        <PickSheet title="Предмет для улучшения" onClose={() => setPicker(null)}>
          <p className="craft-hint forge-sheet__hint">Улучшать можно только выкованные вещи - сначала выкуй вещь с рейд-босса во вкладке «Крафт».</p>
          {forged.length === 0 && <p className="craft-hint">Выкованных вещей нет.</p>}
          {forged.map((row) => (
            <button key={row.id} type="button"
              className={`crown-sheet__item${row.id === itemId ? ' crown-sheet__item--active' : ''}`}
              onClick={() => { setItemId(row.id); setPicker(null); }}>
              <ItemIcon icon={row.icon} rarity={row.rarity} alt={row.name} />
              <span className="crown-sheet__text">
                <b>{row.name}</b>
                <small>
                  {row.spec_title} · {row.efficiency}%
                  {row.next_efficiency ? ` → ${row.next_efficiency}%` : ' · потолок'} · {statLine(row.stats)}
                </small>
              </span>
            </button>
          ))}
        </PickSheet>
      )}

      {picker === 'tool' && (
        <PickSheet title="Инструмент" onClose={() => setPicker(null)}>
          <p className="craft-hint forge-sheet__hint">
            {need !== null
              ? `Нужен потолок от ${need}%. Инструмент слабее не подойдёт, сильнее - подойдёт, но жалко.`
              : 'Сначала выбери предмет - будет видно, какой инструмент подходит.'}
          </p>
          {data.tools.length === 0 && <p className="craft-hint">Инструментов нет - выкуй ниже из руды.</p>}
          {data.tools.map((t) => (
            <button key={t.ceiling} type="button" disabled={need !== null && !fits(t)}
              className={`crown-sheet__item${t.ceiling === ceiling ? ' crown-sheet__item--active' : ''}`}
              onClick={() => { setCeiling(t.ceiling); setPicker(null); }}>
              <ItemIcon icon={`tool:${t.ceiling}`} alt="Инструмент" />
              <span className="crown-sheet__text">
                <b>Инструмент до {t.ceiling}%</b>
                <small>у тебя ×{t.count}{need !== null && !fits(t) ? ` - слабее нужного (${need}%)` : ''}</small>
              </span>
            </button>
          ))}
        </PickSheet>
      )}
    </>
  );
}

export default function CraftTab() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [subtab, setSubtab] = useState('craft');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [result, setResult] = useState(null);
  const [strike, setStrike] = useState(0);

  const load = useCallback(() => {
    setStatus('loading');
    return getCraft()
      .then((payload) => {
        setData(payload);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (status === 'loading') return <Skeleton />;
  if (status === 'error' || !data) {
    return (
      <Placeholder action={<Button onClick={load}>Попробовать снова</Button>}>
        Мастерская не открылась.
      </Placeholder>
    );
  }
  if (!data.items.length) {
    return (
      <Group>
        <Empty icon="🔨">Ковать пока не из чего. В мастерскую идут вещи с рейд-боссов.</Empty>
      </Group>
    );
  }

  const run = (action) => {
    setBusy(true);
    setNotice(null);
    action()
      .then((res) => {
        setStrike((s) => s + 1);
        setResult(res);
        // Без экрана загрузки: иначе ковка размонтируется и забудет выбор.
        return getCraft().then(setData);
      })
      .catch((error) => setNotice({ ok: false, text: error.message }))
      .finally(() => setBusy(false));
  };

  const forged = data.items.filter((i) => i.spec).length;
  const tools = data.tools.reduce((sum, t) => sum + t.count, 0);
  const stock = byOreType(data.ore);

  return (
    <>
      <SectionHead
        kind="craft" icon="⚒️" value={`${forged}/${data.items.length}`} label="вещей выковано"
        aside={<>🧰 {tools}<br /><small>инструментов</small></>}
      />
      <Tabs>
        {SUBTABS.map((tab) => (
          <TabsItem key={tab.id} selected={subtab === tab.id} onClick={() => setSubtab(tab.id)}>
            {tab.label}
          </TabsItem>
        ))}
      </Tabs>

      {notice && (
        <Div className={notice.ok ? 'craft-notice craft-notice--ok' : 'craft-notice craft-notice--bad'}>
          {notice.text}
        </Div>
      )}

      {subtab === 'craft' ? (
        <Forge data={data} busy={busy} run={run} strike={strike} />
      ) : (
        <Upgrade data={data} busy={busy} run={run} strike={strike} />
      )}

      {stock.length > 0 && (
        <Group header={<Header>Запас руды</Header>}>
          <div className="tile-grid ore-grid">
            {stock.map((g) => (
              <div className="tile ore-tile" key={g.id}>
                <ItemIcon icon={`ore:${g.id}`} rarity={g.grades[g.grades.length - 1]?.grade} alt={g.name} size={40} />
                <b className="tile__value">{g.total}</b>
                <small className="tile__label">{g.name}</small>
                <span className="ore-tile__grades">
                  {g.grades.map((row) => (
                    <i key={row.grade} className={`ore-dot ore-dot--${row.grade}`} title={`${row.grade_name}: ${row.count}`} />
                  ))}
                </span>
              </div>
            ))}
          </div>
        </Group>
      )}

      {result && <ResultSheet result={result} onClose={() => setResult(null)} />}
    </>
  );
}
