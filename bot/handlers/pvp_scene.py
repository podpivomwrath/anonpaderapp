"""PvP: кто на клетке - «Осмотреться», список целей, разбор цели /напасть
(номер из осмотра, имя, бой на клетке), согруппники.

Вынесено из bot/handlers/pvp.py без изменений логики (2026-10-22, нарезка).
Состояние боёв живёт в pvp.py, здесь - pvp.X.
"""

from sqlalchemy import select
from bot.handlers import combat as combat_handlers
from bot.pvp_texts import ALONE_ON_CELL
from models import Character
from services import fishing_service, mining_service, pk_service, pvp_shield
from services import daily_service, premium_service, pvp_service
from services import onboarding_service as onboarding_svc
from bot.handlers import pvp


# --- Осмотреться / резолв цели ---


def _battles_at(x: int, y: int) -> list[tuple[int, pvp.Battle]]:
    return [(bid, b) for bid, b in pvp._battles.items() if b.location == (x, y) and not b.arena]


async def _scene_at(db, character: Character) -> tuple[list[Character], list[tuple[int, pvp.Battle]]]:
    others = await pvp_service.others_at(db, character)
    battles = _battles_at(character.pos_x, character.pos_y)
    busy_ids = {cid for _, b in battles for cid in b.participants}
    # Патч 33, ч.3: AFK (нет действий AFK_TIMEOUT_MINUTES) исключён из
    # «Осмотреться»/нумерации целей — уже идущий бой это НЕ трогает (busy_ids
    # выше — отдельная причина, AFK-статус там не проверяется намеренно).
    # Заказ (2026-10-16): от взявшего заказ цель в АФК не прячется.
    from services import contract_service

    hunted = await contract_service.hunted_ids(db, character.id)
    # Жилу из исследования копают незаметно (2026-10-31, владелец): такого
    # игрока видит только взявший на него заказ.
    solo = [
        c for c in others
        if c.id not in busy_ids
        and ((not pvp_service.is_afk(c) and not mining_service.is_event_vein(c)) or c.id in hunted)
    ]
    return solo, battles


async def _afk_target_named(db, character: Character, target: str) -> bool:
    """True — target (по имени; числа никогда не указывают на AFK — они не
    нумеруются вовсе) совпадает с игроком на клетке, который сейчас AFK.
    Только чтобы attack_command показал отдельный лорный текст вместо
    общего "нет такой цели" (патч 33, ч.3)."""
    if target.isdigit():
        return False
    others = await pvp_service.others_at(db, character)
    battles = _battles_at(character.pos_x, character.pos_y)
    busy_ids = {cid for _, b in battles for cid in b.participants}
    lowered = target.lower()
    return any(
        c.id not in busy_ids and pvp_service.is_afk(c) and c.name.lower() == lowered
        for c in others
    )


async def _guild_tags(db, characters: list[Character]) -> dict[int, str]:
    """guild_id -> тег для «Осмотреться» (2026-10-13, просьба игроков)."""
    from sqlalchemy import select

    from models import Guild

    ids = {c.guild_id for c in characters if c.guild_id is not None}
    if not ids:
        return {}
    rows = await db.execute(select(Guild.id, Guild.tag).where(Guild.id.in_(ids)))
    return {gid: tag for gid, tag in rows.all()}


def _class_line(c: Character, tags: dict[int, str] | None = None) -> str:
    title = daily_service.title_name(c)
    tag = (tags or {}).get(c.guild_id)
    prefix = f"{premium_service.badge(c)}[{tag}] " if tag else premium_service.badge(c)
    prefix = f"{pk_service.badge(c)}{prefix}"
    name = f"{prefix}{c.name} «{title}»" if title else f"{prefix}{c.name}"
    return f"{name} · {c.level} ур. · {pvp_service.class_title(c)}{pk_service.wanted_suffix(c)}"


def _battle_scene_line(battle: pvp.Battle) -> str:
    side0 = [p.name for cid, p in battle.participants.items() if battle.side_of.get(cid) == 0]
    side1 = [p.name for cid, p in battle.participants.items() if battle.side_of.get(cid) == 1]
    return f"⚔️ Бой: {' и '.join(side0)} vs {' и '.join(side1)}"


# Патч 35, аудит: список игроков на клетке — ТЕКСТ, без единой инлайн-кнопки
# (цель называют числом/именем через attack_command), поэтому лимит клавиатуры
# VK тут не при чём даже на людной клетке. Длина сообщения теоретически растёт
# с числом игроков на клетке, но лимит VK на текст (4096 симв.) недостижим на
# практике при разумной плотности игроков.
async def _busy_marks(db, characters: list[Character]) -> dict[int, str]:
    """Кто на клетке сейчас дерётся не в PvP (2026-10-15): бой с мобами
    нападение обрывает, разлом и рейд - нет."""
    from bot.handlers import group_combat, raid_combat

    marks = {}
    for c in characters:
        left, why = pvp_shield.left(c.id)
        if left:
            marks[c.id] = f" · 🛡 {why}, напасть нельзя ещё {left} сек."
            continue
        peer = await onboarding_svc.vk_id_for_character(db, c.id)
        if peer is None:
            continue
        if raid_combat.has_active_battle(peer):
            marks[c.id] = " · 🌀 в разломе, напасть нельзя"
        elif combat_handlers.has_active_encounter(peer) or group_combat.has_active_group_battle(peer):
            marks[c.id] = " · ⚔️ в бою с мобами"
        # Работу нападение обрывает (2026-10-25) - видно, кого от чего оторвёшь.
        elif c.screen == "lake" and fishing_service.is_casting(c):
            marks[c.id] = " · 🎣 рыбачит"
        elif c.screen == "mine":
            # В штольне цель заказа не достать - видно, что он там (2026-10-29).
            marks[c.id] = " · ⛏ в забое" if mining_service.is_digging(c) else " · ⛏ в штольне"
        elif mining_service.is_event_vein(c):
            marks[c.id] = " · ⛏ копает жилу"
    return marks


def _scene_text(solo: list[Character], battles: list[tuple[int, pvp.Battle]], tags: dict[int, str] | None = None,
                busy: dict[int, str] | None = None) -> str:
    if not solo and not battles:
        return ALONE_ON_CELL
    lines = ["👁 Ты оглядываешься.", "", "Здесь есть кто-то ещё:"]
    idx = 1
    for c in solo:
        lines.append(f"{idx}. {_class_line(c, tags)}{(busy or {}).get(c.id, '')}")
        idx += 1
    for _, battle in battles:
        lines.append(f"{idx}. {_battle_scene_line(battle)}")
        idx += 1
    return "\n".join(lines)


TARGET_GONE_TEXT = "Этой цели здесь уже нет."


def _remember_look(peer_id: int, character: Character, solo: list[Character],
                   battles: list[tuple[int, pvp.Battle]]) -> None:
    pvp._last_look[peer_id] = (
        (character.pos_x, character.pos_y), [c.id for c in solo], [bid for bid, _ in battles],
    )


def _looked_entry(peer_id: int | None, character: Character, n: int) -> tuple[str, int] | None:
    """Кто был под номером n в последнем «Осмотреться» с этой клетки:
    ("solo", id персонажа) или ("battle", id боя). None - осмотра с этой
    клетки не было или номера в нём нет."""
    look = pvp._last_look.get(peer_id) if peer_id is not None else None
    if look is None:
        return None
    pos, solo_ids, battle_ids = look
    if pos != (character.pos_x, character.pos_y):
        pvp._last_look.pop(peer_id, None)
        return None
    if 1 <= n <= len(solo_ids):
        return "solo", solo_ids[n - 1]
    if 0 <= n - len(solo_ids) - 1 < len(battle_ids):
        return "battle", battle_ids[n - len(solo_ids) - 1]
    return None


async def _resolve_target(db, character: Character, target: str, peer_id: int | None = None):
    """Возвращает (Character, None) — цель-игрок, (None, (battle_id, Battle))
    — идущий бой, (None, None) — цель не найдена."""
    solo, battles = await _scene_at(db, character)
    looked = _looked_entry(peer_id, character, int(target)) if target.isdigit() else None
    if looked is not None:
        kind, ref = looked
        if kind == "battle":
            return None, next(((bid, b) for bid, b in battles if bid == ref), None)
        victim = next((c for c in solo if c.id == ref), None)
        if victim is not None:
            return victim, None
        # Тот, кого видел, уже сам дерётся с кем-то на этой клетке - номер
        # ведёт в его бой.
        return None, next(((bid, b) for bid, b in battles if ref in b.participants), None)
    if target.isdigit():
        n = int(target)
        if 1 <= n <= len(solo):
            return solo[n - 1], None
        battle_idx = n - len(solo) - 1
        if 0 <= battle_idx < len(battles):
            return None, battles[battle_idx]
        return None, None
    lowered = target.lower()
    for c in solo:
        if c.name.lower() == lowered:
            return c, None
    # Ник того, кто уже дерётся на этой клетке, - это вход в его бой, как
    # номер боя из «Осмотреться». Раньше отвечали «Здесь нет такой цели»,
    # хотя игрок стоял рядом и дрался (живой прогон с тестовыми персонажами).
    for battle_id, battle in battles:
        if any(p.name.lower() == lowered for p in battle.participants.values()):
            return None, (battle_id, battle)
    return None, None


GROUPMATE_NO_PVP_TEXT = "Это твой согруппник - на своих не нападают."


async def _same_group(db, character, other_id: int) -> bool:
    """Нападать на согруппника нельзя (2026-10-13, решение владельца)."""
    from services import group_service

    mine = await group_service.get_membership(db, character.id)
    theirs = await group_service.get_membership(db, other_id)
    return mine is not None and theirs is not None and mine.group_id == theirs.group_id


#: Открытого PvP между согильдийцами нет (2026-10-31, владелец: набивка PTS
#: на своих). Подраться со своими - только на арене таверны.
GUILDMATE_NO_PVP_TEXT = "Это твой согильдиец - со своими дерутся только на арене в таверне."
GUILDMATE_IN_GROUP_TEXT = "В группе, на которую нападаешь, твой согильдиец - со своими дерутся только на арене в таверне."
GUILDMATES_BOTH_SIDES_TEXT = "Согильдийцы бьются на обеих сторонах - вступить можно только против своих, а это нельзя."


async def _guildmate_ids(db, character, ids) -> set[int]:
    """Кто из ids в одной гильдии с персонажем (сам он не в счёт)."""
    if character.guild_id is None:
        return set()
    ids = [cid for cid in ids if cid != character.id]
    if not ids:
        return set()
    rows = await db.scalars(
        select(Character.id).where(Character.id.in_(ids), Character.guild_id == character.guild_id)
    )
    return set(rows)


async def _guildmate_sides(db, character, battle: pvp.Battle) -> set[int]:
    """Стороны (1/2), на которых бьются согильдийцы персонажа."""
    mates = await _guildmate_ids(db, character, list(battle.participants))
    return {battle.side_of.get(cid, 0) + 1 for cid in mates}


async def _groupmate_side(db, character, battle: pvp.Battle) -> int | None:
    """Сторона (1/2), на которой бьются согруппники персонажа. None - их в
    бою нет или они на обеих сторонах."""
    from services import group_service

    group = await group_service.get_group_snapshot(db, character.id)
    if group is None:
        return None
    mates = {m.id for m in group.members if m.id != character.id}
    sides = {battle.side_of.get(cid, 0) for cid in battle.participants if cid in mates}
    return next(iter(sides)) + 1 if len(sides) == 1 else None


def _battle_roster_text(battle_id: int, battle: pvp.Battle) -> str:
    combatants = pvp._live_state(battle_id, battle)
    by_side: dict[int, list[str]] = {0: [], 1: []}
    for cid, p in list(battle.participants.items()):
        c = combatants.get(cid)
        if c is None:
            continue
        hp_pct = round(100 * c.current_hp / c.max_hp) if c.max_hp else 0
        by_side.setdefault(battle.side_of.get(cid, 0), []).append(
            f"{p.name} · {c.level} ур. · {p.class_title} ({hp_pct}% HP)"
        )
    lines = ["⚔️ Бой:", f"Сторона 1: {', '.join(by_side.get(0, []))}", f"Сторона 2: {', '.join(by_side.get(1, []))}"]
    return "\n".join(lines)
