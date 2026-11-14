"""«Сейчас идёт» на экране «Персонаж» мини-аппа (2026-11-14, владелец).

Одним списком всё, что у персонажа запущено и когда кончится: возрождение,
переход пешком и поездка верхом, долгий путь, исследование и отдых, добыча,
снасть в воде, варка в доме, повозки обоза, руины, бой, мировой босс.
Раньше за каждым сроком игрок шёл в чат.

Мини-апп живёт в том же процессе, что и бот, поэтому занятия из памяти бота
(исследование, бой, руины) видны и здесь. Ничего не меняет - только читает.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _row(kind: str, icon: str, title: str, ends: datetime | float | None = None, note: str | None = None,
         go: dict | None = None) -> dict:
    """go - куда ведёт нажатие (2026-11-14): {"tab": раздел, "cell": клетка на карте}."""
    if isinstance(ends, datetime):
        ends = _aware(ends).timestamp()
    return {"id": kind, "icon": icon, "title": title, "ends_at": ends, "note": note, "go": go}


def _map(x: int, y: int, label: str | None = None) -> dict:
    return {"tab": "map", "cell": {"x": x, "y": y, "label": label}}


async def collect(db, character, peer_id: int, now: datetime | None = None) -> list[dict]:
    from bot import explore_rest, pending_activity
    from bot.battle_keyboard import in_any_battle
    from bot.handlers import ruins as ruins_handlers
    from models import TradeCart
    from services import (
        alchemy_service,
        death_service,
        elixir_service,
        fishing_service,
        mining_service,
        mount_service,
        movement_service,
        trade_service,
        voyage_service,
        world_boss_service,
    )

    now = now or datetime.now(timezone.utc)
    ts = now.timestamp()
    rows: list[dict] = []

    if death_service.is_dead(character, now):
        rows.append(_row("dead", "💀", "Возрождение", character.respawn_at))
    if in_any_battle(peer_id):
        rows.append(_row("battle", "⚔️", "Идёт бой"))
    if ruins_handlers.is_inside(peer_id):
        rows.append(_row("ruins", "🕳", "Вы в руинах"))

    if explore_rest.exploring(peer_id):
        rows.append(_row("explore", "🧭", "Исследование", await pending_activity.due_at(explore_rest.EXPLORE, peer_id)))
    if explore_rest.resting(peer_id):
        rows.append(_row("rest", "🛌", "Отдых", await pending_activity.due_at(explore_rest.REST, peer_id)))

    if movement_service.is_traveling(character, now):
        rows.append(_row("walk", "🚶", "Переход пешком", ts + movement_service.remaining_seconds(character, now)))
    travel = await mount_service.active_travel(db, character.id)
    if travel is not None and travel.status == "traveling":
        rows.append(_row("ride", "🐎", f"Верхом в ({travel.to_x}; {travel.to_y})", travel.arrives_at,
                         go=_map(travel.to_x, travel.to_y)))
    elif travel is not None and travel.status == "ambushed":
        rows.append(_row("ride", "🐎", f"Верхом в ({travel.to_x}; {travel.to_y})", note="напали в пути",
                         go=_map(travel.to_x, travel.to_y)))

    voyage = await voyage_service.get(db, character.id)
    if voyage is not None and voyage.status == "away":
        rows.append(_row("voyage", "⚓", "Долгий путь", voyage.ends_at))

    if character.screen == "mine" and mining_service.is_digging(character):
        rows.append(_row("dig", "⛏", "Добыча", ts + mining_service.remaining_seconds(character, now)))
    if fishing_service.is_casting(character) and not fishing_service.cast_is_stale(character, now):
        rows.append(_row("fish", "🎣", "Снасть в воде", note="ждёт поклёвки"))

    recipe = alchemy_service.brewing(character)
    if recipe is not None:
        elixir = elixir_service.elixir_def(recipe.elixir_id)
        title = f"Варка: {elixir.name}" if elixir is not None else "Варка зелья"
        rows.append(_row("brew", "⚗️", title, character.house_work_until))

    carts = (await db.scalars(
        select(TradeCart).where(TradeCart.character_id == character.id, TradeCart.status == "traveling")
        .order_by(TradeCart.arrives_at)
    )).all()
    for cart in carts:
        # Город отдельно от слова «в»: «в Шепчущие Пущи» не склеивать (CLAUDE.md).
        city = trade_service.city_title(cart.to_city) if cart.to_city else None
        rows.append(_row(f"cart{cart.slot}", "🛒", "Повозка обоза", cart.arrives_at,
                         note=f"→ {city}" if city else None, go={"tab": "trade"}))

    boss = await world_boss_service.active_boss(db, now)
    if boss is not None:
        wait = await world_boss_service.cooldown_minutes(db, boss, character.id, now)
        rows.append(_row("boss", "🐲", "Мировой босс жив", boss.expires_at,
                         note=f"заход через {wait} мин." if wait else "можно идти",
                         go=_map(boss.x, boss.y, "Мировой босс")))
    return rows
