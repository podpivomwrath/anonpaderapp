"""Бой в приложении «Монолит» (2026-11-15): снимок боя после старта и каждого
хода - для анимаций и своего интерфейса боя.

Текст боя (табло, лог хода, кнопки) по-прежнему приходит событиями message
канала, как в ВК. Здесь - отдельное событие battle с теми же данными в
структуре: бойцы, здоровье, щиты, эффекты, удары и лечение хода. Движок один
(game/combat/tick_engine.py, наблюдатель on_snapshot), собираем для четырёх
его экземпляров: соло, PvP, групповой PvE, рейды (main.py).

Кому: игрокам этого боя, у которых сейчас открыто приложение. В соло-бою
бой идёт по vk_id игрока (session_id), игрок там - боец PLAYER_ID; в
остальных боец игрока - это id персонажа (app_channel.vk_of_character).
"""

from bot import app_channel
from game.combat.resolver import TickResult
from game.combat.session import CombatantState, CombatSessionState


def _effects(c: CombatantState) -> list[dict]:
    return [
        {"kind": str(e.kind.value if hasattr(e.kind, "value") else e.kind), "value": e.value,
         "turns": e.remaining_ticks, "stacks": e.stacks, "tag": getattr(e, "tag", None), "source": e.source_id}
        for e in c.effects
    ]


def _combatant(c: CombatantState, own: bool) -> dict:
    out = {
        "id": c.id, "side": c.side, "kind": c.kind, "name": c.name, "level": c.level,
        "hp": c.current_hp, "max_hp": c.max_hp, "shield": c.shield, "alive": c.alive,
        "base_class": c.base_class, "subclass": c.subclass_id, "effects": _effects(c),
    }
    if own:
        out["cooldowns"] = dict(c.cooldowns)
    return out


def _hits(result: TickResult | None) -> tuple[list[dict], list[dict]]:
    if result is None:
        return [], []
    hits = [
        {"from": h.source_id, "to": h.target_id, "label": h.label, "amount": h.amount, "crit": h.crit,
         "missed": h.missed, "dot": h.is_dot, "tick": getattr(h, "is_tick", False),
         "hp_before": h.hp_before, "hp_after": h.hp_after, "max_hp": h.max_hp}
        for h in result.hit_renders
    ]
    heals = [
        {"from": h.source_id, "to": h.target_id, "label": h.label, "amount": h.amount,
         "hp_before": h.hp_before, "hp_after": h.hp_after, "max_hp": h.max_hp}
        for h in result.heal_renders
    ]
    return hits, heals


def payload(engine: str, state: CombatSessionState, result: TickResult | None, own_id: int) -> dict:
    hits, heals = _hits(result)
    return {
        "type": "battle", "engine": engine, "session": str(state.session_id), "mode": str(state.mode),
        "turn": state.tick_number, "deadline": getattr(state, "turn_deadline", None), "you": own_id,
        "combatants": [_combatant(c, c.id == own_id) for c in state.combatants.values()],
        "hits": hits, "heals": heals,
        "deaths": list(result.deaths) if result else [],
        "lines": list(result.lines) if result else [],
        "finished": bool(result and result.finished),
        "winner_side": result.winner_side if result else None,
        "draw": bool(result and result.draw),
    }


def recipients(engine: str, state: CombatSessionState) -> dict[int, int]:
    """vk_id игрока с открытым приложением -> id его бойца."""
    out: dict[int, int] = {}
    for c in state.combatants.values():
        if c.kind != "character":
            continue
        vk_id = state.session_id if engine == "solo" else app_channel.vk_of_character(c.id)
        if vk_id is not None and app_channel.active(vk_id):
            out[int(vk_id)] = c.id
    return out


def observer(engine: str):
    """Наблюдатель для TickEngine(on_snapshot=...): engine - solo | pvp | group | raid."""

    async def on_snapshot(state: CombatSessionState, result: TickResult | None) -> None:
        if not app_channel.anyone():
            return  # никто не в приложении - ничего не собираем
        for vk_id, own_id in recipients(engine, state).items():
            await app_channel.publish(vk_id, payload(engine, state, result, own_id))

    return on_snapshot
