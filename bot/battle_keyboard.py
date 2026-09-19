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
    from bot.handlers import group_combat, raid_combat

    for handler in (raid_combat, group_combat, pvp_handlers, combat_handlers):
        kb = handler.rebuild_keyboard(peer_id)
        if kb is not None:
            return kb
    return None


def in_any_battle(peer_id: int) -> bool:
    from bot.handlers import combat as combat_handlers
    from bot.handlers import pvp as pvp_handlers
    from bot.handlers import group_combat, raid_combat

    return (raid_combat.has_active_battle(peer_id) or group_combat.has_active_group_battle(peer_id)
            or pvp_handlers.has_active_battle(peer_id) or combat_handlers.has_active_encounter(peer_id))


async def answer_battle_gone(message) -> None:
    """Ответ на кнопку боя, которого в памяти процесса больше нет.

    Реестры боёв живут ТОЛЬКО в памяти (см. bot/handlers/raid_combat.py,
    pvp.py): рестарт бота, аварийное завершение рейда или возврат ключа
    стирают их, а клавиатура у игрока на экране остаётся. Дальше он жмёт её
    кнопки, хендлер не находит бой и молча выходит - не касаясь даже БД.
    Снаружи это неотличимо от мёртвого бота: именно так игрок и застрял на
    проде после одного из деплоев.

    Поэтому молчать нельзя НИКОГДА: отвечаем и обязательно прикладываем
    клавиатуру текущего состояния, иначе мёртвые кнопки останутся висеть.
    """
    from datetime import datetime, timezone

    from bot.handlers import world as world_handlers
    from services import onboarding_service
    from services.db import get_session_factory

    async with get_session_factory()() as db:
        character = await onboarding_service.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        keyboard = await world_handlers._current_keyboard(
            db, character, message.peer_id, datetime.now(timezone.utc)
        )
    await message.answer(
        "Этого боя больше нет - он закончился или прервался. Возвращаю к текущему состоянию.",
        keyboard=keyboard,
    )
