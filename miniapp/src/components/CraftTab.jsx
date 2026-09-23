import { useCallback, useEffect, useState } from 'react';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, Spinner, Tabs, TabsItem,
} from '@vkontakte/vkui';
import { craftItem, craftTool, getCraft, upgradeCraft } from '../api.js';

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
  str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Живучесть', wil: 'Воля',
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

function LeanBars({ lean }) {
  return (
    <div className="craft-lean">
      {lean.map(({ stat, share }) => (
        <div className="craft-lean__row" key={stat}>
          <span className="craft-lean__name">{STAT_TITLES[stat] || stat}</span>
          <span className="craft-lean__track">
            <span className="craft-lean__fill" style={{ width: `${Math.round(share * 100)}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

export default function CraftTab() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading');
  const [subtab, setSubtab] = useState('craft');
  const [itemId, setItemId] = useState(null);
  const [spec, setSpec] = useState(null);
  const [ore, setOre] = useState(null);       // {id, grade}
  const [openOre, setOpenOre] = useState(null); // какой вид раскрыт
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

  const item = data.items.find((i) => i.id === itemId) || data.items[0];
  // В ковку идёт только руда, которая реально поднимет процент: остальная
  // упёрлась бы в тот же потолок и сгорела впустую.
  const craftGroups = byOreType(data.ore.filter((o) => o.craft_efficiency !== null));
  const toolGroups = byOreType(data.ore.filter((o) => o.tool_ceiling !== null));

  const run = (action) => {
    setBusy(true);
    setNotice(null);
    action()
      .then((res) => {
        setNotice({ ok: true, text: describe(res) });
        return load();
      })
      .catch((error) => setNotice({ ok: false, text: error.message }))
      .finally(() => setBusy(false));
  };

  const toggleOre = (id) => setOpenOre((current) => (current === id ? null : id));

  return (
    <>
      <Tabs>
        {SUBTABS.map((tab) => (
          <TabsItem key={tab.id} selected={subtab === tab.id} onClick={() => setSubtab(tab.id)}>
            {tab.label}
          </TabsItem>
        ))}
      </Tabs>

      <Group header={<Header>Предмет</Header>}>
        {data.items.map((row) => (
          <SimpleCell
            key={row.id}
            onClick={() => setItemId(row.id)}
            subtitle={`${statLine(row.stats)}${row.efficiency ? ` · ${row.efficiency}%` : ''}`}
            after={row.id === item.id ? '✓' : null}
          >
            {row.name}
          </SimpleCell>
        ))}
      </Group>

      {notice && (
        <Div className={notice.ok ? 'craft-notice craft-notice--ok' : 'craft-notice craft-notice--bad'}>
          {notice.text}
        </Div>
      )}

      {subtab === 'craft' ? (
        <>
          <Group header={<Header>Во что ковать</Header>}>
            {data.specs.map((option) => (
              <div key={option.id}>
                <SimpleCell
                  onClick={() => setSpec(option.id)}
                  after={option.id === spec ? '✓' : null}
                  subtitle={option.title}
                >
                  {option.name}
                </SimpleCell>
                {/* Полоски только у выбранного: три набора сразу читались как
                    стена, а сравнивать их одновременно всё равно не нужно. */}
                {option.id === spec && (
                  <Div className="craft-expand">
                    <LeanBars lean={option.lean} />
                  </Div>
                )}
              </div>
            ))}
          </Group>

          <Group header={<Header>Руда ({item.next_craft_cost} шт.)</Header>}>
            {craftGroups.length === 0 && <Div>Подходящей руды нет.</Div>}
            {craftGroups.map((group) => (
              <div key={group.id}>
                <SimpleCell
                  onClick={() => toggleOre(group.id)}
                  after={openOre === group.id ? '▴' : '▾'}
                  subtitle={`Всего ${group.total} · старт ${group.craft_efficiency}%`}
                >
                  {`${group.emoji} ${group.name}`}
                </SimpleCell>
                {openOre === group.id && (
                  <div className="craft-expand">
                    {group.grades.map((row) => (
                      <SimpleCell
                        key={row.grade}
                        disabled={row.count < item.next_craft_cost}
                        onClick={() => setOre({ id: row.id, grade: row.grade })}
                        after={
                          ore?.id === row.id && ore?.grade === row.grade
                            ? '✓'
                            : `${row.count} шт.`
                        }
                      >
                        {row.grade_name}
                      </SimpleCell>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </Group>

          <Div>
            <Button
              size="l" stretched mode="primary"
              disabled={busy || !spec || !ore}
              onClick={() => run(() => craftItem(item.id, spec, ore.id, ore.grade))}
            >
              {item.spec ? `Перековать (${item.next_craft_cost} руды)` : `Сковать (${item.next_craft_cost} руды)`}
            </Button>
            {ore && (
              <p className="craft-hint">{`Пойдёт: ${oreLabel(data.ore, ore)}`}</p>
            )}
            {item.spec && (
              <p className="craft-hint">
                Перековка сбрасывает эффективность и роллит статы заново.
                Каждая следующая дороже предыдущей.
              </p>
            )}
          </Div>
        </>
      ) : (
        <>
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

          <Group header={<Header>Инструменты</Header>}>
            {data.tools.length === 0 && <Div>Инструментов нет - выкуй ниже.</Div>}
            {data.tools.map((tool) => (
              <SimpleCell
                key={tool.ceiling}
                after={
                  <Button
                    size="s"
                    disabled={
                      busy || item.efficiency === null || !item.next_efficiency
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
                  {`${group.emoji} ${group.name}`}
                </SimpleCell>
              );
            })}
          </Group>
        </>
      )}
    </>
  );
}

function oreLabel(rows, picked) {
  const row = rows.find((r) => r.id === picked.id && r.grade === picked.grade);
  return row ? `${row.emoji} ${row.name}, ${row.grade_name}` : '';
}

function describe(res) {
  if (res.ceiling) return `Инструмент готов - качает до ${res.ceiling}%.`;
  if (res.efficiency_after) {
    return `${res.efficiency_before}% → ${res.efficiency_after}%.`;
  }
  const item = res.item;
  return `${item.name}: ${statLine(item.stats)} (${item.efficiency}%).`;
}
