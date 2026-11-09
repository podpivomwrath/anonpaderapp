"""Тексты Ключа Монолита (патч 45, ч.4). Патч 55: тексты утверждали, что замка
для ключа не существует, хотя патч 53 этот замок уже добавил."""

RAID_KEY_NAME = "🗝 Ключ Монолита"
RAID_KEY_FLAVOR = (
    "Обломок, формой похожий на ключ. Тёплый, и тяжелее, чем полагается камню "
    "такого размера."
)
def raid_key_status(count: int, cap: int, premium_cap: int | None) -> str:
    """/ключ (2026-11-03, владелец: «сколько из скольких»). premium_cap - лимит
    с Клеймом Хранителя, если его нет; None - уже есть."""
    lines = [f"{RAID_KEY_NAME}: {count} из {cap}."]
    if count >= cap:
        lines.append("Больше не выпадет, пока не потратите хотя бы один.")
    else:
        lines.append("Изредка падает с мобов, событий, ларцов и рыбалки.")
    lines.append("Ключ тратит лидер группы, когда открывает рейд.")
    if premium_cap is not None:
        lines.append(f"С Клеймом Хранителя ключей копится до {premium_cap}.")
    return "\n".join(lines)


def raid_key_drop_line() -> str:
    return f"{RAID_KEY_NAME} - обломок находится среди прочего."


def raid_key_inventory_line(count: int) -> str:
    return f"{RAID_KEY_NAME} ×{count}"
