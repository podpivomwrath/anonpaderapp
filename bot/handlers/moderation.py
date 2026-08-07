"""Админка, часть 1 и 3 (патч 27): бан-гейт на входе + /баг /bug в чате.

Бан проверяется middleware ДО любого хендлера (включая /start) — забаненный
получает только сообщение о блокировке. /баг доступен всем, но с антиспам-
лимитом (config.bug_report_max_per_hour); шлётся ЛС администратору форматным
сообщением + сохраняется в bug_reports.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from vkbottle import BaseMiddleware
from vkbottle.bot import BotLabeler, Message

from bot.battle_keyboard import active_battle_keyboard
from bot.handlers import world as world_handlers
from bot.onboarding_texts import REGION_TITLES
from config import get_settings
from models import Character, CharacterStats, User
from services import admin_service, item_service, movement_service, mount_service, vitals_service
from services import onboarding_service as onboarding_svc
from services import story_service
from services.db import get_session_factory

labeler = BotLabeler()

_bot_api = None

BUG_CONFIRM = "🐞 Репорт отправлен. Спасибо — Пепельные Земли станут чуть менее сломанными."
BUG_ASK_TEXT = "Опиши проблему: /баг <текст>"
BUG_RATE_LIMITED = "🐞 Reportов многовато за последний час — попробуй чуть позже."


def setup_middleware(bot) -> None:
    """Регистрирует бан-гейт РАНЬШЕ остальных middleware (main.create_bot,
    самым первым вызовом) — забаненный не должен доходить даже до /start."""
    bot.labeler.message_view.register_middleware(BanCheckMiddleware)


def setup(bot_api) -> None:
    global _bot_api
    _bot_api = bot_api


def ban_message(character: Character) -> str:
    lines = ["🚫 Доступ заблокирован администратором."]
    if character.ban_reason:
        lines.append(f"Причина: {character.ban_reason}")
    if character.banned_until is not None:
        lines.append(f"До: {character.banned_until.strftime('%d.%m.%Y %H:%M')} (МСК+0, UTC)")
    else:
        lines.append("Срок: бессрочно")
    return "\n".join(lines)


class BanCheckMiddleware(BaseMiddleware[Message]):
    """Проверка бана раньше ЛЮБОГО другого хендлера (патч 27, ч.1) — регистрируется
    первой в main.create_bot. Для незабаненных — no-op, не трогает БД дважды
    (не вызывает onboarding_service.get_character, чтобы не плодить побочные
    эффекты daily-rollover в одноразовой сессии без коммита)."""

    async def pre(self) -> None:
        async with get_session_factory()() as db:
            character = await db.scalar(
                select(Character)
                .join(User, User.id == Character.user_id)
                .where(User.vk_id == self.event.from_id, Character.creation_state.is_(None))
            )
            if character is not None and admin_service.is_ban_active(character):
                await self.event.answer(ban_message(character))
                self.stop("banned")


# --- /баг /bug ---


async def _build_snapshot(db, character: Character, peer_id: int) -> dict:
    """Автосбор состояния для репорта (часть 3, «что собирается автоматически»)."""
    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    gear_bonus = await item_service.compute_gear_bonus(db, character.id)
    vit_bonus = gear_bonus.get("vit", 0)
    max_hp = vitals_service.max_hp(character, stats, vit_bonus) if stats is not None else 0
    current_hp = vitals_service.current_hp(character, stats, vit_bonus) if stats is not None else 0
    hp_percent = round(100 * current_hp / max_hp) if max_hp else 0

    state = "в пути" if movement_service.is_traveling(character) else world_handlers.activity_state(peer_id)
    mount_travel = await mount_service.active_travel(db, character.id)
    if mount_travel is not None and mount_travel.status == "traveling":
        state = "в пути (маунт)"

    quest_line = await story_service.quest_summary_line(db, character)

    return {
        "name": character.name,
        "level": character.level,
        "class_title": admin_service.class_title(character),
        "region": REGION_TITLES.get(character.region, character.region) if character.region else "—",
        "pos_x": character.pos_x,
        "pos_y": character.pos_y,
        "state": state,
        "quest": quest_line,
        "hp_percent": hp_percent,
        "unspent_points": stats.unspent_points if stats is not None else 0,
    }


def _format_report(report_id: int, vk_id: int, snapshot: dict, text: str, sent_at: datetime) -> str:
    lines = [
        f"🐞 РЕПОРТ #{report_id}",
        "",
        f"От: {snapshot['name']} (vk_id {vk_id})",
        f"Уровень {snapshot['level']} · {snapshot['class_title']} · {snapshot['region']}",
        f"Позиция: ({snapshot['pos_x']}; {snapshot['pos_y']}) · состояние: {snapshot['state']}",
    ]
    if snapshot["quest"]:
        lines.append(f"Квест: {snapshot['quest']}")
    lines.append(f"HP: {snapshot['hp_percent']}%")
    lines.append("")
    lines.append("Текст:")
    lines.append(text)
    lines.append("")
    lines.append(f"⏱ {sent_at.strftime('%d.%m.%Y %H:%M')}")
    return "\n".join(lines)


@labeler.message(text=["/баг <text>", "/bug <text>"])
async def bug_report_with_text(message: Message, text: str) -> None:
    await _handle_bug_report(message, text.strip())


@labeler.message(text=["/баг", "/bug"])
async def bug_report_no_text(message: Message) -> None:
    # Патч 30, баг 2: справочные команды не должны стирать боевую клавиатуру.
    await message.answer(BUG_ASK_TEXT, keyboard=active_battle_keyboard(message.peer_id))


async def _handle_bug_report(message: Message, text: str) -> None:
    peer_id = message.peer_id
    if not text:
        await message.answer(BUG_ASK_TEXT, keyboard=active_battle_keyboard(peer_id))
        return
    async with get_session_factory()() as db:
        character = await onboarding_svc.get_character(db, message.from_id)
        if character is None or character.creation_state is not None:
            return
        settings = get_settings()
        since_limit = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = await admin_service.bug_reports_since(db, character.id, since_limit)
        if recent >= settings.bug_report_max_per_hour:
            await db.commit()
            await message.answer(BUG_RATE_LIMITED, keyboard=active_battle_keyboard(peer_id))
            return

        # Патч 30, баг 1, исправление 3: тот же текст от того же игрока за
        # последние 30 сек — не плодим вторую запись (ретрай VK/двойной тап),
        # но подтверждение всё равно отправляем как обычно.
        since_dup = datetime.now(timezone.utc) - timedelta(seconds=30)
        duplicate = await admin_service.duplicate_bug_report(db, character.id, text, since_dup)
        if duplicate is not None:
            await db.commit()
            await message.answer(BUG_CONFIRM, keyboard=active_battle_keyboard(peer_id))
            return

        snapshot = await _build_snapshot(db, character, peer_id)
        snapshot["vk_id"] = message.from_id
        report = await admin_service.create_bug_report(db, character.id, text, snapshot)
        await db.commit()
        report_id = report.id

    formatted = _format_report(report_id, message.from_id, snapshot, text, datetime.now(timezone.utc))
    settings = get_settings()
    if settings.admin_vk_id and _bot_api is not None:
        try:
            await _bot_api.messages.send(peer_id=settings.admin_vk_id, message=formatted, random_id=0)
        except Exception:
            from loguru import logger
            logger.exception("Не удалось отправить репорт бага #{} администратору", report_id)

    await message.answer(BUG_CONFIRM, keyboard=active_battle_keyboard(peer_id))
