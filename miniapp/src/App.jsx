import { useEffect, useState } from 'react';
import bridge from '@vkontakte/vk-bridge';
import { AppRoot, ConfigProvider, SplitLayout, SplitCol } from '@vkontakte/vkui';
import Hub from './components/Hub.jsx';

function App() {
  const [appearance, setAppearance] = useState('dark');

  useEffect(() => {
    bridge.send('VKWebAppInit').catch(() => {
      // не в среде VK (локальная разработка вне iframe) — просто игнорируем
    });
    const handler = (event) => {
      if (event.detail?.type === 'VKWebAppUpdateConfig') {
        const nextAppearance = event.detail.data?.appearance;
        if (nextAppearance) setAppearance(nextAppearance);
      }
    };
    bridge.subscribe(handler);
    return () => bridge.unsubscribe(handler);
  }, []);

  return (
    <ConfigProvider appearance={appearance}>
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
