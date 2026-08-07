"""Единая точка получения актуальной боевой клавиатуры (патч 30, баг 2).

Правило: пока бой активен, ЛЮБОЕ сообщение игроку обязано нести актуальную
боевую клавиатуру — иначе сообщение без клавиатуры (эффект зелья, ответ на
/баг, /профиль, /ежедневки и т.д.) вытесняет уже показанные боевые кнопки, и
игрок оказывается заперт в бою без возможности сходить. Единственное
исключение — сообщения, ЗАВЕРШАЮЩИЕ бой (победа/поражение/ничья): там
клавиатура намеренно не прикрепляется (см. bot/handlers/combat.py, патч 7).

Использование в любом хендлере вне combat.py/pvp.py:
    kb = active_battle_keyboard(peer_id)
    await message.answer(text, keyboard=kb if kb is not None else <обычная клавиатура>)

Импорты combat.py/pvp.py — ЛЕНИВЫЕ (внутри функций), не на уровне модуля:
bot/handlers/__init__.py эагерно импортирует ВСЕ хендлеры (включая
basic.py/moderation.py/dailies.py/world.py, которые импортируют этот модуль)
для сборки LABELERS — модульный импорт combat.py/pvp.py отсюда столкнул бы
их обратно с этим же модулем, ещё не успевшим доинициализироваться."""


def active_battle_keyboard(peer_id: int) -> str | None:
    """None — peer_id сейчас не в бою (ни PvE, ни PvP); иначе — актуальная
    клавиатура того боя, в котором он участвует. PvP проверяется первым:
    в отличие от PvE-энкаунтера, PvP-бой нельзя прервать сторонним
    действием, так что если игрок одновременно числится и там, и там
    (быть не должно, но на всякий случай) — приоритет у того боя, из
    которого нет аварийного выхода."""
    from bot.handlers import combat as combat_handlers
    from bot.handlers import pvp as pvp_handlers

    kb = pvp_handlers.rebuild_keyboard(peer_id)
    if kb is not None:
        return kb
    return combat_handlers.rebuild_keyboard(peer_id)


def in_any_battle(peer_id: int) -> bool:
    from bot.handlers import combat as combat_handlers
    from bot.handlers import pvp as pvp_handlers

    return pvp_handlers.has_active_battle(peer_id) or combat_handlers.has_active_encounter(peer_id)
