"""Метка Хранителя — премиум-аккаунт (патч 50).

Единая точка проверки/продления/уведомлений — вся остальная логика (опыт,
редкость лута, ключи рейда, слоты пресетов, отдых, ежедневки, бейдж) читает
ТОЛЬКО is_premium(character) отсюда, не дублирует сравнение premium_until
по коду (иначе при изменении логики истечения часть бонусов молча отвалится).
"""

from datetime import datetime, timedelta, timezone

from game.economy import premium_config as pc
from models import Character


def is_premium(character: Character, now: datetime | None = None) -> bool:
    if character.premium_until is None:
        return False
    now = now or datetime.now(timezone.utc)
    return character.premium_until > now


def badge(character: Character, now: datetime | None = None) -> str:
    """"💠 " перед ником, иначе пустая строка — единая точка для всех мест
    отображения (Осмотреться, топ PvP, профиль, карточка админки)."""
    return f"{pc.PREMIUM_BADGE} " if is_premium(character, now) else ""


def extend(character: Character, days: int, now: datetime | None = None) -> None:
    """Продление/выдача — срок СУММИРУЕТСЯ с уже оставшимся (не заменяет).
    Сбрасывает флаги разовых уведомлений — на новый срок они должны сработать
    заново."""
    now = now or datetime.now(timezone.utc)
    base = character.premium_until if character.premium_until is not None and character.premium_until > now else now
    character.premium_until = base + timedelta(days=days)
    character.premium_warn_sent = False
    character.premium_expire_notified = False


def check_expiry_notice(character: Character, now: datetime | None = None) -> str | None:
    """Вызывается из services/onboarding_service.py::get_character (та же
    точка входа "на следующее действие игрока", что и ежедневный ролловер) —
    идемпотентно (за счёт premium_warn_sent/premium_expire_notified) отдаёт
    ОДНУ строку уведомления, если пора, иначе None. Мутирует character —
    вызывающий обязан сохранить изменение в БД (обычная db.flush()/commit())."""
    if character.premium_until is None:
        return None
    now = now or datetime.now(timezone.utc)
    if character.premium_until > now:
        remaining = character.premium_until - now
        if not character.premium_warn_sent and remaining <= timedelta(days=pc.EXPIRY_WARNING_DAYS):
            character.premium_warn_sent = True
            return pc.EXPIRY_WARNING_TEXT
        return None
    if not character.premium_expire_notified:
        character.premium_expire_notified = True
        return pc.EXPIRED_TEXT
    return None
