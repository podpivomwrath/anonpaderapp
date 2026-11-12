import { useState } from 'react';
import { Button, Div, Group, Header, SimpleCell, Switch } from '@vkontakte/vkui';
import { setNoImages, setNoNotices, setShortLog, setSignalsOff } from '../api.js';

// Настройки (2026-11-12, владелец): свой раздел под шестерёнкой в шапке.
// Раньше переключатели жили внизу «Героя», а звук и чат - значками в шапке.

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

function Row({ title, subtitle, checked, onChange }) {
  return (
    <SimpleCell
      Component="label" multiline subtitle={subtitle}
      after={<Switch checked={checked} onChange={(e) => onChange(e.target.checked)} />}
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
          title="Отключить оповещения"
          subtitle="Бот перестанет присылать то, о чём вы не просили: открытые разломы, мировых боссов, турбоишака, заказы и прибытие повозок, вести похода, новости гильдии и окончание баффов. Ответы на ваши действия будут приходить как обычно."
          checked={quiet} onChange={toggleQuiet}
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
