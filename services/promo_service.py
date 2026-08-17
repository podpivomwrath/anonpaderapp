"""Промокоды (патч 50): создание/удаление (админ), активация (игрок текстом
в чате — bot/handlers/promo.py).

Награды — список позиций [{"type": ..., ...}] — допускает несколько разных
позиций в одном коде (в отличие от services/daily_service.py::_grant_reward,
который допускает только по одной штуке каждого вида на исход)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.economy import raid_key_config as rc
from models import Character, CharacterStats, PromoActivation, PromoCode
from services import (
    admin_service,
    elixir_service,
    experience_service,
    mount_service,
    premium_service,
    trophy_service,
    wallet_service,
)


def normalize_code(raw: str) -> str:
    return raw.strip().lower()


class PromoValidationError(Exception):
    """Код не может быть создан/удалён так, как запрошено."""


# --- Админ: создание/удаление/просмотр ---


async def create_code(
    db: AsyncSession,
    admin_vk_id: int,
    code: str,
    rewards: list[dict],
    max_activations: int | None,
    one_per_player: bool,
    expires_at: datetime | None,
) -> PromoCode:
    normalized = normalize_code(code)
    if not normalized:
        raise PromoValidationError("Код не может быть пустым")
    existing = await db.scalar(select(PromoCode).where(PromoCode.code == normalized))
    if existing is not None:
        raise PromoValidationError("Такой код уже существует")
    if not rewards:
        raise PromoValidationError("Нужна хотя бы одна награда")
    promo = PromoCode(
        code=normalized, rewards=rewards, max_activations=max_activations,
        one_per_player=one_per_player, expires_at=expires_at, created_by=admin_vk_id,
    )
    db.add(promo)
    await db.flush()
    await admin_service.log_action(
        db, admin_vk_id, "create_promo_code", None,
        new_value={"code": normalized, "rewards": rewards, "max_activations": max_activations},
        note=normalized,
    )
    return promo


async def delete_code(db: AsyncSession, admin_vk_id: int, promo_code_id: int) -> bool:
    promo = await db.get(PromoCode, promo_code_id)
    if promo is None:
        return False
    await admin_service.log_action(
        db, admin_vk_id, "delete_promo_code", None, old_value={"code": promo.code}, note=promo.code,
    )
    await db.delete(promo)
    await db.flush()
    return True


@dataclass
class PromoCodeOverview:
    id: int
    code: str
    rewards: list
    max_activations: int | None
    one_per_player: bool
    expires_at: datetime | None
    created_at: datetime
    activation_count: int


async def list_codes(db: AsyncSession) -> list[PromoCodeOverview]:
    codes = (await db.scalars(select(PromoCode).order_by(PromoCode.created_at.desc()))).all()
    result = []
    for promo in codes:
        count = await db.scalar(
            select(func.count()).select_from(PromoActivation).where(PromoActivation.promo_code_id == promo.id)
        )
        result.append(
            PromoCodeOverview(
                id=promo.id, code=promo.code, rewards=promo.rewards,
                max_activations=promo.max_activations, one_per_player=promo.one_per_player,
                expires_at=promo.expires_at, created_at=promo.created_at, activation_count=count or 0,
            )
        )
    return result


@dataclass
class PromoActivationEntry:
    character_id: int
    character_name: str
    activated_at: datetime


async def code_activations(db: AsyncSession, promo_code_id: int) -> list[PromoActivationEntry]:
    rows = (
        await db.execute(
            select(PromoActivation, Character.name)
            .join(Character, Character.id == PromoActivation.character_id)
            .where(PromoActivation.promo_code_id == promo_code_id)
            .order_by(PromoActivation.activated_at.desc())
        )
    ).all()
    return [
        PromoActivationEntry(character_id=a.character_id, character_name=name, activated_at=a.activated_at)
        for a, name in rows
    ]


# --- Игрок: активация текстом в чате ---


@dataclass
class ActivationOutcome:
    status: str  # "success" | "already_used" | "limit_reached" | "expired"
    lines: list[str] = field(default_factory=list)  # только для "success"


STATUS_TEXTS = {
    "already_used": "Ты уже воспользовался этим кодом.",
    "limit_reached": "Этот код больше не действует.",
    "expired": "Этот код истёк.",
}


async def _apply_reward(db: AsyncSession, character: Character, reward: dict) -> str | None:
    """Одна позиция награды → строка для игрока, либо None (не начислено —
    сама строка с объяснением уже добавлена внутри для пограничных случаев)."""
    rtype = reward.get("type")
    if rtype == "gold":
        amount = int(reward.get("amount", 0))
        if amount <= 0:
            return None
        await wallet_service.deposit(db, character.id, "farm", amount)
        return f"{amount} золота"
    if rtype == "gems":
        amount = int(reward.get("amount", 0))
        if amount <= 0:
            return None
        await wallet_service.deposit(db, character.id, "donate", amount)
        return f"💎 {amount} Пепельных самоцветов"
    if rtype == "xp":
        amount = int(reward.get("amount", 0))
        if amount <= 0:
            return None
        if character.level >= bc.MAX_LEVEL:
            return "Опыт не начислен — достигнут максимальный уровень."
        stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
        experience_service.add_experience(character, stats, amount)
        return f"{amount} опыта"
    if rtype == "trophy":
        trophy_id = reward.get("trophy_id")
        amount = int(reward.get("amount", 0))
        if not trophy_id or amount <= 0:
            return None
        tdef = trophy_service.trophy_def(trophy_id)
        await trophy_service.grant_specific(db, character.id, trophy_id, amount)
        name = f"{tdef.emoji} {tdef.name}" if tdef is not None else trophy_id
        return f"{name} ×{amount}"
    if rtype == "elixir":
        elixir_id = reward.get("elixir_id")
        amount = int(reward.get("amount", 0))
        if not elixir_id or amount <= 0:
            return None
        edef = elixir_service.elixir_def(elixir_id)
        await elixir_service.grant(db, character.id, elixir_id, amount)
        name = f"{edef.emoji} {edef.name}" if edef is not None else elixir_id
        return f"{name} ×{amount}"
    if rtype == "raid_keys":
        amount = int(reward.get("amount", 0))
        if amount <= 0:
            return None
        cap = rc.RAID_KEY_CAP_PREMIUM if premium_service.is_premium(character) else rc.RAID_KEY_CAP
        room = max(cap - character.raid_keys, 0)
        granted = min(amount, room)
        if granted > 0:
            character.raid_keys += granted
        if granted < amount:
            return f"Ключей Монолита выдано: {granted} из {amount} (достигнут лимит {cap})."
        return f"🗝 Ключ Монолита ×{granted}"
    if rtype == "premium":
        days = int(reward.get("days", 0))
        if days <= 0:
            return None
        premium_service.extend(character, days)
        return f"💠 Метка Хранителя на {days} дн."
    if rtype == "mount":
        mount_id = reward.get("mount_id")
        if not mount_id:
            return None
        d = mount_service.mount_def(mount_id)
        granted = await mount_service.grant(db, character, mount_id)
        name = d.name if d is not None else mount_id
        return f"🐎 {name}" if granted else f"🐎 {name} (уже был)"
    return None


async def activate_code(db: AsyncSession, character: Character, raw_text: str) -> ActivationOutcome | None:
    """None — raw_text не совпадает НИ С ОДНИМ существующим кодом (вызывающий
    должен молча пропустить сообщение дальше по цепочке разбора ввода —
    никакого ответа про "код не найден")."""
    normalized = normalize_code(raw_text)
    if not normalized:
        return None
    promo = await db.scalar(select(PromoCode).where(PromoCode.code == normalized))
    if promo is None:
        return None

    now = datetime.now(timezone.utc)
    if promo.expires_at is not None and promo.expires_at <= now:
        return ActivationOutcome(status="expired")

    activation_count = await db.scalar(
        select(func.count()).select_from(PromoActivation).where(PromoActivation.promo_code_id == promo.id)
    )
    if promo.max_activations is not None and (activation_count or 0) >= promo.max_activations:
        return ActivationOutcome(status="limit_reached")

    if promo.one_per_player:
        already = await db.scalar(
            select(PromoActivation).where(
                PromoActivation.promo_code_id == promo.id, PromoActivation.character_id == character.id,
            )
        )
        if already is not None:
            return ActivationOutcome(status="already_used")

    lines: list[str] = []
    for reward in promo.rewards:
        line = await _apply_reward(db, character, reward)
        if line is not None:
            lines.append(line)

    db.add(PromoActivation(promo_code_id=promo.id, character_id=character.id))
    await db.flush()
    return ActivationOutcome(status="success", lines=lines)
