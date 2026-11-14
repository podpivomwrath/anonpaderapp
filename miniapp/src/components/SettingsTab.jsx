import { useState } from 'react';
import { Button, Div, Group, Header, SimpleCell, Switch } from '@vkontakte/vkui';
import { setNoImages, setNoNotices, setNoticeMute, setShortLog, setSignalsOff } from '../api.js';

// Настройки (2026-11-12, владелец): свой раздел под шестерёнкой в шапке.
// Раньше переключатели жили внизу «Героя», а звук и чат - значками в шапке.

// Виды оповещений по отдельности (2026-11-14, владелец). id - bot/notices.KINDS
// (сверка в tests/test_notices.py), порядок - как на экране.
const NOTICE_KINDS = [
  { id: 'boss', title: 'Мировой босс', subtitle: 'Появился босс, к которому вас пускают по уровню.' },
  { id: 'rift', title: 'Разломы', subtitle: 'Открылся разлом - весть носителям Клейма.' },
  { id: 'ishak', title: 'Турбоишак и новости мира', subtitle: 'Ишак выбежал, его поймали, кто-то нашёл редкого питомца.' },
  { id: 'cart', title: 'Прибытие повозок', subtitle: 'Ваша повозка доехала до города.' },
  { id: 'orders', title: 'Срочные торговые заказы', subtitle: 'Город ждёт груз к сроку. Приходят, если во «Фракции» включено «Сообщать в чат о новых заказах».' },
  { id: 'voyage', title: 'Вести долгого пути', subtitle: 'Раз в час, пока вы в пути. Итог похода придёт в любом случае.' },
  { id: 'guild', title: 'Новости гильдии', subtitle: 'Знамёна, постройки, осады, стражи цитадели, кто вступил.' },
  { id: 'buffs', title: 'Окончание баффов', subtitle: 'Кончилась сытость, прикормка, молитва или настойка.' },
  { id: 'crowns', title: 'Венцы топов', subtitle: 'Вас обошли в топе и венец ушёл другому.' },
];

// Список выключенных видов: сразу на экране, при ошибке - назад.
function useMuted(character, onCharacterUpdate) {
  const [muted, setMuted] = useState(() => new Set(character.ui?.notice_mute || []));
  const toggle = (id, on) => {
    const prev = muted;
    const next = new Set(muted);
    if (on) next.delete(id); else next.add(id);
    setMuted(next);
    const list = NOTICE_KINDS.map((k) => k.id).filter((k) => next.has(k));
    setNoticeMute(list)
      .then(() => onCharacterUpdate((p) => ({ ...p, ui: { ...(p.ui || {}), notice_mute: list } })))
      .catch(() => setMuted(prev));
  };
  return [muted, toggle];
}

const PLAYERS_CHAT_URL = 'https://vk.me/join/xuy8wXu8_zoubce24lDXooe6aB_sV1eB3zE=';

// Переключатель флага ui персонажа: сразу на экране, при ошибке - назад.
function useFlag(character, onCharacterUpdate, key, save, invert = false) {
  const read = (ui) => (invert ? !ui?.[key] : Boolean(ui?.[key]));
  const [on, setOn] = useState(read(character.ui));
  const toggle = (next) => {
    setOn(next);
    const stored = invert ? !next : next;
    save(stored)
      .then(() => onCharacterUpdate((prev) => ({ ...prev, ui: { ...(prev.ui || {}), [key]: stored } })))
      .catch(() => setOn(!next));
  };
  return [on, toggle];
}

function Row({ title, subtitle, checked, onChange, disabled = false }) {
  return (
    <SimpleCell
      Component="label" multiline subtitle={subtitle} disabled={disabled}
      after={<Switch checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />}
    >
      {title}
    </SimpleCell>
  );
}

export default function SettingsTab({ character, onCharacterUpdate, soundOn, onToggleSound }) {
  // «Убрать картинки в игре» (2026-10-22, bot/no_images.py).
  const [noImages, toggleImages] = useFlag(character, onCharacterUpdate, 'no_images', setNoImages);
  // Короткий боевой лог (2026-10-22, bot/short_log.py).
  const [short, toggleShort] = useFlag(character, onCharacterUpdate, 'short_log', setShortLog);
  // «Без оповещений» (2026-11-09, репорт 340, bot/notices.py).
  const [quiet, toggleQuiet] = useFlag(character, onCharacterUpdate, 'no_notices', setNoNotices);
  const [muted, toggleKind] = useMuted(character, onCharacterUpdate);
  // Сигналы союзникам (2026-11-11, bot/battle_signals.py): флаг - «выключено».
  const [sigOut, toggleOut] = useFlag(
    character, onCharacterUpdate, 'signals_out_off', (off) => setSignalsOff('out', off), true,
  );
  const [sigIn, toggleIn] = useFlag(
    character, onCharacterUpdate, 'signals_in_off', (off) => setSignalsOff('in', off), true,
  );

  return (
    <>
      <Group header={<Header>Мини-апп</Header>}>
        <Row
          title="Звук"
          subtitle="Щелчки меню, вступление и озвучка подсказок."
          checked={soundOn} onChange={onToggleSound}
        />
      </Group>
      <Group header={<Header>Сообщения бота</Header>}>
        <Row
          title="Убрать картинки в игре"
          subtitle="Бот будет присылать сообщения без картинок."
          checked={noImages} onChange={toggleImages}
        />
        <Row
          title="Короткий лог боя"
          subtitle="В бою только здоровье с изменением за ход и значки эффектов. Весь лог хода - кнопкой «📜 Сводка»."
          checked={short} onChange={toggleShort}
        />
        <Row
          title="Показывать союзникам мои действия"
          subtitle="В групповом бою после выбора действия появится кнопка «📢 Показать союзникам»: союзники увидят, что вы готовите."
          checked={sigOut} onChange={toggleOut}
        />
        <Row
          title="Получать действия союзников"
          subtitle="Бот будет присылать, что готовят союзники по групповому бою, если они нажали «📢 Показать союзникам»."
          checked={sigIn} onChange={toggleIn}
        />
      </Group>
      <Group header={<Header>Оповещения</Header>}>
        <Row
          title="Отключить все оповещения"
          subtitle="Бот перестанет присылать то, о чём вы не просили. Ответы на ваши действия будут приходить как обычно."
          checked={quiet} onChange={toggleQuiet}
        />
        {NOTICE_KINDS.map((k) => (
          <Row
            key={k.id} title={k.title} subtitle={k.subtitle} disabled={quiet}
            checked={!quiet && !muted.has(k.id)} onChange={(on) => toggleKind(k.id, on)}
          />
        ))}
      </Group>
      <Group header={<Header>Игроки</Header>}>
        <Div>
          <Button
            size="l" stretched mode="secondary"
            href={PLAYERS_CHAT_URL} target="_blank" rel="noopener noreferrer"
          >
            💬 Чат игроков
          </Button>
        </Div>
      </Group>
    </>
  );
}
