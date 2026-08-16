"""Тексты Ключа Монолита (патч 45, ч.4) — задел под будущий рейд, пока без
функционала."""

RAID_KEY_NAME = "🗝 Ключ Монолита"
RAID_KEY_FLAVOR = (
    "Обломок, формой похожий на ключ, — только замка под него в Пепельных "
    "Землях нет. Пока нет."
)
RAID_KEY_USE_TEXT = "Ключ тёплый на ощупь и слегка гудит. Замка для него пока не нашлось."


def raid_key_drop_line() -> str:
    return f"{RAID_KEY_NAME} — обломок находится среди прочего."


def raid_key_inventory_line(count: int) -> str:
    return f"{RAID_KEY_NAME} ×{count}"
