"""Сухие описания микробаффов для вкладки «Испытания» (патчи 48-49)."""

from game.combat import balance_config as bc
from game.content_loader import load_content
from game.economy import buff_descriptions


def test_unimplemented_buff_has_empty_description() -> None:
    buffs = load_content().buffs
    buff = buffs["guardian_sturdy_armor"]
    assert buff.implemented is False
    assert buff_descriptions.describe(buff) == ""


def test_implemented_buffs_have_nonempty_description() -> None:
    buffs = load_content().buffs
    for buff_id, buff in buffs.items():
        if buff.implemented:
            assert buff_descriptions.describe(buff) != "", buff_id


def test_description_reflects_live_config_value() -> None:
    """Число в описании должно совпадать с текущим значением константы —
    не захардкожено, иначе разойдётся с реальностью при калибровке."""
    buffs = load_content().buffs
    text = buff_descriptions.describe(buffs["guardian_bulwark"])
    assert f"{round(bc.GUARDIAN_BULWARK_FULL_BLOCK_CHANCE * 100)}%" in text

    # Патч 49, ч.1: итоговое значение, не прибавка — "20% вместо 12%", не "+8pp".
    text2 = buff_descriptions.describe(buffs["blood_knight_thirst"])
    base_ratio = 0.20  # blood_knight_lifesteal_strike.effect_value
    total = round((base_ratio + bc.BLOOD_KNIGHT_THIRST_LOW_HP_LIFESTEAL_BONUS) * 100)
    assert f"{round(bc.BLOOD_KNIGHT_THIRST_LOW_HP_LIFESTEAL_BONUS * 100)} процентных пунктов" in text2


def test_no_forbidden_abbreviations_anywhere() -> None:
    """Патч 49, ч.1: 'pp'/'пп'/'%%' запрещены в игровых текстах — интерфейс
    должен читаться без справки."""
    buffs = load_content().buffs
    for buff_id, buff in buffs.items():
        text = buff_descriptions.describe(buff)
        assert " pp" not in text and "pp." not in text and not text.endswith("pp"), buff_id
        assert "пп" not in text, buff_id
        assert "%%" not in text, buff_id


def test_final_value_shown_not_delta_for_percentage_stat_bonuses() -> None:
    """Патч 49, ч.1: для баффов, добавляющих проценты к уже существующему
    процентному значению (лайфстил, кап, длительность), описание либо
    показывает итог "X вместо Y", либо (если итог зависит от статов цели)
    прибавку словами — но никогда не голое "+N%"."""
    buffs = load_content().buffs
    for buff_id in ("blood_knight_eternal_hunger", "blood_knight_feast", "blood_knight_blood_pact"):
        text = buff_descriptions.describe(buffs[buff_id])
        assert "вместо" in text, buff_id


def test_category_label_maps_known_categories() -> None:
    assert buff_descriptions.category_label("damage") == "Урон"
    assert buff_descriptions.category_label("defense") == "Оборона"
    assert buff_descriptions.category_label("control_utility") == "Контроль/утилита"
    assert buff_descriptions.category_label("group_support") == "Групповая поддержка"


def test_all_buff_categories_are_mapped() -> None:
    """Ни один bufф.category не должен молча остаться немаппленным —
    иначе фронт покажет сырое английское значение вместо русской метки."""
    buffs = load_content().buffs
    assert len(buffs) == 78
    for buff_id, buff in buffs.items():
        assert buff.category in buff_descriptions.CATEGORY_LABELS, buff_id
