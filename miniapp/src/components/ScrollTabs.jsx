import { HorizontalScroll, Tabs as VkTabs } from '@vkontakte/vkui';

/**
 * Вкладки, которые всегда листаются вбок (2026-10-21, просьба владельца).
 *
 * Обычные Tabs VKUI не прокручиваются: лишние вкладки просто уезжают за
 * край экрана (так пропали «Донаты» в админке). Здесь они всегда внутри
 * HorizontalScroll: помещаются - растягиваются на всю ширину, как раньше,
 * не помещаются - листаются, и выбранная подкручивается в поле зрения.
 * Все вкладки мини-аппа берут Tabs отсюда, а не из VKUI напрямую.
 */
export default function Tabs({ children, ...rest }) {
  return (
    <VkTabs withScrollToSelectedTab scrollBehaviorToSelectedTab="center" {...rest}>
      <HorizontalScroll arrowSize="m" scrollOnAnyWheel>
        {children}
      </HorizontalScroll>
    </VkTabs>
  );
}
