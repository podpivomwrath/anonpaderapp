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
import { Bar } from './ui.jsx';

// Ремесла (2026-10-21): у каждого ремесла - уровень, опыт, короткая подсказка
// и своя сумка. Рыба и руда переехали сюда из инвентаря: всё ремесленное
// лежит в одном месте. Сами действия - в чате (озеро, рудник, дом).

function kg(grams) {
  return (grams / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 });
}

// Шапка ремесла (2026-10-22): кольцо уровня, полоска опыта и что откроется
// следующим. Кольцо заполняется опытом до следующего уровня.
function CraftHead({ icon, level, max, xp, xpNext, next }) {
  const r = 26;
  const len = 2 * Math.PI * r;
  const share = xpNext > 0 ? Math.min(1, xp / xpNext) : 1;
  return (
    <div className="craft-head">
      <span className="craft-ring">
        <svg viewBox="0 0 64 64" width="64" height="64" aria-hidden="true">
          <circle cx="32" cy="32" r={r} className="craft-ring__track" />
          <circle cx="32" cy="32" r={r} className="craft-ring__bar"
            strokeDasharray={len} strokeDashoffset={len * (1 - share)} />
        </svg>
        <span className="craft-ring__icon" aria-hidden="true">{icon}</span>
        <b className="craft-ring__level">{level}</b>
      </span>
      <span className="craft-head__text">
        <span className="craft-head__lvl">
          Уровень {level}{max ? ` из ${max}` : ''}
        </span>
        {xpNext > 0 ? (
          <span className="daily-card__progress">
            <Bar value={xp} max={xpNext} tone="green" thin />
            <span className="daily-card__count">{xp}/{xpNext}</span>
          </span>
        ) : <small className="craft-head__max">предел</small>}
        {next && <small className="craft-head__next">Дальше: {next}</small>}
      </span>
    </div>
  );
}

// Первое закрытое в списке (трава, рецепт) - «на N уровне».
function nextLocked(rows) {
  const row = (rows || []).find((r) => !r.known);
  return row ? `новое на ${row.level} уровне` : null;
}

export default function CraftsTab({ character }) {
  const [bag, setBag] = useState(null);
  const [status, setStatus] = useState('loading');
  const [detail, setDetail] = useState(null);
  const [open, setOpen] = useState(null);
  const [qtyEntry, setQtyEntry] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const [notice, setNotice] = useState(null);

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
      {notice && <p className="tab-notice" onClick={() => setNotice(null)}>{notice}</p>}
      {character.fishing && (
        <Group header={<Header>🎣 Рыбалка</Header>}>
          <CraftHead icon="🎣" level={character.fishing.level} xp={character.fishing.xp} xpNext={character.fishing.xp_to_next} />
          {fishBag && (
            <div className="milestone milestone--inset">
              <span className="milestone__head">
                <span>Садок</span>
                <span>{kg(fishBag.grams)} / {kg(fishBag.capacity)} кг</span>
              </span>
              <Bar value={fishBag.grams} max={fishBag.capacity} tone={fishBag.grams >= fishBag.capacity ? 'red' : 'blue'} thin />
            </div>
          )}
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
          {pouch('fish', 'Рыба в садке',
            'fish', fish, 'Садок пуст.')}
        </Group>
      )}

      {character.mining && (
        <Group header={<Header>⛏ Горное дело</Header>}>
          <CraftHead icon="⛏" level={character.mining.level} xp={character.mining.xp} xpNext={character.mining.xp_to_next} />
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            Потолка нет. Уровень ускоряет добычу и повышает шанс на редкую руду. Руда идёт в мастерскую,
            лишнее железо и кварц дёшево берёт Иргал.
          </Caption>
          {pouch('ore', 'Руда', 'ore', ore, 'Руды нет.')}
        </Group>
      )}

      {herbal && (
        <Group header={<Header>🌿 Травничество</Header>}>
          <CraftHead icon="🌿" level={herbal.level} max={herbal.max_level} xp={herbal.xp} xpNext={herbal.xp_to_next}
            next={nextLocked(herbal.catalog)} />
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
          <CraftHead icon="⚗️" level={alch.level} max={alch.max_level} xp={alch.xp} xpNext={alch.xp_to_next}
            next={nextLocked(alch.recipes)} />
          <Caption level="1" style={{ padding: '0 16px 12px', opacity: 0.7 }}>
            {alch.has_house
              ? 'Варят в чате: Дом на площади родного города, Алхимический стол. '
              : 'Нужен дом - он продается в Магазине за самоцветы. '}
            Зелья те же, что в лавке, а выходит дешевле: лечебные по 10 штук, боевые по 3. Варка идет 30 секунд,
            и до конца из дома не выйти. Каждые 10 уровней склянки дешевле на 10% и +10% к шансу дополнительной порции
            {alch.level >= 10 ? ` (сейчас -${alch.discount_pct}% и ${alch.bonus_pct}%)` : ''}.
          </Caption>
          {pouch('recipes', 'Рецепты', 'recipe', alch.recipes, '')}
        </Group>
      )}

      {cook && (
        <Group header={<Header>🔥 Кулинария</Header>}>
          <CraftHead icon="🔥" level={cook.level} max={cook.max_level} xp={cook.xp} xpNext={cook.xp_to_next}
            next={nextLocked(cook.recipes)} />
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
        <QuantitySheet
          entry={qtyEntry} onClose={() => setQtyEntry(null)} onCopied={(id) => markCopied(id)}
          onTransferred={(text) => {
            setQtyEntry(null);
            setNotice(text);
            getInventory().then(setBag).catch(() => { /* перечитается при следующем заходе */ });
          }}
        />
      )}
    </>
  );
}
