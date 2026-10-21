import { useEffect, useState } from 'react';
import {
  Caption, Div, Group, Header, Placeholder, SimpleCell, Spinner,
} from '@vkontakte/vkui';
import { getInventory } from '../api.js';
import ItemIcon from './ItemIcon.jsx';
import { itemIcon } from '../itemIcons.js';
import { ItemSheet } from './InventoryTab.jsx';

// Ремесла (2026-10-21): у каждого ремесла - уровень, опыт, короткая подсказка
// и своя сумка. Рыба и руда переехали сюда из инвентаря: всё ремесленное
// лежит в одном месте. Сами действия - в чате (озеро, рудник, дом).

function kg(grams) {
  return (grams / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 });
}

function Progress({ skill }) {
  return (
    <>
      <div className="stat-row">
        <span className="stat-row__label">Уровень</span>
        <span className="stat-row__value">{skill.level}</span>
      </div>
      <div className="stat-row">
        <span className="stat-row__label">Опыт</span>
        <span className="stat-row__value">{skill.xp} / {skill.xp_to_next}</span>
      </div>
    </>
  );
}

export default function CraftsTab({ character }) {
  const [bag, setBag] = useState(null);
  const [status, setStatus] = useState('loading');
  const [detail, setDetail] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    getInventory()
      .then((res) => { setBag(res); setStatus('ready'); })
      .catch(() => setStatus('error'));
  }, []);

  if (status === 'loading') {
    return <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}><Spinner size="l" /></Div>;
  }
  if (status === 'error') {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🛠</div>}>Не удалось загрузить ремёсла.</Placeholder>;
  }

  const fish = bag.fish || [];
  const ore = bag.ore || [];
  const fishBag = bag.fish_bag;
  const herbs = bag.herbs || [];
  const herbal = character.herbalism;

  const row = (kind, entry) => (
    <SimpleCell
      key={entry.id}
      multiline
      before={(
        <button type="button" className="item-open" onClick={() => setDetail({ kind, data: entry })}
          aria-label={`Подробнее: ${entry.name}`}>
          {/* Своих картинок у трав пока нет - эмодзи на их месте. */}
          {itemIcon(entry.icon) || !entry.emoji
            ? <ItemIcon icon={entry.icon} rarity={entry.rarity} alt={entry.name} />
            : <span className="craft-emoji-icon" aria-hidden="true">{entry.emoji}</span>}
        </button>
      )}
      subtitle={{
        fish: `${entry.grade_title} · ${entry.weight} · ${entry.price} зол.`,
        ore: `${entry.grade_title} · ×${entry.count}`,
        herb: `${entry.tier}-й тир · ×${entry.count}`,
      }[kind]}
    >
      <button type="button" className="item-open item-open--name" onClick={() => setDetail({ kind, data: entry })}>
        {entry.name}
      </button>
    </SimpleCell>
  );

  const catalogRow = (h) => (
    <SimpleCell key={h.id} before={<span className="craft-emoji-icon" aria-hidden="true">{h.emoji}</span>}
      subtitle={h.known ? 'Различаешь' : `Откроется на ${h.level} уровне`}
      style={h.known ? undefined : { opacity: 0.55 }}>
      {h.known ? h.name : '???'}
    </SimpleCell>
  );

  const pouch = (key, title, kind, rows, empty) => (
    <>
      <SimpleCell
        onClick={() => setOpen((cur) => (cur === key ? null : key))}
        after={open === key ? '▴' : `${rows.length} ▾`}
      >
        {title}
      </SimpleCell>
      {open === key && (
        <div className="craft-expand">
          {rows.length
            ? rows.map((r) => (kind === 'catalog' ? catalogRow(r) : row(kind, r)))
            : <Div><Caption level="1">{empty}</Caption></Div>}
        </div>
      )}
    </>
  );

  return (
    <>
      {character.fishing && (
        <Group header={<Header>🎣 Рыбалка</Header>}>
          <Progress skill={character.fishing} />
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            Потолка нет. Уровень повышает шанс на крупную рыбу, снижает обрыв лески и увеличивает садок.
            Рыбу берёт Иргал, а Рыбак у воды в глубоких кольцах платит больше.
          </Caption>
          {pouch('fish', fishBag ? `Садок · ${kg(fishBag.grams)} / ${kg(fishBag.capacity)} кг` : 'Садок',
            'fish', fish, 'Садок пуст.')}
        </Group>
      )}

      {character.mining && (
        <Group header={<Header>⛏ Горное дело</Header>}>
          <Progress skill={character.mining} />
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            Потолка нет. Уровень ускоряет добычу и повышает шанс на редкую руду. Руда идёт в мастерскую,
            лишнее железо и кварц дёшево берёт Иргал.
          </Caption>
          {pouch('ore', 'Руда', 'ore', ore, 'Руды нет.')}
        </Group>
      )}

      {herbal && (
        <Group header={<Header>🌿 Травничество</Header>}>
          <div className="stat-row">
            <span className="stat-row__label">Уровень</span>
            <span className="stat-row__value">{herbal.level} / {herbal.max_level}</span>
          </div>
          {herbal.xp_to_next > 0 && (
            <div className="stat-row">
              <span className="stat-row__label">Опыт</span>
              <span className="stat-row__value">{herbal.xp} / {herbal.xp_to_next}</span>
            </div>
          )}
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            Трава вырастает на случайных клетках, пока игроки исследуют мир, и ждет сутки. Зайдешь на клетку
            с травой - в чате появится кнопка «Собрать». Кто первый сорвал, того и трава. Каждые 10 уровней
            открывают новые травы и дают +10% к шансу сорвать два пучка
            {herbal.double_pct ? ` (сейчас ${herbal.double_pct}%)` : ''}.
          </Caption>
          {pouch('herbs', 'Сумка травника', 'herb', herbs, 'Сумка пуста.')}
          {pouch('herb_catalog', 'Травы', 'catalog', herbal.catalog, '')}
        </Group>
      )}

      {detail && <ItemSheet entry={detail} onClose={() => setDetail(null)} />}
    </>
  );
}
