"""Травничество в чате (2026-10-21): «здесь растёт ...» с кнопкой «Собрать».

Заметка приходит при входе на клетку (world.send_cell_buttons) и после
каждого исследования - под сводкой локации, пока траву никто не сорвал.
Логика - services/herb_service.py.
"""

import random

from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message

from bot.battle_keyboard import in_any_battle
from services import death_service, herb_service, movement_service
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
    """Если на клетке трава, которую персонаж различает, - сказать об этом."""
    async with get_session_factory()() as db:
        found = await herb_service.visible_here(db, character)
    if found is None:
        return
    patch, herb = found
    await _api().messages.send(
        peer_id=peer_id, random_id=0,
        message=f"{herb.emoji} Здесь растет {herb.name}.",
        keyboard=pick_keyboard(patch.id),
    )


def picked_text(result) -> str:
    herb = result.herb
    bunches = "два пучка" if result.amount == 2 else "пучок"
    text = f"{herb.emoji} {herb.name}: {bunches} в сумке травника. Травничество +{result.xp} опыта."
    if result.level_after > result.level_before:
        text += f"\n🌿 Травничество: {result.level_after} уровень."
    if result.unlocked:
        text += "\nТеперь ты различаешь новые травы: " + ", ".join(h.name for h in result.unlocked) + "."
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
        await db.commit()
    await message.answer(picked_text(result) if result.status == "ok" else REFUSALS[result.status])
