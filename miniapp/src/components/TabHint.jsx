import Spotlight from './Spotlight.jsx';
import { TAB_HINTS } from './tabHints.js';

/**
 * Подсказки раздела при первом заходе - в том же виде, что тур по шапке:
 * затемнение и подсветка нужного блока, шаг за шагом. Что уже прочитано -
 * на сервере (ui.hints), поэтому с другого устройства подсказка не
 * повторится. Полный гайд по всем разделам - кнопка «?» в шапке (guide.js).
 *
 * Цель шага - см. Spotlight: 'h:Заголовок' - блок с таким заголовком,
 * селектор - любой элемент, null - карточка по центру.
 */

export default function TabHint({ tab, before = [], onClose }) {
  const steps = [...before, ...(TAB_HINTS[tab] || [])];
  if (!steps.length) return null;
  return <Spotlight key={tab} steps={steps} onDone={onClose} label="Подсказки раздела" />;
}
