"""Пресеты баффов в чате (патч 14, ч.3): команды /пресет N, /preset N, и
кнопка [⚔️ Пресеты] со списком (окно редактируется на месте, патч 13, ч.1).

Переключение — всегда бесплатно и мгновенно (см. services/preset_service.py);
недоступно во время боя и до выбора подкласса."""

from sqlalchemy import select
from vkbottle.bot import BotLabeler, Message

from bot import editable_message
from bot.handlers import combat as combat_handlers
from bot.keyboards.presets import BTN_PRESETS, no_keyboard, presets_list_keyboard
from game.content_loader import load_content
from models import CharacterBuffPreset
from services import onboarding_service as onboarding_svc
from services import preset_service
from services.preset_service import PresetValidationError
from services.db import get_session_factory

labeler = BotLabeler()

_NS = "presets"
_bot_api = None

NO_SUBCLASS_TEXT = "Твоя Метка ещё не обрела форму — пресеты недоступны."
IN_COMBAT_TEXT = "Не сейчас. Кровь занята другим."


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


async def _ordered_presets(db, character_id: int) -> list[CharacterBuffPreset]:
    return (
        await db.scalars(
            select(CharacterBuffPreset)
            .where(CharacterBuffPreset.character_id == character_id)
            .order_by(CharacterBuffPreset.id)
        )
    ).all()


def _list_text(presets: list[CharacterBuffPreset]) -> str:
    if not presets:
        return "⚔️ Пресетов пока нет. Собери первый в разделе «Персонаж» мини-аппа."
    lines = ["⚔️ Пресеты:", ""]
    for idx, preset in enumerate(presets, start=1):
        mark = "✅" if preset.is_active else "▫️"
        lines.append(f"{mark} {idx}. {preset.name}")
    return "\n".join(lines)


def _summary_text(index: int, preset: CharacterBuffPreset, catalog: dict) -> str:
    lines = [f"✨ Активен пресет {index}: «{preset.name}»"]
    for buff_id in preset.buff_ids:
        buff = catalog.get(buff_id)
        lines.append(f"· {buff.name if buff else buff_id}")
    return "\n".join(lines)


@labeler.message(text=[BTN_PRESETS])
async def open_presets(message: Message) -> None:
    peer_id = message.peer_id
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if character.subclass is None:
            await message.answer(NO_SUBCLASS_TEXT)
            return
        presets = await _ordered_presets(db, character.id)

    if not presets:
        await editable_message.send_or_edit(_bot_api, _NS, peer_id, _list_text(presets), no_keyboard())
        return
    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, _list_text(presets), presets_list_keyboard(presets)
    )


@labeler.message(payload_contains={"type": "preset_switch"})
async def switch_preset_button(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    preset_id = payload.get("id")
    if not isinstance(preset_id, int):
        return
    if combat_handlers.has_active_encounter(peer_id):
        await message.answer(IN_COMBAT_TEXT)
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        try:
            await preset_service.switch_active_preset(db, character.id, preset_id)
        except PresetValidationError:
            return
        await db.commit()
        presets = await _ordered_presets(db, character.id)

    await editable_message.send_or_edit(
        _bot_api, _NS, peer_id, _list_text(presets), presets_list_keyboard(presets)
    )


@labeler.message(text=["/пресет <n:int>", "/preset <n:int>"])
async def switch_preset_command(message: Message, n: int) -> None:
    peer_id = message.peer_id
    if combat_handlers.has_active_encounter(peer_id):
        await message.answer(IN_COMBAT_TEXT)
        return

    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        if character.subclass is None:
            await message.answer(NO_SUBCLASS_TEXT)
            return

        presets = await _ordered_presets(db, character.id)
        if n < 1 or n > len(presets):
            await message.answer(f"Пресет {n} пуст. Собери его в разделе «Персонаж».")
            return

        target = presets[n - 1]
        try:
            await preset_service.switch_active_preset(db, character.id, target.id)
        except PresetValidationError:
            await message.answer(f"Пресет {n} пуст. Собери его в разделе «Персонаж».")
            return
        await db.commit()
        catalog = load_content().buffs
        text = _summary_text(n, target, catalog)

    await message.answer(text)
