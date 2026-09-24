import { useEffect } from 'react';
import bridge from '@vkontakte/vk-bridge';
import { AppRoot, ConfigProvider, SplitLayout, SplitCol } from '@vkontakte/vkui';
import Hub from './components/Hub.jsx';

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
const APPEARANCE = 'dark';

function App() {
  useEffect(() => {
    bridge.send('VKWebAppInit').catch(() => {
      // не в среде VK (локальная разработка вне iframe) - просто игнорируем
    });
  }, []);

  return (
    <ConfigProvider appearance={APPEARANCE}>
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
