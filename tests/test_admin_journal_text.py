"""Журнал админки обычным языком (2026-10-13): формы записей - как на проде."""

from types import SimpleNamespace as NS

from services.admin_journal_text import describe


def _a(kind, old=None, new=None, note=None):
    return NS(action_type=kind, old_value=old, new_value=new, note=note)


def test_currency_debit_reads_as_plain_text() -> None:
    text = describe(_a("grant_currency", {"donate": 49036}, {"donate": 0}, "delta=-49036"), "Корво")
    assert text == "списал 49 036 💎 самоцветов - Корво (было 49 036, стало 0)"


def test_xp_and_teleport() -> None:
    xp = describe(_a("grant_xp", {"level": 20, "experience": 1}, {"level": 36, "experience": 2}, "amount=500000"), "Мич")
    assert xp == "выдал 500 000 опыта - Мич (уровень 20 → 36)"
    assert describe(_a("teleport", {"x": 0, "y": -30}, {"x": 20, "y": 20}), "Мич") == "перенёс Мич с (0; -30) на (20; 20)"


def test_ban_promo_reset_and_unknown() -> None:
    ban = describe(_a("ban", {"is_banned": False}, {"is_banned": True, "ban_reason": "читы", "banned_until": None}), "X")
    assert ban == "забанил X навсегда. Причина: читы"
    promo = describe(_a("create_promo_code", None, {"code": "kazik", "rewards": [{"type": "lootbox", "amount": 10}],
                                                    "max_activations": None}, "kazik"), None)
    assert promo == "создал промокод «kazik»: 🗃️ Пепельные ларцы ×10, без лимита активаций"
    reset = describe(_a("reset_character", {"name": "Кригер", "vk_id": 790979228, "level": 2}, None), None)
    assert "обнулил персонажа «Кригер»" in reset
    assert describe(_a("something_new", note="x"), "Y") == "действие «something_new» - Y: x"


def test_no_raw_codes_for_known_actions() -> None:
    for kind in ("restore_hp", "reset_activity", "reset_stats", "unban", "set_level", "grant_item",
                 "grant_admin_weapon", "grant_any", "delete_promo_code"):
        text = describe(_a(kind, {"level": 1, "code": "c"}, {"level": 2, "name": "Меч"}, "Меч ×1"), "Z")
        assert kind not in text and "_" not in text
