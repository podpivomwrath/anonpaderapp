"""Тексты рыбалки (патч 58). Числа — game/economy/fishing_config.py.

Два правила, которым здесь всё подчинено:

1. Формулировки принадлежат СЕРВЕРУ. Мини-апп и клавиатуры берут готовые
   строки отсюда и не пересказывают правила своими словами — однажды клиент
   уже пересказал серверное правило и соврал (состав пресета, патч 57).

2. Тексты САМОЙ ловли — короткие. Лор уместен один раз, при выходе к воде;
   дальше игрок жмёт [Забросить] десятки раз подряд, и абзац на каждый заброс
   превращается в стену, которую перестают читать. Длина строки здесь — часть
   геймплея, а не оформление.
"""

import random

from bot.vk_media import photo_attachment
from game.content_loader import LakeDef
from game.economy import fishing
from game.economy import fishing_config as fc

#: Вторая дверь к озеру — как «Монолит» у рейда. Кнопка приходит только с
#: клавиатурой движения, то есть при ВХОДЕ на клетку; игроку, который уже
#: стоял на озере, иначе пришлось бы уходить и возвращаться.
LAKE_COMMAND = "/озеро"
LAKE_HINT_LINE = f"🎣 Напиши «{LAKE_COMMAND}», чтобы подойти к воде."

BTN_FISH = "🎣 К воде"
BTN_CAST = "🎣 Забросить"
BTN_STRIKE = "🪝 Подсечь"
BTN_BAG = "🧺 Садок"
BTN_LEAVE_LAKE = "Отойти от воды"
#: Пока снасть в воде (2026-10-19): вместо ухода - отмена заброса, игрок
#: остаётся у воды. Разводится по payload, подпись «Отменить» есть и у других.
BTN_CANCEL_CAST = "✖️ Отменить"
CANCEL_CAST_TEXT = "Ты вытаскиваешь снасть. Можно забросить снова."

SEP = "━━━━━━━━━━━━━━"


def lake_intro(lake: LakeDef, rng: random.Random) -> str:
    """Единственное место, где показывается описание озера — при входе к воде."""
    safe = (
        "🕊 PvP запрещено."
        if lake.tier <= fc.PVP_SAFE_MAX_LAKE_TIER
        else "⚔️ Открытое PvP."
    )
    return f"🎣 {lake.name}" + chr(10) + rng.choice(lake.descriptions) + chr(10) * 2 + safe


def level_line(character) -> str:
    need = fishing.xp_to_next(character.fishing_level)
    return (
        f"🎣 Рыбалка: ур. {character.fishing_level} "
        f"({character.fishing_xp} / {need})"
    )


def bag_line(grams: int, capacity: int) -> str:
    return f"🧺 Садок: {fishing.format_kg(grams)} / {fishing.format_kg(capacity)}"


CAST_TEXT = "Заброс сделан. Ждём."

BITE_TEXTS = [
    "🌊 Повело! Подсекай.",
    "🌊 Поплавок ушёл под воду. Подсекай!",
    "🌊 Резко повело в сторону. Подсекай!",
]

NOTHING_TEXT = "Поплавок так и не шевельнулся. Пусто."
TOO_EARLY_TEXT = "Рано - снасть вышла пустой."
STRIKE_MISSED_TEXT = "Опоздал."
NOT_AT_LAKE_TEXT = "Здесь негде рыбачить."
ALREADY_CASTING_TEXT = "Снасть уже заброшена. Жди."
NOT_CASTING_TEXT = "Сначала забрось."


def bag_full_text(capacity: int) -> str:
    return (
        f"🧺 Садок полон ({fishing.format_kg(capacity)}). "
        "Снасть осталась в воде - сходи продай улов."
    )


#: Классы веса для сорвавшейся рыбы. Вид НЕ называется намеренно: потерять то,
#: что почти держал в руках, интереснее, когда не знаешь наверняка, что ушло.
#: Строки короткие — обрыв случается часто; разница между ними только в
#: масштабе потери, и этого достаточно.
BREAK_TEXTS = [
    (0.00, "Леска лопнула. Мелочь."),
    (0.25, "Крючок разогнуло."),
    (0.70, "Леска не выдержала. Было что-то приличное."),
    (0.92, "Удилище согнуло дугой - и оборвало. Было что-то очень большое."),
    (0.99, "Снасть ушла в воду целиком. Ты даже не разглядел, что это было."),
]


def break_text(fraction: float) -> str:
    result = BREAK_TEXTS[0][1]
    for threshold, text in BREAK_TEXTS:
        if fraction >= threshold:
            result = text
    return result


def fishing_xp_line(character) -> str:
    from game.combat import display

    return display.craft_xp_line(
        "🎣", "Рыбалка", character.fishing_level, character.fishing_xp, fishing.xp_to_next(character.fishing_level),
    )


def catch_text(result, character=None) -> str:
    """Сообщение об удачной подсечке: строка улова, рекорд, опыт. Описание
    вида сюда НЕ попадает — его место в альманахе, а не в каждой поимке."""
    fish = result.fish
    emoji = fc.GRADE_EMOJI.get(result.grade_id, "")
    mark = f"{emoji} " if emoji else ""
    lines = [
        (
            f"{mark}{fish.emoji} {fish.name} - {fishing.format_kg(result.grams)} "
            f"({result.grade_label})"
        )
    ]
    if result.is_record:
        lines.append("📏 Личный рекорд!")
    lines.append(f"🎣 +{result.xp} опыта рыбалки")
    if result.levels_gained:
        lines.append(f"⬆️ Уровень рыбалки: {result.new_level}")
    if character is not None:
        lines.append(fishing_xp_line(character))
    return chr(10).join(lines)


DECIDE_FIRST_TEXT = "Сначала реши, что делать с уловом: в садок или обратно в воду."
NOTHING_TO_DECIDE_TEXT = "Решать уже нечего."
CATCH_GONE_TEXT = "Ты отошел от воды, и рыба уплыла."


def kept_line(decision) -> str:
    return f"🧺 {decision.fish.emoji} {decision.fish.name} ({fishing.format_kg(decision.grams)}) в садке."


def released_line(decision) -> str:
    return f"🐟 {decision.fish.name} уходит обратно в воду."


def bag_full_decide_text(capacity: int) -> str:
    return f"🧺 Садок полон ({fishing.format_kg(capacity)}). Эту рыбу можно только отпустить."


def junk_text(junk_id: str, character=None) -> str:
    from services import guild_service

    emoji, name, price = fc.JUNK_ITEMS[junk_id]
    label = guild_service.gold_label(character, price, "зол.") if character is not None else f"{price} зол."
    return f"{emoji} {name}. Продано за {label}"


def bag_screen(bag: list, grams: int, capacity: int, value: int) -> str:
    """Экран садка. Показывается стоимость СТАКА, не цена за килограмм:
    per-kg — внутреннее число калибровки, игроку оно ничего не говорит."""
    if not bag:
        return "🧺 Садок пуст." + chr(10) * 2 + bag_line(0, capacity)
    lines = ["🧺 САДОК", SEP]
    for definition, grade_id, stack_grams in bag:
        emoji = fc.GRADE_EMOJI.get(grade_id, "")
        mark = f"{emoji} " if emoji else ""
        label = fishing.grade_name(grade_id)
        price = fishing.price_of(definition.id, stack_grams, grade_id)
        lines.append(
            f"{mark}{definition.emoji} {definition.name} ({label}) - "
            f"{fishing.format_kg(stack_grams)} · {price} зол."
        )
    lines += [
        SEP,
        bag_line(grams, capacity),
        f"💰 Иргал даст за всё: {value} зол.",
        "Рыбак у воды в глубоких кольцах платит больше.",
    ]
    return chr(10).join(lines)



# --- Иллюстрации (фото в альбоме группы VK, патч 99) ---

#: Одна картинка на ТИР, а не на озеро: озёр двадцать семь, а тиров пять.
#: Своё поле image у места по-прежнему главнее - если однажды захочется
#: выделить особое место, картинка тира его не перебьёт (то же правило
#: наследования, что у мобов, патч 36).
#: Пустая строка - картинки ещё нет, сообщение уйдёт без вложения.
TIER_PHOTO_IDS: dict[int, str] = {
    1: "457239160",
    2: "457239161",
    3: "457239162",
    4: "457239163",
    5: "457239164",
}


def lake_attachment(lake: LakeDef) -> str | None:
    """Только ко входу к воде. Подсечка - повторяющееся действие, картинка
    там была бы шумом."""
    photo_id = lake.image or TIER_PHOTO_IDS.get(lake.tier)
    return photo_attachment(photo_id) if photo_id else None


# --- Пепельная донка (2026-10-23): авторыбалка из магазина ----------------------
DONKA_NAME = "Пепельная донка"
BTN_DONKA_ON = "🪝 Поставить донку"
BTN_DONKA_OFF = "🪝 Снять донку"
DONKA_ON_TEXT = (
    "🪝 Донка на дне. Тянет сама, но вчетверо медленнее, чем руками; "
    "рыба идёт прямо в садок. Работает час после твоего последнего действия, "
    "любое действие продлевает. Пока донка стоит, от воды не отойти."
)
DONKA_OFF_TEXT = "🪝 Донка смотана. Можно рыбачить руками или поставить её снова."
DONKA_BREAK_TEXT = "🪝 Донка: сорвалась."
DONKA_FULL_TEXT = "🪝 Садок полон - донка смотана."
DONKA_IDLE_TEXT = "🪝 Час без действий в игре - донку смотали."
DONKA_CHOICE_LINE = "🪝 Можно рыбачить самому или поставить донку."


def donka_catch_line(fish, grams: int, grade_label: str) -> str:
    return f"🪝 Донка: {fish.emoji} {fish.name}, {fishing.format_kg(grams)} ({grade_label}) - в садке."


def donka_xp_lines(result, character) -> str:
    """Опыт рыбалки с поклёвки донки: прибавка, новый уровень, шкала."""
    lines = [f"🎣 +{result.xp} опыта рыбалки"]
    if result.levels_gained:
        lines.append(f"⬆️ Уровень рыбалки: {result.new_level}")
    lines.append(fishing_xp_line(character))
    return chr(10).join(lines)
