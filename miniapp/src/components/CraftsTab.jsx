import { useEffect, useState } from 'react';
import {
  Caption, Div, Group, Header, Placeholder, SimpleCell, Switch,
} from '@vkontakte/vkui';
import { getInventory, setFishAutoKeep } from '../api.js';
import ItemIcon from './ItemIcon.jsx';
import { itemIcon } from '../itemIcons.js';
import {
  CheckIcon, CopyIcon, ItemSheet, QuantitySheet, copyText,
} from './InventoryTab.jsx';
import Skeleton from './Skeleton.jsx';

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
  const [qtyEntry, setQtyEntry] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  const markCopied = (key) => {
    setCopiedId(key);
    setTimeout(() => setCopiedId((cur) => (cur === key ? null : cur)), 2500);
  };

  // Передача (2026-10-21): рыбу - стаком целиком, готовой командой; травы и
  // руду - сколько выберешь ползунком, как зелья в инвентаре.
  const copyButton = (entry) => {
    if (!entry.transfer_command && !entry.transfer_prefix) return null;
    const key = `craft:${entry.id}`;
    const onClick = entry.transfer_command
      ? async () => { await copyText(entry.transfer_command); markCopied(key); }
      : () => setQtyEntry({ ...entry, id: key });
    return (
      <button type="button" className="copy-transfer" title="Скопировать команду передачи"
        aria-label="Скопировать команду передачи" onClick={onClick}>
        {copiedId === key ? <CheckIcon /> : <CopyIcon />}
      </button>
    );
  };
  const [autoKeep, setAutoKeep] = useState(Boolean(character.ui?.fish_auto_keep));

  function toggleAutoKeep(next) {
    setAutoKeep(next);
    setFishAutoKeep(next).catch(() => setAutoKeep(!next));
  }

  useEffect(() => {
    getInventory()
      .then((res) => { setBag(res); setStatus('ready'); })
      .catch(() => setStatus('error'));
  }, []);

  if (status === 'loading') {
    return <Skeleton />;
  }
  if (status === 'error') {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>🛠</div>}>Не удалось загрузить ремёсла.</Placeholder>;
  }

  const fish = bag.fish || [];
  const ore = bag.ore || [];
  const fishBag = bag.fish_bag;
  const herbs = bag.herbs || [];
  const herbal = character.herbalism;
  const alch = character.alchemy;
  const cook = character.cooking;

  const row = (kind, entry) => (
    <SimpleCell
      key={entry.id}
      multiline
      after={<div className="inventory-actions">{copyButton(entry)}</div>}
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

  // Картинка, если уже нарисована, иначе эмодзи. У закрытой травы - только эмодзи-замок.
  const glyph = (e, open = true) => (open && e.icon && itemIcon(e.icon)
    ? <ItemIcon icon={e.icon} alt={e.name} />
    : <span className="craft-emoji-icon" aria-hidden="true">{open ? e.emoji : '🔒'}</span>);

  const catalogRow = (h) => (
    <SimpleCell key={h.id} before={glyph(h, h.known)}
      subtitle={h.known ? 'Различаешь' : `Откроется на ${h.level} уровне`}
      style={h.known ? undefined : { opacity: 0.55 }}>
      {h.known ? h.name : '???'}
    </SimpleCell>
  );

  const recipeRow = (r) => (
    <SimpleCell key={r.id} multiline before={glyph(r)}
      subtitle={r.known ? r.needs : `Откроется на ${r.level} уровне`}
      style={r.known ? undefined : { opacity: 0.55 }}>
      {r.out ? `${r.name} ×${r.out}` : r.name}
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
            ? rows.map((r) => {
              if (kind === 'catalog') return catalogRow(r);
              if (kind === 'recipe') return recipeRow(r);
              return row(kind, r);
            })
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
          <SimpleCell
            Component="label"
            multiline
            after={<Switch checked={autoKeep} onChange={(e) => toggleAutoKeep(e.target.checked)} />}
          >
            Автоматически класть всю рыбу в садок
          </SimpleCell>
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

      {alch && (
        <Group header={<Header>⚗️ Алхимия</Header>}>
          <div className="stat-row">
            <span className="stat-row__label">Уровень</span>
            <span className="stat-row__value">{alch.level} / {alch.max_level}</span>
          </div>
          {alch.xp_to_next > 0 && (
            <div className="stat-row">
              <span className="stat-row__label">Опыт</span>
              <span className="stat-row__value">{alch.xp} / {alch.xp_to_next}</span>
            </div>
          )}
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            {alch.has_house
              ? 'Варят в чате: Дом на площади родного города, Алхимический стол. '
              : 'Нужен дом - он продается в Магазине за самоцветы. '}
            Зелья те же, что в лавке, а выходит дешевле: лечебные по 10 штук, боевые по 3. Варка идет 30 секунд,
            и до конца из дома не выйти. Каждые 10 уровней склянки дешевле на 10% и +10% к шансу лишней порции
            {alch.level >= 10 ? ` (сейчас -${alch.discount_pct}% и ${alch.bonus_pct}%)` : ''}.
          </Caption>
          {pouch('recipes', 'Рецепты', 'recipe', alch.recipes, '')}
        </Group>
      )}

      {cook && (
        <Group header={<Header>🔥 Кулинария</Header>}>
          <div className="stat-row">
            <span className="stat-row__label">Уровень</span>
            <span className="stat-row__value">{cook.level} / {cook.max_level}</span>
          </div>
          {cook.xp_to_next > 0 && (
            <div className="stat-row">
              <span className="stat-row__label">Опыт</span>
              <span className="stat-row__value">{cook.xp} / {cook.xp_to_next}</span>
            </div>
          )}
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            {cook.has_house
              ? 'Готовят в чате: Дом на площади родного города, Печь. '
              : 'Нужен дом - он продается в Магазине за самоцветы. '}
            Из рыбы и трав, соль и специи докупаются сами. Тяжелее рыба - больше порций, лучше градация -
            сильнее блюдо. Готовое лежит в Инвентаре во вкладке «Еда», есть можно вне боя. Бафф держится
            {` ${cook.minutes} мин.`}, переживает смерть, новое блюдо заменяет старое. Каждые 10 уровней бафф длится дольше.
          </Caption>
          {pouch('dishes', 'Рецепты', 'recipe', cook.recipes, '')}
        </Group>
      )}

      {detail && <ItemSheet entry={detail} onClose={() => setDetail(null)} />}
      {qtyEntry && (
        <QuantitySheet entry={qtyEntry} onClose={() => setQtyEntry(null)} onCopied={(id) => markCopied(id)} />
      )}
    </>
  );
}
