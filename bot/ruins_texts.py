"""Тексты руин культа (bot/handlers/ruins.py). Правятся по скиллу game-text."""

from game import plural
from game import ruins as rules
from game.economy import ruins_config as rc
from game.economy import runes_config as runes_cfg

TITLE = "Древние руины культа"

BTN_ENTER = "🕳 Спуститься в руины"
BTN_GO = "✅ Иду"
BTN_BAG = "🎒 Мешок"
BTN_PARTY = "👥 Группа"
BTN_DEEPER = "⬇️ Глубже"
BTN_UP = "🚪 Наверх"
BTN_VOTE_YES = "👍 Выгнать"
BTN_VOTE_NO = "👎 Оставить"

ARROWS = {"up": "⬆️", "down": "⬇️", "left": "⬅️", "right": "➡️"}
WHERE = {"up": "вперёд", "down": "назад", "left": "налево", "right": "направо"}
ROOM_ICON = {rules.START: "🕯", rules.FIGHT: "⚔️", rules.ELITE: "💀", rules.BOSS: "👑", "cleared": "▫️"}

MENTOR_INTRO = (
    "- Слыхал, что в Подножном забое стряслось? Забойщики пробили стену, а за ней "
    "лестница вниз. Ступени тёсаные, на стенах знаки культа - того самого, что молился "
    "Монолиту, пока его не разогнали.\n\n"
    "Двое забойщиков спустились посмотреть. Один вернулся седой и говорит, что внизу этажи и "
    "конца им нет. Второго ищут до сих пор.\n\n"
    "Новичков туда не пускай. Сам сходи, раз уж дорос. Только мешок береги: что найдёшь "
    "внизу, твоё, пока ты живой.\n\n"
    f"📜 Новое место: {TITLE}. Вход - в Подножном забое (-1; 0), с {rc.MIN_LEVEL} уровня."
)

HERE_TEXT = (
    "🕳 В дальнем конце забоя разобран завал. За ним лестница уходит вниз, в руины культа.\n"
    f"Спускаются группой до {rc.MAX_PARTY} человек, с {rc.MIN_LEVEL} уровня. Добыча копится в мешке, "
    "выдают её только тем, кто вышел живым."
)
LOCKED_TEXT = f"🕳 За завалом в дальнем конце забоя - лестница вниз. Туда пускают с {rc.MIN_LEVEL} уровня."

PROLOGUE = (
    "Лестница кончается в зале с низким потолком. На полу копоть от старых костров, на стенах - "
    "знаки культа. Обратно хода нет: выход откроется, только когда падёт хозяин этажа."
)

ROOM_TEXT = {
    rules.START: "🕯 Зал у лестницы. Пусто.",
    rules.FIGHT: "⚔️ Из темноты выходят",
    rules.ELITE: "💀 Посреди комнаты стоит",
    rules.BOSS: "👑 Зал хозяина этажа.",
}
CLEARED_ROOM = "Здесь уже прибрано."
EMPTY_ROOM = "Пустая комната."

WAIT_LEADER = "Куда идти, решает лидер. Жди его шага."
NOT_NOW = "Сейчас не до этого."
INSIDE_REMINDER = "Ты в руинах. Ходит группа, ведёт лидер."
MOVE_TIMEOUT_NOTE = "Подтвердили не все - группа пошла и так."

BOSS_DOWN = (
    "👑 Хозяин этажа повержен. В углу зала нашёлся спуск ниже, а за спиной открылась лестница наверх."
)
LEADER_CHOICE = "Решай: глубже или наверх с мешками. Вниз - этажи злее, наверх - добыча твоя."
WAIT_CHOICE = "Лидер решает: глубже или наверх."
RAISED_LINE = f"🩸 Ты пал, но группа подняла тебя: {rc.RAISE_HP} HP."

EXIT_TEXT = "🚪 Группа поднялась по лестнице в забой. Мешки целы."
WIPE_TEXT = "💀 Группа легла в руинах. Мешки остались внизу, их уже не найти."
ULTIMATE_TEXT = "Бой затянулся. Из темноты выходят ещё и ещё, и группу просто задавили числом."
ABANDON_TEXT = "Группа сутки стояла на месте. Наверх вас вывели забойщики, мешки пропали."
RESTART_TEXT = "Руины дрогнули - группа снова у входа в комнату, откуда шла. Здоровье - как до боя."
KICKED_TEXT = "🚪 Группа выставила тебя из руин. Мешок остался у них внизу, а значит, пропал."
KICK_ONLY_INSIDE = "Выгнать можно только своего - того, кто в руинах с тобой."
KICK_NOT_IN_FIGHT = "В бою не голосуют. Дождись конца боя."
KICK_BUSY = "Уже идёт голосование. Дождись его конца."
KICK_SOLO = "Ты в руинах один - выгонять некого."
KICK_FAILED = "Голосование не прошло - {name} остаётся."


def floor_line(floor: int) -> str:
    return f"🕳 Этаж {floor} · мобы {rc.mob_level(floor)} ур."


def exits_line(exits: dict[str, int], seen: dict[int, str]) -> str:
    """Проходы из комнаты; у комнат, где уже были, - значок."""
    if not exits:
        return "Проходов нет."
    parts = []
    for d in ("up", "left", "right", "down"):
        if d in exits:
            icon = ROOM_ICON.get(seen.get(exits[d], ""), "")
            parts.append(f"{ARROWS[d]}{icon}")
    return "Проходы: " + " ".join(parts)


def pending_text(leader: str, direction: str) -> str:
    return (f"{leader} ведёт группу {WHERE[direction]} {ARROWS[direction]}. Жми «{BTN_GO}». "
            f"Через {rc.MOVE_CONFIRM_SECONDS} с группа пойдёт и без тебя.")


def leader_wait_text(direction: str) -> str:
    return f"Ведёшь группу {WHERE[direction]} {ARROWS[direction]}. Ждём остальных."


def _crowd(name: str, n: int) -> str:
    return name.lower() if n == 1 else f"{name.lower()} ×{n}"


def opening_text(kind: str, layout: dict, party: int) -> str:
    """Кто встретил группу в комнате."""
    name, elite, _primary, _label = rules.mob_kind(layout)
    count = rc.mob_count(party)
    retinue = f", с ним {_crowd(name, count - 1)}" if count > 1 else ""
    if kind == rules.BOSS:
        return f"{ROOM_TEXT[rules.BOSS]} С каменного трона встаёт {elite.lower()}{retinue}."
    if kind == rules.ELITE:
        return f"{ROOM_TEXT[rules.ELITE]} {elite.lower()}{retinue}."
    return f"{ROOM_TEXT[rules.FIGHT]}: {_crowd(name, count)}."


def rune_name(rune_id: str) -> str:
    rune = runes_cfg.BY_ID.get(rune_id)
    return f"«{rune.name}»" if rune else rune_id


def trophies_line(drop: dict[str, int]) -> str:
    """«🟣 Кровяной осколок, ⚪ Пепельная крошка ×2» - от дорогих к дешёвым."""
    from services import trophy_service

    parts = []
    for trophy_def in reversed(trophy_service.trophy_defs_ordered()):
        amount = drop.get(trophy_def.id)
        if amount:
            parts.append(f"{trophy_def.emoji} {trophy_def.name}" + (f" ×{amount}" if amount > 1 else ""))
    return ", ".join(parts)


def found_line(found: dict) -> str | None:
    """Что упало в мешок за комнату."""
    lines = []
    trophies = trophies_line(found.get("trophies") or {})
    if trophies:
        lines.append(f"🎒 В мешок: {trophies}")
    runes = found.get("runes") or []
    if runes:
        lines.append("🎒 Руны в мешок: " + ", ".join(rune_name(r) for r in runes))
    if found.get("raised"):
        lines.append(RAISED_LINE)
    return "\n".join(lines) or None


def bag_text(bag: dict, floor: int, used: int) -> str:
    lines = [f"🎒 Мешок · этаж {floor}"]
    runes = bag.get("runes") or {}
    trophies = bag.get("trophies") or {}
    if runes:
        lines.append("Руны: " + ", ".join(
            f"{rune_name(r)}" + (f" ×{n}" if n > 1 else "") for r, n in runes.items()))
    if trophies:
        lines.append("Реликвии: " + trophies_line(trophies))
    if not runes and not trophies:
        lines.append("Пока пусто.")
    lines.append(f"🧪 Зелий на этаж: {max(rc.CONSUMABLES_PER_FLOOR - used, 0)} из {rc.CONSUMABLES_PER_FLOOR}")
    lines.append("Мешок выдают при выходе наверх. Группа легла - мешок пропал.")
    return "\n".join(lines)


def party_text(rows: list[tuple[str, int, int, bool, bool]]) -> str:
    """rows: (имя, здоровье, максимум, пал, лидер)."""
    lines = ["👥 Группа в руинах"]
    for name, hp, max_hp, dead, leader in rows:
        mark = " 👑" if leader else ""
        state = "💀 пал" if dead else f"❤️ {hp}/{max_hp}"
        lines.append(f"{name}{mark} - {state}")
    lines.append("Выгнать: /кик ник")
    return "\n".join(lines)


def exit_bag_line(bag: dict) -> str:
    runes = sum((bag.get("runes") or {}).values())
    trophies = sum((bag.get("trophies") or {}).values())
    if not runes and not trophies:
        return "Мешок пустой."
    parts = []
    if runes:
        parts.append(plural.count(runes, "руна", "руны", "рун"))
    if trophies:
        parts.append(plural.count(trophies, "реликвия", "реликвии", "реликвий"))
    return "Из мешка: " + ", ".join(parts) + "."


def vote_text(starter: str, target: str) -> str:
    return (f"🗳 {starter} предлагает выгнать {target} из руин. Мешок изгнанного пропадёт. "
            f"Голосуйте, на это {rc.KICK_VOTE_SECONDS} с.")


def kicked_others(name: str) -> str:
    return f"🚪 {name} больше не с вами. Руины подстроятся под группу со следующего боя."


def new_leader(name: str) -> str:
    return f"👑 Теперь ведёт {name}."
