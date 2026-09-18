"""Сверяет значения в content/buffs.json с константами balance_config.

Зачем отдельный инструмент. Числа микробаффов живут в двух местах: константа в
balance_config (её читают боевой код и генератор описаний) и stat_modifiers в
content/buffs.json (его читает пресет игрока). Правка баланса меняет константу,
а json остаётся со старым числом - и бафф начинает врать игроку. Раньше это
ловилось только тестом на конкретный подкласс.

Запуск:
    python tools/sync_buff_values.py          # только показать расхождения
    python tools/sync_buff_values.py --apply  # привести json к константам
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from game.combat import balance_config as bc

BUFFS = pathlib.Path("content/buffs.json")

#: (id баффа, ключ в stat_modifiers) -> имя константы balance_config.
#: Здесь только те баффы, чьё значение ДОЛЖНО совпадать с константой. Флаги
#: (1.0 - «бафф включён») и интервалы, заданные прямо в json, сюда не входят.
MAPPING: dict[tuple[str, str], str] = {
    ("guardian_sturdy_armor", "incoming_damage_reduction"): "GUARDIAN_STURDY_ARMOR_REDUCTION",
    ("guardian_bulwark", "full_block_chance"): "GUARDIAN_BULWARK_FULL_BLOCK_CHANCE",
    ("guardian_resilience", "low_hp_damage_reduction"): "GUARDIAN_RESILIENCE_REDUCTION",
    ("guardian_reflection", "block_reflect_pct"): "GUARDIAN_REFLECTION_PCT",
    ("guardian_command", "aggro_bonus"): "GUARDIAN_COMMAND_AGGRO_BONUS",
    ("guardian_guard", "guard_block_bonus"): "GUARDIAN_GUARD_BLOCK_BONUS",
    ("guardian_allys_shield", "ally_shield_share_pct"): "GUARDIAN_ALLYS_SHIELD_SHARE",
    ("guardian_vital_block", "heal_on_block_pct_max_hp"): "GUARDIAN_HEAL_ON_BLOCK",
    ("guardian_counterattack", "counterattack_mult"): "GUARDIAN_COUNTERATTACK_MULT",
    ("guardian_retribution", "counterstrike_mult"): "GUARDIAN_COUNTERSTRIKE_MULT",
    ("guardian_heavy_hand", "damage_bonus"): "GUARDIAN_HEAVY_HAND_BONUS",
    ("blood_knight_shared_thirst", "shared_heal_pct"): "BLOOD_KNIGHT_SHARED_THIRST_ALLY_HEAL_PCT",
    ("blood_knight_shared_feast", "group_damage_bonus"): "BLOOD_KNIGHT_SHARED_FEAST_GROUP_DAMAGE_BONUS",
    ("shadow_blade_deadly_precision", "crit_chance_bonus"): "SHADOW_BLADE_DEADLY_PRECISION_CRIT",
    ("shadow_blade_carve", "carve_crit_mult"): "SHADOW_BLADE_CARVE_CRIT_MULT",
    ("shadow_blade_shadow", "dodge_bonus"): "SHADOW_BLADE_SHADOW_DODGE",
    ("shadow_blade_slip_away", "slip_away_bonus"): "SHADOW_BLADE_SLIP_AWAY",
    ("shadow_blade_hunters_solitude", "solo_damage_bonus"): "SHADOW_BLADE_SOLO_DAMAGE",
    ("shadow_blade_mark_passed_on", "mark_ally_crit_bonus"): "SHADOW_BLADE_ALLY_CRIT_ON_MARK",
    ("shadow_blade_inspiration", "inspiration_heal_pct"): "SHADOW_BLADE_INSPIRATION_HEAL",
    ("shadow_blade_inspiration", "inspiration_damage_bonus"): "SHADOW_BLADE_INSPIRATION_DAMAGE",
    ("shadow_blade_mark_of_prey_plus", "mark_on_attack_chance"): "SHADOW_BLADE_MARK_ON_ATTACK_CHANCE",
    ("poisoner_toxic_blood", "vulnerability_bonus"): "POISONER_TOXIC_BLOOD_VULN_BONUS",
    ("poisoner_desiccation", "weaken_bonus"): "POISONER_DESICCATION_WEAKEN_BONUS",
    ("poisoner_double_dose", "double_dose_chance"): "POISONER_DOUBLE_DOSE_CHANCE",
    ("poisoner_corroding_toxin", "poison_damage_bonus"): "POISONER_CORRODING_TOXIN_BONUS",
    ("poisoner_necrosis", "poison_damage_per_stack"): "POISONER_NECROSIS_PER_STACK",
    ("poisoner_toxic_burst", "poison_expire_burst_pct"): "POISONER_TOXIC_BURST_EXPIRE_PCT",
    ("poisoner_hallucinogen", "disrupt_chance_bonus"): "POISONER_HALLUCINOGEN_BONUS",
    ("poisoner_paralytic", "paralytic_resist_down"): "POISONER_PARALYTIC_RESIST_DOWN",
    ("poisoner_toxicology", "poison_shield_pierce"): "POISONER_TOXICOLOGY_SHIELD_PIERCE",
    ("dark_mystic_blood_bond", "pact_conversion_bonus"): "DARK_MYSTIC_BLOOD_BOND_BONUS",
    ("dark_mystic_dark_resonance", "resonance_bonus"): "DARK_MYSTIC_RESONANCE_BONUS",
    ("dark_mystic_blood_pact_plus", "hp_cost_reduction"): "DARK_MYSTIC_HP_COST_REDUCTION",
    ("dark_mystic_dark_reward", "dark_reward_bonus"): "DARK_MYSTIC_DARK_REWARD_BONUS",
    ("dark_mystic_edge", "edge_bonus"): "DARK_MYSTIC_EDGE_BONUS",
    ("dark_mystic_blood_ward", "ward_shield_bonus"): "DARK_MYSTIC_WARD_SHIELD_BONUS",
    ("dark_mystic_steadfast_ward", "ward_absorb_bonus"): "DARK_MYSTIC_STEADFAST_WARD_BONUS",
    ("dark_mystic_shared_pact", "shared_pact_pct"): "DARK_MYSTIC_SHARED_PACT_PCT",
    ("dark_mystic_echo", "heal_overflow_shield"): "DARK_MYSTIC_ECHO_PCT",
    ("elementalist_flame_power", "fire_damage_bonus"): "ELEMENTALIST_FLAME_POWER_BONUS",
    ("elementalist_frost_power", "ice_damage_bonus"): "ELEMENTALIST_FROST_POWER_BONUS",
    ("elementalist_storm_power", "lightning_damage_bonus"): "ELEMENTALIST_STORM_POWER_BONUS",
    ("elementalist_universal_element", "all_elements_damage_bonus"): "ELEMENTALIST_UNIVERSAL_ELEMENT_BONUS",
    ("elementalist_deep_freeze", "control_chance_bonus"): "ELEMENTALIST_DEEP_FREEZE_CHANCE_BONUS",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="записать константы в json")
    args = parser.parse_args()

    text = BUFFS.read_text(encoding="utf-8")
    items = json.loads(text)
    by_id = {b["id"]: b for b in items}

    drift: list[tuple[str, str, float, float]] = []
    for (buff_id, key), const_name in MAPPING.items():
        buff = by_id.get(buff_id)
        if buff is None:
            print(f"нет такого баффа: {buff_id}")
            continue
        if key not in buff["stat_modifiers"]:
            continue  # бафф ещё не реализован
        expected = getattr(bc, const_name)
        actual = buff["stat_modifiers"][key]
        if abs(actual - expected) > 1e-9:
            drift.append((buff_id, key, actual, expected))

    if not drift:
        print("расхождений нет: json совпадает с константами")
        return

    for buff_id, key, actual, expected in drift:
        print(f"  {buff_id}.{key}: json {actual} != константа {expected}")

    if not args.apply:
        print(f"\nнайдено расхождений: {len(drift)}. Запусти с --apply, чтобы поправить.")
        return

    # Правим построчно, чтобы не переверстать файл целиком.
    for buff_id, key, actual, expected in drift:
        start = text.index(f'{{"id": "{buff_id}"')
        end = text.index("\n", start)
        line = text[start:end]
        new_line = line.replace(f'"{key}": {json.dumps(actual)}', f'"{key}": {json.dumps(expected)}', 1)
        assert new_line != line, f"не удалось подставить {buff_id}.{key}"
        text = text[:start] + new_line + text[end:]
    BUFFS.write_text(text, encoding="utf-8")
    print(f"\nобновлено значений: {len(drift)}")


if __name__ == "__main__":
    main()
