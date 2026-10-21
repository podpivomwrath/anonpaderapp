"""/застрял: аварийный выход из зависшей активности (патч 25, п.5).

Перенесено из bot/handlers/world.py без изменений (2026-10-21, шаг 1
нарезки большого файла). Состояние мира (кто исследует, кто отдыхает)
по-прежнему живёт в world.py - здесь к нему обращаются через модуль, чтобы
копия была одна. Какие занятия снимает /застрял - bot/busy.py (ENDS_BY).
"""

from datetime import datetime, timezone

from vkbottle.bot import BotLabeler, Message

from bot import pending_activity
from bot.battle_keyboard import active_battle_keyboard
from bot.handlers import combat as combat_handlers
from bot.handlers import group_combat as group_combat_handlers
from bot.handlers import pvp as pvp_handlers
from bot.handlers import raid_combat as raid_combat_handlers
from models import MountTravel
from services import mining_service, mount_service, movement_service, screen_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра

STUCK_LINE = "Ты встряхиваешься и приходишь в себя."
STUCK_BATTLE_LINE = "Бой продолжается - кнопки обновлены."


async def force_unstick(db, character, peer_id: int, *, admin_override: bool = False) -> bool:
    """Аварийный выход из зависшей активности (патч 25, п.5). Общая логика
    /застрял и админского «Сбросить активности» — по умолчанию (admin_override=
    False, игрок сам себе жмёт /застрял) PvP НЕ прерывает (защита от абьюза),
    там только позволяет пересобрать боевую клавиатуру у вызывающего и
    возвращает True — вызывающий должен сам обработать этот случай отдельно,
    остальные состояния ниже в этом случае НЕ трогаются.

    admin_override=True (патч 39: bot/miniapp_admin_api.py, только с
    админ-панели) — снимает ВСЕ состояния без исключений, PvP включая: боец
    помечается погибшим в своём бою (pvp_handlers.force_defeat), а не
    блокирует сброс остального, как раньше (был баг — PvP-ветка делала
    ранний return ДО перемещения/маунта/исследования/отдыха, так что если
    что-то из этого тоже зависло одновременно с PvP, сброс не долечивал
    ничего). Возвращает False в этом режиме всегда — вызывающий не должен
    дополнительно ветвиться на PvP."""
    from bot.handlers import world  # лениво: world импортирует этот модуль у себя

    # Патч 37: /застрял всегда возвращает на корневой экран (город/карта) —
    # даже если PvP не даёт прервать сам бой, застрявший вложенный экран
    # (скупщик/лавка/инвентарь) сбрасывается.
    await screen_service.set_screen(db, character, None)
    # Добыча (2026-10-21): /застрял выносит из забоя - значит, и кирку бросает,
    # начатый кусок возвращается в жилу (как «Бросить кирку»).
    await mining_service.cancel_dig(db, character)
    # Ниже interrupt_for_pvp и маунт пишут строку персонажа СВОИМИ сессиями.
    # Пока эта держит её изменённой (экран, время активности), они ждали её
    # до таймаута базы - и /застрял сам застревал (2026-10-11, дважды).
    await db.commit()
    if (raid_combat_handlers.has_active_battle(peer_id)
            or group_combat_handlers.has_active_group_battle(peer_id)):
        return True  # restore the battle UI; never escape a raid via /stuck
    if pvp_handlers.rebuild_keyboard(peer_id) is not None:
        if not admin_override:
            return True
        pvp_handlers.force_defeat(peer_id)
    if combat_handlers.has_active_encounter(peer_id):
        # Игрок сам себе - бой НЕ прерывается (2026-10-13): безнаградный и
        # безштрафной аборт был лазейкой - проигрышный бой бросали через
        # /застрял. Вызывающий пересылает доску и боевые кнопки.
        if not admin_override:
            return True
        # Админ - безнаградный/безштрафной аборт, как прерывание PvE открытым PvP
        await combat_handlers.interrupt_for_pvp(peer_id)
        travel_id = combat_handlers.pop_mount_ambush(peer_id)
        if travel_id is not None:
            # бой-нападение прерван вручную — поездка не должна зависнуть в ambushed
            travel = await db.get(MountTravel, travel_id)
            if travel is not None:
                await mount_service.cancel_travel(db, travel)
    world._exploring.discard(peer_id)
    world._resting.discard(peer_id)
    # Запись в Redis снимается вместе с отметкой в памяти. Иначе сброшенный
    # отдых воскрес бы после следующего деплоя и вылечил бы бесплатно.
    await pending_activity.forget("explore", peer_id)
    await pending_activity.forget("rest", peer_id)
    now = datetime.now(timezone.utc)
    if movement_service.is_traveling(character, now):
        movement_service.cancel_travel(character)
    # Патч 39: отменяем ЛЮБОЙ активный статус маунт-поездки, не только
    # "traveling" — active_travel() возвращает и "ambushed" (нападение в
    # пути, чей бой потерян/прерван), а тот раньше не снимался ВООБЩЕ НИЧЕМ
    # (ни этой функцией, ни admin_service.reset_activity_db) — см. живой
    # баг игрока 24815750/char 15: кнопка маунта была заблокирована навсегда.
    active_mount_travel = await mount_service.active_travel(db, character.id)
    if active_mount_travel is not None:
        await mount_service.cancel_travel(db, active_mount_travel)
    return False


@labeler.message(text=["/застрял", "/stuck"])
async def stuck_command(message: Message) -> None:
    """Патч 25, п.5: аварийный выход из зависшей активности. PvP НЕ прерывает
    (защита от абьюза) — там только пересобирает боевую клавиатуру."""
    from bot.handlers import world  # лениво: world импортирует этот модуль у себя

    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if await force_unstick(db, character, peer_id):
            await db.commit()  # патч 37: сброс character.screen должен сохраниться и в PvP-ветке
            # В бою /застрял не выводит из боя, а обновляет его: доска и кнопки.
            board = combat_handlers.board_text(peer_id)
            text = f"{STUCK_BATTLE_LINE}\n\n{board}" if board else STUCK_BATTLE_LINE
            await message.answer(text, keyboard=active_battle_keyboard(peer_id))
            return
        now = datetime.now(timezone.utc)
        await db.commit()
        keyboard = await world._current_keyboard(db, character, peer_id, now)
    await message.answer(STUCK_LINE, keyboard=keyboard)
