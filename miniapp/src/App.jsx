import { useEffect } from 'react';
import bridge from '@vkontakte/vk-bridge';
import { AppRoot, ConfigProvider, SplitLayout, SplitCol, Tabs, TabsItem } from '@vkontakte/vkui';
import BackgroundScene from './components/BackgroundScene.jsx';
import Hub from './components/Hub.jsx';
import IntroScene from './components/IntroScene.jsx';
import TabHint from './components/TabHint.jsx';
import Tour from './components/Tour.jsx';
import { ChronicleSection } from './components/DailiesTab.jsx';

// Патч 77: тема ВСЕГДА тёмная, за клиентом ВК больше не следуем.
//
// Раньше приложение подхватывало appearance из VKWebAppUpdateConfig, и у
// игрока со светлой темой ВК мини-апп становился светлым. Игра нарисована
// тёмной: иконки предметов сгенерированы с собственным тёмным фоном,
// палитра - пепел и ржавчина. На белом это выглядело чужеродно, а на
// телефоне - где светлая тема у ВК по умолчанию - так видело большинство.
//
// Отдельной светлой темы не делаем: поддерживать два комплекта артов ради
// неё пришлось бы бесконечно.
//
// Проп называется colorScheme. Раньше тут стоял appearance - в VKUI 8 его
// уже нет, React передавал неизвестный проп дальше, и VKUI молча брал тему
// из системы. На ПК у клиента ВК тёмная, на телефоне светлая - отсюда и
// белый интерфейс на телефоне при «зафиксированной» тёмной теме.
const COLOR_SCHEME = 'dark';

// Только при разработке: #intro - вступление отдельно, без входа через ВК
// (хаб без подписи ВК не откроется, а сцену надо видеть).
const DEV_INTRO = import.meta.env.DEV && window.location.hash === '#intro';

function App() {
  useEffect(() => {
    bridge.send('VKWebAppInit').catch(() => {
      // не в среде VK (локальная разработка вне iframe) - просто игнорируем
    });
  }, []);

  if (import.meta.env.DEV && ['#tour', '#hints'].includes(window.location.hash)) {
    const hints = window.location.hash === '#hints';
    // Макет шапки с теми же data-tour, что в Hub - проверить подсветку тура.
    return (
      <ConfigProvider colorScheme={COLOR_SCHEME}>
        <AppRoot>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, background: '#111' }}>
            <span data-tour="menu" style={{ fontSize: 22 }}>☰</span>
            <span>Персонаж</span>
            <span data-tour="tools">🔄 🔊 📖</span>
            <span data-tour="help">?</span>
          </div>
          <div className="hub-banner" data-tour="banner" style={{ padding: 16 }}>Имя персонажа · Маг · Ур. 9</div>
          <div className="hub-content"><div className="tab-enter tab-enter--fwd">
          <Tabs>
            {['Сюжет', 'Ежедневные', 'Вход'].map((label, i) => (
              <TabsItem key={label} selected={i === 0}>{label}</TabsItem>
            ))}
          </Tabs>
          <ChronicleSection
            song={{ read: true, complete: true, fragments: [
              { index: 0, seen: true, text: 'Когда-то было солнце. Так писали в старых книгах. / Теперь лишь зарево вдали - и никаких улыбок.' },
              { index: 1, seen: false, text: '' },
            ] }}
            titles={[
              { id: 'attentive', name: 'Внимательный', tier: 'legendary', unlocked: true },
              { id: 'chronicler', name: 'Летописец', tier: 'rare', unlocked: true },
              { id: 'relentless', name: 'Неотступный', tier: 'legendary', unlocked: false, how: '365 дней серии ежедневных заданий' },
              { id: 'x', name: '???', tier: 'legendary', unlocked: false, secret: true },
            ]}
          />
          <Tabs>
            {['Обзор', 'Состав', 'Задания', 'Казна', 'Земли', 'Древо', 'Осады'].map((label, i) => (
              <TabsItem key={label} selected={i === 1}>{label}</TabsItem>
            ))}
          </Tabs>
          </div></div>
          {hints
            ? <TabHint tab="dailies" onClose={() => { window.location.hash = 'hints-done'; }} />
            : <Tour onDone={() => { window.location.hash = 'tour-done'; }} />}
        </AppRoot>
      </ConfigProvider>
    );
  }

  if (DEV_INTRO) {
    return (
      <ConfigProvider colorScheme={COLOR_SCHEME}>
        <AppRoot>
          <IntroScene onDone={(sound) => { window.location.hash = `done-${sound}`; }} />
        </AppRoot>
      </ConfigProvider>
    );
  }

  return (
    <ConfigProvider colorScheme={COLOR_SCHEME}>
      <BackgroundScene />
      <AppRoot className="hub">
        <SplitLayout>
          <SplitCol>
            <Hub />
          </SplitCol>
        </SplitLayout>
      </AppRoot>
    </ConfigProvider>
  );
}

export default App;
