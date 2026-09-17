"""Рейд «Кукольный театр» (патч 53) — построение боевых участников этапов +
скриптованные ходы Хирурга + механика порядка убийства Вельдов.

Чистая логика поверх game.combat.session/resolver/skills — юнит-тестируется
без БД и без бота. Оркестрация (когда открывать окно прерывания, когда
считать фазу проваленной, рассылка сообщений) — bot/handlers/raid_combat.py,
этот модуль сам ничего не знает про VK/БД."""

import random
from dataclasses import dataclass, field

from game.combat.resolver import _choose_mob_target
from game.combat.session import CombatantState, CombatSessionState, EffectKind, Stats, build_combatant
from game.combat.skills import PendingHit, compute_hit
from game.economy import raid_config as rc
from game.world.encounters import balanced_mob_stats

BOSS_LEVEL = 60

# Множители к статам противников этапов (кроме HP — та фиксирована по
# тексту патча и выставляется напрямую поверх формулы). Числа НЕ из текста
# патча (там задан только HP) — это балансировочная прикидка урона,
# крутить здесь, а не в тексте патча.
STAGE1_STAT_MULT = 2.0
VELD_STAT_MULT = 2.5
SURGEON_STAT_MULT = 3.0


def _boss_combatant(
    id: int, name: str, hp: int, stat_mult: float, primary_stat: str = "str",
) -> CombatantState:
    base = balanced_mob_stats(BOSS_LEVEL, primary_stat)
    scaled = Stats(
        strength=round(base.strength * stat_mult),
        agility=round(base.agility * stat_mult),
        intellect=round(base.intellect * stat_mult),
        vitality=base.vitality,
        will=round(base.will * stat_mult),
    )
    combatant = build_combatant(
        id=id, side=1, kind="mob", name=name, level=BOSS_LEVEL,
        stats=scaled, primary_stat=primary_stat,
    )
    # HP этапа зафиксирован текстом патча — не формулой (build_combatant уже
    # посчитал HP от VIT, здесь он ПЕРЕЗАПИСЫВАЕТСЯ на заданное значение).
    combatant.max_hp = hp
    combatant.current_hp = hp
    return combatant


def build_stage1_mobs(start_id: int) -> list[CombatantState]:
    """Три «Пробные куклы» — одинаковые, без механик."""
    return [
        _boss_combatant(start_id + i, "Пробная кукла", rc.STAGE1_MOB_HP, STAGE1_STAT_MULT)
        for i in range(rc.STAGE1_MOB_COUNT)
    ]


def build_veld_mobs(start_id: int) -> dict[str, CombatantState]:
    """{veld_id: CombatantState} — id комбатанта = start_id + позиция в
    rc.VELD_ORDER (устойчиво, не зависит от порядка обхода словаря)."""
    return {
        veld_id: _boss_combatant(start_id + i, rc.VELD_NAMES[veld_id], rc.VELD_HP[veld_id], VELD_STAT_MULT)
        for i, veld_id in enumerate(rc.VELD_ORDER)
    }


def build_surgeon(id: int) -> CombatantState:
    return _boss_combatant(id, rc.SURGEON_NAME, rc.SURGEON_HP, SURGEON_STAT_MULT)


# --- Этап 2: порядок убийства Вельдов ---


@dataclass
class VeldOrderResult:
    violations: int  # накопительное число ошибок (0/1/2) ПОСЛЕ этого тика
    lines: list[str] = field(default_factory=list)


def check_veld_kill_order(
    combatants: dict[int, CombatantState],
    veld_combatant_ids: dict[str, int],
    dead_veld_ids_this_tick: list[str],
    killed_so_far: list[str],
    violations_so_far: int,
) -> VeldOrderResult:
    """Вызывать РОВНО ОДИН РАЗ за тик, после резолва, со списком veld_id,
    погибших В ЭТОТ тик (порядок — по rc.VELD_ORDER, если несколько сразу).
    killed_so_far — накопительный список УЖЕ обработанных veld_id (в порядке
    фактической гибели), мутируется на месте вызывающим кодом между тиками.

    При ошибке порядка — абсолютный (не накапливающийся с предыдущим) ×2/×5
    к ТЕКУЩЕМУ (не «базовому») max_hp/current_hp всех ОСТАВШИХСЯ живых кукол:
    вторая ошибка применяется поверх уже применённой первой (составное ×10
    от исходного) — так каждое "получает ×N к характеристикам" читается как
    моментальный буст относительно состояния боя ПРЯМО СЕЙЧАС."""
    lines: list[str] = []
    violations = violations_so_far
    id_by_veld = veld_combatant_ids
    for veld_id in dead_veld_ids_this_tick:
        expected_idx = len(killed_so_far)
        killed_so_far.append(veld_id)
        is_correct = expected_idx < len(rc.VELD_ORDER) and rc.VELD_ORDER[expected_idx] == veld_id
        if is_correct:
            continue
        violations += 1
        remaining_ids = [
            cid for vid, cid in id_by_veld.items()
            if vid not in killed_so_far and combatants[cid].alive
        ]
        mult = rc.VELD_FIRST_VIOLATION_MULT if violations <= 1 else rc.VELD_SECOND_VIOLATION_MULT
        for cid in remaining_ids:
            c = combatants[cid]
            c.max_hp = round(c.max_hp * mult)
            c.current_hp = round(c.current_hp * mult)
        if violations <= 1:
            lines.append(
                "Оставшиеся замирают. Что-то в них натягивается - будто нити, которых не видно, дёрнули разом."
            )
        else:
            lines.append(
                "Литта перестаёт смотреть на тебя. Она смотрит туда, где стояли остальные.\n\n"
                "И то, что происходит дальше, происходит очень быстро."
            )
    return VeldOrderResult(violations=violations, lines=lines)


# --- Этап 3: Хирург ---


class SurgeonAI:
    """Держит фазу/ротацию как СОСТОЯНИЕ ЭКЗЕМПЛЯРА — подключается к
    CombatantState.scripted_hit (см. game/combat/session.py), резолвер
    вызывает его вместо стандартного "кусает" КАЖДЫЙ тик, пока Хирург жив.

    Оркестрация (bot/handlers/raid_combat.py) читает и меняет
    awaiting_interrupt/phase/phase3_turns_left МЕЖДУ тиками (после резолва,
    до следующего) — этот класс сам не знает про TickResult/control_landed_by,
    только генерирует урон текущего хода."""

    ROTATION = ("resection", "replace_parts", "material_work", "stitch_pull")

    def __init__(self) -> None:
        self.phase = 1
        self.rotation_index = 0
        self.preparing = True             # первый ход — не атакует вовсе
        self.awaiting_interrupt = False   # True — этот тик "окно", атаки нет
        self.phase3_turns_left: int | None = None  # None вне фазы 3

    def open_interrupt_window(self) -> None:
        """Хирург замирает готовя инструмент — следующий ХОД он не атакует
        (см. __call__: preparing/awaiting_interrupt оба гасят атаку), а ход
        ПОСЛЕ ТОГО — окно, когда группа обязана его прервать (см.
        bot/handlers/raid_combat.py — именно оно вешает FREEZE(1)+
        CONTROL_RESIST_DOWN(2) на комбатанта Хирурга, здесь только флаг для
        подавления атаки на этот единственный тик)."""
        self.awaiting_interrupt = True

    def close_interrupt_window(self) -> None:
        self.awaiting_interrupt = False

    def enter_phase3(self) -> None:
        self.phase = 3
        self.phase3_turns_left = rc.SURGEON_PHASE3_TURNS

    def __call__(
        self, boss: CombatantState, session: CombatSessionState, rng: random.Random,
    ) -> list[PendingHit]:
        if self.preparing:
            self.preparing = False
            return []
        if self.phase3_turns_left is not None and self.phase3_turns_left > 0:
            return []  # фаза проверки урона — Хирург бездействует
        if self.awaiting_interrupt:
            return []  # окно прерывания — атаки нет
        return self._rotation_hit(boss, session, rng)

    def _rotation_hit(
        self, boss: CombatantState, session: CombatSessionState, rng: random.Random,
    ) -> list[PendingHit]:
        move = self.ROTATION[self.rotation_index % len(self.ROTATION)]
        self.rotation_index += 1
        targets = session.alive_enemies_of(boss)
        if not targets:
            return []
        if move == "material_work":
            return [
                compute_hit(
                    boss, t, rng, label="Работа с материалом",
                    multiplier=rc.SURGEON_MATERIAL_WORK_MULT, is_ability=True,
                )
                for t in targets
            ]
        target = _choose_mob_target(session, boss, rng)
        if target is None:
            return []
        if move == "resection":
            return [
                compute_hit(
                    boss, target, rng, label="Резекция",
                    multiplier=rc.SURGEON_RESECTION_MULT, is_ability=True,
                )
            ]
        if move == "replace_parts":
            hit = compute_hit(
                boss, target, rng, label="Замена частей",
                multiplier=rc.SURGEON_REPLACE_PARTS_MULT, is_ability=True,
            )
            target.apply_effect(
                EffectKind.WEAKEN, rc.SURGEON_REPLACE_PARTS_WEAKEN,
                rc.SURGEON_REPLACE_PARTS_WEAKEN_DURATION, boss.id,
            )
            return [hit]
        # stitch_pull — лайфстил применяется ПРЯМОЙ самомутацией current_hp,
        # СРАЗУ здесь (тот же паттерн, что "себестоимость HP" у Багрового
        # пира/Круга тьмы — см. комментарий патча 45, ч.1 в resolver.py: hp_
        # before_apply снимается ПОСЛЕ таких самомутаций, лог считает верно).
        hit = compute_hit(
            boss, target, rng, label="Подтяжка нитей",
            multiplier=rc.SURGEON_STITCH_PULL_MULT, is_ability=True,
        )
        if hit.amount > 0:
            heal = max(round(hit.amount * rc.SURGEON_STITCH_PULL_LIFESTEAL), 1)
            boss.current_hp = min(boss.current_hp + heal, boss.max_hp)
        return [hit]
