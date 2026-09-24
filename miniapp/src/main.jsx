import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@vkontakte/vkui/dist/vkui.css'
import './index.css'
// Пути к фонам (патч 80). Файл генерируется tools/icon_assets.py и существует
// всегда, даже пустой: пока картинок нет, приложение собирается и работает
// без фона.
import './background.css'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
