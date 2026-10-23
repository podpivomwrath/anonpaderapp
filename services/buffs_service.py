"""Действующие баффы персонажа одним списком (2026-10-23): еда, прикормка,
молитва в часовне, настойка пепла, эффекты событий исследования.

Для вкладки «Герой» - короткие плашки слева от силуэта: название, проценты,
сколько осталось. Сами баффы живут каждый в своём сервисе, здесь только сводка.
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import cooking
from game.economy import craft_gear_config as gc
from game.economy import guild_config as ggc
from models import Character

#: Короткие подписи эффектов блюд - в плашку длинное «к шансу лишней
#: реликвии с моба» не влезает.
FOOD_SHORT = {
    "max_hp_bonus": "здоровье",
    "xp_bonus": "опыт",
    "damage_bonus": "урон",
    "incoming_damage_reduction": "защита",
    "relic_bonus": "реликвии",
    "crit_chance_bonus": "крит",
    "dodge_bonus": "уклонение",
}

STAT_SHORT = {"str": "сила", "agi": "ловкость", "int": "интеллект", "vit": "выносливость", "wil": "воля"}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _pct(value: float) -> str:
    return f"{round(value * 100):+d}%"


def timed(character: Character, now: datetime | None = None) -> list[dict]:
    """Баффы со сроком: {id, emoji, name, value, until}."""
    from services import cooking_service, craft_gear_service, death_service, guild_territory_service

    now = now or datetime.now(timezone.utc)
    out = []
    found = cooking_service.active(character, now)
    if found:
        dish, grade = found
        d = cooking.dish_def(dish.dish_id)
        values = cooking_service.buff(character, now)
        out.append({
            "id": "food", "emoji": d.emoji if d else "🍲", "name": d.name if d else "Еда",
            "value": ", ".join(f"{_pct(v)} {FOOD_SHORT.get(k, k)}" for k, v in values.items()),
            "until": _aware(character.food_until).isoformat(),
        })
    if craft_gear_service.bait_minutes_left(character, now) > 0:
        out.append({
            "id": "bait", "emoji": "🪱", "name": "Прикормка",
            "value": f"клёв на {round(gc.BAIT_SPEED * 100)}% быстрее", "until": _aware(character.bait_until).isoformat(),
        })
    if guild_territory_service.prayer_active(character, now):
        out.append({
            "id": "prayer", "emoji": "🙏", "name": "Молитва",
            "value": f"{_pct(ggc.PRAYER_STAT_BONUS)} {STAT_SHORT.get(character.prayer_stat, '')}".strip(),
            "until": _aware(character.prayer_until).isoformat(),
        })
    if death_service.tincture_active(character, now):
        out.append({
            "id": "tincture", "emoji": "🫗", "name": "Настойка пепла",
            "value": "смерть без потери опыта", "until": _aware(character.ash_tincture_until).isoformat(),
        })
    return out


async def active(db: AsyncSession, character: Character, now: datetime | None = None) -> list[dict]:
    """Все баффы: со сроком и эффекты событий, которые считаются боями."""
    from game.world import scene_events
    from services import scene_event_service

    out = timed(character, now)
    effects = scene_events.content().effects
    for effect_id, left in await scene_event_service.active_effects(db, character.id):
        e = effects[effect_id]
        parts = [f"{_pct(v)} {FOOD_SHORT.get(k, k)}" for k, v in e.modifiers.items()]
        if e.trophy_bonus:
            parts.append(f"{_pct(e.trophy_bonus)} трофеи")
        out.append({
            "id": f"event:{effect_id}", "emoji": e.emoji, "name": e.name,
            "value": ", ".join(parts), "fights": left,
            # Событие может и навредить («Хрип в груди») - плашка красная.
            "bad": any(v < 0 for v in e.modifiers.values()),
        })
    return out
