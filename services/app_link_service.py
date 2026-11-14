"""Привязка приложения «Монолит» к персонажу (2026-11-15, владелец).

1. Мини-апп: «Авторизовать приложение» -> create_code(): код XXXX-XXXX на
   PAIR_CODE_SECONDS, у игрока один код, новый заменяет старый.
2. Приложение: pair(код, имя устройства, платформа) -> постоянный ключ
   устройства. Код сгорает сразу.
3. Дальше приложение шлёт ключ в Authorization: Bearer, и bot/miniapp_auth.py
   пускает его во все /api/miniapp/* как этого игрока (device_for_token).
4. Мини-апп показывает устройства и отключает любое (revoke).

В базе только SHA-256 кода и ключа. Перебор кода: 31^8 ≈ 8.5·10^11
вариантов на 10 минут, неверная попытка ещё и ждёт (bot/app_api.py).
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import AppDevice, AppPairCode, Character, User

PAIR_CODE_SECONDS = 10 * 60
#: Без 0/O, 1/I/L: код переписывают с экрана руками.
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LENGTH = 8
TOKEN_PREFIX = "app1."
#: Сколько устройств подключено одновременно. Больше - отключить старое.
MAX_DEVICES = 5
#: last_seen_at обновляется не чаще: иначе запись в базу на каждый запрос.
SEEN_EVERY = timedelta(minutes=10)
PLATFORMS = ("windows", "android")
NAME_MAX = 48


class AppLinkError(Exception):
    """code: bad_code | too_many_devices | bad_platform | no_character."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Paired:
    token: str
    device: AppDevice
    character_name: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_code(raw: str) -> str:
    """Как ни ввёл: строчными, с дефисом, пробелами - сравниваем по буквам."""
    return "".join(ch for ch in str(raw).upper() if ch.isalnum())


def format_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}"


async def create_code(db: AsyncSession, user: User, now: datetime | None = None) -> tuple[str, datetime]:
    now = now or _now()
    character = await db.scalar(select(Character).where(Character.user_id == user.id))
    if character is None or character.creation_state is not None:
        raise AppLinkError("no_character")
    await db.execute(delete(AppPairCode).where(AppPairCode.user_id == user.id))
    code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
    expires = now + timedelta(seconds=PAIR_CODE_SECONDS)
    db.add(AppPairCode(code_hash=_hash(code), user_id=user.id, expires_at=expires))
    await db.flush()
    return format_code(code), expires


async def active_devices(db: AsyncSession, user_id: int) -> list[AppDevice]:
    return list((await db.scalars(
        select(AppDevice).where(AppDevice.user_id == user_id, AppDevice.revoked_at.is_(None))
        .order_by(AppDevice.id)
    )).all())


async def pair(db: AsyncSession, raw_code: str, name: str, platform: str, now: datetime | None = None) -> Paired:
    now = now or _now()
    if platform not in PLATFORMS:
        raise AppLinkError("bad_platform")
    code = normalize_code(raw_code)
    if len(code) != CODE_LENGTH:
        raise AppLinkError("bad_code")
    row = await db.get(AppPairCode, _hash(code))
    if row is None:
        raise AppLinkError("bad_code")
    if _aware(row.expires_at) < now:
        await db.delete(row)
        await db.flush()
        raise AppLinkError("bad_code")
    character = await db.scalar(select(Character).where(Character.user_id == row.user_id))
    if character is None:
        raise AppLinkError("no_character")
    # Лимит - до сжигания кода: отключил старое устройство - тот же код подойдёт.
    if len(await active_devices(db, row.user_id)) >= MAX_DEVICES:
        raise AppLinkError("too_many_devices")
    await db.delete(row)  # одноразовый
    await db.flush()
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    clean_name = " ".join(str(name or "").split())[:NAME_MAX] or ("ПК" if platform == "windows" else "Телефон")
    device = AppDevice(user_id=row.user_id, token_hash=_hash(token), name=clean_name, platform=platform,
                       created_at=now, last_seen_at=now)
    db.add(device)
    await db.flush()
    return Paired(token=token, device=device, character_name=character.name)


def is_app_token(token: str) -> bool:
    return token.startswith(TOKEN_PREFIX)


async def device_for_token(db: AsyncSession, token: str, now: datetime | None = None) -> tuple[AppDevice, int] | None:
    """(устройство, vk_id) по ключу или None, если ключа нет или он отключён."""
    if not is_app_token(token):
        return None
    row = (await db.execute(
        select(AppDevice, User.vk_id).join(User, User.id == AppDevice.user_id)
        .where(AppDevice.token_hash == _hash(token))
    )).first()
    if row is None or row[0].revoked_at is not None:
        return None
    device, vk_id = row
    now = now or _now()
    seen = _aware(device.last_seen_at)
    if seen is None or now - seen >= SEEN_EVERY:
        device.last_seen_at = now
        await db.commit()
    return device, vk_id


async def revoke(db: AsyncSession, user_id: int, device_id: int, now: datetime | None = None) -> bool:
    device = await db.get(AppDevice, device_id)
    if device is None or device.user_id != user_id or device.revoked_at is not None:
        return False
    device.revoked_at = now or _now()
    await db.flush()
    return True


def device_view(device: AppDevice, current_id: int | None = None) -> dict:
    return {
        "id": device.id, "name": device.name, "platform": device.platform,
        "created_at": _aware(device.created_at).timestamp() if device.created_at else None,
        "last_seen_at": _aware(device.last_seen_at).timestamp() if device.last_seen_at else None,
        "current": device.id == current_id,
    }
