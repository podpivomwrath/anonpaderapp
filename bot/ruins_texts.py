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
ROOM_ICON = {
    rules.START: "🕯", rules.FIGHT: "⚔️", rules.ELITE: "💀", rules.BOSS: "👑", rules.AMBUSH: "🗡",
    rules.SPRING: "⛲", rules.ALTAR: "🩸", rules.EVENT: "❓", rules.TRAP: "🪤", rules.CRYPT: "⚰️",
    rules.WELL: "🔁", rules.CAVEIN: "⛏", rules.PRISONER: "⛓", rules.STOREROOM: "🏺", rules.CHAPEL: "📿",
    rules.TREASURE: "💰", "cleared": "▫️",
}

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

#: Ворон с письмом наставника - на 60 уровне, один раз (2026-11-05).
RAVEN_LETTER = (
    "🐦‍⬛ На плечо садится ворон. Глаз у него не сосчитать: по всей голове, по шее, вдоль крыльев, "
    "и все уставились на тебя. К лапе привязано письмо.\n\n"
    "«Дошёл до шестидесятого - я в тебе не ошибся. Для тебя есть новое поручение, "
    "в письме о нём писать не стану. Загляни ко мне.\n"
    "Ворона не корми, он и так ест за троих.\n"
    "- Наставник»"
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
    rules.AMBUSH: "🗡 Засада! Сумки прижаты к полу, до зелий не дотянуться. Из ниш выходят",
    rules.TREASURE: "💰 Сундук ощерился зубами. Мимик, а с ним",
}

#: Особые комнаты: что видно при входе.
SPECIAL_TEXT = {
    rules.SPRING: "⛲ Из трещины в стене бьёт ключ. Вода холодная и чистая, на камне рядом выбита чаша.",
    rules.ALTAR: "🩸 Алтарь культа, на нём бурая корка. Культисты платили ему кровью и получали дары.",
    rules.CRYPT: "⚰️ Склеп. В нишах кости послушников, на крышках - слова, которыми их поднимали.",
    rules.WELL: "🔁 Сухой колодец. На краю сложены чужие подношения: кольца, пряжки, зубы.",
    rules.CAVEIN: "⛏ Проход завален наполовину. Пролезть можно, но порежешься. В обход - через нишу, а там шевелятся послушники.",
    rules.PRISONER: "⛓ У стены на цепи сидит забойщик - тот, второй, которого ищут наверху. Рядом спит охрана.",
    rules.STOREROOM: "🏺 Кладовая культа: кувшины, свёртки, ящики под печатями. На двери выцарапано: «Взял - заплатишь».",
    rules.CHAPEL: "📿 Молельня. На полу медные чаши, в каждой - реликвии, которые сюда принесли до вас.",
    rules.TREASURE: "💰 В углу стоит окованный сундук. Замок сбит.",
    rules.TRAP: "🪤 Под ногой щёлкает плита.",
}

#: Сценки (комната «Событие»).
EVENT_TEXT = {
    "candles": "❓ Склад свечей. Тысячи огарков, в некоторые вплавлены кольца, бусины, кости.",
    "hermit": "❓ В нише сидит старый сектант. Говорит, что ждёт тут сорок лет, и просит его выслушать.",
    "sealed": "❓ Сундук с сургучной печатью культа. Печать тёплая на ощупь.",
    "writing": "❓ Надпись на стене, свежей краской поверх старой. Слова знакомые, но порядок чужой.",
}

#: Подписи кнопок выбора.
CHOICE_LABEL = {
    "drink": "🥤 Испить", "gift": "🎁 Просить дар", "blood": "🩸 Дать крови", "raise": "⚰️ Поднять павших",
    "squeeze": "⛏ Пролезть", "detour": "⚔️ В обход", "free": "⛓ Освободить", "take": "🏺 Взять",
    "pray": "📿 Пожертвовать", "open": "💰 Открыть", "grab": "🕯 Набить карманы", "listen": "👂 Выслушать",
    "chase": "👢 Прогнать", "break": "🔓 Сорвать печать", "read": "📖 Прочесть вслух", "leave": "🚶 Не трогать",
}

#: Исходы выбора.
OUTCOME = {
    "leave": "Группа оставляет комнату как есть.",
    "spring_drink": f"⛲ Вода смывает усталость: +{round(rc.SPRING_HEAL * 100)}% здоровья живым.",
    "spring_gift": "⛲ Лидер опускает руку в воду - и нащупывает на дне тёплый камешек.",
    "altar_blood": f"🩸 Каждый режет ладонь над алтарём: -{round(rc.ALTAR_BLOOD * 100)}% здоровья. Корка на камне светлеет.",
    "crypt_raise": (f"⚰️ Слова с крышек работают. Павшие встают с {round(rc.CRYPT_RAISE * 100)}% здоровья, "
                    f"живые отдают по {round(rc.CRYPT_COST * 100)}%."),
    "cavein_squeeze": f"⛏ Пролезли, ободрав бока: -{round(rc.CAVEIN_HIT * 100)}% здоровья. Проход дальше открыт.",
    "cavein_detour": "⛏ В обход, через нишу. Там не пусто.",
    "prisoner_free": "⛓ Охрана просыпается от звона цепи.",
    "storeroom_take": "🏺 Мешки потяжелели. Дверь за спиной захлопывается сама, и на всех ложится проклятие этажа.",
    "chapel_pray": f"📿 Каждый кладёт в чашу по {rc.CHAPEL_PRICE} реликвии из мешка.",
    "treasure_open": "💰 В сундуке старые подношения - разбирайте.",
    "treasure_mimic": "💰 Сундук открывает пасть сам.",
    "candles_ok": "🕯 В огарках нашлось кое-что ценное.",
    "candles_fire": "🕯 Огарки вспыхивают разом, обжигая руки: -15% здоровья.",
    "hermit_listen": "👂 Старик долго рассказывает, путая годы. Под конец суёт лидеру в руку свой оберег.",
    "hermit_chase": "👢 Старик уходит, бросив котомку. В ней реликвии.",
    "sealed_ok": "🔓 Внутри подношения - их делят на всех.",
    "sealed_trap": "🔓 Из-под печати брызжет кислота: -20% здоровья.",
    "writing_ok": "📖 Слова складываются, и на стене проступает знак дара.",
    "writing_bad": "📖 Язык заплетается на третьем слове. Голова гудит: -10% здоровья.",
    "well": "🔁 Старый дар уходит в колодец. Со дна поднимается другое.",
}

TRAP_LINE = "🪤 Из стен вылетают шипы."


def trap_text(dodged: dict[int, bool], names: dict[int, str]) -> str:
    hit = [names[c] for c, ok in dodged.items() if not ok and c in names]
    safe = [names[c] for c, ok in dodged.items() if ok and c in names]
    lines = [SPECIAL_TEXT[rules.TRAP], TRAP_LINE]
    if safe:
        lines.append("Увернулись: " + ", ".join(safe))
    if hit:
        lines.append(f"Задело ({round(rc.TRAP_HIT * 100)}% здоровья): " + ", ".join(hit))
    return "\n".join(lines)


def offer_text(ids: list[str], leader: bool, leader_name: str) -> str:
    from game import ruins_gifts

    lines = ["🎁 Дары на выбор:"] + [f"{i}. {ruins_gifts.line(g)}" for i, g in enumerate(ids, 1)]
    lines.append(f"Выбирай, на это {rc.GIFT_SECONDS} с, потом выпадет случайный." if leader
                 else f"Выбирает {leader_name}.")
    return "\n".join(lines)


def gift_taken(gift_id: str, by: str | None) -> str:
    from game import ruins_gifts

    who = f"{by} выбирает" if by else "Никто не выбрал - руины выбирают сами"
    return f"🎁 {who}: {ruins_gifts.line(gift_id)}"


def gifts_block(gifts: list[dict]) -> str | None:
    from game import ruins_gifts

    if not gifts:
        return None
    rows = [ruins_gifts.line(g["id"]) + (" (до конца этажа)" if g.get("floor") else "") for g in gifts]
    return "🎁 Дары группы:\n" + "\n".join(rows)


def chests_line(n: int) -> str:
    return f"🔮 Первая победа над этим хозяином: {plural.count(n, 'ларец рун', 'ларца рун', 'ларцов рун')} - уже в сумке."


def curse_line(gift_id: str) -> str:
    from game import ruins_gifts

    return f"🩸 Проклятие этажа: {ruins_gifts.line(gift_id)}"
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


BOSS_INTRO = {
    "Привратник завала": "Из завала поднимается Привратник - глыба с руками. Своды над ним дрожат.",
    "Счетовод культа": "За столом сидит Счетовод с книгой долгов. Он поднимает голову и макает перо.",
    "Свечница": "Свечница в восковом платье стоит среди огней. Пока они горят, раны на ней затягиваются.",
    "Глашатай": "Глашатай в рваной ризе дует в рог. Он заранее кричит, какой удар не потерпит.",
    "Братья-копатели": "Два брата с лопатами, спина к спине. Ранишь одного сильнее - второй звереет.",
    "Настоятель": "Настоятель в чёрном, с кадилом. Каждый ход он объявляет обет, и нарушать его больно всем.",
}


def boss_opening(names: list[str]) -> str:
    head = "👑 Зал хозяина этажа." if len(names) == 1 else f"👑 Зал хозяев этажа - их здесь {len(names)}."
    return "\n".join([head] + [BOSS_INTRO.get(n, n) for n in names])


def opening_text(kind: str, layout: dict, party: int) -> str:
    """Кто встретил группу в комнате."""
    name, elite, _primary, _label = rules.mob_kind(layout)
    count = rc.mob_count(party)
    retinue = f", с ним {_crowd(name, count - 1)}" if count > 1 else ""
    if kind in (rules.AMBUSH, rules.TREASURE):
        crowd = _crowd(name, count if kind == rules.AMBUSH else count - 1)
        return f"{ROOM_TEXT[kind]} {crowd}." if crowd else f"{ROOM_TEXT[kind]}."
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


def bag_text(bag: dict, floor: int, used: int, limit: int = rc.CONSUMABLES_PER_FLOOR) -> str:
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
    lines.append(f"🧪 Зелий на этаж: {max(limit - used, 0)} из {limit}")
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
