"""Переработанный боевой лог (патч 51, ч.5): два раздела (своя сторона /
противник, всегда в этом порядке), формат строки `[Кто] → [Что] по [Кому] —
[урон] ([цель]: было% → стало%)`, ДоТ-эффекты — отдельной строкой в конце
раздела цели, HP-полосы отдельным блоком внизу (сначала противники, потом
своя сторона). Никакой образности — тот же принцип, что и патч 43.

Строит лог из result.hit_renders/heal_renders (структурные, см.
game/combat/resolver.py::RenderedHit/RenderedHeal) для урона/лечения — точная
атрибуция по стороне без разбора текста. Остальные строки (контроль/щиты/
смерти/ничья — result.lines[:prelude_line_count] и хвост после hit/heal-
рендеров) раскладываются по разделам эвристикой: чьё имя комбатанта
встречается в строке, того и сторона (эти строки уже человекочитаемы и
называют участника по имени — комбатанты в одном бою уникальны по имени)."""

from game.combat import combat_flavor, display
from game.combat.resolver import RenderedHeal, RenderedHit, TickResult
from game.combat.session import CombatMode, CombatSessionState, EffectKind

_SEP = "━━━━━━━━━━━━━━"


def _mode(session: CombatSessionState) -> str:
    return display.MODE_PVE_NUM if session.mode == CombatMode.PVE else display.MODE_PVP


def _action_word(label: str) -> str:
    return "атака" if combat_flavor.is_basic_attack_label(label) else label


def _hit_line(hit: RenderedHit, source_name: str, target_name: str, mode: str) -> str:
    word = _action_word(hit.label)
    if hit.missed:
        # Промах называет то, чем били: навык, промахнувшийся «атакой»,
        # выглядел так, будто нажатие не сработало.
        mark = f" 🎯 Метка добычи ×{hit.marked}" if hit.marked else ""
        return f"{source_name} → {word} по {target_name} - промах, {target_name} уклоняется{mark}"
    crit = " (крит!)" if hit.crit else ""
    before = display.hp_text(hit.hp_before, hit.max_hp, mode)
    after = display.hp_text(hit.hp_after, hit.max_hp, mode)
    return f"{source_name} → {word} по {target_name} - {hit.amount} урона{crit} ({target_name}: {before} → {after})"


def _dot_line(hit: RenderedHit, target_name: str) -> str:
    return f"{target_name} теряет {hit.amount} HP от эффекта «{hit.label}»"


def _heal_line(heal: RenderedHeal, source_name: str, target_name: str, mode: str) -> str:
    before = display.hp_text(heal.hp_before, heal.max_hp, mode)
    after = display.hp_text(heal.hp_after, heal.max_hp, mode)
    who = "" if source_name == target_name else f"{target_name}: "
    return f"{source_name} → {heal.label} - восполнено {heal.amount} HP ({who}{before} → {after})"


def _guess_side(session: CombatSessionState, line: str) -> int | None:
    """Строка уже называет участника по имени (control_line и т.п.) —
    сопоставляем по вхождению имени. None — общее сообщение без привязки
    к конкретному участнику (напр. "Ничья: обе стороны пали одновременно")."""
    for combatant in session.combatants.values():
        if combatant.name in line:
            return combatant.side
    return None


def _mark_suffix(session: CombatSessionState, target, viewer_side: int, owner_id: int | None = None) -> str:
    """Патч 56, «Клеймо охоты» Клинка теней: стаки Метки добычи видны не только
    её владельцу, но и всей его стороне. owner_id (2026-10-13) - чья это доска:
    свои метки владелец видит всегда, без баффа (соло-бой, личная строка в
    групповом)."""
    watchers = [
        c for c in session.combatants.values()
        if c.side == viewer_side and c.alive and (
            c.buff_modifiers.get("mark_visible_to_allies", 0.0) > 0 or c.id == owner_id
        )
    ]
    if not watchers:
        return ""
    stacks = sum(
        e.stacks for e in target.effects_of(EffectKind.MARK)
        if any(e.source_id == w.id for w in watchers)
    )
    return f" - Метка добычи ×{stacks}" if stacks else ""


def _turns(n: int) -> str:
    return f"ещё {n} х." if n > 0 else "последний ход"


def class_line(combatants, owner_id: int) -> str | None:
    """Свои классовые механики бойца одной строкой-блоком под доской боя
    (2026-10-13, просьба игроков: Клинок сбивался со счёта Меток на боссах,
    Отравитель - со стаков яда). Только то, что повесил сам owner_id.
    combatants - словарь бойцов (CombatSessionState или дуэль). None - нечего
    показывать: подкласса нет или ничего не висит."""
    from game.combat.session import BURN_TAG, SECOND_HEART_TAG

    combatants = dict(combatants)
    owner = combatants.get(owner_id)
    if owner is None or not owner.alive:
        return None
    sub = owner.subclass_id
    enemies = [c for c in combatants.values() if c.alive and c.side != owner.side]
    allies = [c for c in combatants.values() if c.alive and c.side == owner.side]

    def mine(c, kind, burn=None):
        return [e for e in c.effects_of(kind) if e.source_id == owner_id
                and (burn is None or (getattr(e, "tag", None) == BURN_TAG) == burn)]

    parts: list[str] = []
    # «Последний вздох» держится 3 хода - игроки думали, что до первого
    # смертельного удара (2026-10-13). Показываем остаток любому классу.
    breath = owner.effects_of(EffectKind.LAST_BREATH)
    if breath:
        parts.append(f"💀 Последний вздох ({_turns(max(e.remaining_ticks for e in breath))})")
    if sub == "shadow_blade":
        for c in enemies:
            stacks = sum(e.stacks for e in mine(c, EffectKind.MARK))
            if stacks:
                parts.append(f"🎯 Метка добычи: {c.name} ×{stacks}")
    elif sub == "poisoner":
        for c in enemies:
            poison = mine(c, EffectKind.DOT, burn=False)
            if poison:
                stacks = sum(e.stacks for e in poison)
                parts.append(f"☠ Яд: {c.name} ×{stacks} ({_turns(max(e.remaining_ticks for e in poison))})")
    elif sub == "elementalist":
        for c in enemies:
            burn = mine(c, EffectKind.DOT, burn=True)
            if burn:
                parts.append(f"🔥 Горит: {c.name} ({_turns(max(e.remaining_ticks for e in burn))})")
            frozen = mine(c, EffectKind.FREEZE)
            if frozen:
                parts.append(f"❄ Скован: {c.name} ({_turns(max(e.remaining_ticks for e in frozen))})")
    elif sub == "blood_knight":
        for c in enemies:
            seal = mine(c, EffectKind.BLOOD_SEAL)
            if seal:
                parts.append(f"🩸 Кровавая печать: {c.name} ({_turns(max(e.remaining_ticks for e in seal))})")
    elif sub == "guardian":
        stance = owner.effects_of(EffectKind.BLOCK_STANCE)
        if stance:
            parts.append(f"🛡 Глухая оборона ({_turns(max(e.remaining_ticks for e in stance))})")
        cap = owner.effects_of(EffectKind.DAMAGE_CAP)
        if cap:
            parts.append(f"🪨 Несокрушимый ({_turns(max(e.remaining_ticks for e in cap))})")
        taunted = [c.name for c in enemies if getattr(c, "taunted_by", None) == owner_id]
        if taunted:
            parts.append("📣 Провокация: " + ", ".join(taunted))
    elif sub == "dark_mystic":
        for c in allies:
            ward = [e for e in mine(c, EffectKind.SHIELD_POOL) if getattr(e, "tag", None) != SECOND_HEART_TAG]
            left = round(sum(e.value for e in ward))
            if ward and left > 0:
                who = "ты" if c.id == owner_id else c.name
                parts.append(f"🛡 Оберег: {who} - {left} ({_turns(max(e.remaining_ticks for e in ward))})")
    return "\n".join(parts) if parts else None


def render_tick(
    session: CombatSessionState,
    result: TickResult,
    viewer_side: int = 0,
    enemy_lines: list[str] | None = None,
    title: str = "⚔️ БОЙ",
    side_titles: tuple[str, str] | None = None,
    owner_id: int | None = None,
) -> str:
    """Личный боевой лог этого хода с точки зрения стороны viewer_side —
    ВСЕГДА показывает "своя сторона" первой, "противник" второй, независимо
    от того, чьи это были действия внутри хода (одновременный резолв).

    enemy_lines — сценарные реплики рейд-босса (готовит инструмент, добивает,
    меняет фазу). Это ДЕЙСТВИЯ противника, поэтому им место в его разделе;
    раньше рейд клеил их над всей доской, и «Инструмент находит цель» висело
    выше строки «⚔️ БОЙ - ход N», будто относилось к прошлому ходу.

    title / side_titles — для массового боя (осада): заголовок вместо «БОЙ» и
    названия сторон по номеру стороны. Разделы тогда подписаны названием, но
    «своя сторона» всё равно первой; без side_titles всё как раньше."""
    mode = _mode(session)
    own: list[str] = []
    enemy: list[str] = []

    def bucket(side: int) -> list[str]:
        return own if side == viewer_side else enemy

    # Делим по is_tick, а не по is_dot: «ядовитый» по механике удар может быть
    # ДЕЙСТВИЕМ игрока (Токсический выброс), и его место в разделе того, кто бил.
    non_dot = [h for h in result.hit_renders if not h.is_tick]
    dot_hits = [h for h in result.hit_renders if h.is_tick]

    for hit in non_dot:
        source_name = session.combatants[hit.source_id].name
        target_name = session.combatants[hit.target_id].name
        bucket(hit.source_side).append(_hit_line(hit, source_name, target_name, mode))

    for heal in result.heal_renders:
        source_name = session.combatants[heal.source_id].name
        target_name = session.combatants[heal.target_id].name
        bucket(heal.source_side).append(_heal_line(heal, source_name, target_name, mode))

    hit_heal_span = len(result.hit_renders) + len(result.heal_renders)
    other_lines = (
        result.lines[: result.prelude_line_count]
        + result.lines[result.prelude_line_count + hit_heal_span :]
    )
    for line in other_lines:
        side = _guess_side(session, line)
        bucket(side if side is not None else 1 - viewer_side).append(line)

    for hit in dot_hits:
        target_name = session.combatants[hit.target_id].name
        bucket(hit.target_side).append(_dot_line(hit, target_name))

    # Сценарные реплики босса идут первыми в его разделе: они объясняют, что
    # он сделал в этот ход, и без них удары выглядят беспричинными.
    if enemy_lines:
        enemy[:0] = enemy_lines

    header = f"{title} - ход {session.tick_number}"
    if side_titles is not None and viewer_side in (0, 1):
        own_title = f"👥 {side_titles[viewer_side]} (ВАША СТОРОНА)"
        enemy_title = f"💀 {side_titles[1 - viewer_side]}"
    else:
        own_title, enemy_title = "👥 ВАША СТОРОНА", "💀 ПРОТИВНИК"
    parts = [
        header, "",
        own_title,
        *(own or ["Без изменений."]),
        "",
        enemy_title,
        *(enemy or ["Без изменений."]),
        "",
        _SEP,
    ]
    enemy_bars = [
        f"{c.name}: {display.health_bar(c.current_hp, c.max_hp, mode)}{display.shield_suffix(c)}"
        f"{_mark_suffix(session, c, viewer_side)}"
        for c in session.combatants.values()
        if c.side != viewer_side and c.alive
    ]
    # Противники пали - их полосок нет, и второй разделитель подряд был бы
    # пустым блоком между двумя линиями.
    if enemy_bars:
        parts += enemy_bars
        parts.append(_SEP)
    for c in session.combatants.values():
        if c.side == viewer_side and c.alive:
            parts.append(f"{c.name}: {display.health_bar(c.current_hp, c.max_hp, mode)}{display.shield_suffix(c)}")
    own_line = class_line(session.combatants, owner_id) if owner_id is not None else None
    if own_line:
        parts.append(own_line)
    return "\n".join(parts)
