"""Кеш событий исследования (патч 9, блок 1): content/events/exploration.json.

Тот же паттерн, что и game/world/encounters.py для мобов стартового кольца.
"""

import random

from game.content_loader import ExplorationEventDef, load_exploration_events

_events: list[ExplorationEventDef] | None = None


def all_events() -> list[ExplorationEventDef]:
    global _events
    if _events is None:
        _events = load_exploration_events()
    return _events


def random_event(rng: random.Random, has_fish: bool = False) -> ExplorationEventDef:
    """Случайное событие. has_fish=False убирает из пула события, требующие
    непустого садка (патч 58): предложить продать улов тому, у кого улова нет,
    — это пустой исход, а их в событиях быть не должно."""
    pool = [e for e in all_events() if has_fish or not e.requires_fish]
    return rng.choice(pool)


def event_by_id(event_id: str) -> ExplorationEventDef | None:
    for event in all_events():
        if event.id == event_id:
            return event
    return None
