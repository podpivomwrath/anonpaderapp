"""Травничество в чате (2026-10-21): «здесь растёт ...» с кнопкой «Собрать».

Заметка приходит при входе на клетку (world.send_cell_buttons) и после
каждого исследования - под сводкой локации, пока траву никто не сорвал.
Логика - services/herb_service.py.
"""

import random

from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot.battle_keyboard import in_any_battle
from bot import dailies_texts
from services import daily_service, death_service, herb_service, movement_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
labeler.vbml_ignore_case = True  # команды без учёта регистра

BTN_PICK = "🌿 Собрать"
_rng = random.Random()


def _api():
    from bot.handlers import world as world_handlers  # избегаем цикла импортов

    return world_handlers._bot_api


def pick_keyboard(patch_id: int) -> str:
    kb = Keyboard(inline=True)
    kb.add(Text(BTN_PICK, payload={"type": "herb_pick", "id": patch_id}), color=KeyboardButtonColor.POSITIVE)
    return kb.get_json()


async def notify(peer_id: int, character) -> None:
    """Если на клетке трава, которую персонаж различает, - сказать об этом.
    С серпом нужного тира трава срезается сама (2026-10-23)."""
    from game.economy import craft_gear
    from services import craft_gear_service

    async with get_session_factory()() as db:
        found = await herb_service.visible_here(db, character)
        if found is None:
            return
        patch, herb = found
        sickle = await craft_gear_service.tier(db, character.id, "sickle")
    if craft_gear.sickle_cuts(sickle, herb.tier) and not in_any_battle(peer_id):
        # Фоном, а не здесь: notify зовут и изнутри открытой сессии, где строка
        # персонажа ещё не закоммичена. Срезание пишет опыт в ту же строку и
        # ждало бы её, а вызывающий - срезание (memory: nested-session-deadlock).
        from bot import background

        background.spawn(_auto_cut(peer_id, character.id, patch.id))
        return
    await _api().messages.send(
        peer_id=peer_id, random_id=0,
        message=f"{herb.emoji} Здесь растет {herb.name}.",
        keyboard=pick_keyboard(patch.id),
    )


async def _auto_cut(peer_id: int, character_id: int, patch_id: int) -> None:
    """Серп срезает траву (2026-10-23): своя сессия, после вызывающего."""
    from models import Character

    async with get_session_factory()() as db:
        character = await db.get(Character, character_id)
        if character is None:
            return
        result = await herb_service.pick(db, character, patch_id, _rng)
        if result.status != "ok":
            await db.rollback()
            return
        progress = await daily_service.record_craft(db, character, "herb_pick")
        await db.commit()
        text = "🌙 Серп срезал траву.\n" + picked_text(result, character)
    await _api().messages.send(peer_id=peer_id, random_id=0, message=text)
    notice = dailies_texts.progress_notice(progress) if progress is not None else None
    if notice:
        await _api().messages.send(peer_id=peer_id, random_id=0, message=notice)


#: Север - рост y (Кряж на (0;30)).
_SIDES = {
    (-1, 1): "северо-запад", (0, 1): "север", (1, 1): "северо-восток",
    (-1, 0): "запад", (1, 0): "восток",
    (-1, -1): "юго-запад", (0, -1): "юг", (1, -1): "юго-восток",
}


async def notify_nearby(peer_id: int, character) -> None:
    """Альманах травника (2026-10-23): трава на соседних клетках, включая
    диагональные. Только при входе на клетку - одна строка на всё."""
    from services import craft_gear_service

    async with get_session_factory()() as db:
        found = await herb_service.visible_around(db, character)
        # Только отмеченная в мини-аппе трава (2026-10-29, владелец).
        wanted = await craft_gear_service.almanac_filter(db, character.id) if found else None
        if wanted is not None:
            found = [(d, h) for d, h in found if h.id in wanted]
        # 10 подсказок, потом час зарядки (2026-10-29). Тратит подсказку только
        # найденная трава, а не пустая клетка.
        uses = await craft_gear_service.almanac_use(db, character.id) if found else None
        if uses is None:
            return
        await db.commit()
    parts = [f"{herb.emoji} {herb.name} - {_SIDES[(dx, dy)]}" for (dx, dy), herb in found]
    left, total = uses
    from game.economy import craft_gear_config as gc

    tail = (f"Подсказок до зарядки: {left} из {total}." if left
            else f"Это была последняя подсказка: альманах заряжается {gc.ALMANAC_CHARGE_MINUTES} мин.")
    await _api().messages.send(
        peer_id=peer_id, random_id=0, message="📗 Альманах: рядом трава.\n" + "\n".join(parts) + "\n" + tail,
    )


def picked_text(result, character=None) -> str:
    herb = result.herb
    bunches = {1: "пучок", 2: "два пучка", 3: "три пучка"}.get(result.amount, f"{result.amount} пучков")
    text = f"{herb.emoji} {herb.name}: {bunches} в сумке травника. Травничество +{result.xp} опыта."
    if result.level_after > result.level_before:
        text += f"\n🌿 Травничество: {result.level_after} уровень."
    if result.unlocked:
        text += "\nТеперь ты различаешь новые травы: " + ", ".join(h.name for h in result.unlocked) + "."
    if character is not None:
        from game.combat import display
        from game.economy import herbalism

        text += "\n" + display.craft_xp_line(
            "🌿", "Травничество", character.herbalism_level, character.herbalism_xp,
            herbalism.xp_to_next(character.herbalism_level),
        )
    return text


REFUSALS = {
    "gone": "🌿 Пусто: траву уже сорвали.",
    "elsewhere": "🌿 Ты уже ушел с той клетки.",
    "unseen": "🌿 Пусто: траву уже сорвали.",
}


@labeler.message(payload_contains={"type": "herb_pick"})
async def pick_herb(message: Message) -> None:
    payload = message.get_payload_json() or {}
    patch_id = payload.get("id")
    if not isinstance(patch_id, int):
        return
    if in_any_battle(message.peer_id):
        await message.answer("⚔️ Сначала бой.")
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if death_service.is_dead(character) or movement_service.is_traveling(character):
            await message.answer(REFUSALS["elsewhere"])
            return
        result = await herb_service.pick(db, character, patch_id, _rng)
        progress = await daily_service.record_craft(db, character, "herb_pick") if result.status == "ok" else None
        await db.commit()
    await message.answer(picked_text(result, character) if result.status == "ok" else REFUSALS[result.status])
    notice = dailies_texts.progress_notice(progress) if progress is not None else None
    if notice:
        await message.answer(notice)
