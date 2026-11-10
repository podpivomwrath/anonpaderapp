"""Пассивки подклассов и путей (руны-навыки, 2026-11-10).

Навыков у подкласса больше нет - его отличает пассивка: она усиливает
определённый стиль, и игрок сам тянется к подходящим рунам-навыкам
(документ дизайна, раздел 4). Ключ - subclass_service.buff_pool: id
подкласса или "<класс>_path" у тех, кто отказался от подкласса.

Часть пассивки уже живёт в коде и сюда не входит: база крита и уклонения
Клинка теней и Отравителя (stat_model.GAME.base_crit/base_dodge), вес
Стража в выборе цели мобов (resolver), Воля Отравителя в силе яда.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Passive:
    title: str
    #: Строки для игрока - по одной на свойство.
    lines: tuple[str, ...]
    mods: dict = field(default_factory=dict)


PASSIVES: dict[str, Passive] = {
    "guardian": Passive("Страж", (
        "Входящий урон меньше на 12%.",
        "Мобы бьют вас на 40% чаще, чем союзников.",
        "Щиты от ваших навыков крепче на 25%.",
    ), {"incoming_damage_reduction": 0.12, "aggro_bonus": 0.4, "shield_power": 0.25}),
    "blood_knight": Passive("Кровавый рыцарь", (
        "Вампиризм навыков выше на 5%, а пока у вас меньше 50% здоровья - ещё на 8%.",
        "Пока у вас меньше 30% здоровья, урон по вам меньше на 10%.",
    ), {"lifesteal_ratio_bonus": 0.05, "low_hp_lifesteal_bonus": 0.08,
        "low_hp_damage_reduction": 0.10, "low_hp_damage_reduction_threshold": 0.3}),
    "shadow_blade": Passive("Клинок теней", (
        "Шанс крита +15%, уклонение +5%.",
        "После вашего крита следующий удар тоже критический (не чаще раза в 6 ходов).",
        "Пока вы деретесь один, урон больше на 10%.",
    ), {"bloodlust_cooldown": 6.0, "solo_damage_bonus": 0.10}),
    "poisoner": Passive("Отравитель", (
        "Урон за ход (яд, горение) сильнее на 25%, яд держится на ход дольше.",
        "Шанс крита +10%, уклонение +5%.",
        "Яд погибшего врага переходит на соседнего вполсилы.",
    ), {"dot_damage_bonus": 0.25, "poison_duration_bonus": 1.0, "plague_spread": 1.0}),
    "elementalist": Passive("Элементалист", (
        "Три разных стихийных навыка подряд (огонь, лёд, молния) - следующее действие на 20% сильнее.",
        "Раз в 6 ходов следующий навык не уходит на перезарядку.",
    ), {"elemental_flow_bonus": 0.2, "overload_active": 1.0}),
    "dark_mystic": Passive("Тёмный мистик", (
        "Лечение и щиты на союзников сильнее на 25%.",
        "Лишнее лечение - наполовину щитом самому раненому союзнику на 2 хода.",
        "Навыки, забирающие ваше здоровье, забирают на 20% меньше.",
    ), {"ally_heal_power": 0.25, "heal_overflow_shield": 0.5, "hp_cost_reduction": 0.2}),
    # Без подкласса - универсалист без уклона (как прежние баффы путей).
    "warrior_path": Passive("Путь воина", (
        "Прямой урон больше на 8%, входящий урон меньше на 8%.",
    ), {"direct_damage_bonus": 0.08, "incoming_damage_reduction": 0.08}),
    "rogue_path": Passive("Путь разбойника", (
        "Шанс крита +12%, уклонение +8%.",
    ), {"crit_chance_bonus": 0.12, "dodge_bonus": 0.08}),
    "mage_path": Passive("Путь мага", (
        "Прямой урон больше на 8%, шанс крита +8%.",
    ), {"direct_damage_bonus": 0.08, "crit_chance_bonus": 0.08}),
}


def passive_of(pool: str | None) -> Passive | None:
    return PASSIVES.get(pool) if pool else None
