"""Чем занят игрок - одна проверка на весь бот (2026-10-21).

Раньше у каждого входа была своя копия: bot/activity.py::blocked_reason,
маунт в чате, отправка маунта с карты мини-аппа, обработчики ходьбы. Копии
расходились: карта не знала про групповой бой и рейд, маунт в чате - про
забой и варку, ходьба держала добычу и вне забоя (Морфей застрял навсегда).

Теперь состояние определяет busy(), а входы только выбирают свой текст
отказа по коду. Новое блокирующее состояние добавляется СЮДА, в STATES и в
ENDS_BY (как оно заканчивается) - tests/test_busy.py не даст забыть второе.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

#: Код -> текст отказа по умолчанию (входы могут подставить свой).
STATES: dict[str, str] = {
    "dead": "Сначала дождись возрождения.",
    "pvp": "Сначала закончи текущий бой.",
    "battle": "Сначала закончи текущий бой.",
    "busy": "Сначала закончи исследование или отдых.",
    "digging": "",  # текст с остатком времени - mining_texts.busy_text
    "house_work": "Сначала закончи варку в доме.",
    "traveling_on_foot": "Сначала дождись прибытия.",
    "riding": "Сначала дождись окончания поездки.",
}

#: Как каждое состояние кончается - чтобы ни одно не держало игрока вечно.
#:   unstick - его снимает /застрял (bot/handlers/world.py::force_unstick);
#:   timer   - кончается само по времени (воскрешение, варка);
#:   battle  - бой кончается боем, /застрял только перерисовывает доску.
ENDS_BY: dict[str, str] = {
    "dead": "timer",
    "pvp": "battle",
    "battle": "battle",
    "busy": "unstick",
    "digging": "unstick",
    "house_work": "timer",
    "traveling_on_foot": "unstick",
    "riding": "unstick",
}


@dataclass(frozen=True)
class Busy:
    code: str
    text: str


async def busy(db, character, peer_id: int, now: datetime | None = None, skip: tuple[str, ...] = ()) -> Busy | None:
    """Первое занятие, которое не даёт начать новое действие, или None.
    skip - коды, которые этот вход проверяет сам по-своему."""
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import pvp as pvp_handlers
    from bot.handlers import world
    from services import death_service, mining_service, mount_service, movement_service

    now = now or datetime.now(timezone.utc)

    def hit(code: str, text: str | None = None) -> Busy | None:
        return None if code in skip else Busy(code, text if text is not None else STATES[code])

    checks = []
    if death_service.is_dead(character, now):
        checks.append(hit("dead"))
    if pvp_handlers.has_active_battle(peer_id):
        checks.append(hit("pvp"))
    if in_any_battle(peer_id):
        checks.append(hit("battle"))
    if world.is_busy(peer_id):
        checks.append(hit("busy"))
    # Добыча держит, только пока игрок в забое: вынесло наверх - он волен
    # уйти, добыча сбросится на следующей клетке (abandon_if_elsewhere).
    if character.screen == "mine" and mining_service.is_digging(character):
        from bot import mining_texts

        checks.append(hit("digging", mining_texts.busy_text(mining_service.remaining_seconds(character))))
    if getattr(character, "house_work", None) is not None:
        checks.append(hit("house_work"))
    if movement_service.is_traveling(character, now):
        checks.append(hit("traveling_on_foot"))
    found = next((c for c in checks if c is not None), None)
    if found is not None or "riding" in skip:
        return found
    travel = await mount_service.active_travel(db, character.id)
    if travel is not None and travel.status in ("traveling", "ambushed"):
        return hit("riding")
    return None
