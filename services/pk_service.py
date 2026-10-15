"""Пепельное клеймо - наказание убийц слабых без запретов (2026-10-15).

Правила и числа - game/economy/pk_config.py. Метки сходят сами, по одной за
DECAY_HOURS: считаем это лениво (marks), а в базу «сход» записывает settle -
он же снимает награду за голову, когда меток не осталось. settle зовут
при каждом изменении клейма и периодическая задача (settle_all).

Награда за голову (2026-10-15, решение владельца) - только обещание: в
момент убийства у клеймёного ничего не списывается. Золото уходит из его
кошелька охотнику, когда охотник его убьёт.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.economy import pk_config as pc
from models import Character
from services import wallet_service

_PERIOD = timedelta(hours=pc.DECAY_HOURS)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(moment: datetime | None) -> datetime | None:
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def marks(character: Character, now: datetime | None = None) -> int:
    """Меток сейчас, с учётом уже сошедших (без записи в базу)."""
    stored = getattr(character, "pk_marks", 0) or 0
    started = _aware(getattr(character, "pk_marks_at", None))
    if stored <= 0 or started is None:
        return max(stored, 0)
    gone = int(((now or _now()) - started) / _PERIOD)
    return max(stored - gone, 0)


def _normalize(character: Character, now: datetime) -> None:
    stored = character.pk_marks or 0
    started = _aware(character.pk_marks_at)
    if stored <= 0 or started is None:
        character.pk_marks, character.pk_marks_at = 0, None
        return
    gone = min(int((now - started) / _PERIOD), stored)
    character.pk_marks = stored - gone
    character.pk_marks_at = None if character.pk_marks == 0 else started + gone * _PERIOD


async def settle(db: AsyncSession, character: Character, now: datetime | None = None) -> None:
    """Записать сошедшие метки. Клеймо сошло, а голову так никто и не взял -
    залог награды возвращается в кошелёк (без налога гильдии: это его же золото)."""
    now = now or _now()
    _normalize(character, now)
    if character.pk_marks <= 0:
        if character.pk_bounty:
            await wallet_service.deposit(db, character.id, "farm", character.pk_bounty, taxable=False)
        character.pk_bounty = 0


async def settle_all(db: AsyncSession, now: datetime | None = None) -> int:
    """Периодически: записать сошедшие метки. Возвращает, у скольких
    клеймо сошло совсем."""
    now = now or _now()
    rows = (await db.scalars(select(Character).where(Character.pk_marks > 0))).all()
    cleared = 0
    for character in rows:
        await settle(db, character, now)
        cleared += character.pk_marks == 0
    return cleared


def badge(character: Character, now: datetime | None = None) -> str:
    n = marks(character, now)
    return f"🩸{n} " if n else ""


def wanted_suffix(character: Character, now: datetime | None = None) -> str:
    if not marks(character, now):
        return ""
    return f" · 💰 награда {character.pk_bounty}" if character.pk_bounty else ""


def death_xp_mult(character: Character) -> float:
    return pc.DEATH_XP_MULT if marks(character) >= pc.COSTLY_DEATH_FROM else 1.0


def costly_death(character: Character) -> bool:
    return marks(character) >= pc.COSTLY_DEATH_FROM


def shop_mult(character: Character) -> float:
    return pc.SHOP_PRICE_MULT if marks(character) >= pc.CITY_PENALTY_FROM else 1.0


def relic_mult(character: Character) -> float:
    return pc.RELIC_SELL_MULT if marks(character) >= pc.CITY_PENALTY_FROM else 1.0


def city_banned(character: Character) -> bool:
    return marks(character) >= pc.CITY_BAN_FROM


CITY_BAN_TEXT = (
    "🛡 Стража не пускает тебя в город: у тебя 20 или больше меток клейма. "
    "Каждая метка исчезает сама через 5 часов - когда их станет меньше 20, пустят."
)


def revenge_bonus(attacker: Character, target_id: int, now: datetime | None = None) -> float:
    until = _aware(attacker.revenge_until)
    if attacker.revenge_target_id != target_id or until is None or until <= (now or _now()):
        return 0.0
    return pc.REVENGE_BONUS


def consequences(n: int) -> str:
    """Чем грозит клеймо на n метках - одной строкой."""
    parts = ["все видят 🩸 рядом с твоим именем"]
    if n >= pc.BOUNTY_FROM:
        parts.append("за твою голову назначена награда: кто тебя убьёт, получит её из твоего кошелька")
    if n >= pc.COSTLY_DEATH_FROM:
        parts.append("при смерти теряешь в 1,5 раза больше опыта (даже в PvP), и твои трофеи заберёт любой победитель")
    if n >= pc.CITY_PENALTY_FROM:
        parts.append("зелья в лавке в 1,5 раза дороже, скупщик платит за реликвии в 2 раза меньше")
    if n >= pc.CITY_BAN_FROM:
        parts.append("в город не пускают")
    return "; ".join(parts) + "."


@dataclass
class KillOutcome:
    killer_lines: list[str] = field(default_factory=list)
    victim_lines: list[str] = field(default_factory=list)
    bounty_claimed: int = 0
    branded: bool = False
    bounty_added: int = 0
    victim_name: str = ""


def mass_killer_lines(killer: Character, outcomes: list[KillOutcome]) -> list[str]:
    """Итог клейма за массовый бой одной сводкой (2026-10-15, просьба
    владельца): «x2 метки» и общая сумма, а не абзац на каждого убитого."""
    lines = []
    claimed = [o for o in outcomes if o.bounty_claimed]
    if claimed:
        names = ", ".join(o.victim_name for o in claimed)
        lines.append(f"💰 Награда за голову ({names}): +{sum(o.bounty_claimed for o in claimed)} золота.")
    branded = sum(o.branded for o in outcomes)
    if branded:
        n = killer.pk_marks or 0
        lines.append(f"🩸 Клеймо x{branded} (меток: {n}). {BOARD_HINT}")
    added = sum(o.bounty_added for o in outcomes)
    if added:
        lines.append(_bounty_line(added, killer.pk_bounty))
    return lines


#: Лог клейма - одной строкой (2026-10-15, просьба владельца): правила и
#: последствия расписаны во вкладке «Доска», в чате их не повторяем.
BOARD_HINT = "Подробности - во вкладке «Доска»."


def _bounty_line(added: int, total: int) -> str:
    return f"💰 В залог за твою голову ушло {added} золота (всего {total}). Сойдут метки - вернётся."


async def on_pvp_kill(
    db: AsyncSession, killer: Character, victim: Character, now: datetime | None = None,
) -> KillOutcome:
    """Убийство в открытом PvP: награда за голову клеймёного - убийце;
    за убийство слабого на LEVEL_GAP+ - метка, заморозка награды, право
    мести жертве. Осады и разломы сюда не заходят."""
    now = now or _now()
    out = KillOutcome(victim_name=victim.name)
    await settle(db, killer, now)
    await settle(db, victim, now)

    victim_branded = marks(victim, now) > 0
    if victim_branded and victim.pk_bounty:
        # Награда уже лежит в залоге (списана при метке) - охотник берёт её целиком.
        claimed = victim.pk_bounty
        victim.pk_bounty = 0
        await wallet_service.deposit(db, killer.id, "farm", claimed)
        out.bounty_claimed = claimed
        out.killer_lines.append(f"💰 Награда за голову {victim.name}: +{claimed} золота.")
        out.victim_lines.append(f"💰 Награду за твою голову ({claimed} золота) забрал {killer.name}.")

    if victim_branded or killer.level - victim.level < pc.LEVEL_GAP:
        return out

    out.branded = True
    if not killer.pk_marks:
        killer.pk_marks_at = now
    killer.pk_marks = (killer.pk_marks or 0) + 1
    n = killer.pk_marks
    added = 0
    if n >= pc.BOUNTY_FROM:
        # Залог (2026-10-15, решение владельца): золото списывается сразу,
        # иначе его успевали потратить или передать и награда была пустой.
        wallet = await wallet_service.get_wallet(db, killer.id)
        added = int(max(wallet.farm_currency, 0) * min(pc.BOUNTY_SHARE_PER_MARK * n, pc.BOUNTY_SHARE_MAX))
        if added > 0:
            await wallet_service.charge(db, killer.id, "farm", added)
            killer.pk_bounty = (killer.pk_bounty or 0) + added
            out.bounty_added = added
    line = f"🩸 Метка клейма за убийство слабого (меток: {n}). {BOARD_HINT}"
    if added:
        line += "\n" + _bounty_line(added, killer.pk_bounty)
    out.killer_lines.append(line)

    victim.revenge_target_id = killer.id
    victim.revenge_until = now + timedelta(hours=pc.REVENGE_HOURS)
    out.victim_lines.append(
        f"🩸 {killer.name} убил тебя, хотя он сильнее на {pc.LEVEL_GAP}+ уровней, и получил метку клейма. "
        f"Право мести: следующие {pc.REVENGE_HOURS} ч твой урон по {killer.name} на {round(pc.REVENGE_BONUS * 100)}% больше."
    )
    return out
