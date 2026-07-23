"""Обработчики команд. Новые модули с labeler'ами добавляются в LABELERS.

Порядок важен: onboarding первым (перехватывает FSM создания раньше
остальных команд), fallback — строго последним (ловит всё необработанное
и, если персонажа нет, заново запускает онбординг после вайпа).
"""

from bot.handlers.appraiser import labeler as appraiser_labeler
from bot.handlers.basic import labeler as basic_labeler
from bot.handlers.combat import labeler as combat_labeler
from bot.handlers.fallback import labeler as fallback_labeler
from bot.handlers.inventory import labeler as inventory_labeler
from bot.handlers.list_keeper import labeler as list_keeper_labeler
from bot.handlers.onboarding import labeler as onboarding_labeler
from bot.handlers.stats_window import labeler as stats_window_labeler
from bot.handlers.world import labeler as world_labeler

LABELERS = [
    onboarding_labeler, world_labeler, combat_labeler, appraiser_labeler, inventory_labeler,
    list_keeper_labeler, stats_window_labeler, basic_labeler, fallback_labeler,
]
