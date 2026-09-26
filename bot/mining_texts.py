"""Тексты горного дела (патч 59). Числа — game/economy/mining_config.py.

Те же два правила, что у рыбалки: формулировки принадлежат серверу, а тексты
самой добычи короткие. Лор показывается один раз, при входе в выработку.
"""

import random

from bot.vk_media import photo_attachment
from game.content_loader import MineDef
from game.economy import mining
from game.economy import mining_config as mc

#: Вторая дверь в рудник — как «Озеро» и «Монолит». Кнопка приходит только при
#: ВХОДЕ на клетку, поэтому тому, кто уже стоит на руднике, нужна команда.
MINE_COMMAND = "Рудник"
MINE_HINT_LINE = f"⛏ Напиши «{MINE_COMMAND}», чтобы спуститься в выработку."

BTN_MINE = "⛏ В выработку"
BTN_DIG = "⛏ Добыть"
BTN_ORE = "🪨 Руда"
BTN_LEAVE_MINE = "Выйти наверх"
BTN_ABANDON = "Бросить кирку"

#: Кнопка в ивенте мелкой жилы. Подпись ОБЯЗАНА отличаться от BTN_DIG: в
#: vkbottle побеждает первый подходящий обработчик, и при совпадении текстовое
#: правило «Добыть» перехватывало нажатие инлайн-кнопки жилы раньше её
#: собственного обработчика — вся ветка мелких жил молча не работала.
BTN_DIG_VEIN = "⛏ Копать жилу"

SEP = "━━━━━━━━━━━━━━"


def mine_intro(mine: MineDef, rng: random.Random, ore_count: int) -> str:
    """Единственное место, где показывается описание рудника."""
    safe = (
        "🕊 PvP запрещено."
        if mine.tier <= mc.PVP_SAFE_MAX_MINE_TIER
        else "⚔️ Открытое PvP."
    )
    stock = (
        f"🪨 Руды в жиле: {ore_count} из {mc.MINE_ORE_CAP}."
        if ore_count else "🪨 Жила пуста. Порода появляется, пока живёт мир."
    )
    return (
        f"⛏ {mine.name}" + chr(10) + rng.choice(mine.descriptions)
        + chr(10) * 2 + stock + chr(10) + safe
    )


def depth_warning(mine: MineDef, mining_level: int) -> str | None:
    """Строка-предупреждение, если рудник игроку не по уровню. None - по уровню.

    Штраф за глубину - намеренный барьер (mining.time_multiplier), но его не
    было видно: новичок у глубокой жилы узнавал о нём, только начав копать,
    а о том, что руда всё равно будет по его уровню, - не узнавал вовсе.
    Выходил час ожидания ради того, что рядом с городом добывается за
    десять минут. Одна строка: вход в рудник видят часто, а лор - в описании.
    """
    factor = mining.time_multiplier(mine.tier, mining_level)
    if factor <= 1.0:
        return None
    low, high = (sec * factor for sec in mc.STATIC_MINE_SECONDS)
    need = mc.MINE_REQUIRED_LEVEL[mine.tier]
    ore_note = (
        " Руда глубже твоего уровня отсюда не пойдёт."
        if mining.unlocked_tier(mining_level) < mine.tier else ""
    )
    return (
        f"⚠️ Не по уровню (нужен {need}): кусок займёт от "
        f"{mining.format_duration(low)} до {mining.format_duration(high)}.{ore_note}"
    )


def level_line(character) -> str:
    need = mining.xp_to_next(character.mining_level)
    return (
        f"⛏ Горное дело: ур. {character.mining_level} "
        f"({character.mining_xp} / {need})"
    )


def dig_started_text(seconds: float) -> str:
    return f"Ты берёшься за кирку. Работы примерно на {mining.format_duration(seconds)}."


def dig_progress_text(seconds: float) -> str:
    return f"⛏ Копаешь. Осталось примерно {mining.format_duration(seconds)}."


EMPTY_MINE_TEXT = (
    "Жила выбрана подчистую. Порода нарастает сама - возвращайся позже."
)
NOT_AT_MINE_TEXT = "Здесь нечего копать."
ALREADY_DIGGING_TEXT = "Ты уже копаешь."
NOT_DIGGING_TEXT = "Сначала возьмись за кирку."
LEAVE_WHILE_DIGGING_TEXT = "Не бросив кирку, наверх не подняться."
ABANDONED_TEXT = "Ты бросаешь забой. Начатая порода остаётся в жиле."


def busy_text(seconds: float) -> str:
    """Отказ во время добычи. Раньше это была глухая фраза «ты занят»; теперь
    любая нажатая кнопка заодно отвечает, сколько осталось — иначе узнать это
    было негде, кроме как ждать."""
    return f"⛏ Ты в забое. Осталось примерно {mining.format_duration(seconds)}."


def dig_result_text(result) -> str:
    """Короткая сводка добычи: что подняли, опыт, уровень."""
    emoji = mc.GRADE_EMOJI.get(result.grade_id, "")
    mark = f"{emoji} " if emoji else ""
    lines = [
        f"{mark}{result.ore.emoji} {result.ore.name} ({result.grade_label})",
        f"⛏ +{result.xp} опыта горного дела",
    ]
    if result.levels_gained:
        lines.append(f"⬆️ Уровень горного дела: {result.new_level}")
    return chr(10).join(lines)


def ore_screen(ore: list) -> str:
    """Инвентарь руды. Цен нет: руду нельзя продать ни одному НПС, она ждёт
    прокачки снаряжения и торговли между игроками."""
    if not ore:
        return "🪨 Руды нет."
    lines = ["🪨 РУДА", SEP]
    for definition, grade_id, count in ore:
        emoji = mc.GRADE_EMOJI.get(grade_id, "")
        mark = f"{emoji} " if emoji else ""
        lines.append(
            f"{mark}{definition.emoji} {definition.name} "
            f"({mining.grade_name(grade_id)}) - {count} шт."
        )
    lines += [
        SEP,
        f"Всего: {sum(c for _d, _g, c in ore)} шт.",
        "Руду пока некому продать - она пойдёт на прокачку снаряжения.",
    ]
    return chr(10).join(lines)


# --- Иллюстрации (фото в альбоме группы VK, патч 99) ---

#: Одна картинка на ТИР, а не на рудник: рудников двадцать семь, а тиров пять.
#: Своё поле image у места по-прежнему главнее - если однажды захочется
#: выделить особое место, картинка тира его не перебьёт (то же правило
#: наследования, что у мобов, патч 36).
#: Пустая строка - картинки ещё нет, сообщение уйдёт без вложения.
TIER_PHOTO_IDS: dict[int, str] = {1: "", 2: "", 3: "", 4: "", 5: ""}


def mine_attachment(mine: MineDef) -> str | None:
    """Только ко входу в рудник. Ход добычи - повторяющееся действие."""
    photo_id = mine.image or TIER_PHOTO_IDS.get(mine.tier)
    return photo_attachment(photo_id) if photo_id else None
