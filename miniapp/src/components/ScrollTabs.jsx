import { useLayoutEffect, useRef, useState } from 'react';
import { HorizontalScroll, Tabs as VkTabs } from '@vkontakte/vkui';

/**
 * Вкладки, которые всегда листаются вбок (2026-10-21, просьба владельца).
 *
 * Обычные Tabs VKUI не прокручиваются: лишние вкладки просто уезжают за
 * край экрана (так пропали «Донаты» в админке). Здесь они всегда внутри
 * HorizontalScroll: помещаются - растягиваются на всю ширину, как раньше,
 * не помещаются - листаются, и выбранная подкручивается в поле зрения.
 * Все вкладки мини-аппа берут Tabs отсюда, а не из VKUI напрямую.
 *
 * 2026-10-22: подсветка выбранной вкладки - одна общая подложка, которая
 * перетекает от вкладки к вкладке (свой подчерк VKUI скрыт в index.css).
 * Подложка лежит в той же прокручиваемой ленте, что и вкладки, поэтому
 * уезжает вместе с ними.
 */
export default function Tabs({ children, ...rest }) {
  const box = useRef(null);
  const placeRef = useRef(null);
  const [ink, setInk] = useState(null);
  // Не влезли - края ленты тают (2026-11-12): так видно, что её можно
  // листать. Стрелки VKUI ложились прямо на названия вкладок.
  // '' | 'right' | 'left' | 'both' - с какой стороны ещё есть вкладки.
  const [overflow, setOverflow] = useState('');

  // Выбранная вкладка могла смениться - подложку переставить. Дёшево: только
  // замер, наблюдатель за размером один на всё время жизни (раньше
  // создавался заново на каждую перерисовку).
  useLayoutEffect(() => { placeRef.current?.(); });

  useLayoutEffect(() => {
    const root = box.current;
    if (!root) return undefined;
    const strip = root.querySelector('.vkuiHorizontalScroll__in');
    const edges = () => {
      if (!strip || strip.scrollWidth <= strip.clientWidth + 1) {
        setOverflow('');
        return;
      }
      const left = strip.scrollLeft > 1;
      const right = strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1;
      setOverflow(left && right ? 'both' : left ? 'left' : right ? 'right' : '');
    };
    strip?.addEventListener('scroll', edges, { passive: true });
    const place = () => {
      edges();
      const tab = root.querySelector('.vkuiTabsItem__selected');
      if (!tab) {
        setInk(null);
        return;
      }
      setInk((prev) => {
        const next = { left: tab.offsetLeft, width: tab.offsetWidth };
        return prev && prev.left === next.left && prev.width === next.width ? prev : next;
      });
    };
    placeRef.current = place;
    place();
    const observer = new ResizeObserver(place);
    observer.observe(root);
    return () => {
      observer.disconnect();
      strip?.removeEventListener('scroll', edges);
    };
  }, []);

  return (
    <div ref={box} className={overflow ? `ink-tabs ink-tabs--fade-${overflow}` : 'ink-tabs'}>
      <VkTabs withScrollToSelectedTab scrollBehaviorToSelectedTab="center" {...rest}>
        <HorizontalScroll showArrows={false} scrollOnAnyWheel>
          {children}
          {ink && (
            <span
              className="ink-tabs__ink"
              style={{ transform: `translateX(${ink.left}px)`, width: ink.width }}
              aria-hidden="true"
            />
          )}
        </HorizontalScroll>
      </VkTabs>
    </div>
  );
}
