import { useCallback, useEffect, useState } from 'react';
import {
  Button, Div, Group, Header, Placeholder, SimpleCell, Spinner, Tabs, TabsItem,
} from '@vkontakte/vkui';
import { craftItem, craftTool, getCraft, upgradeCraft } from '../api.js';

// Патч 72: мастерская. Два подраздела - «Крафт» (сковать/перековать) и
// «Улучшение» (инструменты и ступени процентов).
//
// Чисел будущего предмета здесь НЕТ намеренно: игрок видит, куда целится
// специализация (полоски предрасположенности), но не что именно выпадет.
// Ровно в этом смысл системы - иначе выбор превращался бы в арифметику.

const STAT_TITLES = {
  str: 'Сила', agi: 'Ловкость', int: 'Интеллект', vit: 'Живучесть', wil: 'Воля',
  primary: 'Основной стат',
};

const SUBTABS = [
  { id: 'craft', label: 'Крафт' },
  { id: 'upgrade', label: 'Улучшение' },
];

function statLine(stats) {
  const entries = Object.entries(stats || {}).sort((a, b) => b[1] - a[1]);
  if (!entries.length) return '-';
  return entries.map(([stat, value]) => `${STAT_TITLES[stat] || stat} +${value}`).join(' · ');
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
  const [ore, setOre] = useState(null); // {id, grade}
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
  const craftOre = data.ore.filter((o) => o.craft_efficiency !== null);
  const toolOre = data.ore.filter((o) => o.tool_ceiling !== null);

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
              <SimpleCell
                key={option.id}
                multiline
                onClick={() => setSpec(option.id)}
                after={option.id === spec ? '✓' : null}
                subtitle={<LeanBars lean={option.lean} />}
              >
                {`${option.name} · ${option.title}`}
              </SimpleCell>
            ))}
          </Group>

          <Group header={<Header>Руда ({item.next_craft_cost} шт.)</Header>}>
            {craftOre.length === 0 && <Div>Подходящей руды нет.</Div>}
            {craftOre.map((row) => (
              <SimpleCell
                key={`${row.id}:${row.grade}`}
                onClick={() => setOre({ id: row.id, grade: row.grade })}
                after={ore?.id === row.id && ore?.grade === row.grade ? '✓' : null}
                subtitle={`${row.grade_name} · старт ${row.craft_efficiency}% · есть ${row.count}`}
              >
                {`${row.emoji} ${row.name}`}
              </SimpleCell>
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
            {toolOre.length === 0 && <Div>Подходящей руды нет.</Div>}
            {toolOre.map((row) => (
              <SimpleCell
                key={`${row.id}:${row.grade}`}
                after={
                  <Button
                    size="s"
                    disabled={busy || row.count < row.tool_cost}
                    onClick={() => run(() => craftTool(row.id, row.grade))}
                  >
                    {`${row.tool_cost} шт.`}
                  </Button>
                }
                subtitle={`${row.grade_name} · до ${row.tool_ceiling}% · есть ${row.count}`}
              >
                {`${row.emoji} ${row.name}`}
              </SimpleCell>
            ))}
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
