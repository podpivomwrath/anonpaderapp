import { useCallback, useEffect, useState } from 'react';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, Spinner, Tabs, TabsItem,
} from '@vkontakte/vkui';
import { craftItem, craftTool, getCraft, upgradeCraft } from '../api.js';
import ItemIcon from './ItemIcon.jsx';

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

function Forge({ data, busy, run }) {
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
            <span className="forge-plus">+</span>
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

export default function CraftTab() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [subtab, setSubtab] = useState('craft');
  const [itemId, setItemId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => {
    setStatus('loading');
    return getCraft()
      .then((payload) => {
        setData(payload);
        setStatus('ready');
        setItemId((current) => current ?? payload.items[0]?.id ?? null);
      })
      .catch(() => setStatus('error'));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (status === 'loading') {
    return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 32 }}><Spinner /></Div>;
  }
  if (status === 'error' || !data) {
    return (
      <Placeholder action={<Button onClick={load}>Попробовать снова</Button>}>
        Мастерская не открылась.
      </Placeholder>
    );
  }
  if (!data.items.length) {
    return (
      <Placeholder icon={<div style={{ fontSize: 44 }}>🔨</div>}>
        Ковать пока не из чего. Нужен предмет с рейд-босса.
      </Placeholder>
    );
  }

  // Улучшать можно только выкованное: вещь прямо с босса сначала куют
  // под роль во вкладке «Крафт», и только потом она попадает сюда.
  const items = subtab === 'upgrade' ? data.items.filter((i) => i.spec) : data.items;
  const item = items.find((i) => i.id === itemId) || items[0];
  const toolGroups = byOreType(data.ore.filter((o) => o.tool_ceiling !== null));

  const run = (action) => {
    setBusy(true);
    setNotice(null);
    action()
      .then((res) => {
        setNotice({ ok: true, text: describe(res) });
        // Без экрана загрузки: иначе ковка размонтируется и забудет выбор.
        return getCraft().then(setData);
      })
      .catch((error) => setNotice({ ok: false, text: error.message }))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <Tabs>
        {SUBTABS.map((tab) => (
          <TabsItem key={tab.id} selected={subtab === tab.id} onClick={() => setSubtab(tab.id)}>
            {tab.label}
          </TabsItem>
        ))}
      </Tabs>

      {!item && (
        <Placeholder icon={<div style={{ fontSize: 44 }}>🔨</div>}>
          Улучшать пока нечего. Сначала выкуй вещь во вкладке «Крафт» - инструменты можно готовить уже сейчас.
        </Placeholder>
      )}

      {item && subtab === 'upgrade' && (
      <Group header={<Header>Предмет</Header>}>
        {items.map((row) => (
          <SimpleCell
            key={row.id}
            before={<ItemIcon icon={row.icon} rarity={row.rarity} alt={row.name} />}
            onClick={() => setItemId(row.id)}
            subtitle={`${statLine(row.stats)}${row.efficiency ? ` · ${row.efficiency}%` : ''}`}
            after={row.id === item.id ? '✓' : null}
          >
            {row.name}
          </SimpleCell>
        ))}
      </Group>
      )}

      {notice && (
        <Div className={notice.ok ? 'craft-notice craft-notice--ok' : 'craft-notice craft-notice--bad'}>
          {notice.text}
        </Div>
      )}

      {subtab === 'craft' ? (
        <Forge data={data} busy={busy} run={run} />
      ) : (
        <>
          {item && (
          <Group header={<Header>Эффективность</Header>}>
            {item.efficiency === null ? (
              <Div>Сначала выкуй предмет - улучшать пока нечего.</Div>
            ) : (
              <SimpleCell
                multiline
                subtitle={
                  item.next_efficiency
                    ? `Следующая ступень: ${item.next_efficiency}%`
                    : 'Это потолок.'
                }
              >
                {`${item.name} - ${item.efficiency}%`}
              </SimpleCell>
            )}
          </Group>
          )}

          <Group header={<Header>Инструменты</Header>}>
            {data.tools.length === 0 && <Div>Инструментов нет - выкуй ниже.</Div>}
            {data.tools.map((tool) => (
              <SimpleCell
                key={tool.ceiling}
                before={<ItemIcon icon={`tool:${tool.ceiling}`} alt="Инструмент" />}
                after={
                  <Button
                    size="s"
                    disabled={
                      busy || !item || item.efficiency === null || !item.next_efficiency
                      || tool.ceiling < item.next_efficiency
                    }
                    onClick={() => run(() => upgradeCraft(item.id, tool.ceiling))}
                  >
                    Применить
                  </Button>
                }
                subtitle={`Качает до ${tool.ceiling}%`}
              >
                {`Инструмент ×${tool.count}`}
              </SimpleCell>
            ))}
          </Group>

          <Group header={<Header>Выковать инструмент</Header>}>
            {toolGroups.length === 0 && <Div>Подходящей руды нет.</Div>}
            {toolGroups.map((group) => {
              // На инструмент градация не влияет вовсе - только тир. Поэтому
              // выбирать её игроку незачем: берём самую дешёвую, которой
              // хватает, и честно пишем какую.
              const pick = group.grades.find((row) => row.count >= row.tool_cost);
              return (
                <SimpleCell
                  key={group.id}
                  multiline
                  before={
                    <ItemIcon
                      icon={`ore:${group.id}`}
                      rarity={group.grades[group.grades.length - 1]?.grade}
                      alt={group.name}
                    />
                  }
                  after={
                    <Button
                      size="s"
                      disabled={busy || !pick}
                      onClick={() => run(() => craftTool(pick.id, pick.grade))}
                    >
                      {`${group.tool_cost} шт.`}
                    </Button>
                  }
                  subtitle={
                    pick
                      ? `До ${group.tool_ceiling}% · всего ${group.total} · пойдёт ${pick.grade_name}`
                      : `До ${group.tool_ceiling}% · всего ${group.total} - не хватает`
                  }
                >
                  {group.name}
                </SimpleCell>
              );
            })}
          </Group>
        </>
      )}
    </>
  );
}

function describe(res) {
  if (res.ceiling) return `Инструмент готов - качает до ${res.ceiling}%.`;
  if (res.efficiency_after) {
    return `${res.efficiency_before}% → ${res.efficiency_after}%.`;
  }
  const item = res.item;
  return `${item.name}: ${statLine(item.stats)} (${item.efficiency}%).`;
}
