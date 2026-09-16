"""Реестр боевых режимов (патч 54): подписи кнопок + НАБОР доступных действий.

ПРАВИЛО: боевые обработчики опираются на СВОЙСТВА режима (этот реестр), а не
на его идентификатор. Не писать проверок вида `if mode == "pvp_group" or
mode == "raid"` — добавление нового режима должно сводиться к ОДНОЙ записи
здесь плюс своему обработчику, а не к правкам в десяти местах.

Почему этот файл вообще существует
----------------------------------
Три патча подряд (30 — PvP, 52 — эликсиры в PvP, 54 — рейд) выкатывались с
неработающими боевыми кнопками, и причина КАЖДЫЙ РАЗ одна и та же:

    vkbottle диспетчерит по ПЕРВОМУ совпавшему правилу и на этом
    останавливается.

Если кнопка нового режима называется так же, как кнопка старого, правило
`text=[...]` ЧУЖОГО обработчика срабатывает первым, тот не находит у игрока
своего боя и молча выходит (`return`) — до «своего» обработчика очередь уже
не доходит, игрок видит полную тишину в ответ на нажатие.

Отсюда характерный симптом патча 54: навыки работают (у них уникальный
payload), а атака/цель/предметы — нет (текст совпадал с групповым PvE).
Тем же путём с патча 51 молча сломался выбор цели в массовом PvP: его
«🎯 Цель» перехватывал групповой PvE, зарегистрированный раньше.

Поэтому подписи ОБЯЗАНЫ быть уникальны на весь проект. Это проверяет
tests/test_combat_mode_registry.py (в том числе автоматическим разбором всех
`text=`-правил в bot/handlers/), а не внимательность ревьюера.

Кнопки навыков и (где есть) выбора цели/предметов дополнительно несут
УНИКАЛЬНЫЙ payload — это второй рубеж: даже если подписи когда-нибудь
случайно сойдутся, диспетчер всё равно разведёт их по payload.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CombatModeUi:
    """Свойства боевого режима с точки зрения интерфейса.

    target/escape = None — действие в этом режиме НЕ СУЩЕСТВУЕТ (а не просто
    временно недоступно): в соло-PvE и дуэли противник всегда один, выбирать
    не из чего; из PvP, группового PvE и рейда выйти нельзя в принципе
    (рейд — патч 53: «Покинуть рейд нельзя. Единственный выход — смерть
    всей группы»).
    """

    mode_id: str
    attack: str
    item: str
    target: str | None
    escape: str | None
    skill_payload: str

    @property
    def allows_target_selection(self) -> bool:
        return self.target is not None

    @property
    def allows_escape(self) -> bool:
        return self.escape is not None

    @property
    def action_labels(self) -> tuple[str, ...]:
        """Все подписи кнопок действий режима — то, что обязано быть
        уникально на весь проект (см. докстринг модуля)."""
        return tuple(
            label for label in (self.attack, self.item, self.target, self.escape)
            if label is not None
        )


# Соло-PvE (bot/handlers/combat.py): один моб, побег возможен.
SOLO_PVE = CombatModeUi(
    mode_id="solo_pve",
    attack="🗡️ Атака",
    item="🎒 Предмет",
    target=None,
    escape="🏃 Побег",
    skill_payload="skill",
)

# Открытое PvP (bot/handlers/pvp.py): дуэль + массовый бой. Побега нет.
# Кнопка цели — только в массовом бою (см. pvp_combat_keyboard(show_target)).
PVP = CombatModeUi(
    mode_id="pvp",
    attack="🗡️ Атаковать",
    item="🎒 Предметы",
    # Патч 54: было «🎯 Цель» — ДОСЛОВНО как у группового PvE, из-за чего
    # выбор цели в массовом PvP молча не работал с патча 51.
    target="🎯 Смена цели",
    escape=None,
    skill_payload="pvp_skill",
)

# Групповой PvE (bot/handlers/group_combat.py, патч 51).
GROUP_PVE = CombatModeUi(
    mode_id="group_pve",
    attack="⚔️ Ударить",
    item="🎒 Снаряжение",
    target="🎯 Цель",
    escape=None,
    skill_payload="group_pve_skill",
)

# Рейд (bot/handlers/raid_combat.py, патч 53). Патч 54: все три подписи были
# дословными копиями группового PvE — рейд был непроходим, работали только
# навыки.
RAID = CombatModeUi(
    mode_id="raid",
    attack="🩸 Удар",
    item="🎒 Сумка",
    target="🎯 Выбор цели",
    escape=None,
    skill_payload="raid_skill",
)

ALL_MODES: tuple[CombatModeUi, ...] = (SOLO_PVE, PVP, GROUP_PVE, RAID)
