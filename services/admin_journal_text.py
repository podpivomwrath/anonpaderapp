"""Журнал админ-панели обычным языком (2026-10-13).

Раньше вкладка «Журнал» показывала сырые записи admin_actions: grant_currency,
персонаж #57, delta=-49036. Здесь каждая запись превращается в фразу «кто -
что сделал - с кем»: «Админ списал 49 036 💎 у Корво».

Форма old_value/new_value/note у каждого действия своя - её задают места
записи (services/admin_service.py, admin_grant_service, promo_service,
character_reset_service). Незнакомое действие не теряется: показывается
как есть с пометкой.
"""

from models import AdminAction

CURRENCY = {"farm": ("💰", "золота"), "donate": ("💎", "самоцветов")}
STAT_TITLES = {"str": "Сила", "agi": "Ловкость", "int": "Интеллект", "vit": "Выносливость", "wil": "Воля"}
REWARD_TITLES = {
    "gold": "💰 золото", "gems": "💎 самоцветы", "xp": "✨ опыт", "trophy": "трофей",
    "elixir": "зелье", "raid_keys": "🗝 Ключи Монолита", "lootbox": "🗃️ Пепельные ларцы",
    "premium": "💠 Метка Хранителя", "mount": "🐎 маунт",
}


def money(value) -> str:
    try:
        return f"{int(value):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


def _trophy(trophy_id: str) -> str:
    from services import trophy_service

    trophy = trophy_service.trophy_def(trophy_id)
    return f"{trophy.emoji} {trophy.name}" if trophy is not None else trophy_id


def _mount(mount_id: str) -> str:
    from services import mount_service

    mount = mount_service.mount_def(mount_id)
    return mount.name if mount is not None else mount_id


def _rewards(rewards) -> str:
    parts = []
    for r in rewards or []:
        kind = r.get("type")
        title = REWARD_TITLES.get(kind, kind)
        if kind == "premium":
            parts.append(f"{title} на {r.get('days')} дн.")
        elif kind == "trophy":
            parts.append(f"{_trophy(r.get('trophy_id', ''))} ×{money(r.get('amount'))}")
        elif kind == "mount":
            parts.append(f"🐎 {_mount(r.get('mount_id', ''))}")
        else:
            parts.append(f"{title} ×{money(r.get('amount'))}")
    return ", ".join(parts) or "без наград"


def describe(action: AdminAction, target: str | None) -> str:
    """Что сделано - без «кто» (его подставляет вызывающий)."""
    old, new, note = action.old_value or {}, action.new_value or {}, action.note or ""
    who = target or "персонаж удалён"
    kind = action.action_type

    if kind == "grant_currency":
        currency = next(iter(new), next(iter(old), "farm"))
        emoji, word = CURRENCY.get(currency, ("", currency))
        delta = int(new.get(currency, 0) or 0) - int(old.get(currency, 0) or 0)
        verb = "выдал" if delta >= 0 else "списал"
        return f"{verb} {money(abs(delta))} {emoji} {word} - {who} (было {money(old.get(currency))}, стало {money(new.get(currency))})"
    if kind == "grant_xp":
        amount = note.removeprefix("amount=")
        return f"выдал {money(amount)} опыта - {who} (уровень {old.get('level')} → {new.get('level')})"
    if kind == "set_level":
        return f"поставил уровень {new.get('level')} (был {old.get('level')}) - {who}"
    if kind == "grant_trophy":
        count = int(new.get("count", 0) or 0) - int(old.get("count", 0) or 0)
        return f"выдал {_trophy(new.get('trophy_id', ''))} ×{money(count)} - {who}"
    if kind == "grant_item":
        return f"выдал вещь «{new.get('name')}» - {who}"
    if kind == "grant_admin_weapon":
        return f"выдал админское оружие «{new.get('name')}» - {who}"
    if kind == "grant_admin_mount":
        return f"выдал маунта «{_mount(note)}» - {who}"
    if kind == "grant_any":
        return f"выдал {note} - {who}"
    if kind == "grant_buff":
        return f"открыл бафф - {who}" + (f": {note}" if note else "")
    if kind == "set_craft_level":
        return f"поставил {note or 'ремеслу'} уровень {new.get('level')} (был {old.get('level')}) - {who}"
    if kind == "clear_house_work":
        return f"снял работу в доме ({old.get('work') or 'пусто'}) - {who}"
    if kind == "teleport":
        return f"перенёс {who} с ({old.get('x')}; {old.get('y')}) на ({new.get('x')}; {new.get('y')})"
    if kind == "restore_hp":
        return f"вылечил {who} до полного здоровья"
    if kind == "reset_activity":
        return f"сбросил зависшие занятия - {who}"
    if kind == "reset_stats":
        return f"сбросил характеристики - {who}"
    if kind == "reset_character":
        name = old.get("name") or who
        return f"обнулил персонажа «{name}» (ур. {old.get('level')}, vk {old.get('vk_id')}) - игрок начнёт заново"
    if kind == "ban":
        until = new.get("banned_until")
        term = f"до {until[:16].replace('T', ' ')}" if until else "навсегда"
        reason = new.get("ban_reason") or "без причины"
        return f"забанил {who} {term}. Причина: {reason}"
    if kind == "unban":
        return f"снял бан - {who}"
    if kind == "create_promo_code":
        limit = new.get("max_activations")
        limit_text = f", активаций: {limit}" if limit else ", без лимита активаций"
        return f"создал промокод «{new.get('code')}»: {_rewards(new.get('rewards'))}{limit_text}"
    if kind == "delete_promo_code":
        return f"удалил промокод «{old.get('code') or note}»"
    # Покупки в магазине за самоцветы (2026-10-16).
    if kind == "shop_rename":
        return f"сменил ник: {old.get('name')} → {new.get('name')}"
    if kind == "shop_firm_rename":
        return f"сменил название фирмы: «{old.get('name')}» → «{new.get('name')}»"
    # Учёт донатов (2026-10-16).
    if kind == "donation":
        gems = f" ({money(new.get('gems'))} 💎)" if new.get("gems") else ""
        return f"задонатил {money(new.get('rub'))} ₽{gems} через ЮКассу"
    if kind == "donation_manual":
        return f"внёс донат вручную: {new.get('donor')} - {money(new.get('rub'))} ₽" + (f" ({note})" if note else "")
    if kind == "donation_deleted":
        return f"удалил запись доната: {old.get('donor')} - {money(old.get('rub'))} ₽"
    tail = f": {note}" if note else ""
    return f"действие «{kind}» - {who}{tail}"
