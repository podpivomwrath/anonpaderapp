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
    """"🌑 " (Клеймо) или "💠 " (Метка) перед ником, иначе пустая строка —
    единая точка для всех мест отображения (Осмотреться, топ PvP, профиль,
    карточка админки). Оба сразу - видно старшее, Клеймо."""
    return badge_of(getattr(character, "brand_until", None), character.premium_until, now)


def badge_of(brand_until: datetime | None, premium_until: datetime | None, now: datetime | None = None) -> str:
    """То же по голым срокам - для топов, где строки читаются колонками."""
    from game.economy import brand_config as bc

    now = now or datetime.now(timezone.utc)
    if brand_until is not None and brand_until > now:
        return f"{bc.BRAND_BADGE} "
    if premium_until is not None and premium_until > now:
        return f"{pc.PREMIUM_BADGE} "
    return ""


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
    идемпотентно (за счёт premium_warn_sent/premium_expire_notified и тех же
    флагов Клейма) отдаёт строку уведомления (Метка и Клеймо - через перевод
    строки), если пора, иначе None. Мутирует character —
    вызывающий обязан сохранить изменение в БД (обычная db.flush()/commit())."""
    now = now or datetime.now(timezone.utc)
    lines = [line for line in (_premium_notice(character, now), _brand_notice(character, now)) if line]
    return "\n".join(lines) or None


def _premium_notice(character: Character, now: datetime) -> str | None:
    if character.premium_until is None:
        return None
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


# --- Клеймо Хранителя (2026-11-06) -------------------------------------------


def is_brand(character: Character, now: datetime | None = None) -> bool:
    """Клеймо Хранителя активно. Единая проверка, как is_premium."""
    until = getattr(character, "brand_until", None)
    if until is None:
        return False
    return until > (now or datetime.now(timezone.utc))


def big_key_cap(character: Character, now: datetime | None = None) -> bool:
    """Ключей Монолита до 4 и лишний слот пресета: Клеймо - или Метка,
    активная в день переноса этих бонусов, до конца её срока."""
    if is_brand(character, now):
        return True
    legacy = getattr(character, "legacy_perks_until", None)
    return legacy is not None and legacy > (now or datetime.now(timezone.utc)) and is_premium(character, now)


def extend_brand(character: Character, days: int, now: datetime | None = None) -> None:
    """Продление Клейма - срок складывается с оставшимся, как у Метки."""
    now = now or datetime.now(timezone.utc)
    base = character.brand_until if is_brand(character, now) else now
    character.brand_until = base + timedelta(days=days)
    character.brand_warn_sent = False
    character.brand_expire_notified = False


def _brand_notice(character: Character, now: datetime) -> str | None:
    from game.economy import brand_config as bc

    until = getattr(character, "brand_until", None)
    if until is None:
        return None
    if until > now:
        if not character.brand_warn_sent and until - now <= timedelta(days=bc.EXPIRY_WARNING_DAYS):
            character.brand_warn_sent = True
            return bc.EXPIRY_WARNING_TEXT
        return None
    if not character.brand_expire_notified:
        character.brand_expire_notified = True
        return bc.EXPIRED_TEXT
    return None
