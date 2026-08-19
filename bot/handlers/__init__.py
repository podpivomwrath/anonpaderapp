"""Обработчики команд. Новые модули с labeler'ами добавляются в LABELERS.

Порядок важен: onboarding первым (перехватывает FSM создания раньше
остальных команд), fallback — строго последним (ловит всё необработанное
и, если персонажа нет, заново запускает онбординг после вайпа).
"""

from bot.handlers.appraiser import labeler as appraiser_labeler
from bot.handlers.basic import labeler as basic_labeler
from bot.handlers.combat import labeler as combat_labeler
from bot.handlers.dailies import labeler as dailies_labeler
from bot.handlers.elixir_shop import labeler as elixir_shop_labeler
from bot.handlers.fallback import labeler as fallback_labeler
from bot.handlers.group import labeler as group_labeler
from bot.handlers.group_combat import labeler as group_combat_labeler
from bot.handlers.inventory import labeler as inventory_labeler
from bot.handlers.list_keeper import labeler as list_keeper_labeler
from bot.handlers.moderation import labeler as moderation_labeler
from bot.handlers.mounts import labeler as mounts_labeler
from bot.handlers.onboarding import labeler as onboarding_labeler
from bot.handlers.presets import labeler as presets_labeler
from bot.handlers.promo import labeler as promo_labeler
from bot.handlers.pvp import labeler as pvp_labeler
from bot.handlers.stats_window import labeler as stats_window_labeler
from bot.handlers.world import labeler as world_labeler

LABELERS = [
    onboarding_labeler, world_labeler, combat_labeler, group_combat_labeler, pvp_labeler, appraiser_labeler,
    inventory_labeler, list_keeper_labeler, presets_labeler, elixir_shop_labeler,
    dailies_labeler, mounts_labeler, stats_window_labeler, moderation_labeler, basic_labeler,
    # Патч 51, ч.2: группы — команды конкретные ("пригласить <ник>", "/выйти",
    # "/выгнать <ник>"), но одиночное слово "пригласить" (приглашение
    # пересылкой) технически проходит под тот же regex, что и промокод —
    # регистрируется СТРОГО ДО promo_labeler, чтобы угадавший совпадение
    # промокод не перехватил приглашение.
    group_labeler,
    # Патч 50: промокоды — TEXT_ONLY, без state/payload гейта, поэтому
    # регистрируется ПОСЛЕ всех более специфичных обработчиков (координаты
    # маунта, никнейм, PvP "1"/"2" и т.д.) — те гарантированно успевают
    # забрать своё раньше. Строго ПЕРЕД fallback (тот ловит вообще всё).
    promo_labeler,
    fallback_labeler,
]
