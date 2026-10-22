import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@vkontakte/vkui/dist/vkui.css'
import './index.css'
import './guild.css'
import './intro.css'
// Пути к фонам (патч 80). Файл генерируется tools/icon_assets.py и существует
// всегда, даже пустой: пока картинок нет, приложение собирается и работает
// без фона.
import './background.css'
import './motion.css'
import './profile.css'
import App from './App.jsx'

// Масштаб страницы щипком выключен целиком: у карты и древа гильдии свой зум,
// а родной зум страницы на экране древа (там прокрутка страницы заперта)
// красил весь мини-апп в чёрное (репорт #35, 2026-10-12). iOS не слушает
// user-scalable=no в метатеге, поэтому жесты гасим и здесь.
const blockPageZoom = (e) => e.preventDefault()
document.addEventListener('gesturestart', blockPageZoom, { passive: false })
document.addEventListener('gesturechange', blockPageZoom, { passive: false })
document.addEventListener('touchmove', (e) => {
  if (e.touches.length > 1 && !e.target.closest?.('.guild-tree, .map-viewport')) e.preventDefault()
}, { passive: false })

// Слабое устройство (2026-10-22): мало ядер или памяти - без размытия
// панелей, искр и пульсаций (profile.css, body.lite). Мини-апп не должен
// тормозить ради красоты.
const cores = navigator.hardwareConcurrency || 8
const memory = navigator.deviceMemory || 8
if (cores <= 4 || memory <= 2) document.body.classList.add('lite')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
